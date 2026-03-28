from datetime import datetime, UTC
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

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

    async def fake_refresh_token_pair(token):
        assert token == refresh_token
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
        (refresh_token, "refresh"),
    ]
