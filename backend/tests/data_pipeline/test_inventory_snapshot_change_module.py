from pathlib import Path

from backend.services.data_pipeline.refresh_registry import (
    PIPELINE_DEPENDENCIES,
    SQL_TARGET_PATHS,
)


def test_inventory_snapshot_sql_assets_exist():
    assert Path("sql/mart/inventory_snapshot_history.sql").exists()
    assert Path("sql/mart/inventory_snapshot_latest.sql").exists()


def test_inventory_snapshot_change_sql_asset_exists():
    assert Path("sql/mart/inventory_snapshot_change.sql").exists()


def test_inventory_snapshot_change_sql_mentions_stock_delta_and_stagnant_days():
    sql_text = Path("sql/mart/inventory_snapshot_change.sql").read_text(encoding="utf-8")
    assert "stock_delta" in sql_text
    assert "estimated_stagnant_days" in sql_text


def test_inventory_snapshot_semantic_sql_maps_miaoshou_starred_fields():
    sql_text = Path("sql/semantic/inventory_snapshot.sql").read_text(encoding="utf-8")
    assert "*商品SKU" in sql_text
    assert "*商品名称" in sql_text
    assert "库存总量" in sql_text


def test_refresh_registry_tracks_inventory_snapshot_assets():
    assert "mart.inventory_snapshot_history" in PIPELINE_DEPENDENCIES
    assert "mart.inventory_snapshot_latest" in PIPELINE_DEPENDENCIES
    assert "mart.inventory_snapshot_change" in PIPELINE_DEPENDENCIES
    assert SQL_TARGET_PATHS["mart.inventory_snapshot_history"] == "sql/mart/inventory_snapshot_history.sql"
    assert SQL_TARGET_PATHS["mart.inventory_snapshot_latest"] == "sql/mart/inventory_snapshot_latest.sql"
    assert SQL_TARGET_PATHS["mart.inventory_snapshot_change"] == "sql/mart/inventory_snapshot_change.sql"


def test_inventory_snapshot_semantic_sql_accepts_star_product_alias():
    sql_text = Path("sql/semantic/inventory_snapshot.sql").read_text(encoding="utf-8")
    assert "*商品" in sql_text
