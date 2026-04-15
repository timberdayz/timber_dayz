from pathlib import Path


def _find_a_class_business_tables_timestamp_default_migration() -> Path:
    versions_dir = Path("migrations/versions")
    matches = sorted(versions_dir.glob("*a_class*business*timestamp*default*.py"))
    assert matches, "expected an a_class business tables timestamp default repair migration in migrations/versions"
    return matches[-1]


def test_a_class_business_tables_timestamp_default_migration_exists():
    _find_a_class_business_tables_timestamp_default_migration()


def test_a_class_business_tables_timestamp_default_migration_mentions_required_repairs():
    migration_path = _find_a_class_business_tables_timestamp_default_migration()
    source = migration_path.read_text(encoding="utf-8")

    assert "sales_campaigns" in source
    assert "sales_campaign_shops" in source
    assert "performance_config" in source
    assert "employee_shop_assignments" in source
    assert "shop_commission_config" in source
    assert "created_at" in source
    assert "updated_at" in source
    assert "SET DEFAULT now()" in source
