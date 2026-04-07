from pathlib import Path


def test_annual_summary_shop_month_uses_current_operating_cost_columns():
    for path_str in (
        "sql/mart/annual_summary_shop_month.sql",
        "sql/api_modules/business_overview_operational_metrics_module.sql",
    ):
        text = Path(path_str).read_text(
            encoding="utf-8",
            errors="replace",
        )

        assert "information_schema.columns" in text
        assert "year_month" in text
        assert '"年月"' in text
        assert "shop_id" in text
        assert '"店铺ID"' in text
        assert "rent" in text
        assert '"租金"' in text
        assert '"工资"' in text
        assert '"水电费"' in text
        assert '"其他成本"' in text


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
    assert '"年月"' in service_text
    assert '"目标销售额"' in service_text
    assert '"目标订单数"' in service_text
    assert '"目标单量"' in service_text
    assert "information_schema.columns" in sql_text
    assert "target_sales_amount" in sql_text
    assert "target_quantity" in sql_text
    assert "year_month" in sql_text
    assert '"年月"' in sql_text
    assert '"目标销售额"' in sql_text
    assert '"目标订单数"' in sql_text
