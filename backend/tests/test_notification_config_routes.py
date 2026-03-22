from __future__ import annotations

from types import SimpleNamespace

from backend.routers import notification_config


async def _call_get_smtp_config_without_existing_config(monkeypatch):
    class FakeService:
        async def get_smtp_config(self):
            return None

    monkeypatch.setattr(
        notification_config,
        "get_notification_config_service",
        lambda _db: FakeService(),
    )
    return await notification_config.get_smtp_config(
        db=object(),
        current_user=SimpleNamespace(user_id=1, username="admin"),
    )


def test_get_smtp_config_returns_default_placeholder_when_missing(monkeypatch):
    import asyncio

    response = asyncio.run(_call_get_smtp_config_without_existing_config(monkeypatch))

    assert response.id == 0
    assert response.smtp_server == ""
    assert response.smtp_port == 587
    assert response.username == ""
    assert response.from_email == ""
    assert response.is_active is False
