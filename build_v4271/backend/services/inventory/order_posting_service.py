from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.services.inventory.sales_outbound_service import (
    InventorySalesOutboundService,
)


def should_post_pending_order(order_row: dict[str, Any]) -> bool:
    if order_row.get("inventory_deducted"):
        return False
    if not order_row.get("sku"):
        return False
    qty = int(order_row.get("qty") or 0)
    if qty <= 0:
        return False
    status = str(order_row.get("status") or "").strip().lower()
    if status in {"cancelled", "canceled", "取消", "已取消"}:
        return False
    return True


class InventoryOrderPostingService:
    def __init__(self, db: Session):
        self.db = db
        self.sales_outbound_service = InventorySalesOutboundService(db)

    def post_pending_orders(self, limit: int = 500) -> dict[str, int]:
        rows = self.db.execute(
            text(
                """
                SELECT
                    id,
                    platform_code,
                    shop_id,
                    order_id,
                    sku,
                    qty,
                    order_ts,
                    status,
                    inventory_deducted
                FROM fact_sales_orders
                WHERE COALESCE(inventory_deducted, FALSE) = FALSE
                ORDER BY order_ts ASC NULLS LAST, id ASC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        ).mappings().all()

        posted = 0
        skipped = 0

        for row in rows:
            order_row = dict(row)
            if not should_post_pending_order(order_row):
                skipped += 1
                continue

            existing_ledger = self.db.execute(
                text(
                    """
                    SELECT ledger_id
                    FROM finance.inventory_ledger
                    WHERE platform_code = :platform_code
                      AND shop_id = :shop_id
                      AND platform_sku = :platform_sku
                      AND link_order_id = :order_id
                    LIMIT 1
                    """
                ),
                {
                    "platform_code": order_row["platform_code"],
                    "shop_id": order_row["shop_id"],
                    "platform_sku": order_row["sku"],
                    "order_id": str(order_row["order_id"]),
                },
            ).fetchone()

            if existing_ledger:
                self.db.execute(
                    text(
                        """
                        UPDATE fact_sales_orders
                        SET inventory_deducted = TRUE,
                            updated_at = NOW()
                        WHERE id = :order_id
                        """
                    ),
                    {"order_id": order_row["id"]},
                )
                posted += 1
                continue

            inventory_row = self.db.execute(
                text(
                    """
                    SELECT quantity_available, avg_cost
                    FROM fact_inventory
                    WHERE platform_code = :platform_code
                      AND shop_id = :shop_id
                      AND product_id = (
                          SELECT product_surrogate_id
                          FROM dim_products
                          WHERE platform_code = :platform_code
                            AND platform_sku = :platform_sku
                          LIMIT 1
                      )
                    LIMIT 1
                    """
                ),
                {
                    "platform_code": order_row["platform_code"],
                    "shop_id": order_row["shop_id"],
                    "platform_sku": order_row["sku"],
                },
            ).fetchone()

            qty_before = int(inventory_row.quantity_available if inventory_row else 0)
            avg_cost_before = float(
                inventory_row.avg_cost if inventory_row and inventory_row.avg_cost else 0.0
            )

            self.sales_outbound_service.post_sale_and_consume_layers(
                platform_code=order_row["platform_code"],
                shop_id=order_row["shop_id"],
                platform_sku=str(order_row["sku"]),
                qty_out=int(order_row["qty"] or 0),
                order_id=str(order_row["order_id"]),
                transaction_date=order_row["order_ts"] or datetime.now(),
                avg_cost_before=avg_cost_before,
                qty_before=qty_before,
                created_by="order_import",
            )

            self.db.execute(
                text(
                    """
                    UPDATE fact_sales_orders
                    SET inventory_deducted = TRUE,
                        updated_at = NOW()
                    WHERE id = :order_id
                    """
                ),
                {"order_id": order_row["id"]},
            )
            posted += 1

        self.db.commit()
        return {"posted": posted, "skipped": skipped}
