import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

from backend.routers.dashboard_api_postgresql import (
    get_annual_summary_by_shop_postgresql,
    get_annual_summary_kpi_postgresql,
    get_annual_summary_target_completion_postgresql,
    get_annual_summary_trend_postgresql,
    get_business_overview_comparison_postgresql,
    get_business_overview_inventory_backlog_postgresql,
    get_business_overview_kpi_postgresql,
    get_business_overview_operational_metrics_postgresql,
    get_business_overview_shop_racing_postgresql,
    get_business_overview_traffic_ranking_postgresql,
    get_clearance_ranking_postgresql,
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


def test_postgresql_annual_summary_trend_route_returns_service_payload(monkeypatch):
    class _ServiceStub:
        async def get_annual_summary_trend(self, granularity, period):
            return [{"period_month": "2026-03-01", "gmv": 300, "total_cost": 100, "profit": 70}]

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    response = asyncio.run(
        get_annual_summary_trend_postgresql(
            request=_make_request("/api/dashboard/annual-summary/trend"),
            granularity="yearly",
            period="2026",
        )
    )

    body = json.loads(response.body.decode("utf-8"))
    assert body["success"] is True
    assert body["data"][0]["gmv"] == 300


def test_postgresql_annual_summary_by_shop_route_returns_service_payload(monkeypatch):
    class _ServiceStub:
        async def get_annual_summary_by_shop(self, granularity, period):
            return [{"shop_id": "shop-a", "platform_code": "shopee", "gmv": 300, "roi": 0.2}]

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    response = asyncio.run(
        get_annual_summary_by_shop_postgresql(
            request=_make_request("/api/dashboard/annual-summary/by-shop"),
            granularity="yearly",
            period="2026",
        )
    )

    body = json.loads(response.body.decode("utf-8"))
    assert body["success"] is True
    assert body["data"][0]["shop_id"] == "shop-a"


def test_postgresql_annual_summary_target_completion_route_returns_service_payload(monkeypatch):
    class _ServiceStub:
        async def get_annual_summary_target_completion(self, db, granularity, period):
            return {
                "target_gmv": 1000,
                "achieved_gmv": 800,
                "achievement_rate_gmv": 80.0,
                "target_orders": 80,
                "target_profit": None,
                "achieved_profit": 120,
                "achievement_rate_profit": None,
            }

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    response = asyncio.run(
        get_annual_summary_target_completion_postgresql(
            request=_make_request("/api/dashboard/annual-summary/target-completion"),
            granularity="yearly",
            period="2026",
            db=None,
        )
    )

    body = json.loads(response.body.decode("utf-8"))
    assert body["success"] is True
    assert body["data"]["achievement_rate_gmv"] == 80.0


def test_postgresql_shop_racing_route_returns_service_payload(monkeypatch):
    class _ServiceStub:
        async def get_business_overview_shop_racing(self, granularity, target_date, group_by, platform):
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
            platform="shopee",
            platforms=None,
        )
    )

    body = json.loads(response.body.decode("utf-8"))
    assert body["success"] is True
    assert body["data"][0]["rank"] == 1


def test_postgresql_traffic_ranking_route_returns_service_payload(monkeypatch):
    class _ServiceStub:
        async def get_business_overview_traffic_ranking(self, granularity, target_date, dimension, platform):
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
            platform="shopee",
            platforms=None,
            shops=None,
        )
    )

    body = json.loads(response.body.decode("utf-8"))
    assert body["success"] is True
    assert body["data"][0]["rank"] == 1


@pytest.mark.asyncio
async def test_postgresql_traffic_ranking_route_accepts_date_value_alias(monkeypatch):
    captured = {}

    class _ServiceStub:
        async def get_business_overview_traffic_ranking(self, granularity, target_date, dimension, platform):
            captured["granularity"] = granularity
            captured["target_date"] = target_date
            captured["dimension"] = dimension
            captured["platform"] = platform
            return [{"name": "shop-a", "visitor_count": 100, "rank": 1}]

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    app = FastAPI()
    app.include_router(router)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/dashboard/business-overview/traffic-ranking",
            params={
                "granularity": "monthly",
                "dimension": "shop",
                "date_value": "2026-03-01",
                "platform": "shopee",
            },
        )

    body = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 200
    assert body["success"] is True
    assert captured == {
        "granularity": "monthly",
        "target_date": "2026-03-01",
        "dimension": "shop",
        "platform": "shopee",
    }


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


def test_postgresql_inventory_backlog_route_returns_summary_payload(monkeypatch):
    class _ServiceStub:
        async def get_business_overview_inventory_backlog(self, min_days):
            return {
                "summary": {"total_value": 1000, "backlog_30d_value": 300},
                "top_products": [
                    {
                        "platform_code": "shopee",
                        "platform_sku": "SKU-1",
                        "estimated_turnover_days": 45,
                        "risk_level": "medium",
                        "clearance_priority_score": 123.4,
                    }
                ],
            }

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    response = asyncio.run(
        get_business_overview_inventory_backlog_postgresql(
            request=_make_request("/api/dashboard/business-overview/inventory-backlog"),
            days=30,
        )
    )

    body = json.loads(response.body.decode("utf-8"))
    assert body["success"] is True
    assert body["data"]["summary"]["total_value"] == 1000
    assert body["data"]["top_products"][0]["risk_level"] == "medium"


def test_postgresql_clearance_ranking_route_returns_priority_fields(monkeypatch):
    class _ServiceStub:
        async def get_clearance_ranking(self, limit):
            return [
                {
                    "platform_code": "shopee",
                    "platform_sku": "SKU-1",
                    "estimated_turnover_days": 80,
                    "estimated_stagnant_days": 14,
                    "stagnant_snapshot_count": 3,
                    "risk_level": "high",
                    "clearance_priority_score": 456.7,
                }
            ]

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    response = asyncio.run(
        get_clearance_ranking_postgresql(
            request=_make_request("/api/dashboard/clearance-ranking"),
            limit=10,
        )
    )

    body = json.loads(response.body.decode("utf-8"))
    assert body["success"] is True
    assert body["data"][0]["risk_level"] == "high"
    assert body["data"][0]["clearance_priority_score"] == 456.7
