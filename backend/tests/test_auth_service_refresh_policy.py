from fastapi import HTTPException
import pytest

from backend.services.auth_service import AuthService


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
