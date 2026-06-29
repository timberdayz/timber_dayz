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
    monkeypatch,
):
    async def _fake_inspect(_session):
        return {
            "ready": False,
            "assets_drift": True,
            "modules": {
                "business_overview": {
                    "status": "drift",
                    "ready": False,
                }
            },
        }

    monkeypatch.setattr(
        "backend.services.data_pipeline.dashboard_bootstrap.inspect_dashboard_assets",
        _fake_inspect,
    )

    response = await system_client.get("/api/healthz/ready")

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "unready"
    assert payload["checks"]["database"]["status"] == "connected"
    assert payload["checks"]["dashboard"]["status"] == "degraded"


@pytest.mark.asyncio
async def test_metrics_endpoint_exposes_cloud_sync_gauges(system_client: AsyncClient, monkeypatch):
    class _FakeAsyncSession:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return None

    class _FakeSyncSession:
        def close(self):
            return None

    class _FakeQueryService:
        async def get_overview_summary(self, runtime_health=None):
            return {
                "pending_catalog_file_count": 2,
                "overdue_pending_catalog_file_count": 1,
                "refresh_failed_task_count": 3,
                "last_receive_at": "2026-06-29T04:00:00+00:00",
            }

        async def get_runtime_summary(self, runtime_health=None):
            return {
                "last_runtime_heartbeat_at": "2026-06-29T04:05:00+00:00",
                "seconds_since_task_heartbeat": 12,
            }

        async def list_table_states(self):
            return [
                {
                    "source_table_name": "fact_shopee_orders_monthly",
                    "receive_log": {"last_receive_at": "2026-06-29T04:00:00+00:00"},
                }
            ]

    class _FakeDashboardService:
        async def get_business_overview_data_freshness(self):
            return {
                "table_checks": [
                    {
                        "table_name": "fact_shopee_orders_monthly",
                        "side": "orders",
                        "stale_hours": 30,
                    }
                ]
            }

    monkeypatch.setattr("backend.models.database.AsyncSessionLocal", lambda: _FakeAsyncSession())
    monkeypatch.setattr("backend.models.database.SessionLocal", lambda: _FakeSyncSession())
    monkeypatch.setattr("backend.services.cloud_sync_admin_query_service.CloudSyncAdminQueryService", lambda session: _FakeQueryService())
    monkeypatch.setattr("backend.services.postgresql_dashboard_service.PostgresqlDashboardService", lambda: _FakeDashboardService())
    monkeypatch.setattr("backend.tasks.scheduled_tasks.detect_auto_ingest_orphan_locks", lambda db: [1])

    response = await system_client.get("/metrics")

    assert response.status_code == 200
    text = response.text
    assert "xihong_cloud_sync_pending_catalog_files_total 2" in text
    assert "xihong_cloud_sync_pending_catalog_files_overdue_total 1" in text
    assert "xihong_cloud_sync_refresh_queue_failed_total 3" in text
    assert 'xihong_cloud_sync_table_receive_age_seconds{source_table_name="fact_shopee_orders_monthly"}' in text
    assert 'xihong_business_table_stale_hours{side="orders",table_name="fact_shopee_orders_monthly"} 30.0' in text
