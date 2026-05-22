from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.app.system_routes import register_system_routes


class _FakeDbSession:
    def execute(self, _query):
        return 1


@pytest_asyncio.fixture
async def system_client(monkeypatch):
    app = FastAPI()
    app.state.dashboard_assets_ready = False
    app.state.dashboard_assets_report = {"ready": False, "reason": "not bootstrapped"}

    settings = SimpleNamespace(DATABASE_URL="sqlite://")

    def get_db():
        return _FakeDbSession()

    class _FakeExecutorManager:
        async def check_health(self, timeout=2.0):
            return {
                "overall_status": "healthy",
                "cpu_executor": {"status": "healthy"},
                "io_executor": {"status": "healthy"},
            }

    monkeypatch.setattr(
        "backend.services.executor_manager.get_executor_manager",
        lambda: _FakeExecutorManager(),
    )

    register_system_routes(app, settings, "test-version", get_db)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.asyncio
async def test_live_health_endpoint_is_lightweight(system_client: AsyncClient):
    response = await system_client.get("/api/healthz/live")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "alive"
    assert payload["service"] == "西虹ERP系统API"


@pytest.mark.asyncio
async def test_ready_health_endpoint_reports_unready_when_dashboard_assets_missing(
    system_client: AsyncClient,
):
    response = await system_client.get("/api/healthz/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["checks"]["database"]["status"] == "connected"
    assert payload["checks"]["dashboard"]["status"] == "degraded"

