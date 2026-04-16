from pathlib import Path
import asyncio
from unittest.mock import AsyncMock

from backend.services.data_pipeline import dashboard_bootstrap


def test_dashboard_bootstrap_targets_cover_key_modules():
    assert "api.business_overview_comparison_module" in dashboard_bootstrap.DASHBOARD_BOOTSTRAP_TARGETS
    assert "api.business_overview_operational_metrics_module" in dashboard_bootstrap.DASHBOARD_BOOTSTRAP_TARGETS
    assert "ops.pipeline_run_log" in dashboard_bootstrap.DASHBOARD_REQUIRED_OBJECTS
    assert "core.field_alias_rules" in dashboard_bootstrap.DASHBOARD_REQUIRED_OBJECTS


def test_backend_main_bootstraps_dashboard_assets_on_startup():
    text = Path("backend/main.py").read_text(encoding="utf-8", errors="replace")

    assert "bootstrap_dashboard_assets_if_needed" in text


def test_bootstrap_dashboard_assets_relaxes_statement_timeout(monkeypatch):
    session = AsyncMock()
    monkeypatch.setattr(dashboard_bootstrap, "execute_sql_file", AsyncMock())
    monkeypatch.setattr(dashboard_bootstrap, "execute_refresh_plan", AsyncMock(return_value="run-1"))
    monkeypatch.setattr(
        dashboard_bootstrap,
        "inspect_dashboard_assets",
        AsyncMock(return_value={"ready": True, "missing_objects": [], "missing_schemas": []}),
    )

    report = asyncio.run(dashboard_bootstrap.bootstrap_dashboard_assets(session))

    executed_sql = str(session.execute.await_args_list[0].args[0])
    assert "SET LOCAL statement_timeout = 0" in executed_sql
    assert report["run_id"] == "run-1"
