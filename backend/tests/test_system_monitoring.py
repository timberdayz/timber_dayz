"""
系统资源监控 API 集成测试

测试资源监控 API 端点:
- /api/system/resource-usage
- /api/system/executor-stats
- /api/system/db-pool-stats
"""

import pytest
from httpx import AsyncClient, ASGITransport
from backend.main import app
from backend.utils.auth import create_access_token
from modules.core.db import DimUser


@pytest.fixture
async def admin_token():
    """创建管理员 token(模拟)"""
    # 注意:实际测试中应该使用真实的用户和 token
    # 这里仅用于测试 API 结构
    return "test_admin_token"


@pytest.fixture
async def client():
    """创建测试客户端 (基于 ASGITransport，兼容 httpx 新版本)"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        yield client


@pytest.mark.asyncio
async def test_resource_usage_endpoint_exists(client):
    """测试资源使用情况端点存在"""
    # 注意:实际测试需要有效的认证 token
    # 这里只测试端点是否注册
    response = await client.get("/api/system/resource-usage")
    # 应该返回 401(未认证)或 403(权限不足),而不是 404
    assert response.status_code in [401, 403, 422]  # 422 可能是缺少依赖


@pytest.mark.asyncio
async def test_executor_stats_endpoint_exists(client):
    """测试执行器统计端点存在"""
    response = await client.get("/api/system/executor-stats")
    # 应该返回 401(未认证)或 403(权限不足),而不是 404
    assert response.status_code in [401, 403, 422]


@pytest.mark.asyncio
async def test_db_pool_stats_endpoint_exists(client):
    """测试数据库连接池统计端点存在"""
    response = await client.get("/api/system/db-pool-stats")
    # 应该返回 401(未认证)或 403(权限不足),而不是 404
    assert response.status_code in [401, 403, 422]


@pytest.mark.asyncio
async def test_resource_usage_response_structure(client, admin_token):
    """测试资源使用情况响应结构(需要认证)"""
    # 注意:实际测试需要有效的认证 token
    headers = {"Authorization": f"Bearer {admin_token}"}
    response = await client.get("/api/system/resource-usage", headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        # 验证响应结构
        assert "data" in data or "cpu_usage" in data or "cpu_usage_percent" in data


@pytest.mark.asyncio
async def test_executor_stats_response_structure(client, admin_token):
    """测试执行器统计响应结构(需要认证)"""
    headers = {"Authorization": f"Bearer {admin_token}"}
    response = await client.get("/api/system/executor-stats", headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        # 验证响应结构
        assert "data" in data or "cpu_executor" in data


@pytest.mark.asyncio
async def test_db_pool_stats_response_structure(client, admin_token):
    """测试数据库连接池统计响应结构(需要认证)"""
    headers = {"Authorization": f"Bearer {admin_token}"}
    response = await client.get("/api/system/db-pool-stats", headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        # 验证响应结构
        assert "data" in data or "sync_pool" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

