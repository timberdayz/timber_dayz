"""
Authentication dependency helper tests
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from backend.dependencies.auth import get_current_user, is_admin_user


def test_is_admin_user_accepts_superuser():
    user = SimpleNamespace(is_superuser=True, roles=[])

    assert is_admin_user(user) is True


def test_is_admin_user_accepts_admin_role_code():
    user = SimpleNamespace(
        is_superuser=False,
        roles=[SimpleNamespace(role_code="admin", role_name="whatever")],
    )

    assert is_admin_user(user) is True


def test_is_admin_user_accepts_admin_role_name():
    user = SimpleNamespace(
        is_superuser=False,
        roles=[SimpleNamespace(role_code="finance", role_name="admin")],
    )

    assert is_admin_user(user) is True


def test_is_admin_user_rejects_non_admin_user():
    user = SimpleNamespace(
        is_superuser=False,
        roles=[SimpleNamespace(role_code="finance", role_name="finance")],
    )

    assert is_admin_user(user) is False


def _scalar_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


@pytest.mark.asyncio
async def test_get_current_user_rejects_inactive_session(monkeypatch):
    request = SimpleNamespace(cookies={"access_token": "access-token"})
    user = SimpleNamespace(
        user_id=7,
        username="admin",
        is_active=True,
        status="active",
        roles=[],
    )
    inactive_session = SimpleNamespace(
        session_id="session-id",
        user_id=7,
        is_active=False,
        expires_at=None,
    )
    db = AsyncMock()
    db.execute.side_effect = [_scalar_result(user), _scalar_result(inactive_session)]

    monkeypatch.setattr(
        "backend.dependencies.auth.auth_service.verify_token",
        lambda token: {"user_id": 7},
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(request=request, credentials=None, db=db)

    assert exc_info.value.status_code == 401
