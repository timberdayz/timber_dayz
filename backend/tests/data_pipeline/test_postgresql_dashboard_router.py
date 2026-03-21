import asyncio
import json
from types import SimpleNamespace

from starlette.requests import Request

from backend.routers.dashboard_api_postgresql import (
    get_annual_summary_kpi_postgresql,
    get_business_overview_comparison_postgresql,
    get_business_overview_kpi_postgresql,
    get_business_overview_operational_metrics_postgresql,
    get_business_overview_shop_racing_postgresql,
    get_business_overview_traffic_ranking_postgresql,
    router,
)


def _make_request(path: str):
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


def test_postgresql_kpi_route_returns_service_payload(monkeypatch):
    class _ServiceStub:
        async def get_business_overview_kpi(self, month, platform):
            return {
                "gmv": 123,
                "order_count": 10,
                "visitor_count": 200,
                "conversion_rate": 5,
                "avg_order_value": 12.3,
                "attach_rate": 1.2,
                "labor_efficiency": 0,
            }

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    response = asyncio.run(
        get_business_overview_kpi_postgresql(
            request=_make_request("/api/dashboard/business-overview/kpi"),
            month="2026-03-01",
            platform=None,
        )
    )

    body = json.loads(response.body.decode("utf-8"))
    assert body["success"] is True
    assert body["data"]["gmv"] == 123


def test_postgresql_comparison_route_returns_service_payload(monkeypatch):
    class _ServiceStub:
        async def get_business_overview_comparison(self, granularity, target_date, platform):
            return {
                "metrics": {
                    "sales_amount": {"today": 100, "yesterday": 90, "average": 10, "change": 11.11}
                },
                "target": {"sales_amount": 120, "achievement_rate": 83.33},
            }

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    response = asyncio.run(
        get_business_overview_comparison_postgresql(
            request=_make_request("/api/dashboard/business-overview/comparison"),
            granularity="monthly",
            date="2026-03-01",
            platform=None,
        )
    )

    body = json.loads(response.body.decode("utf-8"))
    assert body["success"] is True
    assert "metrics" in body["data"]


def test_postgresql_annual_summary_kpi_route_returns_service_payload(monkeypatch):
    class _ServiceStub:
        async def get_annual_summary_kpi(self, granularity, period):
            return {
                "gmv": 300,
                "total_cost": 100,
                "profit": 70,
                "gross_margin": 23.33,
                "net_margin": -10.0,
                "roi": -0.3,
            }

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    response = asyncio.run(
        get_annual_summary_kpi_postgresql(
            request=_make_request("/api/dashboard/annual-summary/kpi"),
            granularity="yearly",
            period="2026",
        )
    )

    body = json.loads(response.body.decode("utf-8"))
    assert body["success"] is True
    assert body["data"]["roi"] == -0.3


def test_postgresql_shop_racing_route_returns_service_payload(monkeypatch):
    class _ServiceStub:
        async def get_business_overview_shop_racing(self, granularity, target_date, group_by):
            return [{"name": "shop-a", "gmv": 100, "rank": 1}]

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    response = asyncio.run(
        get_business_overview_shop_racing_postgresql(
            request=_make_request("/api/dashboard/business-overview/shop-racing"),
            granularity="monthly",
            date="2026-03-01",
            group_by="shop",
            platforms=None,
        )
    )

    body = json.loads(response.body.decode("utf-8"))
    assert body["success"] is True
    assert body["data"][0]["rank"] == 1


def test_postgresql_traffic_ranking_route_returns_service_payload(monkeypatch):
    class _ServiceStub:
        async def get_business_overview_traffic_ranking(self, granularity, target_date, dimension):
            return [{"name": "shop-a", "visitor_count": 100, "rank": 1}]

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    response = asyncio.run(
        get_business_overview_traffic_ranking_postgresql(
            request=_make_request("/api/dashboard/business-overview/traffic-ranking"),
            granularity="monthly",
            dimension="visitor",
            date="2026-03-01",
            platforms=None,
            shops=None,
        )
    )

    body = json.loads(response.body.decode("utf-8"))
    assert body["success"] is True
    assert body["data"][0]["rank"] == 1


def test_postgresql_operational_metrics_route_returns_service_payload(monkeypatch):
    class _ServiceStub:
        async def get_business_overview_operational_metrics(self, month, platform):
            return {
                "monthly_target": 100,
                "monthly_total_achieved": 80,
                "estimated_expenses": 30,
                "operating_result_text": "盈利",
            }

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    response = asyncio.run(
        get_business_overview_operational_metrics_postgresql(
            request=_make_request("/api/dashboard/business-overview/operational-metrics"),
            month="2026-03-01",
            platform=None,
        )
    )

    body = json.loads(response.body.decode("utf-8"))
    assert body["success"] is True
    assert body["data"]["operating_result_text"] == "盈利"


def test_postgresql_dashboard_router_exposes_compatibility_paths():
    paths = {route.path for route in router.routes}
    assert "/api/dashboard/business-overview/kpi" in paths
    assert "/api/dashboard/business-overview/comparison" in paths
    assert "/api/dashboard/business-overview/shop-racing" in paths
    assert "/api/dashboard/business-overview/traffic-ranking" in paths
    assert "/api/dashboard/business-overview/inventory-backlog" in paths
    assert "/api/dashboard/business-overview/operational-metrics" in paths
    assert "/api/dashboard/clearance-ranking" in paths
    assert "/api/dashboard/annual-summary/kpi" in paths
    assert "/api/dashboard/annual-summary/trend" in paths
    assert "/api/dashboard/annual-summary/platform-share" in paths
    assert "/api/dashboard/annual-summary/by-shop" in paths
    assert "/api/dashboard/annual-summary/target-completion" in paths
