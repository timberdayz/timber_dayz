import asyncio
import json
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from backend.routers.dashboard_api_postgresql import (
    get_business_overview_comparison_postgresql,
    get_business_overview_kpi_postgresql,
    get_business_overview_operational_metrics_postgresql,
    get_business_overview_shop_racing_postgresql,
    get_business_overview_traffic_ranking_postgresql,
)
from backend.services.postgresql_dashboard_service import (
    aggregate_comparison_source_rows,
    reduce_business_overview_kpi_rows,
)


def _make_request(path: str):
    app = SimpleNamespace(state=SimpleNamespace())
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


def test_reduce_kpi_rows_empty_period_returns_additive_zeros_and_ratio_nulls():
    reduced = reduce_business_overview_kpi_rows([])
    assert reduced["gmv"] == 0
    assert reduced["order_count"] == 0
    assert reduced["visitor_count"] == 0
    assert reduced["profit"] == 0
    assert reduced["conversion_rate"] is None
    assert reduced["avg_order_value"] is None
    assert reduced["attach_rate"] is None


def test_aggregate_comparison_source_rows_empty_period_returns_additive_zeros():
    reduced = aggregate_comparison_source_rows([])
    assert reduced["sales_amount"] == 0
    assert reduced["sales_quantity"] == 0
    assert reduced["traffic"] == 0
    assert reduced["profit"] == 0
    assert reduced["conversion_rate"] is None
    assert reduced["avg_order_value"] is None
    assert reduced["attach_rate"] is None


def test_bo_kpi_route_marks_empty_period_meta(monkeypatch):
    class _ServiceStub:
        async def get_business_overview_kpi(self, month=None, platform=None, granularity="monthly", target_date=None):
            return {
                "gmv": 0,
                "order_count": 0,
                "visitor_count": 0,
                "conversion_rate": None,
                "avg_order_value": None,
                "attach_rate": None,
                "labor_efficiency": 0,
                "profit": 0,
            }

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    response = asyncio.run(
        get_business_overview_kpi_postgresql(
            request=_make_request("/api/dashboard/business-overview/kpi"),
            granularity="monthly",
            period_key="2099-01-01",
            platform_code=None,
            shop_id=None,
        )
    )
    body = json.loads(response.body.decode("utf-8"))
    assert body["success"] is True
    assert body["meta"]["is_empty_period"] is True
    assert body["meta"]["data_status"] == "empty_period"
    assert body["data"]["gmv"] == 0
    assert body["data"]["conversion_rate"] is None


def test_bo_comparison_route_marks_empty_period_meta(monkeypatch):
    class _ServiceStub:
        async def get_business_overview_comparison(self, granularity, target_date, platform):
            return {
                "metrics": {
                    "sales_amount": {"today": 0, "yesterday": 0, "average": 0, "change": None},
                    "conversion_rate": {"today": None, "yesterday": None, "average": None, "change": None},
                },
                "target": {"sales_amount": None, "sales_quantity": None, "achievement_rate": None},
            }

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    response = asyncio.run(
        get_business_overview_comparison_postgresql(
            request=_make_request("/api/dashboard/business-overview/comparison"),
            granularity="monthly",
            period_key="2099-01-01",
            platform_code=None,
            shop_id=None,
        )
    )
    body = json.loads(response.body.decode("utf-8"))
    assert body["success"] is True
    assert body["meta"]["is_empty_period"] is True
    assert body["meta"]["data_status"] == "empty_period"
    assert body["data"]["metrics"]["sales_amount"]["change"] is None


@pytest.mark.parametrize(
    "endpoint_fn,path",
    [
        (get_business_overview_traffic_ranking_postgresql, "/api/dashboard/business-overview/traffic-ranking"),
        (get_business_overview_shop_racing_postgresql, "/api/dashboard/business-overview/shop-racing"),
        (get_business_overview_operational_metrics_postgresql, "/api/dashboard/business-overview/operational-metrics"),
    ],
)
def test_bo_list_modules_empty_period_returns_empty_list(monkeypatch, endpoint_fn, path: str):
    class _ServiceStub:
        async def get_business_overview_traffic_ranking(self, **kwargs):
            return []

        async def get_business_overview_shop_racing(self, **kwargs):
            return []

        async def get_business_overview_operational_metrics(self, **kwargs):
            return []

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    response = asyncio.run(
        endpoint_fn(
            request=_make_request(path),
            granularity="monthly",
            period_key="2099-01-01",
            platform_code=None,
            shop_id=None,
        )
    )
    body = json.loads(response.body.decode("utf-8"))
    assert body["success"] is True
    assert body["meta"]["is_empty_period"] is True
    assert body["meta"]["data_status"] == "empty_period"
    assert body["data"] == []

