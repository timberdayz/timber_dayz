from pathlib import Path


def test_business_overview_frontend_consumes_operational_meta():
    source = Path("frontend/src/domains/business/views/BusinessOverview.vue").read_text(
        encoding="utf-8"
    )

    assert "operationalMeta" in source
    assert "expenses_source" in source
    assert "estimated_expenses_missing_for_platform" in source


def test_operational_metrics_sql_uses_platform_code_and_ai_token_fallback():
    source = Path(
        "sql/api_modules/business_overview_operational_metrics_module.sql"
    ).read_text(encoding="utf-8")
    other_cost_source = Path(
        "sql/semantic/shop_month_other_operating_cost.sql"
    ).read_text(encoding="utf-8")

    assert '"platform_code"' in source or "platform_code" in source
    assert "semantic.shop_month_other_operating_cost" in source
    assert "mart.shop_month_labor_cost" in source
    # 第三批-B：operating_costs 的物理列名已统一为英文
    assert "COALESCE(ai_token_amount, 0)" in other_cost_source
    assert "COALESCE(labor_amount, 0)" in other_cost_source
    assert "total_amount" in other_cost_source
    assert "deleted_at IS NULL" in other_cost_source


def test_operational_metrics_target_join_uses_platform_shop_month_identity():
    source = Path(
        "sql/api_modules/business_overview_operational_metrics_module.sql"
    ).read_text(encoding="utf-8")

    assert "LOWER(TRIM(COALESCE(tb.platform_code, '')))" in source
    assert (
        "LOWER(COALESCE(m.platform_code, '')) = COALESCE(t.platform_code, '')" in source
    )
    assert "COALESCE(m.shop_id, '') = COALESCE(t.shop_id, '')" in source


def test_business_overview_expenses_use_expense_management_columns_and_system_labor():
    source = Path("backend/services/postgresql_dashboard_service.py").read_text(
        encoding="utf-8"
    )

    # 第三批-B：operating_costs 的物理列名已统一为英文
    assert "total_amount" in source
    assert "labor_amount" in source
    assert "finance.employee_labor_cost_allocations" in source
    assert "expense_management_month_summary" in source
    assert "CASE WHEN COALESCE(total_amount, 0) <> 0" in source
    assert "deleted_at IS NULL" in source
    # 旧的中文列名已全部退场
    assert '"成本合计"' not in source
    assert '"人力费用"' not in source
    assert '"删除时间"' not in source
