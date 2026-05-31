from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.models.database import get_async_db
from backend.domains.platform.routers import rbac_admin
from backend.routers import permission, roles


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def scalar_one_or_none(self):
        if isinstance(self._rows, list):
            return self._rows[0] if self._rows else None
        return self._rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


def _admin_user():
    return SimpleNamespace(
        user_id=1,
        username="admin",
        is_active=True,
        is_superuser=False,
        status="active",
        roles=[SimpleNamespace(role_code="admin", role_name="管理员")],
    )


@pytest.mark.asyncio
async def test_admin_rbac_routes_require_authentication():
    from backend.dependencies.auth import get_current_user

    app = FastAPI()
    app.include_router(rbac_admin.router)

    async def override_get_async_db():
        db = SimpleNamespace(execute=AsyncMock(return_value=_ScalarResult([])))
        yield db

    app.dependency_overrides[get_async_db] = override_get_async_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        response = await client.get("/api/admin/permissions")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_permissions_endpoint_returns_catalog():
    from backend.dependencies.auth import get_current_user

    app = FastAPI()
    app.include_router(rbac_admin.router)

    async def override_current_user():
        return _admin_user()

    app.dependency_overrides[get_current_user] = override_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        response = await client.get("/api/admin/permissions")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert any(item["id"] == "permission-management" for item in payload["data"])


@pytest.mark.asyncio
async def test_admin_roles_endpoint_returns_role_code_and_permission_ids():
    from backend.dependencies.auth import get_current_user

    app = FastAPI()
    app.include_router(rbac_admin.router)

    async def override_current_user():
        return _admin_user()

    class FakeDb:
        async def execute(self, _statement):
            return _ScalarResult(
                [
                    SimpleNamespace(
                        role_id=1,
                        role_code="admin",
                        role_name="管理员",
                        description="系统管理员",
                        permissions='["user-management","role-management"]',
                        is_active=True,
                        is_system=True,
                        created_at=datetime(2026, 5, 31, tzinfo=timezone.utc),
                    )
                ]
            )

    async def override_get_async_db():
        yield FakeDb()

    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_async_db] = override_get_async_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        response = await client.get("/api/admin/roles")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"][0]["role_code"] == "admin"
    assert payload["data"][0]["permissions"] == ["user-management", "role-management"]
