from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.models.database import get_async_db
from backend.routers import permission, permissions, roles


def _make_user(role: str = "operator", *, is_superuser: bool = False):
    return SimpleNamespace(
        user_id=1,
        id=1,
        username=f"{role}_user",
        is_active=True,
        status="active",
        is_superuser=is_superuser,
        roles=[SimpleNamespace(role_code=role, role_name=role)],
    )


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return SimpleNamespace(all=lambda: self._value)


@pytest_asyncio.fixture
async def admin_read_auth_client(monkeypatch: pytest.MonkeyPatch):
    from backend.main import app
    from backend.dependencies.auth import get_current_user

    test_app = FastAPI()
    test_app.include_router(roles.router, prefix="/api")
    test_app.include_router(permission.router)
    test_app.include_router(permissions.router)

    async def override_get_async_db():
        db = SimpleNamespace()
        db.execute = AsyncMock(return_value=_ScalarResult([]))
        yield db

    test_app.dependency_overrides[get_async_db] = override_get_async_db

    monkeypatch.setattr(
        "backend.routers.permission.get_permission_service",
        lambda: SimpleNamespace(
            get_permissions_by_category=lambda category=None: [],
            build_permission_tree=lambda: [],
        ),
    )
    monkeypatch.setattr(
        "backend.routers.permissions.get_permission_service",
        lambda: SimpleNamespace(build_permission_tree=lambda: []),
    )

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        yield client, test_app, get_current_user


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/api/roles/",
        "/api/roles/1",
        "/api/roles/permissions/available",
        "/api/system/permissions",
        "/api/system/permissions/tree",
        "/api/permissions/tree",
    ],
)
async def test_admin_read_routes_require_authentication(
    admin_read_auth_client,
    path: str,
):
    client, _app, _get_current_user = admin_read_auth_client

    response = await client.get(path)

    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/api/roles/",
        "/api/roles/1",
        "/api/roles/permissions/available",
        "/api/system/permissions",
        "/api/system/permissions/tree",
        "/api/permissions/tree",
    ],
)
async def test_admin_read_routes_reject_non_admin_users(
    admin_read_auth_client,
    path: str,
):
    client, app, get_current_user = admin_read_auth_client

    async def override_current_user():
        return _make_user("operator")

    app.dependency_overrides[get_current_user] = override_current_user

    response = await client.get(path)

    assert response.status_code == 403
