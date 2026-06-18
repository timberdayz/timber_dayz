from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_monthly_identity_warning_sql_is_platform_aware_for_required_platform_shop_id():
    orders_sql = _read("sql/semantic/orders_monthly_atomic_mv.sql")
    analytics_sql = _read("sql/semantic/analytics_monthly_atomic_mv.sql")

    for sql in (orders_sql, analytics_sql):
        assert "missing_required_platform_shop_id" in sql
        assert "missing_canonical_shop_id" not in sql
        assert "LOWER(COALESCE(m.platform_code, '')) IN ('shopee')" in sql


def test_business_overview_identity_health_uses_actionable_warning_codes():
    source = _read("backend/services/postgresql_dashboard_service.py")

    method_source = source[source.index("async def get_business_overview_identity_health") :]

    assert "'identity_conflict'::varchar AS warning_code" in method_source
    assert "'canonical_shop_id_conflict'::varchar AS warning_code" not in method_source
    assert "'traffic_without_order_match_due_to_identity'::varchar AS warning_code" in method_source


def test_data_ingestion_propagates_catalog_standard_shop_identity_to_raw_rows():
    source = _read("backend/services/data_ingestion_service.py")

    assert 'row["shop_account_id"] = file_shop_account_id' in source
    assert 'row["main_account_id"] = file_main_account_id' in source
    assert 'row["store_name"] = file_store_name' in source
    assert 'row["platform_shop_id"] = file_platform_shop_id' in source
