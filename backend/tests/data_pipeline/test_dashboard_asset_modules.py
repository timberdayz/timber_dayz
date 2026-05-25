import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.routers import dashboard_api_postgresql as router_module
from backend.services.data_pipeline import dashboard_bootstrap


def _make_request(path: str, report: dict):
    app = SimpleNamespace(state=SimpleNamespace(dashboard_assets_report=report))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 8001),
            "app": app,
        }
    )


def test_dashboard_module_targets_exclude_heavy_mv_from_business_overview_core():
    targets = dashboard_bootstrap.DASHBOARD_MODULE_TARGETS["business_overview"]["core_targets"]

    assert "semantic.fact_orders_monthly_atomic_mv" not in targets
    assert "api.business_overview_operational_metrics_module" in targets


def test_dashboard_module_targets_track_business_overview_refreshing_targets():
    targets = dashboard_bootstrap.DASHBOARD_MODULE_TARGETS["business_overview"]["refresh_targets"]

    assert "semantic.fact_orders_monthly_atomic_mv" in targets


@pytest.mark.asyncio
async def test_refresh_materialization_replays_core_targets_after_heavy_refresh(monkeypatch):
    calls = []

    async def fake_execute_refresh_plan(session, targets, **kwargs):
        calls.append((list(targets), dict(kwargs)))
        return f"run-{len(calls)}"

    async def fake_load_state(_session):
        return {
            "business_overview": {
                "asset_fingerprint_expected": "core-fp",
                "asset_fingerprint_applied": "core-fp",
                "run_id": "run-0",
                "details_json": {},
            }
        }

    async def fake_upsert(*args, **kwargs):
        return None

    async def fake_inspect(_session):
        return {
            "ready": True,
            "modules": {
                "business_overview": {"status": "ready", "ready": True},
                "clearance_ranking": {"status": "ready", "ready": True},
                "annual_summary": {"status": "ready", "ready": True},
            },
        }

    class _Session:
        async def execute(self, _stmt, _params=None):
            class _Scalar:
                def scalar_one(self):
                    return None

                def scalar_one_or_none(self):
                    return None

            return _Scalar()

    monkeypatch.setattr(dashboard_bootstrap, "execute_refresh_plan", fake_execute_refresh_plan)
    monkeypatch.setattr(dashboard_bootstrap, "_load_dashboard_asset_state", fake_load_state)
    monkeypatch.setattr(dashboard_bootstrap, "_upsert_dashboard_asset_state", fake_upsert)
    monkeypatch.setattr(dashboard_bootstrap, "inspect_dashboard_assets", fake_inspect)

    report = await dashboard_bootstrap.refresh_dashboard_materialization_assets(
        _Session(), module="business_overview"
    )

    assert report["run_ids"]["business_overview"] == "run-2"
    assert calls[0][0] == dashboard_bootstrap._module_refresh_plan("business_overview")
    assert calls[1][0] == dashboard_bootstrap._all_dashboard_core_plan()


@pytest.mark.parametrize(
    ("path", "module_name"),
    [
        ("/api/dashboard/business-overview/kpi", "business_overview"),
        ("/api/dashboard/clearance-ranking", "clearance_ranking"),
    ],
)
def test_dashboard_asset_ready_error_includes_module_name(path, module_name):
    report = {
        "ready": False,
        "modules": {
            module_name: {
                "module_name": module_name,
                "status": "drift",
                "ready": False,
                "assets_drift": True,
                "asset_fingerprint_expected": "expected",
                "asset_fingerprint_applied": "applied",
            }
        },
    }
    request = _make_request(path, report)

    with pytest.raises(HTTPException) as exc_info:
        router_module._require_dashboard_assets_ready(request)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["module_name"] == module_name
    assert exc_info.value.detail["status"] == "drift"
