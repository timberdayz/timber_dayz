"""改名联动：一次改名，三处同步，老数据不断。

平台侧真实店名最终都要改（``DAONE Mall`` -> ``FIORO``）。不改未来会有分歧：
同一个店在库里出现两个名字，老数据认旧名、新数据认新名，数据分裂。

所以改名必须是一次**联动操作**，六个步骤缺一不可：

1. **唯一性校验**：同平台 ``internal_code`` 唯一；同主账号 ``store_name`` 唯一。
2. **旧名转曾用名**：旧 ``store_name`` 写入别名表
   （``is_active=true`` / ``is_primary=false`` / ``alias_type='former_name'``）
   -> **老数据继续命中同一个店**（曾用名仍参与匹配）。
3. **新名接管主别名**：新 ``store_name`` 写入别名表并置 ``is_primary=true``；
   原主别名降为 ``is_primary=false``、``is_active`` 保持 True。
4. **同步 ``core.dim_shops.shop_name``** -> 否则页面、绩效、提成里显示的还是旧名。
5. **同步 ``internal_code``**（仅当它是按旧店名自动生成的时候）。
6. **入刷新队列**（由调用方在事务提交后入队一次 -> 触发一次归属重算）。

> **同步目标是 ``core.dim_shops``，不是 ``core.platform_accounts``。**
> 后者是**主账号粒度**的旧表（``store_name`` = 主账号名），改店铺名不该动它。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.shop_internal_code_service import (
    ensure_unique_internal_code,
    load_taken_internal_codes,
    suggest_internal_code,
)
from backend.utils.text_normalization import normalize_alias_key, normalize_alias_text
from modules.core.db import DimShop, ShopAccount, ShopAccountAlias
from modules.core.logger import get_logger


logger = get_logger(__name__)

#: 曾用名的别名类型
FORMER_NAME_ALIAS_TYPE = "former_name"
#: 当前主名的别名类型
PRIMARY_ALIAS_TYPE = "primary"
#: 别名来源标记（改名联动写入的别名）
RENAME_ALIAS_SOURCE = "store_name_rename"


@dataclass(frozen=True)
class RenameResult:
    """一次改名联动的结果。"""

    old_store_name: str
    new_store_name: str
    renamed: bool = False
    former_alias_id: Optional[int] = None
    primary_alias_id: Optional[int] = None
    dim_shop_synced: bool = False
    internal_code: Optional[str] = None
    internal_code_regenerated: bool = False


async def apply_store_name_rename(
    db: AsyncSession,
    shop_account: ShopAccount,
    new_store_name: str,
    *,
    old_store_name: Optional[str] = None,
    original_internal_code: Optional[str] = None,
) -> RenameResult:
    """执行一次改名联动。

    顺序固定：

    1. 旧名转曾用名（别名表 is_active=true, is_primary=false）
    2. 新名写入别名表并接管 is_primary
    3. 同步 core.dim_shops.shop_name（展示用的维度表，店铺粒度）
    4. 落库 core.shop_accounts.store_name
    5. 同步 internal_code（仅自动生成的标准名才跟着改）

    刷新队列由调用方在**提交之后**入队一次 —— 本函数不碰队列，
    避免在事务中间提交。

    Args:
        db: 异步会话
        shop_account: 被改名的店铺账号
        new_store_name: 新店名
        old_store_name: 旧店名。调用方若已先做过全量赋值，必须显式传进来。
        original_internal_code: 改动前的内部标准名。用于判断标准名是不是「自动生成」的。

    Returns:
        :class:`RenameResult`
    """
    previous_name = str(old_store_name if old_store_name is not None else shop_account.store_name or "").strip()
    target_name = str(new_store_name or "").strip()
    if not target_name or target_name == previous_name:
        return RenameResult(
            old_store_name=previous_name,
            new_store_name=target_name,
            renamed=False,
            internal_code=shop_account.internal_code,
        )

    former_alias_id: Optional[int] = None
    primary_alias_id: Optional[int] = None

    # 规范化后与旧名相同的（例如 DAONE Mall -> DAONE MALL）属于「只是大小写/分隔符变了」，
    # 别名语义没变 —— 跳过别名写入（否则会撞库层唯一约束），只改 store_name。
    alias_semantics_changed = (
        normalize_alias_key(previous_name) != normalize_alias_key(target_name)
    )

    if alias_semantics_changed:
        # 1) 旧名转曾用名 —— 它仍参与匹配，老数据才不会断
        former_alias = await _upsert_shop_alias(
            db,
            shop_account=shop_account,
            alias_value=previous_name,
            alias_type=FORMER_NAME_ALIAS_TYPE,
            is_primary=False,
            is_active=True,
        )
        former_alias_id = former_alias.id

        # 2) 新名接管主别名：先把本店现有的主别名降级（is_active 保持 True），
        #    曾用名机制依赖「降级但仍 active」。
        await _demote_primary_aliases(db, shop_account.id)
        primary_alias = await _upsert_shop_alias(
            db,
            shop_account=shop_account,
            alias_value=target_name,
            alias_type=PRIMARY_ALIAS_TYPE,
            is_primary=True,
            is_active=True,
        )
        primary_alias_id = primary_alias.id

    # 3) 同步展示用的维度表（店铺粒度）
    dim_shop_synced = await _sync_dim_shop_name(
        db,
        platform=shop_account.platform,
        shop_account=shop_account,
        new_store_name=target_name,
    )

    # 4) 落库
    shop_account.store_name = target_name

    # 5) 同步内部标准名
    internal_code, internal_code_regenerated = await _sync_internal_code_after_rename(
        db,
        shop_account,
        old_store_name=previous_name,
        new_store_name=target_name,
        original_internal_code=original_internal_code,
    )

    return RenameResult(
        old_store_name=previous_name,
        new_store_name=target_name,
        renamed=True,
        former_alias_id=former_alias_id,
        primary_alias_id=primary_alias_id,
        dim_shop_synced=dim_shop_synced,
        internal_code=internal_code,
        internal_code_regenerated=internal_code_regenerated,
    )


async def _demote_primary_aliases(db: AsyncSession, shop_account_db_id: int) -> None:
    """把本店的主别名降级（``is_primary=False``，``is_active`` 保持 True）。

    曾用名机制依赖这一点：降级后的别名仍参与匹配，老数据才不会断。
    """
    result = await db.execute(
        select(ShopAccountAlias).where(
            ShopAccountAlias.shop_account_id == shop_account_db_id,
            ShopAccountAlias.is_active == True,
            ShopAccountAlias.is_primary == True,
        )
    )
    for alias in result.scalars().all():
        alias.is_primary = False


async def _upsert_shop_alias(
    db: AsyncSession,
    *,
    shop_account: ShopAccount,
    alias_value: str,
    alias_type: str,
    is_primary: bool,
    is_active: bool = True,
) -> ShopAccountAlias:
    """写一条别名；已存在则复用，别名被别人占用则 409（不静默覆盖）。"""
    normalized_value = normalize_alias_text(alias_value) or ""
    alias_normalized = normalize_alias_key(normalized_value)
    shop_region = str(shop_account.shop_region or "").strip() or None
    platform = str(shop_account.platform or "").strip()

    existing = (
        await db.execute(
            select(ShopAccountAlias).where(
                ShopAccountAlias.shop_account_id == shop_account.id,
                ShopAccountAlias.alias_normalized == alias_normalized,
            )
        )
    ).scalars().first()
    if existing is not None:
        existing.alias_value = normalized_value
        existing.alias_type = alias_type
        existing.platform = platform
        existing.shop_region = shop_region
        existing.is_primary = is_primary
        existing.is_active = is_active
        return existing

    await assert_alias_available(
        db,
        platform=platform,
        alias_normalized=alias_normalized,
        shop_region=shop_region,
        exclude_shop_account_db_id=shop_account.id,
    )

    record = ShopAccountAlias(
        shop_account_id=shop_account.id,
        platform=platform,
        alias_value=normalized_value,
        alias_normalized=alias_normalized,
        alias_type=alias_type,
        source=RENAME_ALIAS_SOURCE,
        shop_region=shop_region,
        is_primary=is_primary,
        is_active=is_active,
    )
    db.add(record)
    await db.flush()
    return record


async def assert_alias_available(
    db: AsyncSession,
    *,
    platform: str,
    alias_normalized: str,
    shop_region: Optional[str],
    exclude_shop_account_db_id: Optional[int] = None,
) -> None:
    """别名占用的友好预检（库层约束 ``uq_shop_account_aliases_active_alias`` 的人话版）。

    库层约束是 ``UNIQUE NULLS NOT DISTINCT (platform, alias_normalized, shop_region, is_active)``：

    - 只与 ``is_active=true`` 的行冲突；
    - ``shop_region`` 为 NULL 的别名（不限区域）**不与**有区域的别名冲突
      （NULL 只与 NULL 冲突）。

    Args:
        db: 异步会话
        platform: 平台代码
        alias_normalized: 规范化后的别名
        shop_region: 区域码；None 表示不限区域
        exclude_shop_account_db_id: 排除的店铺账号（自己的别名不算冲突）

    Raises:
        HTTPException: 409 —— 别名已被别的店铺账号占用
    """
    if not alias_normalized:
        return

    stmt = select(ShopAccountAlias).where(
        ShopAccountAlias.platform == platform,
        ShopAccountAlias.alias_normalized == alias_normalized,
        ShopAccountAlias.is_active == True,
    )
    if shop_region is None:
        stmt = stmt.where(ShopAccountAlias.shop_region.is_(None))
    else:
        stmt = stmt.where(ShopAccountAlias.shop_region == shop_region)
    if exclude_shop_account_db_id is not None:
        stmt = stmt.where(
            ShopAccountAlias.shop_account_id != exclude_shop_account_db_id
        )

    conflict = (await db.execute(stmt)).scalars().first()
    if conflict is None:
        return

    owner = await db.get(ShopAccount, conflict.shop_account_id)
    owner_store_name = owner.store_name if owner is not None else "未知店铺"
    owner_shop_account_id = (
        owner.shop_account_id if owner is not None else str(conflict.shop_account_id)
    )
    owner_region = (
        (str(owner.shop_region).strip() if owner is not None and owner.shop_region else "")
        or "不限区域"
    )
    raise HTTPException(
        status_code=409,
        detail=(
            f"别名 '{conflict.alias_value}' 在平台 '{platform}' / 区域 '{owner_region}' "
            f"已被店铺账号 '{owner_shop_account_id}'（店名 {owner_store_name}）占用"
        ),
    )


async def _sync_dim_shop_name(
    db: AsyncSession,
    *,
    platform: Optional[str],
    shop_account: ShopAccount,
    new_store_name: str,
) -> bool:
    """同步 ``core.dim_shops.shop_name``（店铺粒度的展示维度表）。

    定位键依次尝试 ``shop_account_id`` 与 ``platform_shop_id`` —— live 库里
    tiktok 行的 ``shop_id`` 就是 ``shop_account_id``，shopee 行则是平台店铺 ID。

    找不到对应行时**不新建**，只记日志。
    """
    platform_code = str(platform or "").strip().lower()
    lookup_ids = [
        str(shop_account.shop_account_id or "").strip(),
        str(shop_account.platform_shop_id or "").strip(),
    ]
    seen: set[str] = set()
    for shop_id in lookup_ids:
        if not shop_id or shop_id in seen:
            continue
        seen.add(shop_id)
        # 用 SAVEPOINT 包住：维度表缺失/查询失败不能连带把整个改名事务搞挂
        try:
            async with db.begin_nested():
                dim_shop = (
                    await db.execute(
                        select(DimShop).where(
                            DimShop.platform_code == platform_code,
                            DimShop.shop_id == shop_id,
                        )
                    )
                ).scalars().first()
                if dim_shop is None:
                    continue
                dim_shop.shop_name = new_store_name
        except SQLAlchemyError:
            logger.warning(
                "[ShopRename] 读取 core.dim_shops 失败（platform_code=%s shop_id=%s），"
                "跳过展示名同步",
                platform_code,
                shop_id,
                exc_info=True,
            )
            return False
        logger.info(
            "[ShopRename] synced core.dim_shops.shop_name for platform_code=%s shop_id=%s -> %s",
            platform_code,
            shop_id,
            new_store_name,
        )
        return True

    logger.info(
        "[ShopRename] core.dim_shops 里没有 platform_code=%s shop_id=%s 的行，跳过展示名同步",
        platform_code,
        shop_account.shop_account_id,
    )
    return False


async def _sync_internal_code_after_rename(
    db: AsyncSession,
    shop_account: ShopAccount,
    *,
    old_store_name: str,
    new_store_name: str,
    original_internal_code: Optional[str],
) -> tuple[Optional[str], bool]:
    """改名后同步内部标准名。

    规则：

    - 本次请求**显式给了**内部标准名 -> 以它为准（调用方已校验同平台唯一）；
    - 标准名是**按旧店名自动生成**的 -> 跟着新店名重算；
    - 标准名是**人工改过**的 -> 保持不动（人读标识不跟着机器重写）。
    """
    current = str(shop_account.internal_code or "").strip()
    previous = str(original_internal_code or "").strip()

    if current != previous:
        # 本次请求显式带了内部标准名 -> 不动
        return current, False

    if not previous:
        return None, False

    auto_old_code = suggest_internal_code(
        old_store_name,
        shop_account.shop_region,
        main_account_id=shop_account.main_account_id,
    )
    if previous != auto_old_code:
        # 人工改过的标准名 -> 保持不动
        return previous, False

    taken_codes = await load_taken_internal_codes(db)
    platform_key = str(shop_account.platform or "").strip().lower()
    used = set(taken_codes.get(platform_key, set()))
    used.discard(previous)
    candidate = suggest_internal_code(
        new_store_name,
        shop_account.shop_region,
        main_account_id=shop_account.main_account_id,
        taken=used,
    )
    new_code = ensure_unique_internal_code(candidate, used)
    shop_account.internal_code = new_code
    logger.info(
        "[ShopRename] internal_code auto-updated: %s -> %s", previous, new_code
    )
    return new_code, True
