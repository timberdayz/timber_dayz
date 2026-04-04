from backend.services.inventory.order_posting_service import should_post_pending_order


def test_should_post_pending_order_requires_positive_qty_and_not_deducted():
    assert should_post_pending_order(
        {
            "inventory_deducted": False,
            "status": "paid",
            "qty": 2,
            "sku": "SKU1",
        }
    )
    assert not should_post_pending_order(
        {
            "inventory_deducted": True,
            "status": "paid",
            "qty": 2,
            "sku": "SKU1",
        }
    )
    assert not should_post_pending_order(
        {
            "inventory_deducted": False,
            "status": "cancelled",
            "qty": 2,
            "sku": "SKU1",
        }
    )
