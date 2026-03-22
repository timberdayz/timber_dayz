import importlib
import json
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


def test_environment_examples_document_dashboard_router_flags():
    for path_str in (".env.example", "env.development.example", "env.production.example"):
        text = Path(path_str).read_text(encoding="utf-8")
        assert "USE_POSTGRESQL_DASHBOARD_ROUTER=" in text


@pytest_asyncio.fixture
async def switched_app(monkeypatch):
    import backend.main as main_module

    monkeypatch.setenv("USE_POSTGRESQL_DASHBOARD_ROUTER", "true")
    reloaded = importlib.reload(main_module)
    yield reloaded.app
    monkeypatch.delenv("USE_POSTGRESQL_DASHBOARD_ROUTER", raising=False)
    importlib.reload(main_module)


@pytest.mark.asyncio
async def test_main_switches_to_postgresql_dashboard_router(switched_app, monkeypatch):
    class _PostgresqlServiceStub:
        async def get_business_overview_kpi(self, month, platform):
            return {
                "gmv": 321,
                "order_count": 10,
                "visitor_count": 200,
                "conversion_rate": 5,
                "avg_order_value": 32.1,
                "attach_rate": 1.5,
                "labor_efficiency": 0,
            }

        async def get_business_overview_shop_racing(self, granularity, target_date, group_by):
            return [{"name": "shop-a", "gmv": 123, "rank": 1}]

        async def get_business_overview_operational_metrics(self, month, platform):
            return {
                "monthly_target": 1000,
                "monthly_total_achieved": 800,
                "estimated_expenses": 300,
                "operating_result_text": "盈利",
            }

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
        lambda: _PostgresqlServiceStub(),
    )

    async with AsyncClient(
        transport=ASGITransport(app=switched_app),
        base_url="http://localhost",
    ) as client:
        response = await client.get("/api/dashboard/business-overview/kpi", params={"month": "2026-03-01"})

    body = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 200
    assert body["data"]["gmv"] == 321

    async with AsyncClient(
        transport=ASGITransport(app=switched_app),
        base_url="http://localhost",
    ) as client:
        shop_racing = await client.get(
            "/api/dashboard/business-overview/shop-racing",
            params={"granularity": "monthly", "date": "2026-03-01", "group_by": "shop"},
        )
        operational = await client.get(
            "/api/dashboard/business-overview/operational-metrics",
            params={"month": "2026-03-01"},
        )
        target_completion = await client.get(
            "/api/dashboard/annual-summary/target-completion",
            params={"granularity": "yearly", "period": "2026"},
        )

    shop_body = json.loads(shop_racing.content.decode("utf-8"))
    operational_body = json.loads(operational.content.decode("utf-8"))
    target_completion_body = json.loads(target_completion.content.decode("utf-8"))
    assert shop_racing.status_code == 200
    assert shop_body["data"][0]["rank"] == 1
    assert operational.status_code == 200
    assert operational_body["data"]["operating_result_text"] == "盈利"
    assert target_completion.status_code == 200
    assert target_completion_body["data"]["achievement_rate_gmv"] == 80.0
