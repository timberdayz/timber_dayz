from __future__ import annotations

from datetime import datetime, timezone

from backend.routers import data_quarantine


def test_detect_quarantine_schema_supports_legacy_columns():
    schema_mode = data_quarantine.detect_quarantine_schema(
        {
            "id",
            "platform",
            "data_type",
            "quarantine_reason",
            "raw_data",
            "created_at",
        }
    )

    assert schema_mode == "legacy"


def test_build_legacy_file_groups_returns_frontend_safe_shape():
    rows = [
        {
            "id": 1,
            "platform": "shopee",
            "data_type": "orders",
            "quarantine_reason": "validation_error",
            "raw_data": '{"source_file": "orders_1.xlsx"}',
            "created_at": datetime(2026, 3, 21, tzinfo=timezone.utc),
        },
        {
            "id": 2,
            "platform": "shopee",
            "data_type": "orders",
            "quarantine_reason": "validation_error",
            "raw_data": '{"source_file": "orders_1.xlsx"}',
            "created_at": datetime(2026, 3, 21, tzinfo=timezone.utc),
        },
    ]

    grouped = data_quarantine.build_legacy_file_groups(rows)

    assert grouped[0]["file_id"] == 1
    assert grouped[0]["file_name"] == "orders_1.xlsx"
    assert grouped[0]["platform_code"] == "shopee"
    assert grouped[0]["data_domain"] == "orders"
    assert grouped[0]["error_count"] == 2


def test_build_legacy_filter_clause_omits_null_parameters():
    where_clause, params = data_quarantine.build_legacy_filter_clause()

    assert where_clause == ""
    assert params == {}


def test_build_legacy_filter_clause_only_includes_present_filters():
    where_clause, params = data_quarantine.build_legacy_filter_clause(
        platform="shopee",
        data_domain="orders",
    )

    assert "platform = :platform" in where_clause
    assert "data_type = :data_domain" in where_clause
    assert params == {"platform": "shopee", "data_domain": "orders"}
