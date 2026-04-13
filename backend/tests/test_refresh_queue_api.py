from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from modules.core.db import RefreshQueueTask


@pytest_asyncio.fixture
async def refresh_queue_client():
    from backend.main import app
    from backend.models.database import get_async_db
    from backend.dependencies.auth import get_current_user

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.execute(text("ATTACH DATABASE ':memory:' AS core"))
        await conn.run_sync(RefreshQueueTask.__table__.create)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_async_db():
        async with session_factory() as session:
            yield session

    async def override_current_user():
        return SimpleNamespace(user_id=1, username="admin", is_active=True, status="active", is_superuser=True, roles=[])

    app.dependency_overrides[get_async_db] = override_get_async_db
    app.dependency_overrides[get_current_user] = override_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        yield client, session_factory

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_refresh_queue_api_lists_tasks_and_filters_by_status(refresh_queue_client):
    client, session_factory = refresh_queue_client

    async with session_factory() as session:
        session.add(
            RefreshQueueTask(
                job_id="job-pending",
                trigger_type="data_ingested",
                pipeline_name="data_ingested_refresh",
                dedupe_key="k1",
                targets_json=["semantic.fact_services_atomic"],
                context_json={"file_id": 1},
                status="pending",
            )
        )
        session.add(
            RefreshQueueTask(
                job_id="job-failed",
                trigger_type="data_ingested",
                pipeline_name="data_ingested_refresh",
                dedupe_key="k2",
                targets_json=["api.clearance_ranking_module"],
                context_json={"file_id": 2},
                status="failed",
                last_error="boom",
            )
        )
        await session.commit()

    response = await client.get("/api/refresh-queue/tasks")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert len(payload["data"]) == 2

    failed_response = await client.get("/api/refresh-queue/tasks", params={"status": "failed"})
    assert failed_response.status_code == 200
    failed_payload = failed_response.json()
    assert failed_payload["success"] is True
    assert len(failed_payload["data"]) == 1
    assert failed_payload["data"][0]["job_id"] == "job-failed"
