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
        "build_query_service",
        lambda *args, **kwargs: type(
            "FakeQueryService",
            (),
            {
                "get_health_summary": staticmethod(
                    lambda runtime_health=None: {
                        "worker": {"status": "idle"},
                        "tunnel": {"status": "healthy"},
                        "cloud_db": {"status": "reachable"},
                        "queue": {"pending": 0, "running": 0, "retry_waiting": 0},
                    }
                )
            },
        )(),
    )

    app = _build_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        response = await client.get("/api/cloud-sync/health")
        assert response.status_code == 200
        body = response.json()
        assert "worker" in body
        assert "tunnel" in body
        assert "cloud_db" in body


@pytest.mark.asyncio
async def test_manual_trigger_endpoint_enqueues_task(monkeypatch):
    from backend.routers import cloud_sync

    class FakeCommandService:
        async def trigger_sync(self, source_table_name: str):
            return {
                "job_id": "job-1",
                "status": "pending",
                "source_table_name": source_table_name,
            }

    monkeypatch.setattr(
        cloud_sync,
        "build_command_service",
        lambda *args, **kwargs: FakeCommandService(),
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

    class FakeQueryService:
        async def list_tasks(self):
            return [
                {
                    "job_id": "job-1",
                    "status": "pending",
                    "source_table_name": "fact_shopee_orders_daily",
                    "attempt_count": 1,
                }
            ]

        async def get_task(self, job_id: str):
            return {
                "job_id": job_id,
                "status": "pending",
                "source_table_name": "fact_shopee_orders_daily",
                "attempt_count": 1,
            }

    monkeypatch.setattr(cloud_sync, "build_query_service", lambda *args, **kwargs: FakeQueryService())

    app = _build_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        list_response = await client.get("/api/cloud-sync/tasks")
        get_response = await client.get("/api/cloud-sync/tasks/job-1")

        assert list_response.status_code == 200
        assert list_response.json()[0]["job_id"] == "job-1"
        assert list_response.json()[0]["attempt_count"] == 1
        assert get_response.status_code == 200
        assert get_response.json()["job_id"] == "job-1"
        assert get_response.json()["attempt_count"] == 1


@pytest.mark.asyncio
async def test_retry_task_endpoint(monkeypatch):
    from backend.routers import cloud_sync

    class FakeCommandService:
        async def retry_task(self, job_id: str):
            return {"job_id": job_id, "status": "pending"}

    monkeypatch.setattr(cloud_sync, "build_command_service", lambda *args, **kwargs: FakeCommandService())

    app = _build_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        response = await client.post("/api/cloud-sync/tasks/job-1/retry")

        assert response.status_code == 200
        assert response.json()["job_id"] == "job-1"


@pytest.mark.asyncio
async def test_manual_trigger_endpoint_rejects_invalid_table_name(monkeypatch):
    from backend.routers import cloud_sync

    class FakeCommandService:
        async def trigger_sync(self, source_table_name: str):
            return {"job_id": "job-1"}

    monkeypatch.setattr(cloud_sync, "build_command_service", lambda *args, **kwargs: FakeCommandService())

    app = _build_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        response = await client.post(
            "/api/cloud-sync/tasks/trigger",
            json={"source_table_name": 'bad";drop table x;--'},
        )

        assert response.status_code == 422


@pytest.mark.asyncio
async def test_tables_endpoint_returns_table_rows(monkeypatch):
    from backend.routers import cloud_sync

    class FakeQueryService:
        async def list_table_states(self):
            return [
                {
                    "source_table_name": "fact_shopee_orders_daily",
                    "checkpoint": {"last_source_id": 321},
                    "latest_task": {"job_id": "job-1"},
                    "projection": {"status": "pending"},
                }
            ]

    monkeypatch.setattr(cloud_sync, "build_query_service", lambda *args, **kwargs: FakeQueryService())

    app = _build_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        response = await client.get("/api/cloud-sync/tables")

        assert response.status_code == 200
        assert response.json()[0]["source_table_name"] == "fact_shopee_orders_daily"


@pytest.mark.asyncio
async def test_events_endpoint_returns_recent_items(monkeypatch):
    from backend.routers import cloud_sync

    class FakeQueryService:
        async def list_events(self):
            return [
                {
                    "title": "task queued",
                    "status": "pending",
                    "timestamp": "2026-03-26T10:00:00+00:00",
                }
            ]

    monkeypatch.setattr(cloud_sync, "build_query_service", lambda *args, **kwargs: FakeQueryService())

    app = _build_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        response = await client.get("/api/cloud-sync/events")

        assert response.status_code == 200
        assert response.json()[0]["title"] == "task queued"


@pytest.mark.asyncio
async def test_table_action_endpoints(monkeypatch):
    from backend.routers import cloud_sync

    class FakeCommandService:
        async def dry_run_table(self, table_name: str):
            return {"status": "accepted", "source_table_name": table_name}

        async def repair_checkpoint(self, table_name: str):
            return {"status": "accepted", "source_table_name": table_name}

        async def refresh_projection(self, table_name: str):
            return {"status": "accepted", "source_table_name": table_name}

        async def cancel_task(self, job_id: str):
            return {"job_id": job_id, "status": "cancelled"}

    monkeypatch.setattr(cloud_sync, "build_command_service", lambda *args, **kwargs: FakeCommandService())

    app = _build_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        dry_run_response = await client.post("/api/cloud-sync/tables/fact_shopee_orders_daily/dry-run")
        repair_response = await client.post("/api/cloud-sync/tables/fact_shopee_orders_daily/repair-checkpoint")
        projection_response = await client.post("/api/cloud-sync/tables/fact_shopee_orders_daily/refresh-projection")
        cancel_response = await client.post("/api/cloud-sync/tasks/job-1/cancel")

        assert dry_run_response.status_code == 200
        assert repair_response.status_code == 200
        assert projection_response.status_code == 200
        assert cancel_response.status_code == 200
        assert cancel_response.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_overview_runtime_history_and_settings_endpoints(monkeypatch):
    from backend.routers import cloud_sync

    class FakeQueryService:
        async def get_overview_summary(self, runtime_health=None):
            return {
                "worker_status": "running",
                "catch_up_status": "up_to_date",
                "exception_task_count": 0,
            }

        async def get_runtime_summary(self, runtime_health=None):
            return {
                "worker_status": "running",
                "is_running": False,
                "active_task_count": 0,
            }

        async def list_history(self):
            return [{"job_id": "job-1", "result_status": "completed"}]

        async def get_settings(self):
            return {"auto_sync_enabled": True, "pause_mode": "buffer_backlog"}

    monkeypatch.setattr(cloud_sync, "build_query_service", lambda *args, **kwargs: FakeQueryService())

    app = _build_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        overview_response = await client.get("/api/cloud-sync/overview")
        runtime_response = await client.get("/api/cloud-sync/runtime")
        history_response = await client.get("/api/cloud-sync/history")
        settings_response = await client.get("/api/cloud-sync/settings")

        assert overview_response.status_code == 200
        assert overview_response.json()["catch_up_status"] == "up_to_date"
        assert runtime_response.status_code == 200
        assert "is_running" in runtime_response.json()
        assert history_response.status_code == 200
        assert history_response.json()[0]["job_id"] == "job-1"
        assert settings_response.status_code == 200
        assert settings_response.json()["auto_sync_enabled"] is True


@pytest.mark.asyncio
async def test_sync_now_retry_failed_and_update_settings_endpoints(monkeypatch):
    from backend.routers import cloud_sync

    class FakeCommandService:
        async def sync_now(self):
            return {"status": "submitted", "detail": "catch_up"}

        async def retry_failed(self):
            return {"status": "submitted", "detail": "retry_failed"}

        async def update_settings(self, enabled: bool):
            return {"status": "updated", "metadata": {"auto_sync_enabled": enabled}}

    monkeypatch.setattr(cloud_sync, "build_command_service", lambda *args, **kwargs: FakeCommandService())

    app = _build_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        sync_now_response = await client.post("/api/cloud-sync/sync-now")
        retry_failed_response = await client.post("/api/cloud-sync/retry-failed")
        settings_update_response = await client.put("/api/cloud-sync/settings", json={"auto_sync_enabled": False})

        assert sync_now_response.status_code == 200
        assert sync_now_response.json()["detail"] == "catch_up"
        assert retry_failed_response.status_code == 200
        assert retry_failed_response.json()["detail"] == "retry_failed"
        assert settings_update_response.status_code == 200
        assert settings_update_response.json()["metadata"]["auto_sync_enabled"] is False
