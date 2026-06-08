from datetime import datetime, UTC
import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from backend.routers import auth as auth_router
from backend.schemas.auth import RefreshTokenRequest


def _scalar_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _refresh_request_stub(refresh_token: str):
    return SimpleNamespace(
        cookies={"refresh_token": refresh_token},
        headers={},
        client=SimpleNamespace(host="127.0.0.1"),
        url=SimpleNamespace(scheme="http"),
    )


def _refresh_request_stub_with_access(refresh_token: str, access_token: str):
    request = _refresh_request_stub(refresh_token)
    request.cookies = {"refresh_token": refresh_token, "access_token": access_token}
    return request


class _TempSession:
    def __init__(self):
        self.execute = AsyncMock(return_value=_scalar_result(None))
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_refresh_route_verifies_refresh_token_type(monkeypatch):
    refresh_token = "refresh-token-value"
    token_pairs = {
        "access_token": "new-access-token",
        "refresh_token": "new-refresh-token",
    }
    verify_calls = []

    def fake_verify_token(token, token_type="access"):
        verify_calls.append((token, token_type))
        return {"user_id": 101, "type": token_type}

    async def fake_refresh_token_pair(token, session_id=None):
        assert token == refresh_token
        assert session_id is None
        return token_pairs

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result(
                SimpleNamespace(
                    user_id=101,
                    status="active",
                    is_active=True,
                    locked_until=None,
                )
            )
        ]
    )

    monkeypatch.setattr(auth_router.auth_service, "verify_token", fake_verify_token)
    monkeypatch.setattr(
        auth_router.auth_service,
        "refresh_token_pair",
        fake_refresh_token_pair,
    )
    monkeypatch.setattr("backend.models.database.AsyncSessionLocal", lambda: _TempSession())

    response = await auth_router.refresh_token(
        http_request=_refresh_request_stub(refresh_token),
        request_body=RefreshTokenRequest(refresh_token=refresh_token),
        db=db,
    )

    assert response.status_code == 200
    assert response.body
    assert verify_calls == [
        (refresh_token, "refresh"),
    ]


@pytest.mark.asyncio
async def test_refresh_route_keeps_stable_session_id(monkeypatch):
    refresh_token = "refresh-token-value"
    access_token = "access-token-value"
    token_pairs = {
        "access_token": "new-access-token",
        "refresh_token": "new-refresh-token",
    }
    session = SimpleNamespace(
        session_id="stable-session-id",
        user_id=101,
        is_active=True,
        expires_at=datetime.max.replace(tzinfo=UTC),
        last_active_at=datetime.now(UTC),
    )

    def fake_verify_token(token, token_type="access"):
        assert token == refresh_token
        assert token_type == "refresh"
        return {"user_id": 101, "type": "refresh", "sid": "stable-session-id"}

    async def fake_refresh_token_pair(token, session_id=None):
        assert token == refresh_token
        assert session_id == "stable-session-id"
        return token_pairs

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result(
                SimpleNamespace(
                    user_id=101,
                    status="active",
                    is_active=True,
                    locked_until=None,
                )
            ),
            _scalar_result(session),
            _scalar_result(session),
        ]
    )
    db.commit = AsyncMock()

    monkeypatch.setattr(auth_router.auth_service, "verify_token", fake_verify_token)
    monkeypatch.setattr(auth_router.auth_service, "refresh_token_pair", fake_refresh_token_pair)

    response = await auth_router.refresh_token(
        http_request=_refresh_request_stub_with_access(refresh_token, access_token),
        request_body=RefreshTokenRequest(refresh_token=refresh_token),
        db=db,
    )

    assert response.status_code == 200
    assert session.session_id == "stable-session-id"
    assert db.commit.await_count == 1


@pytest.mark.asyncio
async def test_refresh_route_fails_closed_when_blacklist_storage_unavailable(monkeypatch):
    refresh_token = "refresh-token-value"

    def fake_verify_token(token, token_type="access"):
        assert token == refresh_token
        assert token_type == "refresh"
        return {"user_id": 101, "type": "refresh"}

    async def fake_refresh_token_pair(token, session_id=None):
        assert session_id is None
        raise HTTPException(status_code=503, detail="Refresh token service unavailable")

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result(
                SimpleNamespace(
                    user_id=101,
                    status="active",
                    is_active=True,
                    locked_until=None,
                )
            )
        ]
    )

    monkeypatch.setattr(auth_router.auth_service, "verify_token", fake_verify_token)
    monkeypatch.setattr(
        auth_router.auth_service,
        "refresh_token_pair",
        fake_refresh_token_pair,
    )

    with pytest.raises(HTTPException) as exc_info:
        await auth_router.refresh_token(
            http_request=_refresh_request_stub(refresh_token),
            request_body=RefreshTokenRequest(refresh_token=refresh_token),
            db=db,
        )

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_logout_revokes_current_session_and_refresh_token(monkeypatch):
    request = SimpleNamespace(
        cookies={
            "access_token": "access-token-value",
            "refresh_token": "refresh-token-value",
        },
        headers={},
        client=SimpleNamespace(host="127.0.0.1"),
    )
    current_user = SimpleNamespace(user_id=101)
    session = SimpleNamespace(is_active=True)
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_result(session))
    db.commit = AsyncMock()

    audit_log = AsyncMock()
    refresh_revoke = AsyncMock(return_value=True)

    monkeypatch.setattr(auth_router.audit_service, "log_action", audit_log)
    monkeypatch.setattr(
        auth_router.auth_service,
        "verify_token",
        lambda token: {"user_id": 101, "sid": "stable-session-id", "type": "access"},
    )
    monkeypatch.setattr(auth_router.auth_service, "revoke_refresh_token", refresh_revoke, raising=False)

    response = await auth_router.logout(
        request=request,
        current_user=current_user,
        db=db,
    )

    assert session.is_active is False
    assert db.commit.await_count >= 1
    compiled_session_query = str(
        db.execute.await_args_list[0].args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "stable-session-id" in compiled_session_query
    refresh_revoke.assert_awaited_once_with("refresh-token-value")
    set_cookie_headers = response.headers.getlist("set-cookie")
    assert any("access_token=" in header for header in set_cookie_headers)
    assert any("refresh_token=" in header for header in set_cookie_headers)


def test_logout_route_accepts_any_authenticated_user_dependency():
    signature = inspect.signature(auth_router.logout)
    dependency = signature.parameters["current_user"].default.dependency

    assert dependency is auth_router.get_current_user
