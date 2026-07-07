from backend.services.deduplication_service import DeduplicationService
from pathlib import Path


def test_prepare_orders_rows_preserves_order_head_amounts_without_touching_line_costs():
    from backend.services.orders_ingestion_normalizer import prepare_orders_rows_for_b_class

    rows = [
        {
            "订单编号": "260610P0GXMYRE",
            "平台SKU": "HKR-LRI9-Transparent-035",
            "SKU ID": "224169128209",
            "产品ID": "27984946015",
            "买家支付(RMB)": "371.32",
            "利润(RMB)": "186.89",
            "仓库操作费(RMB)": "10.73",
            "广告成本(RMB)": "11.14",
            "采购成本(RMB)": "74.00",
        },
        {
            "订单编号": "260610P0GXMYRE",
            "平台SKU": "HKR-LRI9-Transparent-035",
            "SKU ID": "224169128209",
            "产品ID": "27984946015",
            "买家支付(RMB)": "",
            "利润(RMB)": "",
            "仓库操作费(RMB)": "",
            "广告成本(RMB)": "",
            "采购成本(RMB)": "18.50",
        },
    ]

    prepared_rows, identity_values = prepare_orders_rows_for_b_class(rows)

    assert prepared_rows[0]["买家支付(RMB)"] == "371.32"
    assert prepared_rows[0]["利润(RMB)"] == "186.89"
    assert prepared_rows[0]["仓库操作费(RMB)"] == "10.73"
    assert prepared_rows[0]["广告成本(RMB)"] == "11.14"
    assert prepared_rows[1]["买家支付(RMB)"] == ""
    assert prepared_rows[1]["利润(RMB)"] == ""
    assert prepared_rows[1]["仓库操作费(RMB)"] == ""
    assert prepared_rows[1]["广告成本(RMB)"] == ""
    assert prepared_rows[1]["采购成本(RMB)"] == "18.50"
    assert "_source_line_index" not in prepared_rows[0]
    assert identity_values == [
        {},
        {"_source_line_index": 2},
    ]


def test_orders_source_line_index_makes_same_order_same_sku_hashes_distinct():
    from backend.services.orders_ingestion_normalizer import (
        extend_orders_deduplication_fields,
        prepare_orders_rows_for_b_class,
    )

    rows = [
        {
            "order_id": "2606131JJFE29C",
            "platform_sku": "SAME-SKU",
            "sku_id": "SAME-SKU-ID",
            "product_id": "SAME-PRODUCT",
            "buyer_payment_rmb": "100.14",
            "profit_rmb": "55.33",
            "purchase_cost_rmb": "8.00",
        },
        {
            "order_id": "2606131JJFE29C",
            "platform_sku": "SAME-SKU",
            "sku_id": "SAME-SKU-ID",
            "product_id": "SAME-PRODUCT",
            "buyer_payment_rmb": "",
            "profit_rmb": "",
            "purchase_cost_rmb": "16.00",
        },
    ]
    prepared_rows, identity_values = prepare_orders_rows_for_b_class(rows)

    hashes_without_line_index = DeduplicationService(db=None).batch_calculate_data_hash(
        prepared_rows,
        deduplication_fields=["order_id"],
        scope_values={
            "platform_code": "shopee",
            "shop_id": "xihong",
            "data_domain": "orders",
            "granularity": "monthly",
        },
    )
    hashes_with_line_index = DeduplicationService(db=None).batch_calculate_data_hash(
        prepared_rows,
        deduplication_fields=extend_orders_deduplication_fields("orders", ["order_id"]),
        scope_values={
            "platform_code": "shopee",
            "shop_id": "xihong",
            "data_domain": "orders",
            "granularity": "monthly",
        },
        identity_values=identity_values,
    )

    assert hashes_without_line_index[0] == hashes_without_line_index[1]
    assert hashes_with_line_index[0] != hashes_with_line_index[1]


def test_orders_raw_data_merge_prefers_existing_non_empty_order_amounts():
    from backend.services.orders_ingestion_normalizer import merge_orders_raw_data_prefer_non_empty

    existing = {
        "买家支付(RMB)": "126.53",
        "利润(RMB)": "64.06",
        "采购成本(RMB)": "24.00",
    }
    incoming = {
        "买家支付(RMB)": "",
        "利润(RMB)": None,
        "采购成本(RMB)": "8.00",
    }

    merged = merge_orders_raw_data_prefer_non_empty(existing, incoming)

    assert merged["买家支付(RMB)"] == "126.53"
    assert merged["利润(RMB)"] == "64.06"
    assert merged["采购成本(RMB)"] == "8.00"


def test_field_mapping_ingest_prepares_orders_rows_before_hashing():
    source = Path("backend/domains/data_platform/routers/field_mapping_ingest.py").read_text(encoding="utf-8")

    assert "prepare_orders_rows_for_b_class(" in source
    assert "extend_orders_deduplication_fields(" in source
    assert "merge_hash_identity_values(" in source
    assert source.index("prepare_orders_rows_for_b_class(") < source.index(
        "batch_calculate_data_hash("
    )


def test_data_ingestion_service_prepares_orders_rows_before_hashing():
    source = Path("backend/services/data_ingestion_service.py").read_text(encoding="utf-8")

    assert "prepare_orders_rows_for_b_class(" in source
    assert "extend_orders_deduplication_fields(" in source
    assert "merge_hash_identity_values(" in source
    assert source.index("prepare_orders_rows_for_b_class(") < source.index(
        "batch_calculate_data_hash("
    )


def test_raw_data_importer_merges_orders_raw_data_before_upsert():
    source = Path("backend/services/raw_data_importer.py").read_text(encoding="utf-8")

    assert "merge_orders_raw_data_prefer_non_empty" in source
    assert "existing_raw_data_by_hash" in source
