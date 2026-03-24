import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


def _build_test_app():
    from backend.dependencies.auth import require_admin
    from backend.routers import cloud_sync

    app = FastAPI()
    app.include_router(cloud_sync.router)

    async def override_admin():
        return {"user_id": 1, "is_superuser": True}

    app.dependency_overrides[require_admin] = override_admin
    return app


@pytest.mark.asyncio
async def test_cloud_sync_health_endpoint_returns_worker_status(monkeypatch):
    from backend.routers import cloud_sync

    monkeypatch.setattr(
        cloud_sync,
        "build_health_provider",
        lambda: lambda request=None: {
            "worker": {"status": "idle"},
            "tunnel": {"status": "healthy"},
            "queue": {"pending": 0},
        },
    )

    app = _build_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        response = await client.get("/api/cloud-sync/health")
        assert response.status_code == 200
        body = response.json()
        assert "worker" in body
        assert "tunnel" in body


@pytest.mark.asyncio
async def test_manual_trigger_endpoint_enqueues_task(monkeypatch):
    from backend.routers import cloud_sync

    class FakeDispatchService:
        def enqueue_manual(self, source_table_name: str):
            return {
                "job_id": "job-1",
                "status": "pending",
                "source_table_name": source_table_name,
            }

    monkeypatch.setattr(
        cloud_sync,
        "build_dispatch_service",
        lambda: FakeDispatchService(),
    )

    app = _build_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        response = await client.post(
            "/api/cloud-sync/tasks/trigger",
            json={"source_table_name": "fact_shopee_orders_daily"},
        )
        assert response.status_code == 200
        assert response.json()["job_id"] == "job-1"


@pytest.mark.asyncio
async def test_list_and_get_task_endpoints(monkeypatch):
    from backend.routers import cloud_sync

    class FakeDispatchService:
        def list_tasks(self):
            return [{"job_id": "job-1", "status": "pending", "source_table_name": "fact_shopee_orders_daily"}]

        def get_task(self, job_id: str):
            return {"job_id": job_id, "status": "pending", "source_table_name": "fact_shopee_orders_daily"}

    monkeypatch.setattr(cloud_sync, "build_dispatch_service", lambda: FakeDispatchService())

    app = _build_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        list_response = await client.get("/api/cloud-sync/tasks")
        get_response = await client.get("/api/cloud-sync/tasks/job-1")

        assert list_response.status_code == 200
        assert list_response.json()[0]["job_id"] == "job-1"
        assert get_response.status_code == 200
        assert get_response.json()["job_id"] == "job-1"


@pytest.mark.asyncio
async def test_retry_task_endpoint(monkeypatch):
    from backend.routers import cloud_sync

    class FakeDispatchService:
        def retry(self, job_id: str):
            return {"job_id": job_id, "status": "pending"}

    monkeypatch.setattr(cloud_sync, "build_dispatch_service", lambda: FakeDispatchService())

    app = _build_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        response = await client.post("/api/cloud-sync/tasks/job-1/retry")

        assert response.status_code == 200
        assert response.json()["job_id"] == "job-1"


@pytest.mark.asyncio
async def test_manual_trigger_endpoint_rejects_invalid_table_name(monkeypatch):
    from backend.routers import cloud_sync

    class FakeDispatchService:
        def enqueue_manual(self, source_table_name: str):
            return {"job_id": "job-1"}

    monkeypatch.setattr(cloud_sync, "build_dispatch_service", lambda: FakeDispatchService())

    app = _build_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        response = await client.post(
            "/api/cloud-sync/tasks/trigger",
            json={"source_table_name": 'bad";drop table x;--'},
        )

        assert response.status_code == 422
