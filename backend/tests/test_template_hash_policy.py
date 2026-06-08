from backend.services.template_hash_policy import TemplateHashPolicyService
from backend.services.semantic_field_registry import is_hash_identity_semantic_key


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


def test_products_monthly_returns_structured_missing_period_group():
    service = TemplateHashPolicyService()

    result = service.validate(
        data_domain="products",
        granularity="monthly",
        deduplication_fields=["product_id"],
        header_bindings=[
            {
                "source_header": "product id",
                "semantic_key": "product_id",
                "semantic_review_status": "confirmed_semantic",
            }
        ],
        field_parse_rules=[],
    )

    assert result.passed is False
    assert result.missing_required_groups[0]["key"] == "products_period_date"
    assert result.missing_required_groups[0]["accepted_keys"] == [
        "metric_date",
        "period_start_date",
        "period_end_date",
    ]
    assert result.requirement_groups[0]["passed"] is True
    assert result.requirement_groups[1]["passed"] is False
    assert result.effective_components["system_scope_fields"] == [
        "platform_code",
        "shop_id",
        "data_domain",
        "granularity",
        "sub_domain",
    ]
    assert result.effective_components["user_identity_fields"] == ["product_id"]


def test_products_monthly_passes_when_selected_date_parse_rule_is_derived():
    service = TemplateHashPolicyService()

    result = service.validate(
        data_domain="products",
        granularity="monthly",
        deduplication_fields=["product_id", "metric_date"],
        header_bindings=[
            {
                "source_header": "product id",
                "semantic_key": "product_id",
                "semantic_review_status": "confirmed_semantic",
            }
        ],
        field_parse_rules=[
            {
                "target_field": "metric_date",
                "source_column": "__file_date_from__",
                "value_kind": "single_date",
            }
        ],
    )

    assert result.passed is True
    assert result.effective_components["derived_identity_fields"] == ["metric_date"]
    assert result.effective_components["final_fields"] == [
        "platform_code",
        "shop_id",
        "data_domain",
        "granularity",
        "sub_domain",
        "product_id",
        "metric_date",
    ]


def test_products_monthly_parse_rule_without_user_selection_still_fails():
    service = TemplateHashPolicyService()

    result = service.validate(
        data_domain="products",
        granularity="monthly",
        deduplication_fields=["product_id"],
        header_bindings=[
            {
                "source_header": "product id",
                "semantic_key": "product_id",
                "semantic_review_status": "confirmed_semantic",
            }
        ],
        field_parse_rules=[
            {
                "target_field": "metric_date",
                "source_column": "__file_date_from__",
                "value_kind": "single_date",
            }
        ],
    )

    assert result.passed is False
    assert result.missing_required_groups[0]["key"] == "products_period_date"


def test_metric_and_attribute_fields_are_invalid_hash_identity_fields():
    service = TemplateHashPolicyService()

    result = service.validate(
        data_domain="products",
        granularity="daily",
        deduplication_fields=["product_id", "gmv", "sales_amount", "product_name"],
        header_bindings=[
            {
                "source_header": "product id",
                "semantic_key": "product_id",
                "semantic_review_status": "confirmed_semantic",
            },
            {
                "source_header": "gmv",
                "semantic_key": "gmv",
                "semantic_review_status": "confirmed_semantic",
            },
            {
                "source_header": "sales amount",
                "semantic_key": "sales_amount",
                "semantic_review_status": "confirmed_semantic",
            },
            {
                "source_header": "product name",
                "semantic_key": "product_name",
                "semantic_review_status": "confirmed_semantic",
            },
        ],
        field_parse_rules=[],
    )

    assert result.passed is False
    assert result.invalid_keys == ["gmv", "product_name", "sales_amount"]


def test_gmv_band_is_hash_eligible_but_not_required_for_products():
    service = TemplateHashPolicyService()

    result = service.validate(
        data_domain="products",
        granularity="monthly",
        deduplication_fields=["product_id", "metric_date", "gmv_band"],
        header_bindings=[
            {
                "source_header": "product id",
                "semantic_key": "product_id",
                "semantic_review_status": "confirmed_semantic",
            },
            {
                "source_header": "metric date",
                "semantic_key": "metric_date",
                "semantic_review_status": "confirmed_semantic",
            },
            {
                "source_header": "gmv band",
                "semantic_key": "gmv_band",
                "semantic_review_status": "confirmed_semantic",
            },
        ],
        field_parse_rules=[],
    )

    assert is_hash_identity_semantic_key("gmv_band") is True
    assert result.passed is True
    assert result.effective_components["user_identity_fields"] == [
        "product_id",
        "metric_date",
        "gmv_band",
    ]


def test_sample_diagnostics_warns_when_hash_distinct_count_is_too_low():
    service = TemplateHashPolicyService()

    result = service.validate(
        data_domain="traffic",
        granularity="daily",
        deduplication_fields=["metric_date"],
        header_bindings=[
            {
                "source_header": "date",
                "semantic_key": "metric_date",
                "semantic_review_status": "confirmed_semantic",
            }
        ],
        field_parse_rules=[],
        sample_rows=[
            {"date": "2026-06-01", "views": 0},
            {"date": "2026-06-01", "views": 100},
        ],
    )

    assert result.passed is True
    assert result.sample_diagnostics["row_count"] == 2
    assert result.sample_diagnostics["hash_distinct_count"] == 1
    assert any("distinct" in warning for warning in result.warnings)
