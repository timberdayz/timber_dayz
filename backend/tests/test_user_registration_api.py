#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用户注册和审批API测试

测试内容：
1. 用户注册API (POST /api/auth/register)
2. 用户审批API (POST /api/users/{user_id}/approve)
3. 用户拒绝API (POST /api/users/{user_id}/reject)
4. 待审批用户列表API (GET /api/users/pending)
5. 登录状态检查 (POST /api/auth/login)
"""

import pytest
import asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import sessionmaker
from backend.main import app
from backend.models.database import get_async_db, Base, engine
from modules.core.db import DimUser, DimRole, UserApprovalLog
from backend.services.auth_service import auth_service
from sqlalchemy import select
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 测试数据库URL（使用测试数据库）
TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:15432/xihong_erp_test"


@pytest.fixture
async def test_db():
    """创建测试数据库会话"""
    # 使用内存数据库或测试数据库
    test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async_session_maker = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session_maker() as session:
        yield session
        await session.rollback()


@pytest.fixture
def client():
    """创建测试客户端"""
    return TestClient(app)


@pytest.fixture
async def admin_user(test_db: AsyncSession):
    """创建管理员用户用于测试"""
    # 检查是否已存在admin用户
    result = await test_db.execute(select(DimUser).where(DimUser.username == "test_admin"))
    admin = result.scalar_one_or_none()
    
    if not admin:
        # 创建admin角色
        result = await test_db.execute(select(DimRole).where(DimRole.role_code == "admin"))
        admin_role = result.scalar_one_or_none()
        
        if not admin_role:
            admin_role = DimRole(
                role_code="admin",
                role_name="管理员",
                description="系统管理员",
                permissions='[]',
                is_active=True,
                is_system=True
            )
            test_db.add(admin_role)
            await test_db.flush()
        
        # 创建admin用户
        admin = DimUser(
            username="test_admin",
            email="admin@test.com",
            password_hash=auth_service.hash_password("admin123"),
            full_name="Test Admin",
            is_active=True,
            is_superuser=True,
            status="active"
        )
        admin.roles.append(admin_role)
        test_db.add(admin)
        await test_db.commit()
        await test_db.refresh(admin)
    
    return admin


@pytest.mark.asyncio
async def test_user_registration(client: TestClient, test_db: AsyncSession):
    """测试用户注册"""
    # 注册新用户
    response = client.post("/api/auth/register", json={
        "username": "testuser1",
        "email": "testuser1@test.com",
        "password": "test123456",
        "full_name": "Test User 1",
        "phone": "13800138000",
        "department": "测试部门"
    })
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["username"] == "testuser1"
    assert data["data"]["status"] == "pending"
    
    # 验证用户已创建（状态为pending）
    result = await test_db.execute(select(DimUser).where(DimUser.username == "testuser1"))
    user = result.scalar_one_or_none()
    assert user is not None
    assert user.status == "pending"
    assert user.is_active is False


@pytest.mark.asyncio
async def test_user_registration_duplicate_username(client: TestClient):
    """测试重复用户名注册"""
    # 第一次注册
    client.post("/api/auth/register", json={
        "username": "duplicate_user",
        "email": "duplicate1@test.com",
        "password": "test123456",
        "full_name": "Duplicate User 1"
    })
    
    # 第二次注册（相同用户名）
    response = client.post("/api/auth/register", json={
        "username": "duplicate_user",
        "email": "duplicate2@test.com",
        "password": "test123456",
        "full_name": "Duplicate User 2"
    })
    
    assert response.status_code == 400
    data = response.json()
    assert data["success"] is False
    assert "用户名或邮箱已被使用" in data["message"]


@pytest.mark.asyncio
async def test_user_login_pending_status(client: TestClient, test_db: AsyncSession):
    """测试pending状态用户无法登录"""
    # 注册用户
    register_response = client.post("/api/auth/register", json={
        "username": "pending_user",
        "email": "pending@test.com",
        "password": "test123456",
        "full_name": "Pending User"
    })
    assert register_response.status_code == 200
    
    # 尝试登录（应该失败）
    login_response = client.post("/api/auth/login", json={
        "username": "pending_user",
        "password": "test123456"
    })
    
    assert login_response.status_code == 403
    data = login_response.json()
    assert data["success"] is False
    assert data["code"] == 4005  # AUTH_ACCOUNT_PENDING


@pytest.mark.asyncio
async def test_user_approval(client: TestClient, test_db: AsyncSession, admin_user: DimUser):
    """测试用户审批"""
    # 先注册用户
    register_response = client.post("/api/auth/register", json={
        "username": "approve_user",
        "email": "approve@test.com",
        "password": "test123456",
        "full_name": "Approve User"
    })
    assert register_response.status_code == 200
    user_id = register_response.json()["data"]["user_id"]
    
    # 获取admin token
    login_response = client.post("/api/auth/login", json={
        "username": "test_admin",
        "password": "admin123"
    })
    assert login_response.status_code == 200
    token = login_response.json()["data"]["access_token"]
    
    # 审批用户
    approve_response = client.post(
        f"/api/users/{user_id}/approve",
        json={"notes": "审批通过"},
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert approve_response.status_code == 200
    data = approve_response.json()
    assert data["success"] is True
    assert data["data"]["status"] == "active"
    
    # 验证用户状态已更新
    result = await test_db.execute(select(DimUser).where(DimUser.user_id == user_id))
    user = result.scalar_one_or_none()
    assert user.status == "active"
    assert user.is_active is True
    assert user.approved_by == admin_user.user_id


@pytest.mark.asyncio
async def test_user_rejection(client: TestClient, test_db: AsyncSession, admin_user: DimUser):
    """测试用户拒绝"""
    # 先注册用户
    register_response = client.post("/api/auth/register", json={
        "username": "reject_user",
        "email": "reject@test.com",
        "password": "test123456",
        "full_name": "Reject User"
    })
    assert register_response.status_code == 200
    user_id = register_response.json()["data"]["user_id"]
    
    # 获取admin token
    login_response = client.post("/api/auth/login", json={
        "username": "test_admin",
        "password": "admin123"
    })
    assert login_response.status_code == 200
    token = login_response.json()["data"]["access_token"]
    
    # 拒绝用户
    reject_response = client.post(
        f"/api/users/{user_id}/reject",
        json={"reason": "不符合要求"},
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert reject_response.status_code == 200
    data = reject_response.json()
    assert data["success"] is True
    assert data["data"]["status"] == "rejected"
    
    # 验证用户状态已更新
    result = await test_db.execute(select(DimUser).where(DimUser.user_id == user_id))
    user = result.scalar_one_or_none()
    assert user.status == "rejected"
    assert user.is_active is False
    assert user.rejection_reason == "不符合要求"


@pytest.mark.asyncio
async def test_pending_users_list(client: TestClient, test_db: AsyncSession, admin_user: DimUser):
    """测试待审批用户列表"""
    # 注册几个用户
    for i in range(3):
        client.post("/api/auth/register", json={
            "username": f"pending_list_user_{i}",
            "email": f"pending_list_{i}@test.com",
            "password": "test123456",
            "full_name": f"Pending List User {i}"
        })
    
    # 获取admin token
    login_response = client.post("/api/auth/login", json={
        "username": "test_admin",
        "password": "admin123"
    })
    assert login_response.status_code == 200
    token = login_response.json()["data"]["access_token"]
    
    # 获取待审批用户列表
    list_response = client.get(
        "/api/users/pending",
        headers={"Authorization": f"Bearer {token}"},
        params={"page": 1, "page_size": 20}
    )
    
    assert list_response.status_code == 200
    users = list_response.json()
    assert len(users) >= 3
    assert all(user["username"].startswith("pending_list_user_") for user in users)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

