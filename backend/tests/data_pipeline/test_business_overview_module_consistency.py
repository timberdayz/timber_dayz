import asyncio
import json
from types import SimpleNamespace

from starlette.requests import Request

from backend.routers import dashboard_api
from backend.routers.dashboard_api import (
    get_annual_summary_kpi,
    get_business_overview_comparison,
    get_business_overview_kpi,
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


class _MetabaseServiceStub:
    def __init__(self, payload):
        self.payload = payload

    async def query_question(self, *args, **kwargs):
        return self.payload


def test_dashboard_data_source_map_freezes_current_dashboard_modules():
    assert dashboard_api.DASHBOARD_DATA_SOURCE_MAP == {
        "business_overview_kpi": {
            "route": "/business-overview/kpi",
            "source": "metabase_question",
            "query_key": "business_overview_kpi",
        },
        "business_overview_comparison": {
            "route": "/business-overview/comparison",
            "source": "metabase_question",
            "query_key": "business_overview_comparison",
        },
        "business_overview_shop_racing": {
            "route": "/business-overview/shop-racing",
            "source": "metabase_question",
            "query_key": "business_overview_shop_racing",
        },
        "business_overview_traffic_ranking": {
            "route": "/business-overview/traffic-ranking",
            "source": "metabase_question",
            "query_key": "business_overview_traffic_ranking",
        },
        "business_overview_inventory_backlog": {
            "route": "/business-overview/inventory-backlog",
            "source": "metabase_question",
            "query_key": "business_overview_inventory_backlog",
        },
        "business_overview_operational_metrics": {
            "route": "/business-overview/operational-metrics",
            "source": "metabase_question",
            "query_key": "business_overview_operational_metrics",
        },
        "clearance_ranking": {
            "route": "/clearance-ranking",
            "source": "metabase_question",
            "query_key": "clearance_ranking",
        },
        "annual_summary_kpi": {
            "route": "/annual-summary/kpi",
            "source": "hybrid_metabase_postgresql",
            "query_key": "annual_summary_kpi",
        },
        "annual_summary_by_shop": {
            "route": "/annual-summary/by-shop",
            "source": "postgresql_service",
            "query_key": "annual_cost_aggregate_by_shop",
        },
        "annual_summary_trend": {
            "route": "/annual-summary/trend",
            "source": "metabase_question",
            "query_key": "annual_summary_trend",
        },
        "annual_summary_platform_share": {
            "route": "/annual-summary/platform-share",
            "source": "metabase_question",
            "query_key": "annual_summary_platform_share",
        },
        "annual_summary_target_completion": {
            "route": "/annual-summary/target-completion",
            "source": "postgresql_sql",
            "query_key": "annual_summary_target_completion",
        },
    }


def test_business_overview_kpi_contract_shape(monkeypatch):
    request = _make_request("/api/dashboard/business-overview/kpi")
    monkeypatch.setattr(
        "backend.routers.dashboard_api.get_metabase_service",
        lambda: _MetabaseServiceStub(
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
        get_business_overview_kpi(
            request=request,
            month="2026-03-01",
            platform=None,
            start_date=None,
            end_date=None,
            platforms=None,
            shops=None,
        )
    )

    body = json.loads(response.body.decode("utf-8"))
    data = body["data"]
    assert body["success"] is True
    assert set(
        [
            "gmv",
            "order_count",
            "visitor_count",
            "conversion_rate",
            "avg_order_value",
            "attach_rate",
            "labor_efficiency",
        ]
    ).issubset(data.keys())


def test_business_overview_comparison_contract_shape(monkeypatch):
    request = _make_request("/api/dashboard/business-overview/comparison")
    monkeypatch.setattr(
        "backend.routers.dashboard_api.get_metabase_service",
        lambda: _MetabaseServiceStub(
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
        get_business_overview_comparison(
            request=request,
            granularity="monthly",
            date="2026-03-01",
            platforms=None,
            shops=None,
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
        "backend.routers.dashboard_api.get_metabase_service",
        lambda: _MetabaseServiceStub(
            {
                "gmv": 1000,
                "order_count": 80,
                "visitor_count": 2000,
                "conversion_rate": 4.0,
                "avg_order_value": 12.5,
                "attach_rate": 1.4,
                "labor_efficiency": 200,
            }
        ),
    )

    async def _cost_aggregate_stub(*args, **kwargs):
        return {
            "total_cost": 400,
            "gmv": 1000,
            "cost_to_revenue_ratio": 0.4,
            "roi": 1.5,
            "gross_margin": 0.2,
            "net_margin": 0.1,
        }

    monkeypatch.setattr(
        "backend.services.annual_cost_aggregate.get_annual_cost_aggregate",
        _cost_aggregate_stub,
    )

    response = asyncio.run(
        get_annual_summary_kpi(
            request=request,
            db=None,
            granularity="monthly",
            period="2026-03",
        )
    )

    body = json.loads(response.body.decode("utf-8"))
    data = body["data"]
    assert body["success"] is True
    assert set(
        [
            "gmv",
            "total_cost",
            "cost_to_revenue_ratio",
            "roi",
            "gross_margin",
            "net_margin",
        ]
    ).issubset(data.keys())
