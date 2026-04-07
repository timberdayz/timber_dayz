from pathlib import Path

from backend.services.data_pipeline import dashboard_bootstrap


def test_dashboard_bootstrap_targets_cover_key_modules():
    assert "api.business_overview_comparison_module" in dashboard_bootstrap.DASHBOARD_BOOTSTRAP_TARGETS
    assert "api.business_overview_operational_metrics_module" in dashboard_bootstrap.DASHBOARD_BOOTSTRAP_TARGETS
    assert "ops.pipeline_run_log" in dashboard_bootstrap.DASHBOARD_REQUIRED_OBJECTS
    assert "core.field_alias_rules" in dashboard_bootstrap.DASHBOARD_REQUIRED_OBJECTS


def test_backend_main_bootstraps_dashboard_assets_on_startup():
    text = Path("backend/main.py").read_text(encoding="utf-8", errors="replace")

    assert "bootstrap_dashboard_assets_if_needed" in text
