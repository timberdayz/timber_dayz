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
        "daily product metrics require product_id/platform_sku + metric_date to avoid cross-date overwrites."
    ]


def test_products_daily_parse_rule_does_not_replace_hash_identity_selection():
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
            },
            {
                "source_header": "统计日期",
                "semantic_key": "metric_date",
                "semantic_review_status": "confirmed_semantic",
            },
        ],
        field_parse_rules=[
            {
                "target_field": "metric_date",
                "source_column": "统计日期",
                "value_kind": "single_date",
                "date_format": "yyyy-mm-dd",
            }
        ],
    )

    assert result.passed is False
    assert result.blocking_errors == [
        "daily product metrics require product_id/platform_sku + metric_date to avoid cross-date overwrites."
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


def test_hash_policy_rejects_non_semantic_deduplication_field():
    service = TemplateHashPolicyService()

    result = service.validate(
        data_domain="analytics",
        granularity="daily",
        deduplication_fields=["status"],
        header_bindings=[
            {
                "source_header": "状态",
                "semantic_key": None,
                "semantic_review_status": "confirmed_non_semantic",
                "hash_participates": False,
            }
        ],
        field_parse_rules=[],
    )

    assert result.passed is False
    assert "deduplication_fields must be confirmed semantic keys: status" in result.blocking_errors


def test_traffic_daily_requires_metric_date_identity():
    service = TemplateHashPolicyService()

    result = service.validate(
        data_domain="traffic",
        granularity="daily",
        deduplication_fields=["shop_id"],
        header_bindings=[
            {
                "source_header": "店铺",
                "semantic_key": "shop_id",
                "semantic_review_status": "confirmed_semantic",
                "hash_participates": True,
            }
        ],
        field_parse_rules=[],
    )

    assert result.passed is False
    assert result.blocking_errors == [
        "traffic daily data requires metric_date as a semantic hash identity field."
    ]
