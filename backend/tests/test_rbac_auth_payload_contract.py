from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.dependencies.auth import require_admin
from backend.models.database import get_async_db
from backend.routers import auth as auth_router
from backend.schemas.auth import LoginRequest


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


@pytest.mark.asyncio
async def test_admin_role_name_in_chinese_is_treated_as_admin():
    from backend.dependencies.auth import is_admin_user

    user = SimpleNamespace(
        is_superuser=False,
        roles=[SimpleNamespace(role_code="finance", role_name="管理员")],
    )

    assert is_admin_user(user) is True


@pytest.mark.asyncio
async def test_auth_me_returns_backend_driven_roles_permissions_and_admin_flag():
    app = FastAPI()
    app.include_router(auth_router.router, prefix="/api")

    async def override_current_user():
        return SimpleNamespace(
            user_id=7,
            username="admin_user",
            email="admin@example.com",
            full_name="管理员",
            is_active=True,
            is_superuser=False,
            created_at=datetime(2026, 5, 31, tzinfo=timezone.utc),
            last_login=datetime(2026, 5, 31, tzinfo=timezone.utc),
            roles=[
                SimpleNamespace(
                    role_id=1,
                    role_code="admin",
                    role_name="管理员",
                    permissions='["user-management","role-management"]',
                    is_system=True,
                )
            ],
        )

    app.dependency_overrides[auth_router.get_current_user] = override_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        response = await client.get("/api/auth/me")

    assert response.status_code == 200
    payload = response.json()
    assert payload["roles"] == ["admin"]
    assert payload["permissions"] == ["*"]
    assert payload["is_admin"] is True


@pytest.mark.asyncio
async def test_login_response_contains_backend_permissions_payload(monkeypatch):
    user = SimpleNamespace(
        user_id=9,
        username="admin",
        email="admin@example.com",
        full_name="系统管理员",
        password_hash="hashed",
        status="active",
        is_active=True,
        failed_login_attempts=0,
        locked_until=None,
        last_login=None,
        roles=[
            SimpleNamespace(
                role_id=1,
                role_code="admin",
                role_name="管理员",
                permissions='["user-management","role-management"]',
                is_system=True,
            )
        ],
    )
    db = SimpleNamespace(
        execute=AsyncMock(side_effect=[_ScalarResult(user), _ScalarResult(None)]),
        commit=AsyncMock(),
        add=lambda _obj: None,
    )
    request = SimpleNamespace(
        client=SimpleNamespace(host="127.0.0.1"),
        headers={"User-Agent": "pytest"},
        cookies={},
        url=SimpleNamespace(scheme="http"),
    )

    monkeypatch.setattr(auth_router.auth_service, "verify_password", lambda plain, hashed: True)
    monkeypatch.setattr(
        auth_router.auth_service,
        "create_token_pair",
        lambda **_kwargs: {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "token_type": "bearer",
        },
    )
    monkeypatch.setattr(auth_router.audit_service, "log_action", AsyncMock())

    response = await auth_router.login(
        credentials=LoginRequest(username="admin", password="password", remember_me=False),
        request=request,
        db=db,
    )

    assert response.status_code == 200
    payload = response.body.decode("utf-8")
    assert '"roles":["admin"]' in payload
    assert '"permissions":["*"]' in payload
    assert '"is_admin":true' in payload
