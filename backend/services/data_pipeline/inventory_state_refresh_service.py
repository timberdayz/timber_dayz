"""库存状态层刷新服务 —— 「双闸判定」的落点。

背景
----
妙手库存清单的行级「更新时间」**不能**直接当变更信号：

- 误报：实测 file 2764 有 535 行（43.7%）的更新时间被一次 bulk UPDATE
  批量覆盖成 ``2026-05-08 10:36:36~39``，而那些行的库存和销量**完全没变**
- 不完整：两批 1109 共同行中有 93 行（8.4%）库存数量没变、销量却变了
  → 妙手在非库存变动（批量编辑 / 改价 / 盘点）时也会写行

所以采集与落盘必须走「双闸」：

- **闸 1（妙手侧）**：用「更新时间」维度 + 区间筛选，**只决定这次导出哪些行**
- **闸 2（我方侧）**：与上一批比对库存数量，**决定这一行算不算真的变了**

只有闸 2 判定为**进货**（库存总量增加），才推进 ``stock_added_at``（距上次进货天数的分子）；
库存减少（销售）不动 —— 因为经营模式是「卖完不补货」，补货才是新的开始。
否则只推进 ``row_seen_at``（本行最近一次被采集看到的时间）。

本服务沿用 ``inventory_age_refresh_service`` 的既有模式：
ingest 之后独立运行，不侵入采集流程；纯函数判定可写无 DB 单测。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.data_pipeline.refresh_runner import (
    execute_refresh_plan,
    execute_sql_target,
)
from backend.services.data_pipeline.refresh_registry import topologically_sort_targets

INVENTORY_STATE_UPSTREAM_TARGETS = [
    "semantic.fact_inventory_snapshot",
    "mart.inventory_snapshot_history",
]

INVENTORY_STATE_RUNTIME_TARGETS = [
    "mart.inventory_state",
]

INVENTORY_STATE_TARGETS = (
    INVENTORY_STATE_UPSTREAM_TARGETS + INVENTORY_STATE_RUNTIME_TARGETS
)

# 闸 2 判定「进货」的字段：**库存总量**。
# 不用可用库存——订单占用/取消订单只动可用库存不动总量，会被误判成进货。
RESTOCK_SIGNAL_FIELD = "on_hand_stock"

# 变更原因
CHANGE_REASON_FIRST = "first_observation"
CHANGE_REASON_RESTOCKED = "restocked"
CHANGE_REASON_UNCHANGED = "unchanged"


def _num(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def resolve_state_transition(*, previous: Optional[dict], incoming: dict) -> dict:
    """闸 2 判定：**只有库存总量增加（进货）才重置计时器**。

    返回 ``{"stock_changed": bool, "change_reason": str, "stock_added_at": datetime | None}``。

    - 首次观测（状态层还没有这一行）：初值 = ``created_at``（首次铺货 ≈ 首次进货）
    - 库存总量增加（进货）：推进到本次的行级时间戳（妙手刚写过，可信）
    - 库存总量减少（销售）或不变（订单占用/取消）：**保留上一次的值**
    """
    observed_at = incoming.get("observed_at")
    base_at = observed_at or incoming.get("ingest_timestamp")
    created_at = incoming.get("created_at")

    if previous is None:
        return {
            "stock_changed": True,
            "change_reason": CHANGE_REASON_FIRST,
            "stock_added_at": created_at or base_at,
        }

    previous_added = previous.get("stock_added_at") or previous.get("created_at")
    incoming_total = _num(incoming.get(RESTOCK_SIGNAL_FIELD))
    previous_total = _num(previous.get(RESTOCK_SIGNAL_FIELD))
    restocked = (
        incoming_total is not None
        and previous_total is not None
        and incoming_total > previous_total
    )
    if not restocked:
        return {
            "stock_changed": False,
            "change_reason": CHANGE_REASON_UNCHANGED,
            "stock_added_at": previous_added,
        }
    return {
        "stock_changed": True,
        "change_reason": CHANGE_REASON_RESTOCKED,
        "stock_added_at": base_at or previous_added,
    }


def pick_latest_per_key(rows: list[dict]) -> dict[tuple, dict]:
    """同一个 SKU×仓 在本次里可能有多行（多批次），取**最近一次被采集看到**的那行。

    排序键是 ``ingest_timestamp``（我们什么时候看到的），**不是** ``observed_at``。
    原因：妙手的「更新时间」可能被批量操作污染（实测 file 2764 有 535 行被一次
    bulk UPDATE 覆盖成同一时刻，导致它比更早采集的批次还「新」——时间倒流）。
    按 observed_at 取最大值会选中被污染的旧批次行。

    状态层的语义是「当前状态」→ 取最新一次观察，而不是「时间戳最大的那次」。
    """
    latest: dict[tuple, dict] = {}
    for row in rows:
        key = (
            row.get("platform_code"),
            row.get("sku_key"),
            row.get("warehouse_name") or "",
        )
        current = latest.get(key)
        if current is None:
            latest[key] = row
            continue
        if _sort_key(row) > _sort_key(current):
            latest[key] = row
    return latest


def _sort_key(row: dict) -> tuple:
    ingested = row.get("ingest_timestamp")
    observed = row.get("observed_at")
    return (
        ingested.isoformat() if isinstance(ingested, datetime) else "",
        observed.isoformat() if isinstance(observed, datetime) else "",
    )


class InventoryStateRefreshService:
    """把语义层的行级事实收敛成「每 SKU×仓 一行」的状态层。"""

    def __init__(self, db: AsyncSession | None):
        self.db = db

    def build_refresh_targets(self) -> list[str]:
        return topologically_sort_targets(INVENTORY_STATE_TARGETS)

    async def ensure_runtime_assets(self) -> None:
        if self.db is None:
            raise ValueError("AsyncSession is required for refresh execution")
        for target in INVENTORY_STATE_RUNTIME_TARGETS:
            await execute_sql_target(
                self.db,
                target,
                pipeline_name="inventory_state_runtime_assets",
                trigger_source="manual",
                context={"feature": "inventory_restock_days_state"},
            )

    async def get_watermarks(self) -> dict[str, datetime]:
        """每个平台的水位线 = 该平台状态层里最近一次「被采集看到」的时间。"""
        if self.db is None:
            raise ValueError("AsyncSession is required for refresh execution")
        result = await self.db.execute(
            text(
                """
                SELECT platform_code, MAX(row_seen_at) AS watermark
                FROM mart.inventory_state
                GROUP BY platform_code
                """
            )
        )
        return {
            row["platform_code"]: row["watermark"]
            for row in result.mappings().all()
            if row.get("watermark") is not None
        }

    async def load_incoming_rows(self, watermarks: dict[str, datetime]) -> list[dict]:
        """取水位线之后的行（闸 1 的结果已经在语义层筛过了）。"""
        if self.db is None:
            raise ValueError("AsyncSession is required for refresh execution")
        result = await self.db.execute(
            text(
                """
                SELECT *
                FROM (
                    SELECT
                        platform_code,
                        COALESCE(
                            NULLIF(BTRIM(platform_sku), ''),
                            NULLIF(BTRIM(product_sku), ''),
                            NULLIF(BTRIM(sku_id), ''),
                            NULLIF(BTRIM(product_id), '')
                        ) AS sku_key,
                        NULLIF(BTRIM(platform_sku), '') AS platform_sku,
                        NULLIF(BTRIM(product_sku), '') AS product_sku,
                        NULLIF(BTRIM(sku_id), '') AS sku_id,
                        NULLIF(BTRIM(product_id), '') AS product_id,
                        NULLIF(BTRIM(product_name), '') AS product_name,
                        NULLIF(BTRIM(warehouse_name), '') AS warehouse_name,
                        COALESCE(available_stock, 0) AS available_stock,
                        COALESCE(on_hand_stock, 0) AS on_hand_stock,
                        COALESCE(reserved_stock, 0) AS reserved_stock,
                        COALESCE(inventory_value, 0) AS inventory_value,
                        COALESCE(unit_cost, 0) AS unit_cost,
                        checklist_sales_7d,
                        checklist_sales_30d,
                        checklist_sales_60d,
                        checklist_sales_90d,
                        observed_at,
                        created_at,
                        metric_date,
                        file_id AS source_file_id,
                        ingest_timestamp
                    FROM semantic.fact_inventory_snapshot
                ) AS source_rows
                WHERE source_rows.sku_key IS NOT NULL
                """
            )
        )
        rows = [dict(row) for row in result.mappings().all()]
        return [row for row in rows if self._is_new(row, watermarks)]

    @staticmethod
    def _is_new(row: dict, watermarks: dict[str, datetime]) -> bool:
        platform = row.get("platform_code")
        watermark = watermarks.get(platform)
        ingested = row.get("ingest_timestamp")
        if watermark is None or ingested is None:
            return True
        return ingested > watermark

    async def load_existing_state(self) -> dict[tuple, dict]:
        """载入现有状态层（表规模与 SKU×仓 行数同阶，整表读最简单也最不容易写错）。"""
        if self.db is None:
            raise ValueError("AsyncSession is required for refresh execution")
        result = await self.db.execute(
            text(
                """
                SELECT platform_code, sku_key, warehouse_name,
                       available_stock, on_hand_stock, reserved_stock,
                       stock_added_at, created_at, row_seen_at, row_written_at
                FROM mart.inventory_state
                """
            )
        )
        return {
            (row["platform_code"], row["sku_key"], row["warehouse_name"]): dict(row)
            for row in result.mappings().all()
        }

    @staticmethod
    def build_state_row(incoming: dict, transition: dict) -> dict:
        """把一行 + 闸 2 判定结果拼成状态层的一行。"""
        return {
            "platform_code": incoming["platform_code"],
            "sku_key": incoming["sku_key"],
            "warehouse_name": incoming.get("warehouse_name") or "",
            "platform_sku": incoming.get("platform_sku"),
            "product_sku": incoming.get("product_sku"),
            "sku_id": incoming.get("sku_id"),
            "product_id": incoming.get("product_id"),
            "product_name": incoming.get("product_name"),
            "available_stock": incoming.get("available_stock"),
            "on_hand_stock": incoming.get("on_hand_stock"),
            "reserved_stock": incoming.get("reserved_stock"),
            "inventory_value": incoming.get("inventory_value"),
            "unit_cost": incoming.get("unit_cost"),
            "checklist_sales_7d": incoming.get("checklist_sales_7d"),
            "checklist_sales_30d": incoming.get("checklist_sales_30d"),
            "checklist_sales_60d": incoming.get("checklist_sales_60d"),
            "checklist_sales_90d": incoming.get("checklist_sales_90d"),
            "stock_added_at": transition["stock_added_at"],
            "created_at": incoming.get("created_at"),
            "row_seen_at": incoming.get("ingest_timestamp"),
            "row_written_at": incoming.get("observed_at"),
            "last_metric_date": incoming.get("metric_date"),
            "source_file_id": incoming.get("source_file_id"),
        }

    async def persist_rows(self, rows: list[dict]) -> None:
        """upsert 状态层。"""
        if self.db is None:
            raise ValueError("AsyncSession is required for refresh execution")
        if not rows:
            return
        await self.db.execute(
            text(
                """
                INSERT INTO mart.inventory_state (
                    platform_code, sku_key, warehouse_name,
                    platform_sku, product_sku, sku_id, product_id, product_name,
                    available_stock, on_hand_stock, reserved_stock,
                    inventory_value, unit_cost,
                    checklist_sales_7d, checklist_sales_30d,
                    checklist_sales_60d, checklist_sales_90d,
                    stock_added_at, created_at, row_seen_at, row_written_at,
                    last_metric_date, source_file_id, updated_at
                ) VALUES (
                    :platform_code, :sku_key, :warehouse_name,
                    :platform_sku, :product_sku, :sku_id, :product_id, :product_name,
                    :available_stock, :on_hand_stock, :reserved_stock,
                    :inventory_value, :unit_cost,
                    :checklist_sales_7d, :checklist_sales_30d,
                    :checklist_sales_60d, :checklist_sales_90d,
                    :stock_added_at, :created_at, :row_seen_at, :row_written_at,
                    :last_metric_date, :source_file_id, NOW()
                )
                ON CONFLICT (platform_code, sku_key, warehouse_name)
                DO UPDATE SET
                    platform_sku = EXCLUDED.platform_sku,
                    product_sku = EXCLUDED.product_sku,
                    sku_id = EXCLUDED.sku_id,
                    product_id = EXCLUDED.product_id,
                    product_name = EXCLUDED.product_name,
                    available_stock = EXCLUDED.available_stock,
                    on_hand_stock = EXCLUDED.on_hand_stock,
                    reserved_stock = EXCLUDED.reserved_stock,
                    inventory_value = EXCLUDED.inventory_value,
                    unit_cost = EXCLUDED.unit_cost,
                    checklist_sales_7d = EXCLUDED.checklist_sales_7d,
                    checklist_sales_30d = EXCLUDED.checklist_sales_30d,
                    checklist_sales_60d = EXCLUDED.checklist_sales_60d,
                    checklist_sales_90d = EXCLUDED.checklist_sales_90d,
                    stock_added_at = EXCLUDED.stock_added_at,
                    created_at = EXCLUDED.created_at,
                    row_seen_at = EXCLUDED.row_seen_at,
                    row_written_at = EXCLUDED.row_written_at,
                    last_metric_date = EXCLUDED.last_metric_date,
                    source_file_id = EXCLUDED.source_file_id,
                    updated_at = NOW()
                """
            ),
            rows,
        )

    async def refresh(self, force_full: bool = False) -> dict:
        """主流程：上游刷新 → 闸 1 的结果 → 闸 2 判定 → upsert 状态层。

        上游（语义层 + 快照族）**自己先刷一遍**：这样本服务单独调用也站得住，
        不依赖调用方恰好已经刷过上游（与库存库龄刷新服务同款写法）。
        """
        if self.db is None:
            raise ValueError("AsyncSession is required for refresh execution")
        await execute_refresh_plan(
            self.db,
            targets=INVENTORY_STATE_UPSTREAM_TARGETS,
            pipeline_name="inventory_state_upstream_refresh",
            trigger_source="manual",
            context={"feature": "inventory_restock_days_state"},
        )
        await self.ensure_runtime_assets()
        watermarks = {} if force_full else await self.get_watermarks()
        incoming_rows = await self.load_incoming_rows(watermarks)
        latest = pick_latest_per_key(incoming_rows)
        existing = await self.load_existing_state()

        state_rows: list[dict] = []
        changed_count = 0
        for key, incoming in latest.items():
            transition = resolve_state_transition(
                previous=existing.get(key), incoming=incoming
            )
            if transition["stock_changed"]:
                changed_count += 1
            state_rows.append(self.build_state_row(incoming, transition))

        await self.persist_rows(state_rows)
        return {
            "incoming_row_count": len(incoming_rows),
            "state_key_count": len(latest),
            "stock_changed_count": changed_count,
        }
