from pathlib import Path


def test_business_overview_kpi_sql_filters_identity_type():
    sql_text = Path("sql/metabase_questions/business_overview_kpi.sql").read_text(
        encoding="utf-8"
    )
    assert "employee_identity_type = 'employee'" in sql_text


def test_annual_summary_kpi_sql_filters_identity_type():
    sql_text = Path("sql/metabase_questions/annual_summary_kpi.sql").read_text(
        encoding="utf-8"
    )
    assert "employee_identity_type = 'employee'" in sql_text
