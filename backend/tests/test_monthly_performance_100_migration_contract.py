from pathlib import Path


MIGRATION = Path(__file__).parents[2] / "migrations" / "versions" / "20260803_unify_monthly_performance_100_point.py"


def test_100_point_migration_updates_active_config_without_deleting_business_data():
    source = MIGRATION.read_text(encoding="utf-8")

    assert "UPDATE a_class.performance_config" in source
    assert "WHERE is_active = true" in source
    assert "sales_weight = 40" in source
    assert "profit_weight = 40" in source
    assert "key_product_weight = 0" in source
    assert "sales_max_score = 40" in source
    assert "profit_max_score = 40" in source
    assert "key_product_max_score = 0" in source
    assert "DELETE" not in source.upper()
    assert "DROP TABLE" not in source.upper()
