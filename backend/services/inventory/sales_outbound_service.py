from __future__ import annotations

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.services.inventory.layer_consumption_service import consume_layers_fifo


def build_sale_ledger_entry(
    platform_code: str,
    shop_id: str,
    platform_sku: str,
    qty_before: int,
    avg_cost_before: float,
    qty_out: int,
    order_id: str,
) -> dict:
    qty_after = qty_before - qty_out
    ext_value = qty_out * avg_cost_before
    return {
        "platform_code": platform_code,
        "shop_id": shop_id,
        "platform_sku": platform_sku,
        "movement_type": "sale",
        "qty_in": 0,
        "qty_out": int(qty_out),
        "qty_before": int(qty_before),
        "qty_after": int(qty_after),
        "avg_cost_before": float(avg_cost_before),
        "avg_cost_after": float(avg_cost_before),
        "unit_cost_wac": float(avg_cost_before),
        "ext_value": float(ext_value),
        "base_ext_value": float(ext_value),
        "link_order_id": str(order_id),
    }


class InventorySalesOutboundService:
    def __init__(self, db: Session):
        self.db = db

    def post_sale_and_consume_layers(
        self,
        platform_code: str,
        shop_id: str,
        platform_sku: str,
        qty_out: int,
        order_id: str,
        transaction_date: datetime,
        avg_cost_before: float,
        qty_before: int,
        created_by: str = "system",
    ) -> dict:
        entry = build_sale_ledger_entry(
            platform_code=platform_code,
            shop_id=shop_id,
            platform_sku=platform_sku,
            qty_before=qty_before,
            avg_cost_before=avg_cost_before,
            qty_out=qty_out,
            order_id=order_id,
        )

        ledger_row = self.db.execute(
            text(
                """
                INSERT INTO finance.inventory_ledger (
                    platform_code,
                    shop_id,
                    platform_sku,
                    transaction_date,
                    movement_type,
                    qty_in,
                    qty_out,
                    unit_cost_wac,
                    ext_value,
                    base_ext_value,
                    qty_before,
                    avg_cost_before,
                    qty_after,
                    avg_cost_after,
                    link_order_id,
                    created_by
                ) VALUES (
                    :platform_code,
                    :shop_id,
                    :platform_sku,
                    :transaction_date,
                    :movement_type,
                    :qty_in,
                    :qty_out,
                    :unit_cost_wac,
                    :ext_value,
                    :base_ext_value,
                    :qty_before,
                    :avg_cost_before,
                    :qty_after,
                    :avg_cost_after,
                    :link_order_id,
                    :created_by
                )
                RETURNING ledger_id
                """
            ),
            {
                **entry,
                "transaction_date": transaction_date.date(),
                "created_by": created_by,
            },
        ).fetchone()

        layer_rows = self.db.execute(
            text(
                """
                SELECT
                    layer_id,
                    remaining_qty,
                    GREATEST(DATE_PART('day', CURRENT_DATE - received_date), 0)::int AS age_days
                FROM finance.inventory_layers
                WHERE platform_code = :platform_code
                  AND shop_id = :shop_id
                  AND platform_sku = :platform_sku
                  AND remaining_qty > 0
                ORDER BY received_date ASC, layer_id ASC
                """
            ),
            {
                "platform_code": platform_code,
                "shop_id": shop_id,
                "platform_sku": platform_sku,
            },
        ).mappings().all()

        consumptions = consume_layers_fifo(layer_rows, qty_out)
        for item in consumptions:
            self.db.execute(
                text(
                    """
                    UPDATE finance.inventory_layers
                    SET remaining_qty = remaining_qty - :consumed_qty
                    WHERE layer_id = :layer_id
                    """
                ),
                item,
            )
            self.db.execute(
                text(
                    """
                    INSERT INTO finance.inventory_layer_consumptions (
                        outbound_ledger_id,
                        layer_id,
                        platform_code,
                        shop_id,
                        platform_sku,
                        consumed_qty,
                        consumed_at,
                        age_days_at_consumption
                    ) VALUES (
                        :outbound_ledger_id,
                        :layer_id,
                        :platform_code,
                        :shop_id,
                        :platform_sku,
                        :consumed_qty,
                        :consumed_at,
                        :age_days_at_consumption
                    )
                    """
                ),
                {
                    "outbound_ledger_id": int(ledger_row.ledger_id),
                    "layer_id": int(item["layer_id"]),
                    "platform_code": platform_code,
                    "shop_id": shop_id,
                    "platform_sku": platform_sku,
                    "consumed_qty": int(item["consumed_qty"]),
                    "consumed_at": transaction_date,
                    "age_days_at_consumption": int(item["age_days"]),
                },
            )

        return {
            "ledger_id": int(ledger_row.ledger_id),
            "consumption_rows": len(consumptions),
        }
