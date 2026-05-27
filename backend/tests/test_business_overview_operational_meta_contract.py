from pathlib import Path


def test_business_overview_frontend_consumes_operational_meta():
    source = Path(
        "frontend/src/domains/business/views/BusinessOverview.vue"
    ).read_text(encoding="utf-8")

    assert "operationalMeta" in source
    assert "expenses_source" in source
    assert "estimated_expenses_missing_for_platform" in source


def test_operational_metrics_sql_uses_platform_code_and_ai_token_fallback():
    source = Path(
        "sql/api_modules/business_overview_operational_metrics_module.sql"
    ).read_text(encoding="utf-8")

    assert '"platform_code"' in source or "platform_code" in source
    assert 'COALESCE("AI Token费用", 0)' in source
