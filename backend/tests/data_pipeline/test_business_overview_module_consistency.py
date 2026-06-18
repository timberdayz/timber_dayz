import asyncio
import json
from types import SimpleNamespace

from starlette.requests import Request

from backend.routers import dashboard_api_postgresql as dashboard_router
from backend.domains.business.routers.dashboard_api_postgresql import (
    get_business_overview_bootstrap_postgresql,
    get_business_overview_comparison_postgresql,
    get_business_overview_kpi_postgresql,
    get_business_overview_traffic_ranking_postgresql,
)


def _make_request(path: str = "/api/dashboard/test"):
    app = SimpleNamespace(
        state=SimpleNamespace(
            dashboard_assets_report={
                "modules": {
                    "business_overview": {
                        "status": "ready",
                        "ready": True,
                    }
                }
            }
        )
    )
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


class _PostgresqlServiceStub:
    def __init__(self, payload):
        self.payload = payload

    async def get_business_overview_kpi(self, *args, **kwargs):
        return self.payload

    async def get_business_overview_comparison(self, *args, **kwargs):
        return self.payload

    async def get_business_overview_operational_metrics(self, *args, **kwargs):
        return self.payload

    async def get_business_overview_traffic_ranking(self, *args, **kwargs):
        return self.payload

    async def get_business_overview_shop_racing(self, *args, **kwargs):
        return self.payload

    async def get_business_overview_identity_health(self, *args, **kwargs):
        return {
            "status": "warning",
            "warning_count": 1,
            "warnings": [
                {
                    "warning_code": "traffic_without_order_match_due_to_identity",
                    "platform_code": "shopee",
                    "shop_id": "1308200832",
                    "shop_account_id": "shopee_sg_xhkj33_local",
                }
            ],
        }


def _patch_dashboard_service(monkeypatch, service):
    monkeypatch.setattr(
        "backend.domains.business.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: service,
    )
    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: service,
    )


def test_postgresql_dashboard_router_exposes_expected_contract_paths():
    paths = {route.path for route in dashboard_router.router.routes}
    assert "/api/dashboard/business-overview/kpi" in paths
    assert "/api/dashboard/business-overview/comparison" in paths
    assert "/api/dashboard/business-overview/bootstrap" in paths


def test_business_overview_kpi_contract_shape(monkeypatch):
    request = _make_request("/api/dashboard/business-overview/kpi")
    _patch_dashboard_service(
        monkeypatch,
        _PostgresqlServiceStub(
            {
                "gmv": 100,
                "order_count": 10,
                "visitor_count": 200,
                "conversion_rate": 5.0,
                "avg_order_value": 10.0,
                "attach_rate": 1.2,
                "labor_efficiency": 50.0,
            }
        ),
    )

    response = asyncio.run(
        get_business_overview_kpi_postgresql(
            request=request,
            granularity="monthly",
            period_key="2026-03-01",
            platform_code=None,
            shop_id=None,
        )
    )

    body = json.loads(response.body.decode("utf-8"))
    assert "meta" in body
    assert body["meta"]["period_key"] == "2026-03-01"
    assert body["meta"]["granularity"] == "monthly"
    assert body["meta"].get("platform_code") in (None, "")
    data = body["data"]
    assert body["success"] is True
    assert {
        "gmv",
        "order_count",
        "visitor_count",
        "conversion_rate",
        "avg_order_value",
        "attach_rate",
        "labor_efficiency",
    }.issubset(data.keys())


def test_business_overview_comparison_contract_shape(monkeypatch):
    request = _make_request("/api/dashboard/business-overview/comparison")
    _patch_dashboard_service(
        monkeypatch,
        _PostgresqlServiceStub(
            {
                "metrics": {
                    "sales_amount": {
                        "today": 100,
                        "yesterday": 90,
                        "average": 95,
                        "change": 11.11,
                    }
                },
                "target": {
                    "sales_amount": 120,
                    "achievement_rate": 83.33,
                },
            }
        ),
    )

    response = asyncio.run(
        get_business_overview_comparison_postgresql(
            request=request,
            granularity="monthly",
            period_key="2026-03-01",
            platform_code=None,
            shop_id=None,
        )
    )

    body = json.loads(response.body.decode("utf-8"))
    assert "meta" in body
    assert body["meta"]["period_key"] == "2026-03-01"
    assert body["meta"]["granularity"] == "monthly"
    data = body["data"]
    assert body["success"] is True
    assert "metrics" in data
    assert "target" in data
    assert "sales_amount" in data["metrics"]


def test_business_overview_bootstrap_contract_shape(monkeypatch):
    request = _make_request("/api/dashboard/business-overview/bootstrap")
    _patch_dashboard_service(
        monkeypatch,
        _PostgresqlServiceStub(
            {
                "any": "payload",
            }
        ),
    )

    response = asyncio.run(
        get_business_overview_bootstrap_postgresql(
            request=request,
            granularity="monthly",
            period_key="2026-03-01",
            platform_code=None,
            shop_id=None,
        )
    )

    body = json.loads(response.body.decode("utf-8"))
    assert "meta" in body
    assert body["meta"]["granularity"] == "monthly"
    assert body["meta"]["period_key"] == "2026-03-01"
    data = body["data"]
    assert body["success"] is True
    assert {
        "kpi",
        "comparison",
        "operational_metrics",
        "traffic_ranking",
        "shop_racing",
    }.issubset(data.keys())


def test_business_overview_traffic_ranking_meta_includes_identity_health(monkeypatch):
    request = _make_request("/api/dashboard/business-overview/traffic-ranking")
    _patch_dashboard_service(
        monkeypatch,
        _PostgresqlServiceStub(
            [
                {
                    "platform_code": "shopee",
                    "shop_id": "1308200832",
                    "visitor_count": 200,
                    "page_views": 400,
                    "uv_conversion_rate": None,
                    "pv_conversion_rate": None,
                }
            ]
        ),
    )

    response = asyncio.run(
        get_business_overview_traffic_ranking_postgresql(
            request=request,
            granularity="monthly",
            dimension="visitor",
            period_key="2026-06-01",
            platform_code=None,
            shop_id=None,
        )
    )

    body = json.loads(response.body.decode("utf-8"))
    assert body["success"] is True
    assert body["meta"]["identity_health"]["status"] == "warning"
    assert body["meta"]["identity_health"]["warning_count"] == 1
    assert (
        body["meta"]["identity_health"]["warnings"][0]["warning_code"]
        == "traffic_without_order_match_due_to_identity"
    )
