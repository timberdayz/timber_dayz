from pathlib import Path

from scripts.analyze_schema_cleanup_candidates import analyze_duplicate_groups


def test_wave3_ops_and_historical_assets_are_classified_outside_business_cleanup():
    expected = {}
    actual = {
        "data_freshness_log": ["ops"],
        "data_lineage_registry": ["ops"],
        "alembic_version__archive_retired": ["public"],
        "alembic_version": ["core"],
    }

    report = analyze_duplicate_groups(expected, actual)
    by_name = {item["table_name"]: item for item in report["extra_only_tables"]}

    assert by_name["data_freshness_log"]["risk_class"] == "operations_runtime_table"
    assert by_name["data_freshness_log"]["follow_up_wave"] == "wave_3_ops_and_historical"
    assert by_name["alembic_version__archive_retired"]["risk_class"] == "historical_migration_artifact"
    assert by_name["alembic_version"]["follow_up_wave"] == "wave_3_ops_and_historical"


def test_wave3_ops_and_historical_assets_are_grouped_together_for_follow_up():
    expected = {}
    actual = {
        "data_freshness_log": ["ops"],
        "data_lineage_registry": ["ops"],
        "pipeline_run_log": ["ops"],
        "alembic_version__archive_retired": ["public"],
    }

    report = analyze_duplicate_groups(expected, actual)

    assert report["follow_up_waves"]["wave_3_ops_and_historical"] == [
        "alembic_version__archive_retired",
        "data_freshness_log",
        "data_lineage_registry",
        "pipeline_run_log",
    ]


def test_wave3_ops_contract_requires_audit_report_to_explain_non_business_boundary():
    report_text = Path("docs/reports/2026-04-10-schema-alignment-audit.md").read_text(encoding="utf-8")

    assert "wave_3_ops_and_historical" in report_text
    assert "operations/support table" in report_text or "migration-history artifact" in report_text
