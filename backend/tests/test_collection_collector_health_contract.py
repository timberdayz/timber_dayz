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
async def collector_health_client(monkeypatch: pytest.MonkeyPatch):
    app = FastAPI()
    app.state.runtime_mode = "collector"
    app.state.dashboard_assets_ready = False
    app.state.dashboard_assets_report = {"ready": False, "reason": "drift"}
    app.state.collection_queue_runner = object()
    app.state.collection_scheduler = object()
    app.state.collection_leader_lock_acquired = False
    app.state.collection_runtime_checks = {}

    settings = SimpleNamespace(DATABASE_URL="postgresql://collector")

    def get_db():
        return _FakeDbSession()

    register_system_routes(app, settings, "test-version", get_db)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.asyncio
async def test_collector_ready_ignores_dashboard_drift_when_runtime_is_healthy(
    collector_health_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "backend.app.system_routes.inspect_dashboard_assets",
        lambda _session: None,
        raising=False,
    )
    monkeypatch.setattr(
        "backend.app.system_routes.collect_collection_runtime_health",
        lambda app, settings: {
            "status": "ready",
            "runtime_mode": "collector",
            "deployment_role": "collector",
            "checks": {
                "redis": {"status": "connected"},
                "encryption": {"status": "configured"},
                "playwright": {"status": "available"},
                "queue_runner": {"status": "running"},
                "scheduler": {"status": "running"},
                "leader_lock": {"status": "standby"},
            },
        },
    )

    response = await collector_health_client.get("/api/healthz/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["runtime_mode"] == "collector"
    assert payload["checks"]["dashboard"]["status"] == "ignored"
    assert payload["checks"]["leader_lock"]["status"] == "standby"


@pytest.mark.asyncio
async def test_collector_ready_fails_when_encryption_key_missing(
    collector_health_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "backend.app.system_routes.collect_collection_runtime_health",
        lambda app, settings: {
            "status": "unready",
            "runtime_mode": "collector",
            "deployment_role": "collector",
            "checks": {
                "redis": {"status": "connected"},
                "encryption": {"status": "error", "reason": "ACCOUNT_ENCRYPTION_KEY missing"},
                "playwright": {"status": "available"},
                "queue_runner": {"status": "running"},
                "scheduler": {"status": "running"},
                "leader_lock": {"status": "acquired"},
            },
        },
    )

    response = await collector_health_client.get("/api/healthz/ready")

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "unready"
    assert payload["checks"]["encryption"]["status"] == "error"
