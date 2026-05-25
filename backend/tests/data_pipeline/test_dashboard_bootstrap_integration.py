from pathlib import Path
import asyncio
from unittest.mock import AsyncMock

from backend.services.data_pipeline import dashboard_bootstrap


def test_dashboard_bootstrap_targets_cover_key_modules():
    assert "business_overview" in dashboard_bootstrap.DASHBOARD_MODULE_TARGETS
    assert "clearance_ranking" in dashboard_bootstrap.DASHBOARD_MODULE_TARGETS
    assert "ops.dashboard_asset_state" in dashboard_bootstrap.DASHBOARD_REQUIRED_OBJECTS


def test_backend_main_only_inspects_dashboard_assets_on_startup():
    text = Path("backend/main.py").read_text(encoding="utf-8", errors="replace")

    assert "inspect_dashboard_assets" in text
    assert "bootstrap_dashboard_assets_if_needed" not in text


def test_bootstrap_dashboard_assets_relaxes_statement_timeout(monkeypatch):
    session = AsyncMock()
    monkeypatch.setattr(dashboard_bootstrap, "execute_sql_file", AsyncMock())
    monkeypatch.setattr(dashboard_bootstrap, "execute_refresh_plan", AsyncMock(return_value="run-1"))
    monkeypatch.setattr(dashboard_bootstrap, "_load_dashboard_asset_state", AsyncMock(return_value={}))
    monkeypatch.setattr(
        dashboard_bootstrap,
        "inspect_dashboard_assets",
        AsyncMock(
            return_value={
                "ready": True,
                "missing_objects": [],
                "missing_schemas": [],
                "modules": {
                    "business_overview": {"status": "ready", "ready": True},
                    "clearance_ranking": {"status": "ready", "ready": True},
                },
            }
        ),
    )

    report = asyncio.run(dashboard_bootstrap.bootstrap_dashboard_assets(session))

    executed_sql = str(session.execute.await_args_list[0].args[0])
    assert "SET LOCAL statement_timeout = 0" in executed_sql
    assert report["run_ids"]["business_overview"] == "run-1"
