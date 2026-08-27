from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    ROOT
    / "current_migrations"
    / "versions"
    / "20260827_profit_basis_v2_breakdown.py"
)


def test_profit_basis_v2_breakdown_is_a_current_schema_migration():
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'revision = "current_schema_20260827_profit_basis_v2_breakdown"' in source
    assert (
        'down_revision = "current_schema_20260822_operation_metric_catalog_v3"'
        in source
    )
    assert "finance" in source
    assert "shop_profit_basis" in source
    assert "other_a_class_cost_amount" in source
    assert "pre_commission_labor_cost_amount" in source
    assert "cost_status" in source
    assert "def downgrade()" in source
