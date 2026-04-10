from pathlib import Path

from backend.services.data_pipeline.refresh_registry import (
    PIPELINE_DEPENDENCIES,
    SQL_TARGET_PATHS,
)


def test_inventory_snapshot_company_daily_sql_asset_exists():
    assert Path("sql/mart/inventory_snapshot_company_daily.sql").exists()


def test_inventory_age_sql_assets_exist():
    assert Path("sql/mart/inventory_age_history.sql").exists()
    assert Path("sql/mart/inventory_age_current.sql").exists()
    assert Path("sql/api_modules/inventory_age_list_module.sql").exists()
    assert Path("sql/api_modules/inventory_age_summary_module.sql").exists()


def test_inventory_snapshot_company_daily_sql_mentions_sku_key():
    sql_text = Path("sql/mart/inventory_snapshot_company_daily.sql").read_text(encoding="utf-8")
    assert "sku_key" in sql_text
    assert "available_qty" in sql_text
    assert "last_ingest_timestamp" in sql_text


def test_refresh_registry_tracks_inventory_age_assets():
    assert PIPELINE_DEPENDENCIES["mart.inventory_snapshot_company_daily"] == [
        "mart.inventory_snapshot_history"
    ]
    assert PIPELINE_DEPENDENCIES["mart.inventory_age_history"] == [
        "mart.inventory_snapshot_company_daily"
    ]
    assert PIPELINE_DEPENDENCIES["mart.inventory_age_current"] == [
        "mart.inventory_age_history"
    ]
    assert PIPELINE_DEPENDENCIES["api.inventory_age_list_module"] == [
        "mart.inventory_age_current"
    ]
    assert PIPELINE_DEPENDENCIES["api.inventory_age_summary_module"] == [
        "mart.inventory_age_current"
    ]
    assert (
        SQL_TARGET_PATHS["mart.inventory_snapshot_company_daily"]
        == "sql/mart/inventory_snapshot_company_daily.sql"
    )
    assert (
        SQL_TARGET_PATHS["mart.inventory_age_history"]
        == "sql/mart/inventory_age_history.sql"
    )
    assert (
        SQL_TARGET_PATHS["mart.inventory_age_current"]
        == "sql/mart/inventory_age_current.sql"
    )
    assert (
        SQL_TARGET_PATHS["api.inventory_age_list_module"]
        == "sql/api_modules/inventory_age_list_module.sql"
    )
    assert (
        SQL_TARGET_PATHS["api.inventory_age_summary_module"]
        == "sql/api_modules/inventory_age_summary_module.sql"
    )
