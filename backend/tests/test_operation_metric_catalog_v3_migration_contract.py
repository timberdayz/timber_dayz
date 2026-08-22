from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "current_migrations" / "versions" / "20260822_operation_metric_catalog_v3.py"


def test_operation_catalog_v3_is_an_independent_reversible_current_migration():
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'revision = "current_schema_20260822_operation_metric_catalog_v3"' in source
    assert (
        'down_revision = "current_schema_20260822_personal_performance_target_workbench"'
        in source
    )
    assert "def downgrade()" in source
    assert "DELETE FROM a_class.operation_metric_catalog" in source
    assert "catalog_version = 3" in source
    assert "operation_performance_shop_scopes" in source
    assert "target_breakdown" in source
    assert "RAISE EXCEPTION" in source
    assert "cannot downgrade operation metric catalog V3" in source


def test_operation_catalog_v3_contains_only_the_store_metrics():
    source = MIGRATION.read_text(encoding="utf-8")

    for metric_code in (
        "customer_satisfaction",
        "complaint_count",
        "reply_timeliness",
        "operation_special_check",
    ):
        assert metric_code in source

    assert "training_completion_rate" not in source
    assert "catalog_version, metric_code" in source
