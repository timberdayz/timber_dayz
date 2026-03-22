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
