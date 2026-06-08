from pathlib import Path


def test_operational_metrics_sql_uses_current_operating_cost_contract():
    text = Path("sql/api_modules/business_overview_operational_metrics_module.sql").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "platform_code" in text
    assert '"\u5e74\u6708"' in text
    assert '"\u5e97\u94faID"' in text
    assert '"\u79df\u91d1"' in text
    assert '"\u8425\u9500\u8d39\u7528"' in text
    assert '"\u6c34\u7535\u8d39"' in text
    assert '"AI Token\u8d39\u7528"' in text
    assert '"\u5176\u4ed6\u6210\u672c"' in text
    assert '"\u6210\u672c\u5408\u8ba1"' in text
    assert '"\u5220\u9664\u65f6\u95f4"' in text
    assert "information_schema.columns" not in text


def test_target_completion_service_prefers_current_sales_target_columns():
    service_text = Path("backend/services/postgresql_dashboard_service.py").read_text(
        encoding="utf-8",
        errors="replace",
    )
    sql_text = Path("sql/api_modules/business_overview_comparison_module.sql").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "target_sales_amount" in service_text
    assert "target_quantity" in service_text
    assert "year_month" in service_text
    assert '"\u5e74\u6708"' in service_text
    assert '"\u76ee\u6807\u9500\u552e\u989d"' in service_text
    assert '"\u76ee\u6807\u8ba2\u5355\u6570"' in service_text
    assert '"\u76ee\u6807\u5355\u91cf"' in service_text
    assert '"\u5e74\u6708"' in sql_text
    assert '"\u76ee\u6807\u9500\u552e\u989d"' in sql_text
    assert '"\u76ee\u6807\u8ba2\u5355\u6570"' in sql_text
    assert "mart.shop_month_kpi" in sql_text


def test_sales_targets_a_contract_includes_platform_code_identity():
    schema_text = Path("modules/core/db/schema_parts/business.py").read_text(
        encoding="utf-8",
        errors="replace",
    )
    migration_text = Path("migrations/versions/20260610_add_platform_code_to_sales_targets_a.py").read_text(
        encoding="utf-8",
        errors="replace",
    )
    sync_text = Path("backend/services/target_sync_service.py").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "platform_code = Column(String(32)" in schema_text
    assert 'UniqueConstraint("platform_code", "shop_id", "year_month"' in schema_text
    assert "20260609_operating_costs_labor_cost" in migration_text
    assert "op.add_column" in migration_text
    assert "platform_code" in migration_text
    assert "uq_sales_targets_a_platform_shop_month" in migration_text
    assert "ON CONFLICT (platform_code," in sync_text
