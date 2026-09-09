from pathlib import Path


def test_product_profit_finalization_migration_extends_existing_product_center_schema():
    path = Path("current_migrations/versions/20260910_product_profit_finalization.py")
    source = path.read_text(encoding="utf-8")
    assert 'down_revision = "current_schema_20260909_product_cost_estimates"' in source
    assert '"dim_erp_sku"' in source
    assert '"default_purchase_cost"' in source
    assert '"logistics_bill_lines"' in source
    assert '"headhaul_cost"' in source
    assert '"feishu_projection_configs"' in source
    assert '"feishu_projection_tasks"' in source
    assert '"feishu_projection_logs"' in source
