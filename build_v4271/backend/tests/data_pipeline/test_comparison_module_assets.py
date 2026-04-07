from pathlib import Path


def test_business_overview_comparison_module_sql_asset():
    sql_path = Path("sql/api_modules/business_overview_comparison_module.sql")
    assert sql_path.exists()

    sql_text = sql_path.read_text(encoding="utf-8")
    assert "CREATE OR REPLACE VIEW api.business_overview_comparison_module AS" in sql_text
    assert "mart.shop_day_kpi" in sql_text
    assert "mart.shop_week_kpi" in sql_text
    assert "mart.shop_month_kpi" in sql_text
    assert "sales_amount" in sql_text
    assert "sales_quantity" in sql_text
    assert "traffic" in sql_text
    assert "conversion_rate" in sql_text
    assert "avg_order_value" in sql_text
    assert "attach_rate" in sql_text
    assert "profit" in sql_text
