import pytest


def _orders_bindings(include_paid_amount: bool = True):
    bindings = [
        {"raw_name": "order_no", "semantic_key": "order_id"},
        {"raw_name": "shop_name", "semantic_key": "shop_id"},
        {"raw_name": "order_created_at", "semantic_key": "order_date"},
        {"raw_name": "sold_qty", "semantic_key": "sales_volume"},
        {"raw_name": "profit_amount", "semantic_key": "profit"},
        {"raw_name": "estimated_settlement", "semantic_key": "estimated_settlement_amount"},
    ]
    if include_paid_amount:
        bindings.append({"raw_name": "buyer_paid", "semantic_key": "paid_amount"})
    return bindings


@pytest.mark.asyncio
async def test_orders_optional_field_drop_is_non_breaking_semantic_contract():
    from backend.services.semantic_field_contract_service import SemanticFieldContractService

    service = SemanticFieldContractService(db=None)
    result = await service.evaluate(
        platform="shopee",
        data_domain="orders",
        granularity="monthly",
        sub_domain=None,
        header_bindings=_orders_bindings(),
        current_columns=["order_no", "shop_name", "order_created_at", "sold_qty", "buyer_paid", "profit_amount"],
    )

    assert result.status == "non_breaking_drift"
    assert result.should_block is False
    assert result.missing_required_keys == []
    assert result.missing_optional_keys == ["estimated_settlement_amount"]


@pytest.mark.asyncio
async def test_orders_required_paid_amount_drop_blocks_semantic_contract():
    from backend.services.semantic_field_contract_service import SemanticFieldContractService

    service = SemanticFieldContractService(db=None)
    result = await service.evaluate(
        platform="shopee",
        data_domain="orders",
        granularity="weekly",
        sub_domain=None,
        header_bindings=_orders_bindings(include_paid_amount=True),
        current_columns=["order_no", "shop_name", "order_created_at", "sold_qty", "profit_amount"],
    )

    assert result.status == "breaking_drift"
    assert result.should_block is True
    assert result.missing_required_keys == ["paid_amount"]
    assert result.impact_descriptions


@pytest.mark.asyncio
async def test_extra_raw_fields_do_not_block_when_required_semantic_keys_resolve():
    from backend.services.semantic_field_contract_service import SemanticFieldContractService

    service = SemanticFieldContractService(db=None)
    result = await service.evaluate(
        platform="shopee",
        data_domain="orders",
        granularity="weekly",
        sub_domain=None,
        header_bindings=_orders_bindings(),
        current_columns=[
            "order_no",
            "shop_name",
            "order_created_at",
            "sold_qty",
            "buyer_paid",
            "profit_amount",
            "estimated_settlement",
            "platform_new_column",
        ],
    )

    assert result.status == "non_breaking_drift"
    assert result.should_block is False
    assert result.extra_raw_fields == ["platform_new_column"]
