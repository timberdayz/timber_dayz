from pathlib import Path


def _find_finance_timestamp_default_migration() -> Path:
    versions_dir = Path("migrations/versions")
    matches = sorted(versions_dir.glob("*finance*timestamp*default*.py"))
    assert matches, "expected a finance timestamp default repair migration in migrations/versions"
    return matches[-1]


def test_finance_timestamp_default_migration_exists():
    _find_finance_timestamp_default_migration()


def test_finance_timestamp_default_migration_mentions_required_repairs():
    migration_path = _find_finance_timestamp_default_migration()
    source = migration_path.read_text(encoding="utf-8")

    for name in [
        "fx_rates",
        "po_headers",
        "po_lines",
        "grn_headers",
        "grn_lines",
        "inventory_ledger",
        "invoice_headers",
        "invoice_lines",
        "three_way_match_log",
        "fact_expenses_month",
        "allocation_rules",
        "fact_expenses_allocated_day_shop_sku",
        "logistics_costs",
        "logistics_allocation_rules",
        "tax_vouchers",
        "gl_accounts",
        "journal_entries",
        "journal_entry_lines",
        "opening_balances",
        "return_orders",
    ]:
        assert name in source
    assert "created_at" in source
    assert "updated_at" in source
    assert "SET DEFAULT now()" in source
