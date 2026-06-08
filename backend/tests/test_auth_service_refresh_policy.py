from fastapi import HTTPException
import pytest

from backend.services.auth_service import AuthService


class _FakeRedis:
    def __init__(self):
        self.values = {}

    async def exists(self, key):
        return 1 if key in self.values else 0

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, ex=None, nx=False):
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True


@pytest.mark.asyncio
async def test_refresh_token_pair_rejects_when_redis_unavailable(monkeypatch):
    service = AuthService()
    refresh_token = "refresh-token"

    monkeypatch.setattr(service, "_get_redis_client", lambda: None)
    monkeypatch.setattr(
        service,
        "verify_token",
        lambda token, token_type="access": {
            "user_id": 11,
            "username": "admin",
            "roles": ["admin"],
            "exp": 4102444800,
            "type": token_type,
        },
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.refresh_token_pair(refresh_token)

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_refresh_token_pair_is_idempotent_during_rotation_grace(monkeypatch):
    service = AuthService()
    redis = _FakeRedis()
    refresh_token = "refresh-token"
    payload = {
        "user_id": 11,
        "username": "admin",
        "roles": ["admin"],
        "sid": "stable-session-id",
        "exp": 4102444800,
        "type": "refresh",
    }

    monkeypatch.setattr(service, "_get_redis_client", lambda: redis)
    monkeypatch.setattr(
        service,
        "verify_token",
        lambda token, token_type="access": payload,
    )

    first = await service.refresh_token_pair(refresh_token)
    second = await service.refresh_token_pair(refresh_token)

    assert second == first
    assert second["access_token"]
    assert second["refresh_token"]
