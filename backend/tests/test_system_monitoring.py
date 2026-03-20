from __future__ import annotations

from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from backend.dependencies.auth import get_current_user
from backend.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        yield client


@pytest.mark.asyncio
async def test_resource_usage_requires_admin(client: AsyncClient):
    response = await client.get("/api/system/resource-usage")
    assert response.status_code in [401, 403, 422]


@pytest.mark.asyncio
async def test_resource_usage_allows_superuser_override(client: AsyncClient):
    async def override_current_user():
        return SimpleNamespace(
            user_id=1,
            username="admin",
            is_superuser=True,
            role="admin",
            roles=[],
        )

    app.dependency_overrides[get_current_user] = override_current_user
    try:
        response = await client.get("/api/system/resource-usage")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    data = response.json()
    assert "cpu_usage" in data
    assert "memory_usage" in data
    assert "process_count" in data
    assert "thread_count" in data


@pytest.mark.asyncio
async def test_db_pool_stats_allows_superuser_override(client: AsyncClient):
    async def override_current_user():
        return SimpleNamespace(
            user_id=1,
            username="admin",
            is_superuser=True,
            role="admin",
            roles=[],
        )

    app.dependency_overrides[get_current_user] = override_current_user
    try:
        response = await client.get("/api/system/db-pool-stats")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    data = response.json()
    assert "sync_pool" in data
    assert "async_pool" in data
