from datetime import date, datetime, timezone

from backend.services.cloud_b_class_sync_service import build_sync_payload


def test_sync_contract_uses_raw_data_and_header_columns():
    sample_row = {
        "id": 99,
        "platform_code": "shopee",
        "shop_id": "shop-1",
        "data_domain": "orders",
        "granularity": "daily",
        "sub_domain": None,
        "metric_date": date(2026, 3, 24),
        "period_start_date": date(2026, 3, 1),
        "period_end_date": date(2026, 3, 24),
        "period_start_time": datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc),
        "period_end_time": datetime(2026, 3, 24, 0, 0, tzinfo=timezone.utc),
        "file_id": 1,
        "template_id": 2,
        "data_hash": "hash-1",
        "ingest_timestamp": datetime(2026, 3, 24, 1, 0, tzinfo=timezone.utc),
        "currency_code": "USD",
        "raw_data": {"订单号": "A-1", "金额": "100"},
        "header_columns": ["订单号", "金额"],
        "dynamic_text_field": "should-not-sync",
    }

    result = build_sync_payload(sample_row)

    assert "raw_data" in result
    assert "header_columns" in result
    assert result["raw_data"] == {"订单号": "A-1", "金额": "100"}
    assert result["header_columns"] == ["订单号", "金额"]
    assert "dynamic_text_field" not in result


def test_sync_payload_normalizes_non_services_shop_id():
    sample_row = {
        "platform_code": "shopee",
        "shop_id": None,
        "data_domain": "orders",
        "granularity": "daily",
        "sub_domain": None,
        "metric_date": None,
        "period_start_date": None,
        "period_end_date": None,
        "period_start_time": None,
        "period_end_time": None,
        "file_id": 1,
        "template_id": 2,
        "data_hash": "hash-1",
        "ingest_timestamp": None,
        "currency_code": "USD",
        "raw_data": {"订单号": "A-1"},
        "header_columns": ["订单号"],
    }

    result = build_sync_payload(sample_row)

    assert result["shop_id"] == ""
