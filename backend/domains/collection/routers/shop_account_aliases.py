from __future__ import annotations

import codecs
from dataclasses import dataclass
from typing import Any, Iterable, List, Mapping

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies.auth import require_admin
from backend.models.database import get_async_db
from backend.schemas.account import UnmatchedShopAliasItem, UnmatchedShopAliasResponse
from backend.schemas.shop_account_alias import (
    ShopAccountAliasCreate,
    ShopAccountAliasResponse,
)
from backend.services.cache_service import get_cache_service
from backend.services.data_pipeline.refresh_queue_service import RefreshQueueService
from backend.services.shop_rename_service import assert_alias_available
from backend.utils.text_normalization import normalize_alias_key, normalize_alias_text
from modules.core.db import ShopAccount, ShopAccountAlias, ShopAccountBusinessRole
from modules.core.logger import get_logger


router = APIRouter(
    prefix="/shop-account-aliases",
    tags=["Shop Account Aliases"],
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


def _u(value: str) -> str:
    return codecs.decode(value, "unicode_escape")


_CN_SITE = _u(r"\u7ad9\u70b9")
_CN_STORE = _u(r"\u5e97\u94fa")
_CN_STORE_SHORT = _u(r"\u5e97\u94fa\u540d")
_CN_STORE_NAME = _u(r"\u5e97\u94fa\u540d\u79f0")
_CN_ORDER_ID = _u(r"\u8ba2\u5355\u53f7")
_CN_SHOPEE_PAID = _u(r"\u5b9e\u4ed8\u91d1\u989d")
_CN_TIKTOK_PAID = _u(r"\u652f\u4ed8\u91d1\u989d")


_UNMATCHED_ALIAS_QUERY = """
WITH raw_candidates AS (
    SELECT
        LOWER(COALESCE(platform_code, raw_data->>'platform', ''))::varchar AS platform,
        NULLIF(TRIM(COALESCE(raw_data->>:cn_site, raw_data->>'site')), '') AS site,
        NULLIF(
            TRIM(
                COALESCE(
                    raw_data->>:cn_store,
                    raw_data->>:cn_store_short,
                    raw_data->>:cn_store_name,
                    raw_data->>'store_name',
                    raw_data->>'store_label_raw'
                )
            ),
            ''
        ) AS store_label_raw,
        COALESCE(order_id, raw_data->>:cn_order_id, raw_data->>'order_id') AS order_id,
        COALESCE(
            paid_amount,
            NULLIF(raw_data->>:cn_shopee_paid, '')::numeric,
            NULLIF(raw_data->>:cn_tiktok_paid, '')::numeric,
            0
        ) AS paid_amount
    FROM semantic.fact_orders_atomic
    -- [*] 2026-12 性能修正：语义与 COALESCE(shop_id,'') IN ('', 'none', 'unknown') 等价，
    -- 但写成 COALESCE(...) 会让底层事实表已有的 shop_id 索引（ix_fact_*_shop）失效，
    -- 视图 UNION ALL 多张事实表后全表扫描 + JSONB 提取，接口直接被 statement_timeout 打断。
    -- 改成 IS NULL OR IN (...) 后可走索引，扫描量从全量降到「缺店铺的少量行」。
    WHERE shop_id IS NULL OR shop_id IN ('', 'none', 'unknown')
),
grouped AS (
    SELECT
        platform,
        site,
        store_label_raw,
        COUNT(*) AS row_count,
        COUNT(DISTINCT order_id) AS order_count,
        COALESCE(SUM(paid_amount), 0) AS paid_amount
    FROM raw_candidates
    WHERE store_label_raw IS NOT NULL
    GROUP BY platform, site, store_label_raw
)
SELECT
    g.platform,
    g.site,
    g.store_label_raw,
    g.row_count,
    g.order_count,
    g.paid_amount
FROM grouped g
WHERE NOT EXISTS (
    SELECT 1
    FROM core.shop_account_aliases saa
    WHERE LOWER(COALESCE(saa.platform, '')) = LOWER(g.platform)
      AND LOWER(COALESCE(saa.alias_normalized, '')) = LOWER(
          REGEXP_REPLACE(
              REGEXP_REPLACE(TRIM(COALESCE(g.store_label_raw, '')), '^(shopee|tiktok[[:space:]]*shop|tiktok|tk|miaoshou|amazon|lazada)[[:space:]]*', '', 'i'),
              '[[:space:]_\\-()/]+',
              '',
              'g'
          )
      )
      AND saa.is_active = true
)
ORDER BY g.paid_amount DESC, g.row_count DESC, g.platform, g.store_label_raw
"""


_UNMATCHED_ALIAS_PARAMS = {
    "cn_site": _CN_SITE,
    "cn_store": _CN_STORE,
    "cn_store_short": _CN_STORE_SHORT,
    "cn_store_name": _CN_STORE_NAME,
    "cn_order_id": _CN_ORDER_ID,
    "cn_shopee_paid": _CN_SHOPEE_PAID,
    "cn_tiktok_paid": _CN_TIKTOK_PAID,
}


@dataclass(frozen=True)
class _PlatformAliasOccupancy:
    """某个平台下店铺账号的别名占用情况。"""

    total_shop_accounts: int = 0
    occupied_shop_accounts: int = 0
    claimable_shop_accounts: int = 0


async def _load_platform_alias_occupancy(
    db: AsyncSession,
) -> dict[str, _PlatformAliasOccupancy]:
    """统计每个平台下有多少店铺账号、已被其它标签 1:1 占满多少、还能直接认领多少。

    认领接口对「已持有其它主动别名」的店铺账号直接返回 409，因此只有没有任何主动
    别名的经营店铺账号才是可认领目标（采集账号本身禁止认领别名）。
    """
    occupied_shop_account_ids = set(
        (
            await db.execute(
                select(ShopAccountAlias.shop_account_id).where(
                    ShopAccountAlias.is_active == True,  # noqa: E712
                    ShopAccountAlias.is_primary == True,  # noqa: E712
                )
            )
        )
        .scalars()
        .all()
    )
    account_rows = (
        await db.execute(
            select(ShopAccount.platform, ShopAccount.id, ShopAccount.business_role)
        )
    ).all()

    buckets: dict[str, dict[str, int]] = {}
    for platform, shop_account_db_id, business_role in account_rows:
        bucket = buckets.setdefault(
            (platform or "").strip().lower(),
            {"total": 0, "occupied": 0, "claimable": 0},
        )
        bucket["total"] += 1
        if shop_account_db_id in occupied_shop_account_ids:
            bucket["occupied"] += 1
        elif business_role != ShopAccountBusinessRole.collection_source:
            bucket["claimable"] += 1

    return {
        platform: _PlatformAliasOccupancy(
            total_shop_accounts=bucket["total"],
            occupied_shop_accounts=bucket["occupied"],
            claimable_shop_accounts=bucket["claimable"],
        )
        for platform, bucket in buckets.items()
    }


def _build_claim_hint(occupancy: _PlatformAliasOccupancy | None) -> str | None:
    """生成未匹配别名的认领提示：说清「为什么现在不能直接认领、下一步该做什么」。"""
    if occupancy is None:
        return None
    if occupancy.total_shop_accounts <= 0:
        return "该平台下暂无店铺账号，需新建店账号才能认领"
    if occupancy.claimable_shop_accounts > 0:
        return f"该平台下有 {occupancy.claimable_shop_accounts} 个店铺账号可直接认领"
    if occupancy.occupied_shop_accounts >= occupancy.total_shop_accounts:
        return (
            f"该平台下 {occupancy.total_shop_accounts} 个店铺账号已被其它标签 1:1 占满，"
            "需新建店账号才能认领"
        )
    return (
        f"该平台下 {occupancy.occupied_shop_accounts} 个店铺账号已被其它标签 1:1 占满，"
        f"其余 {occupancy.total_shop_accounts - occupancy.occupied_shop_accounts} 个为采集账号，"
        "需新建店账号才能认领"
    )


def _build_unmatched_alias_items(
    rows: Iterable[Mapping[str, Any]],
    occupancy_by_platform: Mapping[str, _PlatformAliasOccupancy],
) -> List[UnmatchedShopAliasItem]:
    """把未匹配别名查询结果装配成契约对象，并补上认领提示。"""
    items: List[UnmatchedShopAliasItem] = []
    for row in rows:
        payload = dict(row)
        platform_key = (payload.get("platform") or "").strip().lower()
        payload["claim_hint"] = _build_claim_hint(
            occupancy_by_platform.get(platform_key)
        )
        items.append(UnmatchedShopAliasItem(**payload))
    return items


class ShopAccountAliasClaimRequest(BaseModel):
    platform: str = Field(..., description="platform code")
    alias_value: str = Field(..., description="alias to claim")
    shop_account_id: str = Field(..., description="target shop account id")
    source: str | None = Field(default="manual_claim", description="source")


def _normalize_alias(alias: str) -> str:
    return normalize_alias_key(alias)


def _serialize_alias(record: ShopAccountAlias) -> ShopAccountAliasResponse:
    alias_value = normalize_alias_text(record.alias_value) or ""
    return ShopAccountAliasResponse(
        id=record.id,
        shop_account_id=record.shop_account_id,
        platform=record.platform,
        alias_value=alias_value,
        alias_normalized=_normalize_alias(alias_value),
        alias_type=record.alias_type,
        source=record.source,
        is_primary=record.is_primary,
        is_active=record.is_active,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


async def _get_shop_account_or_404(
    db: AsyncSession, shop_account_id: str
) -> ShopAccount:
    shop_account = (
        await db.execute(
            select(ShopAccount).where(ShopAccount.shop_account_id == shop_account_id)
        )
    ).scalar_one_or_none()
    if shop_account is None:
        raise HTTPException(
            status_code=404, detail=f"shop account id '{shop_account_id}' not found"
        )
    return shop_account


async def _clear_primary_aliases(
    db: AsyncSession,
    shop_account_db_id: int,
    *,
    deactivate: bool = False,
) -> None:
    alias_result = await db.execute(
        select(ShopAccountAlias).where(
            ShopAccountAlias.shop_account_id == shop_account_db_id,
            ShopAccountAlias.is_active.is_(True),
            ShopAccountAlias.is_primary.is_(True),
        )
    )
    for alias in alias_result.scalars().all():
        alias.is_primary = False
        if deactivate:
            alias.is_active = False


async def _enqueue_shop_identity_refresh(
    db: AsyncSession,
    *,
    shop_account: ShopAccount | None = None,
    shop_account_db_id: int | None = None,
    platform: str | None = None,
    changed_fields: list[str] | None = None,
) -> None:
    context = {
        "changed_fields": changed_fields or ["alias"],
    }
    if shop_account is not None:
        context.update(
            {
                "shop_account_id": shop_account.shop_account_id,
                "shop_account_db_id": shop_account.id,
                "platform": shop_account.platform,
            }
        )
    else:
        context.update(
            {
                "shop_account_db_id": shop_account_db_id,
                "platform": platform,
            }
        )
    try:
        await RefreshQueueService(db).enqueue_refresh(
            trigger_type="shop_identity_changed",
            pipeline_name="postgresql_dashboard",
            targets=_SHOP_IDENTITY_REFRESH_TARGETS,
            context=context,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[ShopIdentity] failed to enqueue dashboard refresh for alias change: %s",
            exc,
            exc_info=True,
        )
    try:
        await get_cache_service().invalidate_dashboard_business_overview()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[ShopIdentity] failed to invalidate business overview cache for alias change: %s",
            exc,
            exc_info=True,
        )


@router.get("", response_model=List[ShopAccountAliasResponse])
async def list_shop_account_aliases(db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(
        select(ShopAccountAlias).order_by(
            ShopAccountAlias.platform, ShopAccountAlias.alias_value
        )
    )
    return [_serialize_alias(record) for record in result.scalars().all()]


@router.post("", response_model=ShopAccountAliasResponse)
async def create_shop_account_alias(
    payload: ShopAccountAliasCreate,
    db: AsyncSession = Depends(get_async_db),
):
    alias_value = normalize_alias_text(payload.alias_value)
    if not alias_value:
        raise HTTPException(status_code=400, detail="alias_value is required")

    shop_account = await db.get(ShopAccount, payload.shop_account_id)
    if shop_account is None:
        raise HTTPException(
            status_code=404,
            detail=f"shop account id '{payload.shop_account_id}' not found",
        )
    shop_region = str(shop_account.shop_region or "").strip() or None
    alias_normalized = _normalize_alias(alias_value)

    # 友好预检：同平台 + 同别名 + 同区域只能有一条 active 别名（库层唯一约束的人话版）
    await assert_alias_available(
        db,
        platform=payload.platform,
        alias_normalized=alias_normalized,
        shop_region=shop_region,
        exclude_shop_account_db_id=shop_account.id,
    )

    record = ShopAccountAlias(
        shop_account_id=payload.shop_account_id,
        platform=payload.platform,
        alias_value=alias_value,
        alias_normalized=alias_normalized,
        alias_type=payload.alias_type,
        source=payload.source,
        shop_region=shop_region,
        is_primary=payload.is_primary,
        is_active=payload.is_active,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    await _enqueue_shop_identity_refresh(
        db,
        shop_account_db_id=payload.shop_account_id,
        platform=payload.platform,
        changed_fields=["alias"],
    )
    return _serialize_alias(record)


@router.post("/claim", response_model=ShopAccountAliasResponse)
async def claim_shop_account_alias(
    payload: ShopAccountAliasClaimRequest,
    db: AsyncSession = Depends(get_async_db),
):
    shop_account = await _get_shop_account_or_404(db, payload.shop_account_id)
    if shop_account.business_role == ShopAccountBusinessRole.collection_source:
        raise HTTPException(
            status_code=422,
            detail="collection_source shop accounts cannot claim aliases",
        )

    alias_value = normalize_alias_text(payload.alias_value)
    if not alias_value:
        raise HTTPException(status_code=400, detail="alias_value is required")
    alias_normalized = _normalize_alias(alias_value)
    shop_region = str(shop_account.shop_region or "").strip() or None

    current_primary_alias = (
        await db.execute(
            select(ShopAccountAlias).where(
                ShopAccountAlias.shop_account_id == shop_account.id,
                ShopAccountAlias.is_active.is_(True),
                ShopAccountAlias.is_primary.is_(True),
            )
        )
    ).scalar_one_or_none()
    if (
        current_primary_alias is not None
        and current_primary_alias.alias_normalized != alias_normalized
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                f"shop account id '{payload.shop_account_id}' already has an active primary alias "
                f"'{current_primary_alias.alias_value}'"
            ),
        )

    # 友好预检：同平台 + 同别名 + 同区域只能有一条 active 别名。
    # 放在任何写操作之前，避免「先降级主别名、再发现冲突」。
    await assert_alias_available(
        db,
        platform=payload.platform,
        alias_normalized=alias_normalized,
        shop_region=shop_region,
        exclude_shop_account_db_id=shop_account.id,
    )

    await _clear_primary_aliases(db, shop_account.id)
    existing = (
        (
            await db.execute(
                select(ShopAccountAlias).where(
                    ShopAccountAlias.shop_account_id == shop_account.id,
                    ShopAccountAlias.alias_normalized == alias_normalized,
                )
            )
        )
        .scalars()
        .first()
    )

    if existing is not None:
        existing.alias_value = alias_value
        existing.alias_type = "claimed"
        existing.source = payload.source
        existing.shop_region = shop_region
        existing.is_primary = True
        existing.is_active = True
        await db.commit()
        await db.refresh(existing)
        await _enqueue_shop_identity_refresh(
            db,
            shop_account=shop_account,
            changed_fields=["alias"],
        )
        return _serialize_alias(existing)

    record = ShopAccountAlias(
        shop_account_id=shop_account.id,
        platform=payload.platform,
        alias_value=alias_value,
        alias_normalized=alias_normalized,
        alias_type="claimed",
        source=payload.source,
        shop_region=shop_region,
        is_primary=True,
        is_active=True,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    await _enqueue_shop_identity_refresh(
        db,
        shop_account=shop_account,
        changed_fields=["alias"],
    )
    return _serialize_alias(record)


@router.delete("/primary/{shop_account_id}")
async def clear_shop_account_primary_alias(
    shop_account_id: str,
    db: AsyncSession = Depends(get_async_db),
):
    shop_account = await _get_shop_account_or_404(db, shop_account_id)
    await _clear_primary_aliases(db, shop_account.id, deactivate=True)
    await db.commit()
    await _enqueue_shop_identity_refresh(
        db,
        shop_account=shop_account,
        changed_fields=["alias"],
    )
    return {"message": f"primary alias cleared for '{shop_account_id}'"}


@router.get("/unmatched", response_model=UnmatchedShopAliasResponse)
async def get_unmatched_shop_aliases(
    db: AsyncSession = Depends(get_async_db),
):
    result = await db.execute(text(_UNMATCHED_ALIAS_QUERY), _UNMATCHED_ALIAS_PARAMS)
    occupancy_by_platform = await _load_platform_alias_occupancy(db)
    items = _build_unmatched_alias_items(result.mappings().all(), occupancy_by_platform)
    return UnmatchedShopAliasResponse(items=items, count=len(items))
