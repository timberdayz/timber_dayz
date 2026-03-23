from pathlib import Path


def test_pipeline_metadata_sql_defines_required_tables():
    sql_path = Path("sql/ops/create_pipeline_tables.sql")
    assert sql_path.exists()

    sql_text = sql_path.read_text(encoding="utf-8")
    assert "CREATE SCHEMA IF NOT EXISTS ops" in sql_text
    for table_name in (
        "pipeline_run_log",
        "pipeline_step_log",
        "data_freshness_log",
        "data_lineage_registry",
    ):
        assert table_name in sql_text


def test_data_pipeline_router_exposes_observability_routes():
    from backend.routers import data_pipeline

    paths = {route.path for route in data_pipeline.router.routes}
    assert "/api/data-pipeline/status" in paths
    assert "/api/data-pipeline/freshness" in paths
    assert "/api/data-pipeline/lineage" in paths
