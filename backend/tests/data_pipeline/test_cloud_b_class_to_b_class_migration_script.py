from pathlib import Path


def test_cloud_b_class_to_b_class_migration_script_targets_expected_schemas_and_refreshes():
    text = Path("scripts/migrate_cloud_b_class_to_b_class.py").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "cloud_b_class" in text
    assert 'schema_name="b_class"' in text or 'schema_name = "b_class"' in text
    assert "ON CONFLICT" in text
    assert "api.business_overview_kpi_module" in text
    assert "api.business_overview_comparison_module" in text
    assert "api.business_overview_shop_racing_module" in text
    assert "api.business_overview_traffic_ranking_module" in text
    assert "api.business_overview_operational_metrics_module" in text
