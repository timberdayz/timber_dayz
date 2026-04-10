from pathlib import Path

from scripts.analyze_schema_cleanup_candidates import analyze_duplicate_groups


def test_wave2_generated_runtime_assets_are_classified_outside_business_table_cleanup():
    expected = {}
    actual = {
        "fact_shopee_orders_daily": ["b_class"],
        "fact_miaoshou_inventory_snapshot": ["b_class"],
        "business_overview_kpi_module": ["api"],
    }

    report = analyze_duplicate_groups(expected, actual)
    by_name = {item["table_name"]: item for item in report["extra_only_tables"]}

    assert by_name["fact_shopee_orders_daily"]["risk_class"] == "generated_runtime_fact"
    assert by_name["fact_shopee_orders_daily"]["follow_up_wave"] == "wave_2_runtime_generated"
    assert by_name["fact_miaoshou_inventory_snapshot"]["risk_class"] == "generated_runtime_fact"
    assert by_name["business_overview_kpi_module"]["risk_class"] == "generated_runtime_api"


def test_wave2_generated_runtime_assets_are_grouped_together_for_follow_up():
    expected = {}
    actual = {
        "fact_shopee_orders_daily": ["b_class"],
        "fact_miaoshou_inventory_snapshot": ["b_class"],
        "business_overview_kpi_module": ["api"],
        "business_overview_inventory_backlog_module": ["api"],
    }

    report = analyze_duplicate_groups(expected, actual)

    assert report["follow_up_waves"]["wave_2_runtime_generated"] == [
        "business_overview_inventory_backlog_module",
        "business_overview_kpi_module",
        "fact_miaoshou_inventory_snapshot",
        "fact_shopee_orders_daily",
    ]


def test_wave2_generated_runtime_contract_requires_audit_report_to_explain_non_cleanup_boundary():
    report_text = Path("docs/reports/2026-04-10-schema-alignment-audit.md").read_text(encoding="utf-8")

    assert "wave_2_runtime_generated" in report_text
    assert "generated runtime fact asset" in report_text or "generated runtime assets" in report_text
