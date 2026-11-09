from pathlib import Path


def test_business_overview_comparison_module_sql_asset():
    sql_path = Path("sql/api_modules/business_overview_comparison_module.sql")
    assert sql_path.exists()

    sql_text = sql_path.read_text(encoding="utf-8")
    assert (
        "CREATE OR REPLACE VIEW api.business_overview_comparison_module AS" in sql_text
    )
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


def test_business_overview_comparison_target_join_uses_platform_shop_month_identity():
    sql_text = Path(
        "sql/api_modules/business_overview_comparison_module.sql"
    ).read_text(encoding="utf-8")

    # 第三批-C：月目标改读 a_class.target_breakdown（真 SSOT），
    # 平台/店铺的归一化写法保持不变（带 tb. 表别名）。
    assert "LOWER(TRIM(COALESCE(tb.platform_code, '')))" in sql_text
    assert "a_class.target_breakdown tb" in sql_text
    assert (
        "LOWER(COALESCE(m.platform_code, '')) = COALESCE(t.platform_code, '')"
        in sql_text
    )
    assert "COALESCE(m.shop_id, '') = COALESCE(t.shop_id, '')" in sql_text
