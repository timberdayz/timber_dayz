from pathlib import Path

from scripts.analyze_schema_cleanup_candidates import analyze_duplicate_groups


def test_wave4_manual_review_assets_stay_outside_automatic_cleanup_buckets():
    expected = {}
    actual = {
        "apscheduler_jobs": ["core"],
        "campaign_targets": ["a_class"],
        "dim_date": ["core"],
        "fact_sales_orders": ["core"],
    }

    report = analyze_duplicate_groups(expected, actual)
    by_name = {item["table_name"]: item for item in report["extra_only_tables"]}

    for table_name in actual:
        assert by_name[table_name]["risk_class"] == "runtime_or_legacy_extra"
        assert by_name[table_name]["follow_up_wave"] == "wave_4_manual_review"


def test_wave4_manual_review_assets_are_grouped_together_for_human_classification():
    expected = {}
    actual = {
        "apscheduler_jobs": ["core"],
        "campaign_targets": ["a_class"],
        "dim_date": ["core"],
    }

    report = analyze_duplicate_groups(expected, actual)

    assert report["follow_up_waves"]["wave_4_manual_review"] == [
        "apscheduler_jobs",
        "campaign_targets",
        "dim_date",
    ]


def test_wave4_manual_review_contract_requires_audit_report_to_explain_manual_boundary():
    report_text = Path("docs/reports/2026-04-10-schema-alignment-audit.md").read_text(encoding="utf-8")

    assert "wave_4_manual_review" in report_text
    assert "manual review" in report_text.lower()
