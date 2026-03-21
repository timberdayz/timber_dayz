from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.dependencies.auth import require_admin
from backend.models.database import get_async_db
from backend.routers import users_admin


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


@pytest.mark.asyncio
async def test_pending_users_route_is_not_shadowed_by_user_id():
    app = FastAPI()
    app.include_router(users_admin.router, prefix="/api")

    fake_rows = [
        SimpleNamespace(
            user_id=1001,
            username="pending_route_user",
            email="pending_route_user@example.com",
            full_name="Pending Route User",
            department="QA",
            status="pending",
            created_at=datetime(2026, 3, 21, tzinfo=timezone.utc),
        )
    ]

    class FakeSession:
        async def execute(self, _statement):
            return _ScalarResult(fake_rows)

    async def override_require_admin():
        return SimpleNamespace(user_id=1, username="admin", is_superuser=True)

    async def override_get_async_db():
        yield FakeSession()

    app.dependency_overrides[require_admin] = override_require_admin
    app.dependency_overrides[get_async_db] = override_get_async_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        response = await client.get("/api/users/pending", params={"page": 1, "page_size": 20})

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert data[0]["username"] == "pending_route_user"
