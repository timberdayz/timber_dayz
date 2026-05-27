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
    assert "semantic.fact_analytics_monthly_atomic_mv" in targets


def test_build_module_report_does_not_keep_stale_refreshing_without_active_run():
    report = dashboard_bootstrap._build_module_report(
        module_name="business_overview",
        module_state={
            "status": "refreshing",
            "asset_fingerprint_applied": dashboard_bootstrap._compute_targets_fingerprint(
                dashboard_bootstrap._module_core_plan("business_overview")
            ),
            "details_json": {
                "refresh_fingerprint_applied": dashboard_bootstrap._compute_targets_fingerprint(
                    dashboard_bootstrap._module_refresh_plan("business_overview")
                )
            },
        },
        existing_objects=set(
            dashboard_bootstrap._module_core_plan("business_overview")
            + dashboard_bootstrap._module_refresh_plan("business_overview")
        ),
        active_refresh_run=None,
    )

    assert report["status"] == "ready"
    assert report["ready"] is True


def test_build_module_report_marks_refreshing_when_active_run_exists():
    report = dashboard_bootstrap._build_module_report(
        module_name="business_overview",
        module_state={
            "status": "ready",
            "asset_fingerprint_applied": dashboard_bootstrap._compute_targets_fingerprint(
                dashboard_bootstrap._module_core_plan("business_overview")
            ),
            "details_json": {
                "refresh_fingerprint_applied": dashboard_bootstrap._compute_targets_fingerprint(
                    dashboard_bootstrap._module_refresh_plan("business_overview")
                )
            },
        },
        existing_objects=set(
            dashboard_bootstrap._module_core_plan("business_overview")
            + dashboard_bootstrap._module_refresh_plan("business_overview")
        ),
        active_refresh_run={"run_id": "run-active"},
    )

    assert report["status"] == "refreshing"
    assert report["ready"] is True


@pytest.mark.asyncio
async def test_inspect_dashboard_assets_ignores_stale_refreshing_state(monkeypatch):
    existing_objects = set()
    for module_name in dashboard_bootstrap.DASHBOARD_MODULE_TARGETS:
        existing_objects.update(dashboard_bootstrap._module_core_plan(module_name))
        existing_objects.update(dashboard_bootstrap._module_refresh_plan(module_name))
    existing_objects.update(dashboard_bootstrap.DASHBOARD_REQUIRED_OBJECTS)

    async def fake_collect(_session):
        return set(dashboard_bootstrap.DASHBOARD_REQUIRED_SCHEMAS), existing_objects

    business_core_fp = dashboard_bootstrap._compute_targets_fingerprint(
        dashboard_bootstrap._module_core_plan("business_overview")
    )
    business_refresh_fp = dashboard_bootstrap._compute_targets_fingerprint(
        dashboard_bootstrap._module_refresh_plan("business_overview")
    )
    clearance_core_fp = dashboard_bootstrap._compute_targets_fingerprint(
        dashboard_bootstrap._module_core_plan("clearance_ranking")
    )

    async def fake_load_state(_session):
        return {
            "business_overview": {
                "status": "refreshing",
                "asset_fingerprint_applied": business_core_fp,
                "details_json": {"refresh_fingerprint_applied": business_refresh_fp},
            },
            "clearance_ranking": {
                "status": "ready",
                "asset_fingerprint_applied": clearance_core_fp,
                "details_json": {},
            },
        }

    monkeypatch.setattr(dashboard_bootstrap, "_collect_existing_assets", fake_collect)
    monkeypatch.setattr(dashboard_bootstrap, "_load_dashboard_asset_state", fake_load_state)
    async def fake_load_active_runs(_session):
        return {}

    monkeypatch.setattr(
        dashboard_bootstrap,
        "_load_active_dashboard_refresh_runs",
        fake_load_active_runs,
    )

    report = await dashboard_bootstrap.inspect_dashboard_assets(object())

    assert report["modules"]["business_overview"]["status"] == "ready"


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
