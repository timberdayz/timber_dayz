from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.data_pipeline.refresh_runner import (
    execute_refresh_plan,
    execute_sql_target,
)
from backend.services.data_pipeline.refresh_registry import topologically_sort_targets

SNAPSHOT_INVENTORY_AGE_UPSTREAM_TARGETS = [
    "semantic.fact_inventory_snapshot",
    "mart.inventory_snapshot_history",
    "mart.inventory_snapshot_latest",
    "mart.inventory_snapshot_change",
    "mart.inventory_snapshot_company_daily",
]

SNAPSHOT_INVENTORY_AGE_RUNTIME_TARGETS = [
    "mart.inventory_age_history",
    "mart.inventory_age_current",
    "api.inventory_age_list_module",
    "api.inventory_age_summary_module",
]

SNAPSHOT_INVENTORY_AGE_TARGETS = (
    SNAPSHOT_INVENTORY_AGE_UPSTREAM_TARGETS + SNAPSHOT_INVENTORY_AGE_RUNTIME_TARGETS
)


def compute_age_transition(
    previous_qty: Optional[int],
    current_qty: int,
    snapshot_date: date,
    previous_anchor_date: Optional[date] = None,
) -> dict:
    if current_qty <= 0:
        return {
            "is_active": False,
            "age_anchor_date": None,
            "age_days": None,
            "reset_reason": "zero_stock",
        }

    if previous_qty is None:
        return {
            "is_active": True,
            "age_anchor_date": snapshot_date,
            "age_days": 0,
            "reset_reason": "first_positive",
        }

    if previous_qty <= 0:
        return {
            "is_active": True,
            "age_anchor_date": snapshot_date,
            "age_days": 0,
            "reset_reason": "reappeared_after_zero",
        }

    if current_qty > previous_qty:
        return {
            "is_active": True,
            "age_anchor_date": snapshot_date,
            "age_days": 0,
            "reset_reason": "stock_increase",
        }

    anchor_date = previous_anchor_date or snapshot_date
    return {
        "is_active": True,
        "age_anchor_date": anchor_date,
            "age_days": max((snapshot_date - anchor_date).days, 0),
            "reset_reason": "continued",
        }


def replay_snapshot_rows(rows: list[dict]) -> tuple[list[dict], dict | None]:
    ordered_rows = sorted(
        rows,
        key=lambda row: (
            row["snapshot_date"],
            row.get("last_ingest_timestamp") or "",
        ),
    )

    history_rows: list[dict] = []
    previous_qty: Optional[int] = None
    previous_anchor_date: Optional[date] = None

    for row in ordered_rows:
        current_qty = int(row.get("available_qty", 0) or 0)
        transition = compute_age_transition(
            previous_qty=previous_qty,
            current_qty=current_qty,
            snapshot_date=row["snapshot_date"],
            previous_anchor_date=previous_anchor_date,
        )
        age_days = transition["age_days"]
        bucket = bucket_age_days(age_days) if age_days is not None else None
        history_row = {
            "snapshot_date": row["snapshot_date"],
            "platform_code": row["platform_code"],
            "sku_key": row["sku_key"],
            "platform_sku": row.get("platform_sku"),
            "product_sku": row.get("product_sku"),
            "sku_id": row.get("sku_id"),
            "product_id": row.get("product_id"),
            "product_name": row.get("product_name"),
            "current_qty": current_qty,
            "previous_qty": previous_qty,
            "qty_delta": (
                current_qty - previous_qty if previous_qty is not None else current_qty
            ),
            "age_anchor_date": transition["age_anchor_date"],
            "age_days": age_days,
            "bucket": bucket,
            "reset_reason": transition["reset_reason"],
            "on_hand_qty": int(row.get("on_hand_qty", 0) or 0),
            "inventory_value": float(row.get("inventory_value", 0.0) or 0.0),
            "warehouse_count": int(row.get("warehouse_count", 0) or 0),
            "last_ingest_timestamp": row.get("last_ingest_timestamp"),
        }
        history_rows.append(history_row)

        previous_qty = current_qty
        previous_anchor_date = transition["age_anchor_date"]

    current_row = None
    if history_rows and history_rows[-1]["current_qty"] > 0:
        current_row = dict(history_rows[-1])

    return history_rows, current_row


def bucket_age_days(age_days: int) -> str:
    if age_days <= 30:
        return "0-30"
    if age_days <= 60:
        return "31-60"
    if age_days <= 90:
        return "61-90"
    if age_days <= 180:
        return "91-180"
    return "180+"


class InventoryAgeRefreshService:
    def __init__(self, db: AsyncSession | None):
        self.db = db

    def build_refresh_targets(self) -> list[str]:
        return topologically_sort_targets(SNAPSHOT_INVENTORY_AGE_TARGETS)

    async def ensure_runtime_assets(self) -> None:
        if self.db is None:
            raise ValueError("AsyncSession is required for refresh execution")

        for target in SNAPSHOT_INVENTORY_AGE_RUNTIME_TARGETS:
            await execute_sql_target(
                self.db,
                target,
                pipeline_name="inventory_age_runtime_assets",
                trigger_source="manual",
                context={"feature": "snapshot_continuous_inventory_aging"},
            )

    async def get_changed_keys(self) -> list[dict]:
        if self.db is None:
            raise ValueError("AsyncSession is required for refresh execution")

        watermark_result = await self.db.execute(
            text("SELECT MAX(last_ingest_timestamp) FROM mart.inventory_age_history")
        )
        watermark = watermark_result.scalar_one_or_none()

        if watermark is None:
            result = await self.db.execute(
                text(
                    """
                    SELECT
                        platform_code,
                        sku_key,
                        MIN(snapshot_date) AS earliest_snapshot_date
                    FROM mart.inventory_snapshot_company_daily
                    GROUP BY platform_code, sku_key
                    ORDER BY platform_code ASC, sku_key ASC
                    """
                )
            )
            return [dict(row) for row in result.mappings().all()]

        result = await self.db.execute(
            text(
                """
                SELECT
                    platform_code,
                    sku_key,
                    MIN(snapshot_date) AS earliest_snapshot_date
                FROM mart.inventory_snapshot_company_daily
                WHERE last_ingest_timestamp > :watermark
                GROUP BY platform_code, sku_key
                ORDER BY platform_code ASC, sku_key ASC
                """
            ),
            {"watermark": watermark},
        )
        return [dict(row) for row in result.mappings().all()]

    async def get_all_keys(self) -> list[dict]:
        if self.db is None:
            raise ValueError("AsyncSession is required for refresh execution")

        result = await self.db.execute(
            text(
                """
                SELECT
                    platform_code,
                    sku_key,
                    MIN(snapshot_date) AS earliest_snapshot_date
                FROM mart.inventory_snapshot_company_daily
                GROUP BY platform_code, sku_key
                ORDER BY platform_code ASC, sku_key ASC
                """
            )
        )
        return [dict(row) for row in result.mappings().all()]

    async def load_snapshot_rows_for_key(
        self,
        platform_code: str,
        sku_key: str,
    ) -> list[dict]:
        if self.db is None:
            raise ValueError("AsyncSession is required for refresh execution")

        result = await self.db.execute(
            text(
                """
                SELECT
                    snapshot_date,
                    platform_code,
                    sku_key,
                    platform_sku,
                    product_sku,
                    sku_id,
                    product_id,
                    product_name,
                    available_qty,
                    on_hand_qty,
                    inventory_value,
                    warehouse_count,
                    last_ingest_timestamp
                FROM mart.inventory_snapshot_company_daily
                WHERE platform_code = :platform_code
                  AND sku_key = :sku_key
                ORDER BY snapshot_date ASC, last_ingest_timestamp ASC
                """
            ),
            {
                "platform_code": platform_code,
                "sku_key": sku_key,
            },
        )
        return [dict(row) for row in result.mappings().all()]

    async def persist_replay_rows(
        self,
        platform_code: str,
        sku_key: str,
        history_rows: list[dict],
        current_row: dict | None,
    ) -> None:
        if self.db is None:
            raise ValueError("AsyncSession is required for refresh execution")

        await self.db.execute(
            text(
                """
                DELETE FROM mart.inventory_age_history
                WHERE platform_code = :platform_code
                  AND sku_key = :sku_key
                """
            ),
            {"platform_code": platform_code, "sku_key": sku_key},
        )
        await self.db.execute(
            text(
                """
                DELETE FROM mart.inventory_age_current
                WHERE platform_code = :platform_code
                  AND sku_key = :sku_key
                """
            ),
            {"platform_code": platform_code, "sku_key": sku_key},
        )

        if history_rows:
            await self.db.execute(
                text(
                    """
                    INSERT INTO mart.inventory_age_history (
                        snapshot_date,
                        platform_code,
                        sku_key,
                        platform_sku,
                        product_sku,
                        sku_id,
                        product_id,
                        product_name,
                        current_qty,
                        previous_qty,
                        qty_delta,
                        age_anchor_date,
                        age_days,
                        bucket,
                        reset_reason,
                        on_hand_qty,
                        inventory_value,
                        warehouse_count,
                        last_ingest_timestamp
                    ) VALUES (
                        :snapshot_date,
                        :platform_code,
                        :sku_key,
                        :platform_sku,
                        :product_sku,
                        :sku_id,
                        :product_id,
                        :product_name,
                        :current_qty,
                        :previous_qty,
                        :qty_delta,
                        :age_anchor_date,
                        :age_days,
                        :bucket,
                        :reset_reason,
                        :on_hand_qty,
                        :inventory_value,
                        :warehouse_count,
                        :last_ingest_timestamp
                    )
                    """
                ),
                history_rows,
            )

        if current_row is not None:
            await self.db.execute(
                text(
                    """
                    INSERT INTO mart.inventory_age_current (
                        platform_code,
                        sku_key,
                        snapshot_date,
                        platform_sku,
                        product_sku,
                        sku_id,
                        product_id,
                        product_name,
                        current_qty,
                        previous_qty,
                        qty_delta,
                        age_anchor_date,
                        age_days,
                        bucket,
                        reset_reason,
                        on_hand_qty,
                        inventory_value,
                        warehouse_count,
                        last_ingest_timestamp
                    ) VALUES (
                        :platform_code,
                        :sku_key,
                        :snapshot_date,
                        :platform_sku,
                        :product_sku,
                        :sku_id,
                        :product_id,
                        :product_name,
                        :current_qty,
                        :previous_qty,
                        :qty_delta,
                        :age_anchor_date,
                        :age_days,
                        :bucket,
                        :reset_reason,
                        :on_hand_qty,
                        :inventory_value,
                        :warehouse_count,
                        :last_ingest_timestamp
                    )
                    """
                ),
                current_row,
            )

    async def refresh(self, force_full: bool = False) -> dict:
        if self.db is None:
            raise ValueError("AsyncSession is required for refresh execution")

        upstream_run_id = await execute_refresh_plan(
            self.db,
            targets=SNAPSHOT_INVENTORY_AGE_UPSTREAM_TARGETS,
            pipeline_name="inventory_age_upstream_refresh",
            trigger_source="manual",
            context={"feature": "snapshot_continuous_inventory_aging"},
        )
        await self.ensure_runtime_assets()

        changed_keys = (
            await self.get_all_keys() if force_full else await self.get_changed_keys()
        )

        if force_full:
            await self.db.execute(text("TRUNCATE TABLE mart.inventory_age_current"))
            await self.db.execute(text("TRUNCATE TABLE mart.inventory_age_history"))

        replayed_key_count = 0
        for item in changed_keys:
            platform_code = item["platform_code"]
            sku_key = item["sku_key"]
            snapshot_rows = await self.load_snapshot_rows_for_key(platform_code, sku_key)
            history_rows, current_row = replay_snapshot_rows(snapshot_rows)
            await self.persist_replay_rows(
                platform_code=platform_code,
                sku_key=sku_key,
                history_rows=history_rows,
                current_row=current_row,
            )
            replayed_key_count += 1

        return {
            "upstream_run_id": upstream_run_id,
            "mode": "full" if force_full else "incremental",
            "replayed_key_count": replayed_key_count,
        }
