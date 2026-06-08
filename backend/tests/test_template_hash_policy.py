from backend.services.template_hash_policy import TemplateHashPolicyService
from backend.services.semantic_field_registry import (
    get_semantic_field_meta,
    is_canonical_semantic_key,
    is_hash_identity_semantic_key,
)


def test_semantic_registry_contains_hour_identity_and_metric_contract_fields():
    required_keys = [
        "metric_date",
        "period_start_date",
        "period_end_date",
        "period_start_time",
        "period_end_time",
        "order_date",
        "order_id",
        "line_id",
        "product_id",
        "product_name",
        "platform_sku",
        "sku_id",
        "service_id",
        "shop_id",
        "warehouse_name",
        "visitor_count",
        "product_visitor_count",
        "page_views",
        "impressions",
        "clicks",
        "click_rate",
        "conversion_rate",
        "order_count",
        "sku_order_count",
        "gmv",
        "total_transaction_amount",
        "bounce_rate",
        "sales_amount",
        "sales_volume",
        "paid_amount",
        "profit",
        "purchase_amount",
        "platform_commission",
        "live_gmv",
        "live_attributed_gmv",
        "live_indirect_gmv",
        "video_gmv",
        "video_attributed_gmv",
        "video_indirect_gmv",
    ]

    assert all(is_canonical_semantic_key(key) for key in required_keys)

    start_time_meta = get_semantic_field_meta("period_start_time")
    end_time_meta = get_semantic_field_meta("period_end_time")
    assert start_time_meta["kind"] == "time"
    assert start_time_meta["hash_eligible"] is True
    assert start_time_meta["default_hash"] is False
    assert end_time_meta["kind"] == "time"
    assert end_time_meta["hash_eligible"] is True
    assert end_time_meta["default_hash"] is False

    for metric_key in ["page_views", "gmv", "live_attributed_gmv"]:
        meta = get_semantic_field_meta(metric_key)
        assert meta["kind"] == "metric"
        assert meta["hash_eligible"] is False
        assert is_hash_identity_semantic_key(metric_key) is False


def test_product_name_is_weak_hash_eligible_identity_field():
    meta = get_semantic_field_meta("product_name")

    assert meta["kind"] == "dimension"
    assert meta["hash_eligible"] is True
    assert meta["default_hash"] is False
    assert meta["identity_strength"] == "weak"
    assert is_hash_identity_semantic_key("product_name") is True


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


def test_sample_diagnostics_treats_file_date_rule_as_derived_hash_field():
    service = TemplateHashPolicyService()

    result = service.validate(
        data_domain="products",
        granularity="daily",
        deduplication_fields=["product_id", "metric_date"],
        header_bindings=[
            {
                "source_header": "Product ID",
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
        sample_rows=[
            {"Product ID": "A-1"},
            {"Product ID": "A-2"},
        ],
    )

    assert result.passed is True
    assert result.sample_diagnostics["field_null_rates"]["metric_date"] == 0.0
    assert result.sample_diagnostics["derived_fields"]["metric_date"]["source_column"] == "__file_date_from__"
    assert not any("metric_date null rate" in warning for warning in result.warnings)


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


def test_metrics_and_item_status_are_invalid_hash_identity_fields():
    service = TemplateHashPolicyService()

    result = service.validate(
        data_domain="products",
        granularity="daily",
        deduplication_fields=[
            "product_id",
            "metric_date",
            "gmv",
            "sales_amount",
            "item_status",
            "page_views",
            "live_attributed_gmv",
        ],
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
                "source_header": "metric date",
                "semantic_key": "metric_date",
                "semantic_review_status": "confirmed_semantic",
            },
            {
                "source_header": "item status",
                "semantic_key": "item_status",
                "semantic_review_status": "confirmed_semantic",
            },
            {
                "source_header": "page views",
                "semantic_key": "page_views",
                "semantic_review_status": "confirmed_semantic",
            },
            {
                "source_header": "live attributed gmv",
                "semantic_key": "live_attributed_gmv",
                "semantic_review_status": "confirmed_semantic",
            },
        ],
        field_parse_rules=[],
    )

    assert result.passed is False
    assert result.invalid_keys == [
        "gmv",
        "item_status",
        "live_attributed_gmv",
        "page_views",
        "sales_amount",
    ]


def test_products_daily_allows_product_name_fallback_with_weak_identity_warning():
    service = TemplateHashPolicyService()

    result = service.validate(
        data_domain="products",
        granularity="daily",
        deduplication_fields=["product_name", "metric_date"],
        header_bindings=[
            {
                "source_header": "商品名称",
                "semantic_key": "product_name",
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
    assert result.invalid_keys == []
    assert result.requirement_groups[0]["selected_keys"] == ["product_name"]
    assert result.effective_components["derived_identity_fields"] == ["metric_date"]
    assert any("product_name" in warning and "弱身份" in warning for warning in result.warnings)


def test_products_daily_warns_when_product_name_is_selected_with_strong_identity():
    service = TemplateHashPolicyService()

    result = service.validate(
        data_domain="products",
        granularity="daily",
        deduplication_fields=["product_id", "product_name", "metric_date"],
        header_bindings=[
            {
                "source_header": "商品 ID",
                "semantic_key": "product_id",
                "semantic_review_status": "confirmed_semantic",
            },
            {
                "source_header": "商品名称",
                "semantic_key": "product_name",
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
    assert result.invalid_keys == []
    assert any("改名" in warning and "product_name" in warning for warning in result.warnings)


def test_traffic_daily_allows_user_selected_hour_identity_field():
    service = TemplateHashPolicyService()

    result = service.validate(
        data_domain="traffic",
        granularity="daily",
        deduplication_fields=["metric_date", "period_start_time"],
        header_bindings=[
            {
                "source_header": "date",
                "semantic_key": "metric_date",
                "semantic_review_status": "confirmed_semantic",
            },
            {
                "source_header": "hour",
                "semantic_key": "period_start_time",
                "semantic_review_status": "confirmed_semantic",
            },
        ],
        field_parse_rules=[],
    )

    assert result.passed is True
    assert result.invalid_keys == []
    assert result.effective_components["user_identity_fields"] == [
        "metric_date",
        "period_start_time",
    ]


def test_traffic_daily_warns_when_hour_field_is_confirmed_but_not_selected_for_hash():
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
            },
            {
                "source_header": "hour",
                "semantic_key": "period_start_time",
                "semantic_review_status": "confirmed_semantic",
            },
        ],
        field_parse_rules=[],
        sample_rows=[
            {"date": "2026-06-08", "hour": "13:00", "page_views": 100},
            {"date": "2026-06-08", "hour": "14:00", "page_views": 200},
        ],
    )

    assert result.passed is True
    assert any("period_start_time" in warning for warning in result.warnings)


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
