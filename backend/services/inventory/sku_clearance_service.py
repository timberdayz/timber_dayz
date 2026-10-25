"""SKU 级滞销排名服务。

口径（docs/superpowers/specs/2026-10-21-sku-level-clearance-ranking-design.md）：

- **主判据** = 「距上次进货天数」（`mart.inventory_state.days_since_restock`）：补货才重新开始计时
  不是 `estimated_stagnant_days`（只是最近两帧间隔，采集越密反而越小），
  也不是 DOS（动销速度；分母不随每次采集刷新，只作参考）。
- **数据源只有一个**：只读视图 `api.sku_clearance_ranking_module`。
  视图里出库龄 / 库存 / 动销 / ERP 关联 + 定价原料。
- **定价字段在这里补齐**，调 `backend/services/product_pricing_service.py` 的纯函数
  （`select_age_tier` / `compute_sku_pricing`）——SQL 里不重写定价公式，
  商品中心与滞销清单用的是同一份口径。

与既有 `get_clearance_ranking`（店铺级）不同：这里的每个筛选参数**真的进 WHERE 子句**。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.schemas.inventory import (
    SkuClearanceRankingItemResponse,
    SkuClearanceRankingResponse,
    SkuClearanceRankingSummaryResponse,
    SkuClearanceTierStat,
)
from backend.services.inventory.inventory_dos_service import compute_dos
from backend.services.product_pricing_service import compute_sku_pricing, select_restock_tier
from backend.services.sku_pricing_policy_service import (
    load_current_policies,
    to_policy_rows,
)
from modules.core.db import BridgeSpuSku, DimErpSku, DimPlatform, DimSpu

# 视图名：唯一的查询入口。测试会断言 SQL 里只出现它。
CLEARANCE_VIEW = "api.sku_clearance_ranking_module"

# 排序字段白名单：值是视图里的列名，**用户输入永远不直接拼进 SQL**。
SORTABLE_COLUMNS: dict[str, str] = {
    "days_since_restock": "days_since_restock",
    "inventory_value": "inventory_value",
    "current_qty": "current_qty",
}

_SELECT_COLUMNS = """
    snapshot_date,
    platform_code,
    product_sku,
    sku_key,
    product_name,
    current_qty,
    on_hand_qty,
    inventory_value,
    warehouse_count,
    days_since_restock,
    checklist_sales_90d,
    sold_units_30d,
    sku_id,
    default_purchase_cost,
    reference_selling_price,
    min_selling_price_override
"""


class SkuClearanceService:
    def __init__(self, db: AsyncSession | None):
        self.db = db

    # ------------------------------------------------------------------
    # 取数接缝
    # ------------------------------------------------------------------
    async def _fetch_rows(self, query: str, params: dict[str, Any]) -> list[dict]:
        """执行只读查询并返回字典列表。

        单独成一个方法是为了让单测可以拦下来断言 SQL 文本
        （与 test_business_overview_query_policy_gates.py 同一套门禁思路）。
        """
        if self.db is None:
            return []
        result = await self.db.execute(text(query), params)
        return [dict(row) for row in result.mappings().all()]

    # ------------------------------------------------------------------
    # 筛选
    # ------------------------------------------------------------------
    @staticmethod
    def _build_filters(
        *,
        min_restock_days: Optional[int],
        max_restock_days: Optional[int],
        platform_code: Optional[str],
        keyword: Optional[str],
    ) -> tuple[list[str], dict[str, Any]]:
        filters: list[str] = []
        params: dict[str, Any] = {}

        if min_restock_days is not None:
            filters.append("days_since_restock >= :min_restock_days")
            params["min_restock_days"] = int(min_restock_days)
        if max_restock_days is not None:
            filters.append("days_since_restock <= :max_restock_days")
            params["max_restock_days"] = int(max_restock_days)
        if platform_code:
            filters.append("platform_code = :platform_code")
            params["platform_code"] = str(platform_code)
        if keyword:
            filters.append("(product_sku ILIKE :keyword OR product_name ILIKE :keyword)")
            params["keyword"] = f"%{keyword}%"

        return filters, params

    @staticmethod
    def _where_clause(filters: list[str]) -> str:
        if not filters:
            return ""
        return "\nWHERE " + "\n  AND ".join(filters)

    # ------------------------------------------------------------------
    # 定价输入
    # ------------------------------------------------------------------
    async def _load_pricing_inputs(self, rows: list[dict]) -> dict[int, dict]:
        """按 sku_id 取定价还缺的原料：SKU 自己的达人佣金率 + SPU 绑定与两个 SPU 率。

        采购成本 / 参考售价 / 人工覆盖最低售价已经在视图里带出来了，不重复查。
        """
        if self.db is None or not rows:
            return {}

        sku_ids = sorted({int(row["sku_id"]) for row in rows if row.get("sku_id") is not None})
        if not sku_ids:
            return {}

        creator_rows = (
            await self.db.execute(
                select(DimErpSku.sku_id, DimErpSku.creator_commission_rate).where(
                    DimErpSku.sku_id.in_(sku_ids)
                )
            )
        ).all()
        creator_rates = {row.sku_id: row.creator_commission_rate for row in creator_rows}

        bindings = (
            await self.db.execute(
                select(BridgeSpuSku.sku_id, BridgeSpuSku.spu).where(
                    BridgeSpuSku.sku_id.in_(sku_ids),
                    BridgeSpuSku.binding_status == "active",
                    BridgeSpuSku.effective_to.is_(None),
                )
            )
        ).all()
        spu_by_sku = {row.sku_id: row.spu for row in bindings}

        spu_rates: dict[str, dict] = {}
        if spu_by_sku:
            spus = (
                await self.db.execute(
                    select(DimSpu).where(DimSpu.spu.in_(set(spu_by_sku.values())))
                )
            ).scalars().all()
            for spu in spus:
                spu_rates[spu.spu] = {
                    "return_loss_rate": spu.return_loss_rate,
                    "logistics_damage_rate": spu.logistics_damage_rate,
                }

        inputs: dict[int, dict] = {}
        for sku_id in sku_ids:
            rates = spu_rates.get(spu_by_sku.get(sku_id))
            inputs[sku_id] = {
                "creator_commission_rate": creator_rates.get(sku_id),
                "spu_bound": rates is not None,
                "spu_return_loss_rate": rates["return_loss_rate"] if rates else None,
                "spu_damage_rate": rates["logistics_damage_rate"] if rates else None,
            }
        return inputs

    async def _load_policy_rows(self) -> list[dict]:
        if self.db is None:
            return []
        return to_policy_rows(await load_current_policies(self.db))

    async def _load_platform(self, policy_rows: list[dict]) -> Optional[DimPlatform]:
        """平台成本率：按规则表的 platform_basis 取（与商品中心同一口径）。"""
        if self.db is None:
            return None
        basis = policy_rows[0]["platform_basis"] if policy_rows else "tiktok"
        return await self.db.get(DimPlatform, basis)

    # ------------------------------------------------------------------
    # 主方法
    # ------------------------------------------------------------------
    async def get_sku_clearance_ranking(
        self,
        *,
        min_restock_days: Optional[int] = 60,
        max_restock_days: Optional[int] = None,
        platform_code: Optional[str] = None,
        keyword: Optional[str] = None,
        sort_by: str = "days_since_restock",
        sort_order: str = "desc",
        limit: int = 100,
        offset: int = 0,
    ) -> SkuClearanceRankingResponse:
        column = SORTABLE_COLUMNS.get(str(sort_by or ""))
        if column is None:
            raise ValueError(
                f"unsupported sort_by: {sort_by!r} (allowed: {sorted(SORTABLE_COLUMNS)})"
            )
        direction = "ASC" if str(sort_order or "desc").lower() == "asc" else "DESC"

        filters, params = self._build_filters(
            min_restock_days=min_restock_days,
            max_restock_days=max_restock_days,
            platform_code=platform_code,
            keyword=keyword,
        )
        where_clause = self._where_clause(filters)

        rows = await self._fetch_rows(
            f"""
            SELECT
            {_SELECT_COLUMNS}
            FROM {CLEARANCE_VIEW}
            {where_clause}
            ORDER BY {column} {direction}, product_sku ASC
            LIMIT :limit OFFSET :offset
            """,
            {**params, "limit": int(limit), "offset": int(offset)},
        )

        pricing_inputs = await self._load_pricing_inputs(rows)
        policy_rows = await self._load_policy_rows()
        platform = await self._load_platform(policy_rows)
        deepest = max(policy_rows, key=lambda p: p["min_restock_days"]) if policy_rows else None
        # 汇总要按档位分组 → 必须先拿到档位表（policy_rows）
        summary = await self._build_summary(where_clause, params, policy_rows)

        items = [
            self._build_item(
                row,
                pricing_inputs=pricing_inputs,
                policy_rows=policy_rows,
                deepest_policy=deepest,
                platform=platform,
            )
            for row in rows
        ]

        return SkuClearanceRankingResponse(
            summary=summary,
            items=items,
            total=summary.sku_count,
            limit=int(limit),
            offset=int(offset),
        )

    async def _build_summary(
        self,
        where_clause: str,
        params: dict[str, Any],
        policy_rows: list[dict],
    ) -> SkuClearanceRankingSummaryResponse:
        """汇总是对**筛选后的全量**算的，不是只算当前页。"""
        total_rows = await self._fetch_rows(
            f"""
            SELECT
                count(*) AS sku_count,
                COALESCE(SUM(current_qty), 0) AS total_quantity,
                COALESCE(SUM(inventory_value), 0) AS total_inventory_value,
                count(*) FILTER (WHERE reference_selling_price IS NULL) AS missing_reference_price_count
            FROM {CLEARANCE_VIEW}
            {where_clause}
            """,
            dict(params),
        )
        base = total_rows[0] if total_rows else {}

        return SkuClearanceRankingSummaryResponse(
            sku_count=int(base.get("sku_count") or 0),
            total_quantity=int(base.get("total_quantity") or 0),
            total_inventory_value=float(base.get("total_inventory_value") or 0.0),
            restock_tiers=await self._build_restock_tiers(
                where_clause, params, policy_rows
            ),
            missing_reference_price_count=int(base.get("missing_reference_price_count") or 0),
        )

    async def _build_restock_tiers(
        self,
        where_clause: str,
        params: dict[str, Any],
        policy_rows: list[dict],
    ) -> list[SkuClearanceTierStat]:
        """按**档位表门槛**分组统计 SKU 数与压资金额。

        门槛一律走**参数绑定**：`tier_label` 是运营填的自由文本，
        拼进 SQL 就是注入。分组边界与
        `backend/services/product_pricing_service.py::select_restock_tier`
        完全一致（命中「门槛 ≤ 天数」里最大的那个门槛）。
        """
        ordered = sorted(
            (row for row in (policy_rows or []) if row is not None),
            key=lambda row: int(row["min_restock_days"]),
        )
        if not ordered:
            return []

        bounds = [int(row["min_restock_days"]) for row in ordered]
        case_sql = (
            "CASE "
            + " ".join(
                f"WHEN days_since_restock >= :bound_{index} THEN {index}"
                for index in range(len(bounds) - 1, 0, -1)
            )
            + " ELSE 0 END"
        )
        tier_params = {f"bound_{index}": value for index, value in enumerate(bounds)}
        rows = await self._fetch_rows(
            f"""
            SELECT
                {case_sql} AS tier_index,
                count(*) AS sku_count,
                COALESCE(SUM(inventory_value), 0) AS inventory_value
            FROM {CLEARANCE_VIEW}
            {where_clause}
            GROUP BY 1
            """,
            {**params, **tier_params},
        )
        buckets = {int(row.get("tier_index") or 0): row for row in rows}

        stats: list[SkuClearanceTierStat] = []
        for index, policy in enumerate(ordered):
            bucket = buckets.get(index, {})
            stats.append(
                SkuClearanceTierStat(
                    min_restock_days=bounds[index],
                    tier_label=str(
                        policy.get("tier_label") or f"≥{bounds[index]}天"
                    ),
                    sku_count=int(bucket.get("sku_count") or 0),
                    inventory_value=float(bucket.get("inventory_value") or 0.0),
                )
            )
        return stats

    @staticmethod
    def _build_item(
        row: dict,
        *,
        pricing_inputs: dict[int, dict],
        policy_rows: list[dict],
        deepest_policy: Optional[dict],
        platform: Optional[DimPlatform],
    ) -> SkuClearanceRankingItemResponse:
        sku_id = row.get("sku_id")
        days_since_restock = row.get("days_since_restock")
        days_since_restock = (
            int(days_since_restock) if days_since_restock is not None else None
        )

        # 未匹配 ERP 主数据的 SKU：定价字段整体留空（spec §3.6）。
        # 这类 SKU 在视图里 LEFT JOIN 出来的采购成本/参考售价本来就是 NULL，
        # 硬算也只会得到一个「看起来能定价、其实没主数据支撑」的数字。
        pricing_matched = sku_id is not None

        if pricing_matched:
            policy = select_restock_tier(policy_rows, days_since_restock)
            inputs = pricing_inputs.get(int(sku_id), {})
            pricing = compute_sku_pricing(
                purchase_cost=row.get("default_purchase_cost"),
                reference_selling_price=row.get("reference_selling_price"),
                creator_commission_rate=inputs.get("creator_commission_rate"),
                platform_creator_commission_rate=(
                    platform.default_creator_commission_rate if platform else None
                ),
                other_cost_rate=platform.other_cost_rate if platform else None,
                spu_bound=bool(inputs.get("spu_bound")),
                spu_return_loss_rate=inputs.get("spu_return_loss_rate"),
                spu_damage_rate=inputs.get("spu_damage_rate"),
                policy=policy,
                deepest_policy=deepest_policy,
                min_selling_price_override=row.get("min_selling_price_override"),
                days_since_restock=days_since_restock,
            )
            target_margin_rate = float(policy["target_margin_rate"]) if policy else None
        else:
            pricing = {
                "pricing_tier_label": None,
                "current_discount_rate": None,
                "clearance_max_discount_rate": None,
                "min_selling_price": None,
                "min_selling_price_source": "unavailable",
            }
            target_margin_rate = None

        # DOS 参考值：**走 inventory_dos_service 的唯一实现**，与业务概览同一口径。
        # 只作展示参考，不参与任何判定 —— 分母（近 90 天销量）在增量模式下不新鲜。
        dos_days = compute_dos(
            available_stock=row.get("current_qty"),
            window_sales=row.get("checklist_sales_90d"),
            window_days=90,
        )

        recovery_amount = _compute_clearance_recovery_amount(
            reference_selling_price=row.get("reference_selling_price"),
            discount_rate=pricing.get("current_discount_rate"),
            current_qty=row.get("current_qty"),
        )

        return SkuClearanceRankingItemResponse(
            snapshot_date=row.get("snapshot_date"),
            platform_code=str(row.get("platform_code") or ""),
            product_sku=str(row.get("product_sku") or ""),
            sku_key=row.get("sku_key"),
            product_name=row.get("product_name"),
            current_qty=int(row.get("current_qty") or 0),
            on_hand_qty=int(row.get("on_hand_qty") or 0),
            inventory_value=float(row.get("inventory_value") or 0.0),
            warehouse_count=int(row.get("warehouse_count") or 0),
            days_since_restock=days_since_restock,
            checklist_dos_sales90=(
                float(dos_days) if dos_days is not None else None
            ),
            sku_id=int(sku_id) if sku_id is not None else None,
            default_purchase_cost=(
                float(row["default_purchase_cost"])
                if row.get("default_purchase_cost") is not None
                else None
            ),
            reference_selling_price=(
                float(row["reference_selling_price"])
                if row.get("reference_selling_price") is not None
                else None
            ),
            min_selling_price_override=(
                float(row["min_selling_price_override"])
                if row.get("min_selling_price_override") is not None
                else None
            ),
            pricing_tier_label=pricing.get("pricing_tier_label"),
            current_discount_rate=pricing.get("current_discount_rate"),
            current_target_margin_rate=target_margin_rate,
            clearance_max_discount_rate=pricing.get("clearance_max_discount_rate"),
            min_selling_price=pricing.get("min_selling_price"),
            min_selling_price_source=pricing.get("min_selling_price_source"),
            clearance_recovery_amount=recovery_amount,
            pricing_matched_erp=pricing_matched,
        )


def _compute_clearance_recovery_amount(
    *,
    reference_selling_price: Any,
    discount_rate: Any,
    current_qty: Any,
) -> Optional[float]:
    """按当前档折扣率能收回的现金上限。

    参考售价缺失时返回 None（**不是 0**）——0 会被前端当成「能收回 0 元」，
    实际含义是「算不出来」。这个缺口由 summary.missing_reference_price_count 暴露。
    """
    if reference_selling_price is None or discount_rate is None:
        return None
    try:
        price = Decimal(str(reference_selling_price))
        rate = Decimal(str(discount_rate))
        qty = Decimal(str(current_qty or 0))
    except Exception:  # noqa: BLE001
        return None
    return float((price * (Decimal("1") - rate) * qty).quantize(Decimal("0.01")))
