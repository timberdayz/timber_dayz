import pytest


def _orders_bindings(include_paid_amount: bool = True):
    bindings = [
        {"raw_name": "order_no", "semantic_key": "order_id"},
        {"raw_name": "shop_name", "semantic_key": "shop_id"},
        {"raw_name": "order_created_at", "semantic_key": "order_date"},
        {"raw_name": "sold_qty", "semantic_key": "sales_volume"},
        {"raw_name": "profit_amount", "semantic_key": "profit"},
        {
            "raw_name": "estimated_settlement",
            "semantic_key": "estimated_settlement_amount",
        },
    ]
    if include_paid_amount:
        bindings.append({"raw_name": "buyer_paid", "semantic_key": "paid_amount"})
    return bindings


@pytest.mark.asyncio
async def test_orders_optional_field_drop_is_non_breaking_semantic_contract():
    from backend.services.semantic_field_contract_service import (
        SemanticFieldContractService,
    )

    service = SemanticFieldContractService(db=None)
    result = await service.evaluate(
        platform="shopee",
        data_domain="orders",
        granularity="monthly",
        sub_domain=None,
        header_bindings=_orders_bindings(),
        current_columns=[
            "order_no",
            "shop_name",
            "order_created_at",
            "sold_qty",
            "buyer_paid",
            "profit_amount",
        ],
    )

    assert result.status == "non_breaking_drift"
    assert result.should_block is False
    assert result.missing_required_keys == []
    assert result.missing_optional_keys == ["estimated_settlement_amount"]


@pytest.mark.asyncio
async def test_orders_metric_paid_amount_drop_is_domain_floor_not_blocking():
    """[*] 批次 F-3: 指标类契约 required 降为「域级下限」—— 缺失**不拦批次**。

    规格 §3.4: 契约降为「域级下限护栏」; 契约表里的 required 混着指标类
    (``page_views`` / ``visitor_count`` / ``paid_amount`` / ``sales_volume`` /
    ``profit``), 指标缺失就把整批文件拦下来是误伤。

    ⇒ 缺口落到 ``below_domain_floor_keys``, 由治理面板引导用户去勾;
    用户勾了 ⇒ 进**模板级** required ⇒ 那时才阻断。
    """
    from backend.services.semantic_field_contract_service import (
        SemanticFieldContractService,
    )

    service = SemanticFieldContractService(db=None)
    result = await service.evaluate(
        platform="shopee",
        data_domain="orders",
        granularity="weekly",
        sub_domain=None,
        header_bindings=_orders_bindings(include_paid_amount=True),
        current_columns=[
            "order_no",
            "shop_name",
            "order_created_at",
            "sold_qty",
            "profit_amount",
        ],
    )

    assert result.status != "breaking_drift"
    assert result.should_block is False
    assert result.missing_required_keys == []
    assert "paid_amount" in result.below_domain_floor_keys


@pytest.mark.asyncio
async def test_orders_identity_contract_key_still_blocks_when_absent():
    """身份/时间类契约 required **仍是硬要求** —— 降级只针对指标类。

    「缺了店铺 / 缺了下单日期 ⇒ 这一行归属不明 ⇒ 整行无意义」,
    这种要求不能让位给「域级下限」, 否则护栏就空了。
    """
    from backend.services.semantic_field_contract_service import (
        SemanticFieldContractService,
    )

    service = SemanticFieldContractService(db=None)
    result = await service.evaluate(
        platform="shopee",
        data_domain="orders",
        granularity="weekly",
        sub_domain=None,
        header_bindings=[],
        current_columns=[
            "order_no",
            "order_created_at",
            "sold_qty",
            "buyer_paid",
            "profit_amount",
        ],
        template_columns=[
            "order_no",
            "shop_name",
            "order_created_at",
            "sold_qty",
            "buyer_paid",
            "profit_amount",
        ],
    )

    assert result.status == "breaking_drift"
    assert result.should_block is True
    # shop_id(身份) + order_date(时间) 都是硬要求 ⇒ 缺一不可
    assert result.missing_required_keys == ["shop_id", "order_date"]
    assert result.impact_descriptions


@pytest.mark.asyncio
async def test_template_level_core_field_required_is_primary_blocking_source():
    """模板级清单的 required 是**主来源** —— 用户勾了指标类, 缺失也阻断。

    规格 §3.4: 「模板级 ``core_fields.required`` 是主来源(用户勾的)」。
    ⇒ 契约降级**不会**削弱用户自己勾出来的要求。
    """
    from backend.services.semantic_field_contract_service import (
        SemanticFieldContractService,
    )

    service = SemanticFieldContractService(db=None)
    result = await service.evaluate(
        platform="shopee",
        data_domain="orders",
        granularity="weekly",
        sub_domain=None,
        header_bindings=_orders_bindings(include_paid_amount=True),
        current_columns=[
            "order_no",
            "shop_name",
            "order_created_at",
            "sold_qty",
            "profit_amount",
        ],
        core_fields=[
            {
                "semantic_key": "paid_amount",
                "raw_name": "buyer_paid",
                "required": True,
                "in_hash": False,
            }
        ],
    )

    assert result.status == "breaking_drift"
    assert result.should_block is True
    assert result.missing_required_keys == ["paid_amount"]
    # 清单勾了 ⇒ 不再是「域级下限缺口」
    assert "paid_amount" not in result.below_domain_floor_keys


@pytest.mark.asyncio
async def test_extra_raw_fields_do_not_block_when_required_semantic_keys_resolve():
    from backend.services.semantic_field_contract_service import (
        SemanticFieldContractService,
    )

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


@pytest.mark.asyncio
async def test_orders_chinese_headers_resolve_required_keys_when_bindings_are_incomplete():
    from backend.services.semantic_field_contract_service import (
        SemanticFieldContractService,
    )

    service = SemanticFieldContractService(db=None)
    result = await service.evaluate(
        platform="shopee",
        data_domain="orders",
        granularity="monthly",
        sub_domain=None,
        header_bindings=[
            {"raw_name": "订单编号", "semantic_key": "order_id"},
            {"raw_name": "店铺", "semantic_key": "shop_id"},
            {"raw_name": "下单时间", "semantic_key": "order_date"},
        ],
        current_columns=[
            "订单编号",
            "店铺",
            "下单时间",
            "销售数量",
            "买家支付(RMB)",
            "利润(RMB)",
        ],
        template_columns=[
            "订单编号",
            "店铺",
            "下单时间",
            "销售数量",
            "买家支付(RMB)",
            "利润(RMB)",
            "预估回款金额",
        ],
    )

    assert result.status == "ready"
    assert result.should_block is False
    assert result.missing_required_keys == []
    # [*] 批次 F-3: resolved_required_keys 只含**身份/时间类**的硬要求
    #     (指标类降为域级下限, 不再是 required)。
    assert result.resolved_required_keys == [
        "order_id",
        "shop_id",
        "order_date",
    ]
    assert result.missing_optional_keys == []


@pytest.mark.asyncio
async def test_orders_chinese_headers_do_not_block_when_metric_is_absent():
    """[*] 批次 F-3: 指标类缺失不再阻断批次(降为域级下限)。"""
    from backend.services.semantic_field_contract_service import (
        SemanticFieldContractService,
    )

    service = SemanticFieldContractService(db=None)
    result = await service.evaluate(
        platform="shopee",
        data_domain="orders",
        granularity="monthly",
        sub_domain=None,
        header_bindings=[],
        current_columns=[
            "订单编号",
            "店铺",
            "下单时间",
            "买家支付(RMB)",
            "利润(RMB)",
        ],
        template_columns=[
            "订单编号",
            "店铺",
            "下单时间",
            "销售数量",
            "买家支付(RMB)",
            "利润(RMB)",
        ],
    )

    assert result.status != "breaking_drift"
    assert result.should_block is False
    assert result.missing_required_keys == []
    assert "sales_volume" in result.below_domain_floor_keys
