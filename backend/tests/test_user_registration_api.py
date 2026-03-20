#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用户注册和审批路由函数测试

使用 mock AsyncSession，验证路由核心业务契约而不是数据库集成行为。
"""

from datetime import datetime
from datetime import UTC
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import json

import pytest

from backend.routers import auth as auth_router
from backend.routers import users_admin as users_admin_router
from backend.schemas.auth import (
    ApproveUserRequest,
    LoginRequest,
    RegisterRequest,
    RejectUserRequest,
)
from backend.services.auth_service import auth_service
from modules.core.db import DimRole, DimUser


def _request_stub():
    return SimpleNamespace(
        client=SimpleNamespace(host="127.0.0.1"),
        headers={"User-Agent": "pytest"},
        state=SimpleNamespace(user=None),
    )


def _scalar_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    result.scalar_one.return_value = value
    result.scalars.return_value.all.return_value = value if isinstance(value, list) else []
    return result


def _payload(response):
    if isinstance(response, dict):
        return response
    if hasattr(response, "body"):
        return json.loads(response.body.decode("utf-8"))
    raise TypeError(f"Unsupported response type: {type(response)!r}")


@pytest.fixture(autouse=True)
def patch_side_effects(monkeypatch):
    async def fake_log_action(*args, **kwargs):
        return None

    async def fake_notify_user_registered(*args, **kwargs):
        return None

    async def fake_notify_user_approved(*args, **kwargs):
        return None

    async def fake_notify_user_rejected(*args, **kwargs):
        return None

    async def fake_clear_employee_user_id(*args, **kwargs):
        return None

    monkeypatch.setattr("backend.routers.auth.audit_service.log_action", fake_log_action)
    monkeypatch.setattr("backend.routers.users_admin.audit_service.log_action", fake_log_action)
    monkeypatch.setattr("backend.routers.notifications.notify_user_registered", fake_notify_user_registered)
    monkeypatch.setattr("backend.routers.notifications.notify_user_approved", fake_notify_user_approved)
    monkeypatch.setattr("backend.routers.notifications.notify_user_rejected", fake_notify_user_rejected)
    monkeypatch.setattr("backend.routers.users_admin._clear_employee_user_id", fake_clear_employee_user_id)
    if getattr(auth_router, "limiter", None):
        monkeypatch.setattr(auth_router.limiter, "enabled", False, raising=False)
    if getattr(users_admin_router, "limiter", None):
        monkeypatch.setattr(users_admin_router.limiter, "enabled", False, raising=False)


@pytest.mark.asyncio
async def test_user_registration():
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[
        _scalar_result(None),  # username不存在
        _scalar_result(None),  # email不存在
    ])
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    added = []

    def _add(obj):
        if isinstance(obj, DimUser):
            obj.user_id = 101
        added.append(obj)

    db.add.side_effect = _add

    response = await auth_router.register(
        request_body=RegisterRequest(
            username="testuser1",
            email="testuser1@test.com",
            password="test123456",
            full_name="Test User 1",
            phone="13800138000",
            department="测试部门",
        ),
        request=_request_stub(),
        db=db,
    )

    data = _payload(response)
    assert data["success"] is True
    assert data["data"]["username"] == "testuser1"
    assert data["data"]["status"] == "pending"
    user = next(obj for obj in added if isinstance(obj, DimUser))
    assert user.status == "pending"
    assert user.is_active is False


@pytest.mark.asyncio
async def test_user_registration_duplicate_username():
    existing_user = SimpleNamespace(user_id=1, status="active")
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[
        _scalar_result(existing_user),  # username已存在
        _scalar_result(None),
    ])

    response = await auth_router.register(
        request_body=RegisterRequest(
            username="duplicate_user",
            email="duplicate2@test.com",
            password="test123456",
            full_name="Duplicate User 2",
        ),
        request=_request_stub(),
        db=db,
    )

    data = _payload(response)
    assert data["success"] is False
    assert "用户名或邮箱已被使用" in data["message"]


@pytest.mark.asyncio
async def test_user_login_pending_status():
    pending_user = SimpleNamespace(
        username="pending_user",
        status="pending",
        is_active=False,
        roles=[],
    )
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_result(pending_user))

    response = await auth_router.login(
        credentials=LoginRequest(username="pending_user", password="test123456"),
        request=_request_stub(),
        db=db,
    )

    data = _payload(response)
    assert data["success"] is False
    error_code = data.get("code") or data.get("error", {}).get("code")
    assert error_code == 4005


@pytest.mark.asyncio
async def test_user_approval():
    user = DimUser(
        user_id=201,
        username="approve_user",
        email="approve@test.com",
        password_hash=auth_service.hash_password("test123456"),
        full_name="Approve User",
        status="pending",
        is_active=False,
    )
    user.roles = []
    operator_role = DimRole(
        role_id=2,
        role_name="操作员",
        role_code="operator",
        permissions="[]",
        is_active=True,
        is_system=True,
    )
    current_user = SimpleNamespace(user_id=999, username="test_admin")

    db = MagicMock()
    db.execute = AsyncMock(side_effect=[
        _scalar_result(user),
        _scalar_result(operator_role),
    ])
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()

    response = await users_admin_router.approve_user(
        user_id=201,
        request_body=ApproveUserRequest(notes="审批通过", role_ids=[]),
        request=_request_stub(),
        current_user=current_user,
        db=db,
    )

    data = _payload(response)
    assert data["success"] is True
    assert data["data"]["status"] == "active"
    assert user.status == "active"
    assert user.is_active is True
    assert user.approved_by == current_user.user_id


@pytest.mark.asyncio
async def test_user_rejection():
    user = DimUser(
        user_id=202,
        username="reject_user",
        email="reject@test.com",
        password_hash=auth_service.hash_password("test123456"),
        full_name="Reject User",
        status="pending",
        is_active=False,
    )
    current_user = SimpleNamespace(user_id=999, username="test_admin")

    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_result(user))
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()

    response = await users_admin_router.reject_user(
        user_id=202,
        request_body=RejectUserRequest(reason="不符合要求"),
        request=_request_stub(),
        current_user=current_user,
        db=db,
    )

    data = _payload(response)
    assert data["success"] is True
    assert data["data"]["status"] == "rejected"
    assert user.status == "rejected"
    assert user.is_active is False
    assert user.rejection_reason == "不符合要求"


@pytest.mark.asyncio
async def test_pending_users_list():
    users = [
        DimUser(
            user_id=301 + i,
            username=f"pending_list_user_{i}",
            email=f"pending_list_{i}@test.com",
            password_hash="x",
            full_name=f"Pending List User {i}",
            status="pending",
            is_active=False,
            created_at=datetime.now(UTC),
        )
        for i in range(3)
    ]

    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = users
    db.execute = AsyncMock(return_value=result)

    rows = await users_admin_router.get_pending_users(
        request=_request_stub(),
        page=1,
        page_size=20,
        current_user=SimpleNamespace(user_id=999, username="test_admin"),
        db=db,
    )

    assert len(rows) == 3
    assert all(user.username.startswith("pending_list_user_") for user in rows)
