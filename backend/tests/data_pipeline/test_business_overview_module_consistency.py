import asyncio
import json
from types import SimpleNamespace

from starlette.requests import Request

from backend.routers import dashboard_api_postgresql as dashboard_router
from backend.routers.dashboard_api_postgresql import (
    get_annual_summary_kpi_postgresql,
    get_business_overview_comparison_postgresql,
    get_business_overview_kpi_postgresql,
)


def _make_request(path: str = "/api/dashboard/test"):
    app = SimpleNamespace(state=SimpleNamespace())
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
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

    async def get_annual_summary_kpi(self, *args, **kwargs):
        return self.payload


def test_postgresql_dashboard_router_exposes_expected_contract_paths():
    paths = {route.path for route in dashboard_router.router.routes}
    assert "/api/dashboard/business-overview/kpi" in paths
    assert "/api/dashboard/business-overview/comparison" in paths
    assert "/api/dashboard/annual-summary/kpi" in paths


def test_business_overview_kpi_contract_shape(monkeypatch):
    request = _make_request("/api/dashboard/business-overview/kpi")
    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _PostgresqlServiceStub(
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
            month="2026-03-01",
            platform=None,
        )
    )

    body = json.loads(response.body.decode("utf-8"))
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
    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _PostgresqlServiceStub(
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
            date="2026-03-01",
            platform=None,
        )
    )

    body = json.loads(response.body.decode("utf-8"))
    data = body["data"]
    assert body["success"] is True
    assert "metrics" in data
    assert "target" in data
    assert "sales_amount" in data["metrics"]


def test_annual_summary_kpi_contract_shape(monkeypatch):
    request = _make_request("/api/dashboard/annual-summary/kpi")
    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _PostgresqlServiceStub(
            {
                "gmv": 1000,
                "total_cost": 400,
                "cost_to_revenue_ratio": 0.4,
                "roi": 1.5,
                "gross_margin": 0.2,
                "net_margin": 0.1,
            }
        ),
    )

    response = asyncio.run(
        get_annual_summary_kpi_postgresql(
            request=request,
            granularity="monthly",
            period="2026-03",
        )
    )

    body = json.loads(response.body.decode("utf-8"))
    data = body["data"]
    assert body["success"] is True
    assert {
        "gmv",
        "total_cost",
        "cost_to_revenue_ratio",
        "roi",
        "gross_margin",
        "net_margin",
    }.issubset(data.keys())
