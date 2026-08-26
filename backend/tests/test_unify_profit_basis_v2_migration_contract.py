from pathlib import Path


SOURCE = Path("migrations/versions/20260826_unify_profit_basis_v2.py").read_text(
    encoding="utf-8"
)


def test_unify_v2_migration_adds_persisted_profit_basis_breakdown_columns():
    for column in (
        "other_a_class_cost_amount",
        "pre_commission_labor_cost_amount",
        "cost_status",
    ):
        assert column in SOURCE
    assert 'schema="finance"' in SOURCE
