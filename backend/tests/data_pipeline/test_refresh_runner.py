from pathlib import Path


def test_sql_loader_reads_sql_file_text():
    from backend.services.data_pipeline.sql_loader import load_sql_text

    sql_text = load_sql_text(Path("sql/ops/create_pipeline_tables.sql"))
    assert "CREATE SCHEMA IF NOT EXISTS ops" in sql_text


def test_refresh_registry_exposes_dependency_order():
    from backend.services.data_pipeline.refresh_registry import (
        PIPELINE_DEPENDENCIES,
        SQL_TARGET_PATHS,
        topologically_sort_targets,
    )

    assert PIPELINE_DEPENDENCIES["semantic.fact_orders_atomic"] == []
    assert SQL_TARGET_PATHS["semantic.fact_orders_atomic"] == "sql/semantic/orders_atomic.sql"
    assert SQL_TARGET_PATHS["api.business_overview_kpi_module"] == "sql/api_modules/business_overview_kpi_module.sql"
    ordered = topologically_sort_targets(
        [
            "api.business_overview_kpi_module",
            "mart.shop_month_kpi",
            "semantic.fact_orders_atomic",
            "semantic.fact_analytics_atomic",
        ]
    )
    assert ordered.index("semantic.fact_orders_atomic") < ordered.index("mart.shop_month_kpi")
    assert ordered.index("semantic.fact_analytics_atomic") < ordered.index("mart.shop_month_kpi")
    assert ordered.index("mart.shop_month_kpi") < ordered.index("api.business_overview_kpi_module")


def test_refresh_runner_builds_step_plan():
    from backend.services.data_pipeline.refresh_runner import build_refresh_plan

    plan = build_refresh_plan(["api.business_overview_kpi_module"])
    assert plan == [
        "semantic.fact_orders_atomic",
        "semantic.fact_analytics_atomic",
        "mart.shop_month_kpi",
        "api.business_overview_kpi_module",
    ]
