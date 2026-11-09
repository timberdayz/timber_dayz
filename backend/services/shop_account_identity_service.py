"""店铺身份主数据服务(SSOT)—— 平台店铺编号的唯一来源。

唯一权威源
----------
``core.shop_accounts.platform_shop_id`` —— 主数据里登记的平台店铺编号。

运行时**只**从这里取编号:

* 取到 → 用主数据登记值;
* 取不到(未登记 / 账号查无 / 数据库不可用) → **编号留空**;
* **绝不**回退到账号上下文里的来路不明编号(``platform_shop_id`` / ``shop_id`` /
  ``cnsc_shop_id``),**绝不**按店名猜测,**绝不**保留任何硬编码覆盖表。

历史包袱
--------
本模块取代了旧文件 ``backend/services/shopee_shop_id_resolver.py``: 那张文件里有
两张硬编码覆盖表(账号 ID → 编号、店名 → 编号), 用「猜出来的编号」覆盖主数据。
本项目已删除该文件, 不保留任何兼容层。

与 ``shop_identity_reconciliation_service`` 的分工
---------------------------------------------------
* **本模块(采集侧 / 运行时)**: 只**读**主数据, 回答「这个店铺账号登记的平台编号是
  多少」。不写库、不改数据、不做历史行收敛。
* ``backend/services/shop_identity_reconciliation_service.py``(**入库侧**): 负责把
  历史事实行的行内身份收敛到主数据, 并提供 alias → 账号的反查索引。

两者不重叠: 本模块不碰事实行, 那个模块不碰运行时取值。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import ShopAccount
from modules.core.logger import get_logger
from modules.core.validators import normalize_enum_value

logger = get_logger(__name__)


@dataclass(frozen=True)
class MasterShopIdentity:
    """一条店铺账号的主数据身份快照(只读)。"""

    shop_account_id: str
    platform: str
    platform_shop_id: str
    store_name: str
    shop_region: str
    enabled: bool
    business_role: str


def _enum_value(value: object) -> str:
    """把枚举 / 字符串统一成字符串(``business_role`` 可能是 SAEnum 成员)。

    ⚠️ SSOT: 实现已上提到 ``modules/core/validators.normalize_enum_value``。
    本函数保留为薄封装, 供本模块内既有调用方使用; **不要在这里另写一份实现**
    —— 2026-11-07 的采集同步丢数事故, 根因就是同一个归一化逻辑在两个服务里
    写成了两个版本(其中一份漏了枚举解包), 导致收敛 100% 静默失效。
    """
    return normalize_enum_value(value)


def normalize_master_platform_shop_id(value: object) -> str:
    """规范化主数据登记的平台店铺编号: 去空白;空值 → 空串。"""
    return str(value or "").strip()


def pick_master_platform_shop_id(identity: Optional[MasterShopIdentity]) -> str:
    """取主数据登记的平台店铺编号。

    主数据为空(未登记 / 账号查无) → 返回空串。**不猜、不回退。**
    """
    if identity is None:
        return ""
    return normalize_master_platform_shop_id(identity.platform_shop_id)


def is_operating_store(identity: Optional[MasterShopIdentity]) -> bool:
    """该店铺账号是否是「经营店铺」(在营 + 业务身份为 operating_store)。"""
    if identity is None:
        return False
    return bool(identity.enabled) and identity.business_role == "operating_store"


def identity_from_shop_account_row(row: Any) -> Optional[MasterShopIdentity]:
    """把 ``core.shop_accounts`` 行(或等价对象)转成 :class:`MasterShopIdentity`。

    对象里根本没有 ``platform_shop_id`` 字段(说明它**不是**主数据行) → 返回 ``None``,
    由调用方决定是否按 ``shop_account_id`` 回查主数据。
    """
    if row is None or not hasattr(row, "platform_shop_id"):
        return None
    return MasterShopIdentity(
        shop_account_id=str(getattr(row, "shop_account_id", "") or "").strip(),
        platform=str(getattr(row, "platform", "") or "").strip().lower(),
        platform_shop_id=normalize_master_platform_shop_id(
            getattr(row, "platform_shop_id", "")
        ),
        store_name=str(getattr(row, "store_name", "") or "").strip(),
        shop_region=str(getattr(row, "shop_region", "") or "").strip(),
        enabled=bool(getattr(row, "enabled", False)),
        business_role=_enum_value(getattr(row, "business_role", "")),
    )


async def load_master_identities(
    session: AsyncSession,
    shop_account_ids: Iterable[str],
) -> dict[str, MasterShopIdentity]:
    """批量读取主数据身份, 返回 ``{shop_account_id: MasterShopIdentity}``。

    查不到的账号**不会**出现在结果里(调用方据此留空编号)。
    """
    ids = [
        str(item or "").strip() for item in shop_account_ids if str(item or "").strip()
    ]
    if not ids:
        return {}

    result = await session.execute(
        select(ShopAccount).where(ShopAccount.shop_account_id.in_(ids))
    )
    identities: dict[str, MasterShopIdentity] = {}
    for row in result.scalars().all():
        identity = identity_from_shop_account_row(row)
        if identity is None or not identity.shop_account_id:
            continue
        identities[identity.shop_account_id] = identity
    return identities


async def load_master_identity(
    session: AsyncSession,
    shop_account_id: str,
) -> Optional[MasterShopIdentity]:
    """读取单个店铺账号的主数据身份;查无 → ``None``。"""
    key = str(shop_account_id or "").strip()
    if not key:
        return None
    identities = await load_master_identities(session, [key])
    return identities.get(key)


async def resolve_master_platform_shop_id(shop_account_id: str) -> str:
    """按店铺账号 ID 取主数据登记的平台店铺编号(自开异步会话)。

    取不到(账号查无 / 数据库不可用) → 返回空串, 调用方据此留空编号。
    """
    key = str(shop_account_id or "").strip()
    if not key:
        return ""
    try:
        from backend.models.database import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            identity = await load_master_identity(session, key)
    except Exception as exc:  # pragma: no cover - 数据库不可用时兜底
        logger.warning(
            "[ShopIdentity] Failed to load master platform_shop_id: shop_account_id=%s error=%s",
            key,
            exc,
        )
        return ""
    return pick_master_platform_shop_id(identity)


def resolve_master_platform_shop_id_sync(shop_account_id: str) -> str:
    """同步版 :func:`resolve_master_platform_shop_id`(供同步调用方使用)。

    取不到 → 返回空串。数据库不可用时**不抛异常**, 编号留空。
    """
    key = str(shop_account_id or "").strip()
    if not key:
        return ""
    try:
        from backend.models.database import SessionLocal

        session = SessionLocal()
        try:
            row = session.execute(
                select(ShopAccount).where(ShopAccount.shop_account_id == key)
            ).scalar_one_or_none()
        finally:
            session.close()
    except Exception as exc:  # pragma: no cover - 数据库不可用时兜底
        logger.warning(
            "[ShopIdentity] Failed to load master platform_shop_id (sync): shop_account_id=%s error=%s",
            key,
            exc,
        )
        return ""
    return pick_master_platform_shop_id(identity_from_shop_account_row(row))


def resolve_master_identity_for_account(account: Any) -> Optional[MasterShopIdentity]:
    """按账号对象解析它的主数据身份。

    1. 账号对象**本身就是**主数据行 → 直接用行内登记值(不查库);
    2. 否则按 ``shop_account_id`` 回查 ``core.shop_accounts``;
    3. 查不到 → ``None``(调用方据此把编号留空)。
    """
    identity = identity_from_shop_account_row(account)
    if identity is not None:
        return identity

    shop_account_id = str(getattr(account, "shop_account_id", "") or "").strip()
    if not shop_account_id:
        return None
    try:
        from backend.models.database import SessionLocal

        session = SessionLocal()
        try:
            row = session.execute(
                select(ShopAccount).where(
                    ShopAccount.shop_account_id == shop_account_id
                )
            ).scalar_one_or_none()
        finally:
            session.close()
    except Exception as exc:  # pragma: no cover - 数据库不可用时兜底
        logger.warning(
            "[ShopIdentity] Failed to resolve master identity for account: shop_account_id=%s error=%s",
            shop_account_id,
            exc,
        )
        return None
    return identity_from_shop_account_row(row)
