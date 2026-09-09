from pathlib import Path

from backend.services.data_pipeline.refresh_registry import PIPELINE_DEPENDENCIES, SQL_TARGET_PATHS


def test_spu_operating_sql_asset_and_refresh_dependency_exist():
    path = Path("sql/mart/spu_operating_current.sql")
    sql = path.read_text(encoding="utf-8").lower()
    assert "core.dim_spu" in sql
    assert "core.bridge_spu_sku" in sql
    assert "mart.inventory_age_current" in sql
    assert "estimated_margin_rate" in sql
    assert PIPELINE_DEPENDENCIES["mart.spu_operating_current"]
    assert SQL_TARGET_PATHS["mart.spu_operating_current"] == "sql/mart/spu_operating_current.sql"
