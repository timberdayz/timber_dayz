from backend.services.template_hash_policy import TemplateHashPolicyService


def test_products_daily_requires_product_id_and_date_source():
    service = TemplateHashPolicyService()

    result = service.validate(
        data_domain="products",
        granularity="daily",
        deduplication_fields=["product_id"],
        header_bindings=[
            {
                "source_header": "商品 ID",
                "semantic_key": "product_id",
                "semantic_review_status": "confirmed_semantic",
            }
        ],
        field_parse_rules=[],
    )

    assert result.passed is False
    assert result.blocking_errors == [
        "日级商品指标需要 product_id + metric_date，否则不同日期同商品会互相覆盖。"
    ]


def test_products_daily_passes_when_date_is_semantically_resolved():
    service = TemplateHashPolicyService()

    result = service.validate(
        data_domain="products",
        granularity="daily",
        deduplication_fields=["product_id", "metric_date"],
        header_bindings=[
            {
                "source_header": "商品 ID",
                "semantic_key": "product_id",
                "semantic_review_status": "confirmed_semantic",
            },
            {
                "source_header": "统计日期",
                "semantic_key": "metric_date",
                "semantic_review_status": "confirmed_semantic",
            },
        ],
        field_parse_rules=[],
    )

    assert result.passed is True
    assert result.blocking_errors == []


def test_orders_requires_order_id():
    service = TemplateHashPolicyService()

    result = service.validate(
        data_domain="orders",
        granularity="daily",
        deduplication_fields=["order_id"],
        header_bindings=[
            {
                "source_header": "订单号",
                "semantic_key": "order_id",
                "semantic_review_status": "confirmed_semantic",
            }
        ],
        field_parse_rules=[],
    )

    assert result.passed is True
