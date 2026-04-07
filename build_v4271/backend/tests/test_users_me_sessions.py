from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from backend.routers import users_me


def test_serialize_user_sessions_returns_plain_dicts():
    session = SimpleNamespace(
        session_id="abc",
        device_info="pytest",
        ip_address="127.0.0.1",
        location=None,
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        last_active_at=datetime.now(timezone.utc),
        is_active=True,
    )

    data = users_me.serialize_user_sessions([(session, True)])

    assert data[0]["session_id"] == "abc"
    assert data[0]["is_current"] is True
