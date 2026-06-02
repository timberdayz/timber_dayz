from types import SimpleNamespace

import pytest

from backend.domains.platform.routers.notification_websocket import verify_websocket_token


class _FakeWebSocket:
    def __init__(self, cookies=None):
        self.cookies = cookies or {}


@pytest.mark.asyncio
async def test_verify_websocket_token_accepts_cookie_token(monkeypatch):
    websocket = _FakeWebSocket(cookies={"access_token": "cookie-token"})

    monkeypatch.setattr(
        "backend.domains.platform.routers.notification_websocket.auth_service.verify_token",
        lambda token: {"user_id": 9} if token == "cookie-token" else {},
    )

    user_id, error = await verify_websocket_token(websocket, None)

    assert user_id == 9
    assert error is None


@pytest.mark.asyncio
async def test_verify_websocket_token_prefers_query_token_over_cookie(monkeypatch):
    websocket = _FakeWebSocket(cookies={"access_token": "cookie-token"})

    def _verify(token):
        if token == "query-token":
            return {"user_id": 12}
        raise AssertionError(f"unexpected token: {token}")

    monkeypatch.setattr(
        "backend.domains.platform.routers.notification_websocket.auth_service.verify_token",
        _verify,
    )

    user_id, error = await verify_websocket_token(websocket, "query-token")

    assert user_id == 12
    assert error is None
