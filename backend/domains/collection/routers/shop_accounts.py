from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies.auth import require_admin
from backend.models.database import get_async_db
from backend.schemas.shop_account import (
    ShopAccountCreate,
    ShopAccountResponse,
    ShopAccountUpdate,
)
from backend.services.cache_service import get_cache_service
from backend.services.collection_contracts import summarize_shop_scopes
from backend.services.data_pipeline.refresh_queue_service import RefreshQueueService
from backend.services.shop_internal_code_service import (
    load_taken_internal_codes,
    suggest_internal_code_for_account,
)
from backend.services.shop_rename_service import (
    apply_store_name_rename as _apply_store_name_rename,
    retain_previous_platform_shop_id_as_alias as _retain_previous_platform_shop_id_as_alias,
)
from backend.services.shop_sync_service import sync_shop_account_to_dim_shop
from backend.utils.text_normalization import normalize_alias_key, normalize_alias_text
from modules.core.db import (
    CollectionConfig,
    CollectionConfigShopScope,
    MainAccount,
    ShopAccount,
    ShopAccountAlias,
    ShopAccountBusinessRole,
    ShopAccountCapability,
)
from modules.core.logger import get_logger


router = APIRouter(
    prefix="/shop-accounts",
    tags=["shop account management"],
    dependencies=[Depends(require_admin)],
)

logger = get_logger(__name__)

_SHOP_IDENTITY_REFRESH_TARGETS = [
    # 候选集的**物化副本**必须刷。
    # 原子层（orders / analytics / products / services / inventory）读的是它的快照，
    # 不是实时算的 ⇒ 别名或平台店铺ID 改了以后不刷副本，那些链路就一直用旧快照
    # ⇒ 新别名不生效、这家店的历史仍然落进 unknown。
    # 副本只有 136 行，刷新是毫秒级。
    "semantic.shop_identity_resolution_candidates_v2_mv",
    "semantic.fact_orders_monthly_atomic_mv",
    "semantic.fact_analytics_monthly_atomic_mv",
]
_SHOP_IDENTITY_FIELDS = {
    "main_account_id",
    "store_name",
    "platform_shop_id",
    "platform_shop_id_status",
}

#: 平台店铺ID状态取值（服务端派生，不信客户端）。
_PLATFORM_SHOP_ID_STATUS_MISSING = "missing"
_PLATFORM_SHOP_ID_STATUS_MANUAL = "manual_confirmed"


def _derive_platform_shop_id_status(
    platform_shop_id: str | None,
    *,
    previous_status: str | None = None,
    platform_shop_id_changed: bool = False,
) -> str:
    """派生「平台店铺ID状态」—— **服务端说了算**。

    为什么不能信客户端
    ----------------
    这个状态回答的是「这个平台的店铺ID是什么来路、靠不靠谱」，而它必须
    **与数据一致**：没有平台店铺ID却标成 ``manual_confirmed``，就是在骗下游
    （看板的店铺身份健康度、采集对账都会拿它当依据）。

    规则
    ----
    - 没有平台店铺ID ⇒ ``missing``（无论客户端说什么）；
    - 平台店铺ID 变了（人工填的）⇒ ``manual_confirmed``；
    - 平台店铺ID 没变 ⇒ **保留原状态**（``auto_bound`` / ``confirmed`` 都不该
      被一次无关字段的编辑改写掉 —— 那是「自动绑定/平台确认」的成果）。
    """
    if not str(platform_shop_id or "").strip():
        return _PLATFORM_SHOP_ID_STATUS_MISSING
    if platform_shop_id_changed:
        return _PLATFORM_SHOP_ID_STATUS_MANUAL
    return str(previous_status or "").strip() or _PLATFORM_SHOP_ID_STATUS_MANUAL


def _default_capabilities_for(shop_type: str | None) -> dict[str, bool]:
    defaults = {
        "orders": True,
        "products": True,
        "services": True,
        "analytics": True,
        "finance": True,
        "inventory": True,
        "purchase": True,
    }
    if shop_type == "global":
        defaults["services"] = False
    return defaults


async def _load_capabilities(
    db: AsyncSession,
    shop_account_db_id: int,
    shop_type: str | None,
) -> dict[str, bool]:
    capability_result = await db.execute(
        select(ShopAccountCapability).where(
            ShopAccountCapability.shop_account_id == shop_account_db_id
        )
    )
    rows = capability_result.scalars().all()
    if rows:
        return {row.data_domain: bool(row.enabled) for row in rows}
    return _default_capabilities_for(shop_type)


async def _ensure_capability_rows(
    db: AsyncSession,
    shop_account: ShopAccount,
    *,
    shop_type: str | None = None,
    capabilities: dict[str, bool] | None = None,
) -> None:
    capability_result = await db.execute(
        select(ShopAccountCapability).where(
            ShopAccountCapability.shop_account_id == shop_account.id
        )
    )
    existing = capability_result.scalars().all()
    existing_map = {row.data_domain: row for row in existing}
    target_capabilities = (
        capabilities
        if capabilities is not None
        else _default_capabilities_for(shop_type or shop_account.shop_type)
    )

    for domain, enabled in target_capabilities.items():
        capability_row = existing_map.get(domain)
        if capability_row is not None:
            capability_row.enabled = bool(enabled)
            continue
        db.add(
            ShopAccountCapability(
                shop_account_id=shop_account.id,
                data_domain=str(domain),
                enabled=bool(enabled),
            )
        )


async def _serialize_shop_account(
    db: AsyncSession,
    record: ShopAccount,
    *,
    taken_codes: dict[str, set[str]] | None = None,
) -> ShopAccountResponse:
    alias_result = await db.execute(
        select(ShopAccountAlias).where(
            ShopAccountAlias.shop_account_id == record.id,
            # 用 .is_(True) 而不是 `== True`：后者在 SQLAlchemy 里会被改写成
            # `is_active = true`，NULL 行会被漏掉；.is_(True) 语义一致且不踩 E712。
            ShopAccountAlias.is_active.is_(True),
        )
    )
    aliases = alias_result.scalars().all()
    primary_alias = next(
        (alias.alias_value for alias in aliases if alias.is_primary), None
    )
    if primary_alias is None:
        primary_alias = next((alias.alias_value for alias in aliases), None)
    capabilities = await _load_capabilities(db, record.id, record.shop_type)
    suggested_internal_code = await suggest_internal_code_for_account(
        db,
        record,
        taken_codes=taken_codes,
    )
    return ShopAccountResponse(
        id=record.id,
        platform=record.platform,
        shop_account_id=record.shop_account_id,
        main_account_id=record.main_account_id,
        account_alias=normalize_alias_text(primary_alias),
        alias_count=len(aliases),
        capabilities=capabilities,
        store_name=record.store_name,
        internal_code=record.internal_code,
        suggested_internal_code=suggested_internal_code,
        platform_shop_id=record.platform_shop_id,
        platform_shop_id_status=record.platform_shop_id_status,
        shop_region=record.shop_region,
        shop_type=record.shop_type,
        business_role=record.business_role,
        enabled=record.enabled,
        notes=record.notes,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


async def _get_shop_account_or_404(
    db: AsyncSession, shop_account_id: str
) -> ShopAccount:
    result = await db.execute(
        select(ShopAccount).where(ShopAccount.shop_account_id == shop_account_id)
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(
            status_code=404, detail=f"shop_account_id '{shop_account_id}' not found"
        )
    return record


async def _assert_platform_shop_id_unique(
    db: AsyncSession,
    *,
    platform: str,
    platform_shop_id: str | None,
    exclude_id: int | None = None,
) -> None:
    normalized_platform_shop_id = (platform_shop_id or "").strip()
    if not normalized_platform_shop_id:
        return

    stmt = select(ShopAccount).where(
        ShopAccount.platform == platform,
        ShopAccount.platform_shop_id == normalized_platform_shop_id,
    )
    if exclude_id is not None:
        stmt = stmt.where(ShopAccount.id != exclude_id)

    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"platform_shop_id '{normalized_platform_shop_id}' already exists "
                f"for platform '{platform}' on shop_account_id '{existing.shop_account_id}'"
            ),
        )


async def _assert_internal_code_unique(
    db: AsyncSession,
    *,
    platform: str,
    internal_code: str | None,
    exclude_id: int | None = None,
) -> None:
    """内部标准名同平台内唯一（库层约束 uq_shop_accounts_platform_internal_code）。

    这里把约束翻译成人话：冲突时告诉运营「这个名字被哪个店占用了」。
    """
    normalized_internal_code = (internal_code or "").strip()
    if not normalized_internal_code:
        return

    stmt = select(ShopAccount).where(
        ShopAccount.platform == platform,
        ShopAccount.internal_code == normalized_internal_code,
    )
    if exclude_id is not None:
        stmt = stmt.where(ShopAccount.id != exclude_id)

    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"内部标准名 '{normalized_internal_code}' 已被平台 '{platform}' 的店铺账号 "
                f"'{existing.shop_account_id}'（店名 {existing.store_name}）占用"
            ),
        )


async def _assert_store_name_unique_in_main_account(
    db: AsyncSession,
    main_account_id: str,
    store_name: str | None,
    *,
    exclude_id: int | None = None,
) -> None:
    """同一个主账号下店铺名唯一（改名联动的第一步校验）。"""
    normalized_store_name = (store_name or "").strip()
    if not normalized_store_name:
        return

    stmt = select(ShopAccount).where(
        ShopAccount.main_account_id == main_account_id,
        ShopAccount.store_name == normalized_store_name,
    )
    if exclude_id is not None:
        stmt = stmt.where(ShopAccount.id != exclude_id)

    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"主账号 '{main_account_id}' 下已存在同名店铺 '{normalized_store_name}'"
                f"（店铺账号 '{existing.shop_account_id}'）"
            ),
        )


async def _assert_store_name_not_occupied_on_platform(
    db: AsyncSession,
    *,
    platform: str,
    shop_region: str | None,
    store_name: str | None,
    exclude_id: int | None = None,
) -> None:
    """店名在**同平台**内不能被别的店铺账号占用（**跨主账号**也算）。

    为什么不能只查同一个主账号
    ------------------------
    店名是身份解析的**第 4 路匹配键**（``store_name_match``）。语义层
    （``sql/semantic/shop_identity_resolution_candidates*.sql``）按
    ``(platform_code, 规范化店名)`` 找候选 —— **不区分主账号**。

    于是：两个**不同主账号**的店铺用了同一个店名 ⇒ 候选数 = 2 ⇒ 原子层判为
    ``ambiguous_shop_label`` ⇒ 这些行的 ``shop_id`` 落进 ``'unknown'`` ⇒
    **这家店的钱在看板上直接消失**（进 unknown 桶）。

    原来的校验只覆盖「同一个主账号」，跨主账号撞车要到**语义层**才炸，
    而那时候已经是在算钱、已经算错了 ⇒ 必须提前拦在写入侧。

    规范化口径与语义层一致（``normalize_alias_key``：剥平台前缀 → 小写 →
    折叠分隔符），否则「看着不一样、匹配时一样」。

    区域语义与别名表唯一约束一致
    （``UNIQUE NULLS NOT DISTINCT (platform, alias_normalized, shop_region, is_active)``）：
    - 同名 + 同区域 ⇒ 冲突；
    - 同名 + **不同**区域 ⇒ 允许（区域消歧就是为了让同平台同名在不同区域并存）；
    - 一方区域为空（不限区域）⇒ 与另一方也为空才算冲突（NULL 只与 NULL 冲突）。

    Raises:
        HTTPException: 409 —— 店名已被同平台的别的店铺账号占用
    """
    normalized_target = normalize_alias_key(store_name)
    if not normalized_target:
        return

    normalized_platform = str(platform or "").strip().lower()
    if not normalized_platform:
        return

    target_region = str(shop_region or "").strip() or None

    stmt = select(ShopAccount).where(
        ShopAccount.platform == str(platform or "").strip()
    )
    if exclude_id is not None:
        stmt = stmt.where(ShopAccount.id != exclude_id)
    candidates = (await db.execute(stmt)).scalars().all()

    for candidate in candidates:
        if str(candidate.platform or "").strip().lower() != normalized_platform:
            continue
        if normalize_alias_key(candidate.store_name) != normalized_target:
            continue
        candidate_region = str(candidate.shop_region or "").strip() or None
        if target_region != candidate_region:
            # 同名但区域不同 —— 区域消歧允许并存
            continue
        raise HTTPException(
            status_code=409,
            detail=(
                f"店名 '{store_name}' 在平台 '{platform}' 上已被店铺账号 "
                f"'{candidate.shop_account_id}'（主账号 '{candidate.main_account_id}'，"
                f"店名 {candidate.store_name}）占用。"
                f"店名会参与店铺身份匹配，同平台重名会让金额落进 unknown 桶。"
            ),
        )


async def _assert_main_account_exists(
    db: AsyncSession, platform: str, main_account_id: str
) -> None:
    result = await db.execute(
        select(MainAccount).where(
            MainAccount.platform == platform,
            MainAccount.main_account_id == main_account_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=400, detail=f"main_account_id '{main_account_id}' not found"
        )


async def _enqueue_shop_identity_refresh(
    db: AsyncSession,
    *,
    shop_account: ShopAccount,
    changed_fields: list[str],
) -> None:
    if not changed_fields:
        return
    try:
        await RefreshQueueService(db).enqueue_refresh(
            trigger_type="shop_identity_changed",
            pipeline_name="postgresql_dashboard",
            targets=_SHOP_IDENTITY_REFRESH_TARGETS,
            context={
                "shop_account_id": shop_account.shop_account_id,
                "shop_account_db_id": shop_account.id,
                "platform": shop_account.platform,
                "changed_fields": changed_fields,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[ShopIdentity] failed to enqueue dashboard refresh for shop_account_id=%s: %s",
            shop_account.shop_account_id,
            exc,
            exc_info=True,
        )
    try:
        await get_cache_service().invalidate_dashboard_business_overview()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[ShopIdentity] failed to invalidate business overview cache for shop_account_id=%s: %s",
            shop_account.shop_account_id,
            exc,
            exc_info=True,
        )


@router.get("", response_model=List[ShopAccountResponse])
async def list_shop_accounts(
    platform: Optional[str] = Query(None),
    main_account_id: Optional[str] = Query(None),
    business_role: Optional[ShopAccountBusinessRole] = Query(None),
    enabled: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_async_db),
):
    stmt = select(ShopAccount).order_by(
        ShopAccount.platform, ShopAccount.shop_account_id
    )
    if platform:
        stmt = stmt.where(ShopAccount.platform == platform)
    if main_account_id:
        stmt = stmt.where(ShopAccount.main_account_id == main_account_id)
    if business_role is not None:
        stmt = stmt.where(ShopAccount.business_role == business_role)
    if enabled is not None:
        stmt = stmt.where(ShopAccount.enabled == enabled)
    result = await db.execute(stmt)
    records = result.scalars().all()
    taken_codes = await load_taken_internal_codes(db)
    return [
        await _serialize_shop_account(db, record, taken_codes=taken_codes)
        for record in records
    ]


@router.post("", response_model=ShopAccountResponse)
async def create_shop_account(
    payload: ShopAccountCreate,
    db: AsyncSession = Depends(get_async_db),
):
    await _assert_main_account_exists(db, payload.platform, payload.main_account_id)
    await _assert_platform_shop_id_unique(
        db,
        platform=payload.platform,
        platform_shop_id=payload.platform_shop_id,
    )
    normalized_internal_code = str(payload.internal_code or "").strip() or None
    if normalized_internal_code:
        await _assert_internal_code_unique(
            db,
            platform=payload.platform,
            internal_code=normalized_internal_code,
        )
    await _assert_store_name_not_occupied_on_platform(
        db,
        platform=payload.platform,
        shop_region=payload.shop_region,
        store_name=payload.store_name,
    )
    existing = await db.execute(
        select(ShopAccount).where(
            ShopAccount.platform == payload.platform,
            ShopAccount.shop_account_id == payload.shop_account_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=400,
            detail=f"shop_account_id '{payload.shop_account_id}' already exists",
        )

    record = ShopAccount(
        platform=payload.platform,
        shop_account_id=payload.shop_account_id,
        main_account_id=payload.main_account_id,
        store_name=payload.store_name,
        internal_code=normalized_internal_code,
        platform_shop_id=payload.platform_shop_id,
        platform_shop_id_status=_derive_platform_shop_id_status(
            payload.platform_shop_id
        ),
        shop_region=payload.shop_region,
        shop_type=payload.shop_type,
        business_role=payload.business_role,
        enabled=payload.enabled,
        notes=payload.notes,
        created_by="system",
        updated_by="system",
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    # 展示维度表（core.dim_shops）是店铺账号的派生物 —— 新账号立刻进去，
    # 否则看板显示名的 JOIN 落空、只能靠 store_name 兜底。
    await sync_shop_account_to_dim_shop(db, record)
    await _ensure_capability_rows(
        db,
        record,
        shop_type=payload.shop_type,
        capabilities=payload.capabilities,
    )
    await db.commit()
    return await _serialize_shop_account(db, record)


@router.post("/batch", response_model=List[ShopAccountResponse])
async def batch_create_shop_accounts(
    payloads: List[ShopAccountCreate],
    db: AsyncSession = Depends(get_async_db),
):
    created: List[tuple[ShopAccount, ShopAccountCreate]] = []
    for payload in payloads:
        await _assert_main_account_exists(db, payload.platform, payload.main_account_id)
        existing = await db.execute(
            select(ShopAccount).where(
                ShopAccount.platform == payload.platform,
                ShopAccount.shop_account_id == payload.shop_account_id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue
        normalized_internal_code = str(payload.internal_code or "").strip() or None
        if normalized_internal_code:
            await _assert_internal_code_unique(
                db,
                platform=payload.platform,
                internal_code=normalized_internal_code,
            )
        record = ShopAccount(
            platform=payload.platform,
            shop_account_id=payload.shop_account_id,
            main_account_id=payload.main_account_id,
            store_name=payload.store_name,
            internal_code=normalized_internal_code,
            platform_shop_id=payload.platform_shop_id,
            platform_shop_id_status=(
                "manual_confirmed" if payload.platform_shop_id else "missing"
            ),
            shop_region=payload.shop_region,
            shop_type=payload.shop_type,
            business_role=payload.business_role,
            enabled=payload.enabled,
            notes=payload.notes,
            created_by="system",
            updated_by="system",
        )
        db.add(record)
        created.append((record, payload))
    await db.commit()
    for record, payload in created:
        await db.refresh(record)
        await _ensure_capability_rows(
            db,
            record,
            shop_type=record.shop_type,
            capabilities=payload.capabilities,
        )
    await db.commit()
    return [await _serialize_shop_account(db, record) for record, _ in created]


async def _disable_shop_in_collection_scopes(
    db: AsyncSession, shop_account_id: str
) -> int:
    """店铺被停用时，把它从**所有采集配置**的 scope 里摘掉(置为不参与)。

    为什么必须联动
    --------------
    店铺停用只改了 ``core.shop_accounts.enabled``, 而采集配置的
    ``core.collection_config_shop_scopes`` 是**独立的一份引用** ⇒ 停用后
    它会一直留在配置里, 在采集工作区里变成一行"点不动、也没人知道为什么"
    的幽灵店铺(实测: ``shopee_sg_eternalbloom_local`` 残留在 2 条配置 +
    2 个模板里, 而它在 11-05 13:23 被 ``manual:fix_shop_identity_alignment``
    停用, 配置 scope 却建于同日 11:55 —— 差 1.5 小时, 没人回头清理)。

    执行侧其实早就按 ``enabled == True`` 过滤了(``collection_config_execution``),
    所以**不会**真的去采集一个停用店 ⇒ 数据不会错; 但界面会误导人,
    而且配置摘要 ``account_ids`` 会一直带着这个死账号。

    ⚠️ **覆盖边界**: 本函数只覆盖 **API 路径**(``update_shop_account`` /
    ``delete_shop_account``)。一次性维护脚本**直接改库**停用店铺时会绕过它 ——
    上一次残留就是这么来的(``updated_by = 'manual:fix_shop_identity_alignment'``,
    而 API 写入的 ``updated_by`` 是 ``system``) ⇒ 迁移层才是兜底。

    为什么是「置 enabled=false」而不是物理删除
    ------------------------------------------
    物理删除**不可逆** —— 删掉之后无法回答"这个店当初配了哪些数据域"。
    置为不参与则:
      * 采集不再调度它(执行侧只取 enabled 的 scope);
      * 摘要重算时自然被排除(``summarize_shop_scopes`` 只算 enabled 的);
      * 展示层按「账号已停用」过滤 ⇒ 它不会出现在工作区;
      * **可回滚** —— 店铺重新启用后, 把它改回 enabled 即可。
    (用户下次保存该配置时, 前端提交的 scope 不含停用店 ⇒ 残影会被自然删除。)

    返回被摘掉的 scope 行数。
    """
    scopes = (
        (
            await db.execute(
                select(CollectionConfigShopScope)
                .where(
                    CollectionConfigShopScope.shop_account_id == shop_account_id,
                    # 只动**当前还参与**的 scope —— 早已 disabled 的不必再改一遍
                    # (改了也是空操作, 但会把 updated_at 搅乱、让计数失真)。
                    CollectionConfigShopScope.enabled.is_(True),
                )
                .order_by(CollectionConfigShopScope.shop_account_id)
            )
        )
        .scalars()
        .all()
    )
    if not scopes:
        return 0

    config_ids = sorted({scope.config_id for scope in scopes})
    now = datetime.now(timezone.utc)
    for scope in scopes:
        scope.enabled = False
        scope.updated_at = now
    await db.flush()

    for config_id in config_ids:
        config = (
            await db.execute(
                select(CollectionConfig).where(CollectionConfig.id == config_id)
            )
        ).scalar_one_or_none()
        if config is None:
            continue
        remaining = (
            (
                await db.execute(
                    select(CollectionConfigShopScope).where(
                        CollectionConfigShopScope.config_id == config_id,
                        CollectionConfigShopScope.enabled.is_(True),
                    )
                    # ⚠️ 排序必须与迁移内联实现一致(按 shop_account_id) ——
                    # 否则「停用联动算出来的摘要」与「迁移算出来的摘要」顺序不同,
                    # 用户下次保存配置时摘要就会跳动。
                    .order_by(CollectionConfigShopScope.shop_account_id)
                )
            )
            .scalars()
            .all()
        )
        # 用 dict 喂 summarize_shop_scopes —— 它对 ORM 对象走 dict(obj),
        # 而 SQLAlchemy 实体不可 dict() ⇒ 必须显式转成 dict。
        summary = summarize_shop_scopes(
            [
                {
                    "shop_account_id": scope.shop_account_id,
                    "data_domains": list(scope.data_domains or []),
                    "sub_domains": scope.sub_domains or {},
                    "enabled": bool(scope.enabled),
                }
                for scope in remaining
            ]
        )
        config.account_ids = summary["account_ids"]
        config.data_domains = summary["data_domains"]
        config.sub_domains = summary["sub_domains"]

    # ⚠️ 必须 flush —— 否则摘要的改动还挂在 session 里没落库,
    # 同一事务内后续读到的还是旧值(顶部统计与实际配置对不上)。
    await db.flush()

    logger.info(
        "Disabled shop %s in %d collection config scope(s)",
        shop_account_id,
        len(scopes),
    )
    return len(scopes)


@router.put("/{shop_account_id}", response_model=ShopAccountResponse)
async def update_shop_account(
    shop_account_id: str,
    payload: ShopAccountUpdate,
    db: AsyncSession = Depends(get_async_db),
):
    record = await _get_shop_account_or_404(db, shop_account_id)
    update_data = payload.model_dump(exclude_unset=True)
    capabilities_submitted = "capabilities" in update_data
    capabilities = update_data.pop("capabilities", None)
    # 平台店铺ID状态是**服务端派生**的字段：客户端传什么都不作数。
    update_data.pop("platform_shop_id_status", None)
    # 改名联动的两个「原值」必须在赋值前抓住 —— 前端每次提交的是整个表单
    original_store_name = record.store_name
    original_internal_code = record.internal_code
    original_platform_shop_id = record.platform_shop_id
    original_platform_shop_id_status = record.platform_shop_id_status
    original_enabled = bool(record.enabled)
    if "platform_shop_id" in update_data:
        await _assert_platform_shop_id_unique(
            db,
            platform=record.platform,
            platform_shop_id=update_data["platform_shop_id"],
            exclude_id=record.id,
        )
    if "internal_code" in update_data:
        # 空串 = 清空标准名（内部标准名不参与匹配，清掉不影响历史数据）
        normalized_internal_code = str(update_data["internal_code"] or "").strip()
        update_data["internal_code"] = normalized_internal_code or None
        await _assert_internal_code_unique(
            db,
            platform=record.platform,
            internal_code=normalized_internal_code,
            exclude_id=record.id,
        )
    if "store_name" in update_data:
        await _assert_store_name_unique_in_main_account(
            db,
            record.main_account_id,
            update_data["store_name"],
            exclude_id=record.id,
        )
        await _assert_store_name_not_occupied_on_platform(
            db,
            platform=record.platform,
            shop_region=update_data.get("shop_region", record.shop_region),
            store_name=update_data["store_name"],
            exclude_id=record.id,
        )
    # 1) 先按现有逻辑全量赋值（保留 platform_shop_id 唯一性校验与 capabilities 处理）
    for field, value in update_data.items():
        setattr(record, field, value)
    # 1.1) 店铺被停用 ⇒ 把它从采集配置里摘掉。
    #     不做这一步, 采集工作区会留下一行「点不动、也不说为什么」的幽灵店铺,
    #     配置摘要 account_ids 也会一直带着这个死账号(实测已发生)。
    if original_enabled and not bool(record.enabled):
        await _disable_shop_in_collection_scopes(db, record.shop_account_id)
    # 1.5) 平台店铺ID状态由服务端派生（客户端传的值不作数）
    record.platform_shop_id_status = _derive_platform_shop_id_status(
        record.platform_shop_id,
        previous_status=record.platform_shop_id_status,
        platform_shop_id_changed=(
            "platform_shop_id" in update_data
            and str(update_data["platform_shop_id"] or "").strip()
            != str(original_platform_shop_id or "").strip()
        ),
    )
    # 2) 再对 store_name 走改名联动。
    #    注意：前端每次编辑提交整个表单（store_name 恒存在），
    #    若把改名做成 if/else，else 分支永远不走 -> 其它字段全部不落库。
    if "store_name" in update_data and update_data["store_name"] != original_store_name:
        await _apply_store_name_rename(
            db,
            record,
            update_data["store_name"],
            old_store_name=original_store_name,
            original_internal_code=original_internal_code,
        )
    # 2.5) 换绑平台店铺ID 时把**旧值留成别名**。
    #     历史行的店铺键是采集时的平台店铺ID；换绑后旧值不再命中任何候选
    #     ⇒ 这家店的历史数据全部落进 unknown ⇒ 看板上这家店的历史直接消失。
    #     改名（旧名转 former_name 别名）早就堵住了，换绑却漏了 —— 同一个问题的两个入口。
    if "platform_shop_id" in update_data:
        await _retain_previous_platform_shop_id_as_alias(
            db,
            record,
            original_platform_shop_id,
        )
    # 3) 展示维度表同步（core.dim_shops 是店铺账号的派生物）
    await sync_shop_account_to_dim_shop(db, record)
    if capabilities_submitted or "shop_type" in update_data:
        await _ensure_capability_rows(
            db,
            record,
            shop_type=update_data.get("shop_type", record.shop_type),
            capabilities=capabilities,
        )
    record.updated_at = datetime.now(timezone.utc)
    record.updated_by = "system"
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await db.refresh(record)
    changed_identity_fields = [
        field for field in update_data.keys() if field in _SHOP_IDENTITY_FIELDS
    ]
    # 平台店铺ID状态是服务端派生的 ⇒ 「它变了」按**派生结果**判定，
    # 不按客户端声称。派生结果没变 ⇒ 不触发归属重算（避免无谓的刷新风暴）。
    if (
        "platform_shop_id_status" not in changed_identity_fields
        and record.platform_shop_id_status != original_platform_shop_id_status
    ):
        changed_identity_fields.append("platform_shop_id_status")
    # 改名一定会带上 store_name -> 归属重算已经由这一次入队覆盖
    await _enqueue_shop_identity_refresh(
        db,
        shop_account=record,
        changed_fields=changed_identity_fields,
    )
    return await _serialize_shop_account(db, record)


@router.delete("/{shop_account_id}")
async def delete_shop_account(
    shop_account_id: str,
    db: AsyncSession = Depends(get_async_db),
):
    record = await _get_shop_account_or_404(db, shop_account_id)
    # 店铺被删除 ⇒ 采集配置里的引用与摘要同样要清。
    # ⚠️ scope 行本身会被数据库的 ON DELETE CASCADE 带走
    #    (collection_config_shop_scopes.shop_account_id → shop_accounts.shop_account_id),
    #    **但配置的摘要(account_ids / data_domains / sub_domains)没人管** ——
    #    不重算的话, 顶部「店铺总览」会一直挂着一个已经不存在了的账号。
    await _disable_shop_in_collection_scopes(db, shop_account_id)
    await db.delete(record)
    await db.commit()
    return {"message": f"shop_account_id '{shop_account_id}' deleted"}
