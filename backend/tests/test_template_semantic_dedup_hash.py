from backend.services.deduplication_service import DeduplicationService
from datetime import date, datetime


def test_deduplication_hash_resolves_product_id_from_header_binding():
    row = {"商品 ID": "P-001", "商品名": "Test Product"}
    bindings = [
        {
            "raw_name": "商品 ID",
            "display_name": "商品 ID",
            "semantic_key": "product_id",
            "semantic_review_status": "confirmed_semantic",
            "aliases": ["商品 ID", "product_id"],
            "required": False,
            "hash_participates": True,
        },
        {
            "raw_name": "商品名",
            "display_name": "商品名",
            "semantic_key": None,
            "semantic_review_status": "confirmed_non_semantic",
            "aliases": [],
            "required": False,
            "hash_participates": False,
        },
    ]

    service = DeduplicationService(db=None)

    first_hash = service.calculate_data_hash(
        row,
        deduplication_fields=["product_id"],
        header_bindings=bindings,
    )
    second_hash = service.calculate_data_hash(
        {"商品 ID": "P-002", "商品名": "Test Product"},
        deduplication_fields=["product_id"],
        header_bindings=bindings,
    )

    assert first_hash != second_hash


def test_deduplication_hash_includes_file_scope_values():
    row = {"日期": "2026-06-08", "访客数": 100}
    bindings = [
        {
            "raw_name": "日期",
            "display_name": "日期",
            "semantic_key": "metric_date",
            "semantic_review_status": "confirmed_semantic",
            "aliases": ["日期", "metric_date"],
            "required": False,
            "hash_participates": True,
        }
    ]

    service = DeduplicationService(db=None)

    first_hash = service.calculate_data_hash(
        row,
        deduplication_fields=["metric_date"],
        header_bindings=bindings,
        scope_values={
            "platform_code": "tiktok",
            "shop_id": "shop-a",
            "data_domain": "traffic",
            "granularity": "daily",
        },
    )
    second_hash = service.calculate_data_hash(
        row,
        deduplication_fields=["metric_date"],
        header_bindings=bindings,
        scope_values={
            "platform_code": "tiktok",
            "shop_id": "shop-b",
            "data_domain": "traffic",
            "granularity": "daily",
        },
    )

    assert first_hash != second_hash


def test_deduplication_hash_uses_semantic_key_across_header_aliases():
    first_bindings = [
        {
            "raw_name": "订单号",
            "display_name": "订单号",
            "semantic_key": "order_id",
            "semantic_review_status": "confirmed_semantic",
            "aliases": ["订单号", "order_id"],
            "required": True,
            "hash_participates": True,
        }
    ]
    second_bindings = [
        {
            "raw_name": "订单编号",
            "display_name": "订单编号",
            "semantic_key": "order_id",
            "semantic_review_status": "confirmed_semantic",
            "aliases": ["订单编号", "order_id"],
            "required": True,
            "hash_participates": True,
        }
    ]

    service = DeduplicationService(db=None)
    scope_values = {
        "platform_code": "shopee",
        "shop_id": "shop-a",
        "data_domain": "orders",
        "granularity": "daily",
    }

    first_hash = service.calculate_data_hash(
        {"订单号": "SO-001"},
        deduplication_fields=["order_id"],
        header_bindings=first_bindings,
        scope_values=scope_values,
    )
    second_hash = service.calculate_data_hash(
        {"订单编号": "SO-001"},
        deduplication_fields=["order_id"],
        header_bindings=second_bindings,
        scope_values=scope_values,
    )

    assert first_hash == second_hash


def test_deduplication_hash_uses_derived_file_date_identity_value():
    service = DeduplicationService(db=None)
    row = {"visitor_count": 100}
    scope_values = {
        "platform_code": "shopee",
        "shop_id": "shop-a",
        "data_domain": "traffic",
        "granularity": "daily",
    }

    first_hash = service.calculate_data_hash(
        row,
        deduplication_fields=["metric_date"],
        scope_values=scope_values,
        identity_values={"metric_date": date(2026, 6, 1)},
    )
    second_hash = service.calculate_data_hash(
        row,
        deduplication_fields=["metric_date"],
        scope_values=scope_values,
        identity_values={"metric_date": date(2026, 6, 2)},
    )

    assert first_hash != second_hash


def test_products_monthly_hash_uses_metric_date_for_month_identity():
    service = DeduplicationService(db=None)
    row = {
        "product_id": "P-001",
        "product_name": "Test Product",
        "variant_id": "V-001",
    }
    scope_values = {
        "platform_code": "shopee",
        "shop_id": "shop-a",
        "data_domain": "products",
        "granularity": "monthly",
    }
    deduplication_fields = ["product_id", "product_name", "variant_id", "metric_date"]

    april_hash = service.calculate_data_hash(
        row,
        deduplication_fields=deduplication_fields,
        scope_values=scope_values,
        identity_values={"metric_date": date(2026, 4, 1)},
    )
    duplicate_april_hash = service.calculate_data_hash(
        row,
        deduplication_fields=deduplication_fields,
        scope_values=scope_values,
        identity_values={"metric_date": date(2026, 4, 1)},
    )
    may_hash = service.calculate_data_hash(
        row,
        deduplication_fields=deduplication_fields,
        scope_values=scope_values,
        identity_values={"metric_date": date(2026, 5, 1)},
    )

    assert april_hash == duplicate_april_hash
    assert april_hash != may_hash


def test_deduplication_hash_uses_user_selected_hour_identity_value():
    service = DeduplicationService(db=None)
    row = {"page_views": 100}
    scope_values = {
        "platform_code": "shopee",
        "shop_id": "1407964586",
        "data_domain": "analytics",
        "granularity": "daily",
    }

    thirteen_hash = service.calculate_data_hash(
        row,
        deduplication_fields=["metric_date", "period_start_time"],
        scope_values=scope_values,
        identity_values={
            "metric_date": date(2026, 6, 8),
            "period_start_time": datetime(2026, 6, 8, 13, 0, 0),
        },
    )
    fourteen_hash = service.calculate_data_hash(
        row,
        deduplication_fields=["metric_date", "period_start_time"],
        scope_values=scope_values,
        identity_values={
            "metric_date": date(2026, 6, 8),
            "period_start_time": datetime(2026, 6, 8, 14, 0, 0),
        },
    )

    assert thirteen_hash != fourteen_hash
