from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.dependencies.auth import require_admin
from backend.models.database import get_async_db
from backend.routers.notifications import execute_notification_action
from backend.routers import users_admin
from backend.schemas.notification import NotificationActionRequest


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        if isinstance(self._rows, list):
            return self._rows[0] if self._rows else None
        return self._rows


@pytest.mark.asyncio
async def test_pending_users_route_is_not_shadowed_by_user_id():
    app = FastAPI()
    app.include_router(users_admin.router, prefix="/api")

    fake_rows = [
        SimpleNamespace(
            user_id=1001,
            username="pending_route_user",
            email="pending_route_user@example.com",
            full_name="Pending Route User",
            department="QA",
            status="pending",
            created_at=datetime(2026, 3, 21, tzinfo=timezone.utc),
        )
    ]

    class FakeSession:
        async def execute(self, _statement):
            return _ScalarResult(fake_rows)

    async def override_require_admin():
        return SimpleNamespace(user_id=1, username="admin", is_superuser=True)

    async def override_get_async_db():
        yield FakeSession()

    app.dependency_overrides[require_admin] = override_require_admin
    app.dependency_overrides[get_async_db] = override_get_async_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        response = await client.get(
            "/api/users/pending", params={"page": 1, "page_size": 20}
        )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert data[0]["username"] == "pending_route_user"


@pytest.mark.asyncio
async def test_pending_users_count_route_returns_total():
    app = FastAPI()
    app.include_router(users_admin.router, prefix="/api")

    class FakeCountResult:
        def scalar(self):
            return 3

    class FakeSession:
        async def execute(self, _statement):
            return FakeCountResult()

    async def override_require_admin():
        return SimpleNamespace(user_id=1, username="admin", is_superuser=True)

    async def override_get_async_db():
        yield FakeSession()

    app.dependency_overrides[require_admin] = override_require_admin
    app.dependency_overrides[get_async_db] = override_get_async_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        response = await client.get("/api/users/pending-count")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["pending_count"] == 3


@pytest.mark.asyncio
async def test_notification_quick_approve_promotes_pending_user():
    notification = SimpleNamespace(
        notification_id=1,
        recipient_id=99,
        related_user_id=1001,
        is_read=False,
        read_at=None,
    )
    target_user = SimpleNamespace(
        user_id=1001,
        username="pending_route_user",
        status="pending",
        is_active=False,
        approved_at=None,
        approved_by=None,
        roles=[],
    )
    operator_role = SimpleNamespace(role_id=2, role_code="operator", role_name="Operator")
    current_user = SimpleNamespace(
        user_id=99,
        username="admin",
        is_superuser=True,
        roles=[SimpleNamespace(role_code="admin", role_name="Admin")],
    )

    class FakeSession:
        def __init__(self):
            self.added = []
            self.commit = AsyncMock()

        async def execute(self, statement):
            sql = str(statement)
            if "FROM notifications" in sql:
                return _ScalarResult(notification)
            if "FROM dim_users" in sql or "FROM core.dim_users" in sql:
                return _ScalarResult(target_user)
            if "FROM dim_roles" in sql or "FROM core.dim_roles" in sql:
                return _ScalarResult(operator_role)
            return _ScalarResult([])

        def add(self, obj):
            self.added.append(obj)

    db = FakeSession()
    request = SimpleNamespace(
        client=SimpleNamespace(host="127.0.0.1"),
        headers={"User-Agent": "pytest"},
    )

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            "backend.routers.notifications.audit_service.log_action",
            AsyncMock(),
        )
        monkeypatch.setattr(
            "backend.routers.notifications.notify_user_approved",
            AsyncMock(),
        )
        monkeypatch.setattr(
            "backend.routers.notifications.create_notification",
            AsyncMock(),
        )

        response = await execute_notification_action(
            notification_id=1,
            action_request=NotificationActionRequest(action_type="approve_user"),
            request=request,
            current_user=current_user,
            db=db,
        )

    assert response.success is True
    assert target_user.status == "active"
    assert target_user.is_active is True
    assert target_user.approved_by == 99
    assert target_user.roles == [operator_role]


@pytest.mark.asyncio
async def test_reject_users_batch_best_effort_returns_per_item_results():
    app = FastAPI()
    app.include_router(users_admin.router, prefix="/api")

    pending_user_1 = SimpleNamespace(
        user_id=1001,
        username="pending_1",
        status="pending",
        is_active=False,
        rejection_reason=None,
        approved_by=None,
    )
    active_user = SimpleNamespace(
        user_id=1002,
        username="active_1",
        status="active",
        is_active=True,
        rejection_reason=None,
        approved_by=None,
    )
    pending_user_2 = SimpleNamespace(
        user_id=1003,
        username="pending_2",
        status="pending",
        is_active=False,
        rejection_reason=None,
        approved_by=None,
    )

    class FakeSession:
        def __init__(self):
            self._user_results = [
                _ScalarResult(pending_user_1),
                _ScalarResult(active_user),
                _ScalarResult(pending_user_2),
            ]
            self.flush = AsyncMock()
            self.commit = AsyncMock()
            self.rollback = AsyncMock()
            self.added = []

        async def execute(self, statement):
            sql = str(statement)
            if "FROM dim_users" in sql or "FROM core.dim_users" in sql:
                if not self._user_results:
                    return _ScalarResult(None)
                return self._user_results.pop(0)
            return _ScalarResult([])

        def add(self, obj):
            self.added.append(obj)

    async def override_require_admin():
        return SimpleNamespace(user_id=1, username="admin", is_superuser=True)

    async def override_get_async_db():
        yield FakeSession()

    app.dependency_overrides[require_admin] = override_require_admin
    app.dependency_overrides[get_async_db] = override_get_async_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr("backend.routers.users_admin.audit_service.log_action", AsyncMock())
            monkeypatch.setattr("backend.routers.users_admin._clear_employee_user_id", AsyncMock())
            monkeypatch.setattr(
                "backend.services.approval_center_service.sync_user_registration_approval_decision",
                AsyncMock(),
            )
            monkeypatch.setattr("backend.routers.notifications.notify_user_rejected", AsyncMock())

            response = await client.post(
                "/api/users/reject-batch",
                json={"user_ids": [1001, 1002, 1003], "reason": ""},
            )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    assert data["summary"]["total"] == 3
    assert data["summary"]["success"] == 2
    assert data["summary"]["failed"] == 1
    assert [item["user_id"] for item in data["results"]] == [1001, 1002, 1003]
    assert data["results"][0]["ok"] is True
    assert data["results"][1]["ok"] is False
    assert data["results"][2]["ok"] is True


@pytest.mark.asyncio
async def test_delete_users_batch_best_effort_cannot_delete_self():
    app = FastAPI()
    app.include_router(users_admin.router, prefix="/api")

    self_user = SimpleNamespace(
        user_id=1,
        username="admin",
        email="admin@example.com",
        status="active",
        is_active=True,
    )
    other_user = SimpleNamespace(
        user_id=2,
        username="user_2",
        email="user_2@example.com",
        status="active",
        is_active=True,
    )

    class FakeSession:
        def __init__(self):
            self._user_results = [_ScalarResult(self_user), _ScalarResult(other_user)]
            self.commit = AsyncMock()
            self.rollback = AsyncMock()

        async def execute(self, statement):
            sql = str(statement)
            if "FROM dim_users" in sql or "FROM core.dim_users" in sql:
                if not self._user_results:
                    return _ScalarResult(None)
                return self._user_results.pop(0)
            return _ScalarResult([])

    db = FakeSession()

    async def override_require_admin():
        return SimpleNamespace(user_id=1, username="admin", is_superuser=True)

    async def override_get_async_db():
        yield db

    app.dependency_overrides[require_admin] = override_require_admin
    app.dependency_overrides[get_async_db] = override_get_async_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr("backend.routers.users_admin.audit_service.log_action", AsyncMock())
            monkeypatch.setattr("backend.routers.users_admin._clear_employee_user_id", AsyncMock())

            response = await client.post(
                "/api/users/delete-batch",
                json={"user_ids": [1, 2], "reason": ""},
            )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    assert data["summary"]["total"] == 2
    assert data["summary"]["success"] == 1
    assert data["summary"]["failed"] == 1
    assert data["results"][0]["user_id"] == 1
    assert data["results"][0]["ok"] is False
    assert data["results"][1]["user_id"] == 2
    assert data["results"][1]["ok"] is True
    assert other_user.status == "deleted"
    assert other_user.is_active is False
