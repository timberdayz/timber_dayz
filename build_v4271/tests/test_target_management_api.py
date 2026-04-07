#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
目标管理 API 基础测试

验证：
1. GET /api/targets 未认证时返回 401
2. 后端 target_management 模块可正常导入、无语法错误
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_targets_list_requires_auth():
    """未携带 token 时 GET /api/targets 应返回 401（或 400 因 TestClient Host 被拒）"""
    from fastapi.testclient import TestClient
    from backend.main import app

    client = TestClient(app, headers={"Host": "localhost"})
    resp = client.get("/api/targets", params={"page": 1, "page_size": 10})
    # 未认证应被拒绝：401 或 403；若中间件以 400 拒掉也算“未放行”
    assert resp.status_code in (400, 401, 403), (
        f"未认证请求应返回 4xx，实际 {resp.status_code}: {resp.text[:200]}"
    )


def test_target_management_router_import():
    """目标管理路由与模型可正常导入"""
    from backend.routers import target_management
    from modules.core.db import SalesTarget, TargetBreakdown

    assert hasattr(target_management, "router")
    assert target_management.router.prefix == "/targets"


def test_targets_list_authenticated_capture_500_detail():
    """带认证调用 GET /api/targets，若返回 500 则打印 error.detail 便于排查根因"""
    from fastapi.testclient import TestClient
    from backend.main import app
    from backend.routers.auth import get_current_user
    from unittest.mock import MagicMock

    mock_user = MagicMock()
    mock_user.user_id = 1
    mock_user.username = "test"
    mock_user.is_active = True
    mock_user.status = "active"
    mock_user.roles = []

    async def fake_get_current_user():
        return mock_user

    try:
        app.dependency_overrides[get_current_user] = fake_get_current_user
        client = TestClient(app, headers={"Host": "localhost"})
        resp = client.get("/api/targets", params={"page": 1, "page_size": 20})
        if resp.status_code == 500:
            data = resp.json()
            err = data.get("error") or {}
            detail = err.get("detail") or data.get("message") or resp.text
            raise AssertionError(f"GET /api/targets 返回 500，后端错误详情: {detail}")
        assert resp.status_code == 200, resp.text
    finally:
        app.dependency_overrides.pop(get_current_user, None)
