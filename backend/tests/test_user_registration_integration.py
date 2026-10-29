#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用户注册和审批流程 - 集成测试

⚠️ **这是一个会写数据的集成测试**: 它会真的注册用户、审批、拒绝、重置密码。

保护措施(2026-10-29 加固)
--------------------------
1. **默认跳过**: 打 ``integration`` 标记; 不设 ``XIHONG_RUN_INTEGRATION_TESTS=1``
   就整体跳过 —— 默认不会往任何库里写东西。
2. **必须显式指定目标**: 启用时还要给 ``XIHONG_INTEGRATION_BASE_URL``(无默认值)
   与 ``XIHONG_INTEGRATION_DISPOSABLE=1``。
   旧实现默认打 ``http://localhost:8001``, 而那台本地服务连的是**真实业务库**
   —— 默认值本身就是「往生产库写测试用户」的根源。
3. **断言真的断言**: 旧实现用 ``return True/False`` 表示结果, 而 pytest 只把
   「抛异常」当失败 ⇒ 后端没起来时也算**通过**。现在一律用 ``assert``。
4. **断言按接口契约写**: ``GET /api/users/pending`` 返回 JSON **数组**
   (``response_model=List[PendingUserResponse]``), 不是统一信封。

运行方式
--------
::

    # Windows PowerShell
    $env:XIHONG_RUN_INTEGRATION_TESTS = "1"
    $env:XIHONG_INTEGRATION_DISPOSABLE = "1"
    $env:XIHONG_INTEGRATION_BASE_URL = "http://127.0.0.1:8001"
    pytest backend/tests/test_user_registration_integration.py -v

前置条件
--------
* 目标服务已启动, 且 ``/api`` 路由可用;
* 存在管理员账号(默认 ``xihong`` / ``~!Qq1`1``, 可用环境变量覆盖);
* 存在 ``operator`` 角色(审批接口在缺少该角色时返回 500)。
"""

from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path
from typing import Any, Optional

import pytest
import requests

# 添加项目根目录到 Python 路径
root_dir = Path(__file__).parent.parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from integration_gate import (  # noqa: E402  (同级模块, pytest prepend 导入模式)
    IntegrationGateError,
    admin_credentials,
    require_integration_ready,
    skip_reason,
)

pytestmark = pytest.mark.integration

# [*] 默认跳过: 必须显式开启, 否则本模块整体不跑 —— 也就不会写任何数据。
try:
    BASE_URL = require_integration_ready()
except IntegrationGateError as _gate_error:
    pytest.skip(f"{skip_reason()} ({_gate_error})", allow_module_level=True)

API_PREFIX = "/api"
REQUEST_TIMEOUT = 15

# [*] 每个用例用独立前缀, 避免与历史脏数据/并发运行撞名。
RUN_TAG = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
TEST_PASSWORD = "Test123456"

# [*] 本模块创建的用户 id —— 用例结束后尽力软删除, 减少目标环境残留。
_CREATED_USER_IDS: list[int] = []


# ---------------------------------------------------------------------------
# HTTP 辅助
# ---------------------------------------------------------------------------
def _api(
    method: str,
    path: str,
    *,
    token: Optional[str] = None,
    json_body: Optional[dict[str, Any]] = None,
) -> tuple[int, Any]:
    """发一个请求, 返回 (状态码, 解析后的 JSON)。"""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = requests.request(
        method,
        f"{BASE_URL}{API_PREFIX}{path}",
        json=json_body,
        headers=headers,
        timeout=REQUEST_TIMEOUT,
    )
    try:
        payload = response.json()
    except ValueError:
        payload = {"raw": response.text}
    return response.status_code, payload


def _error_code(payload: Any) -> Optional[int]:
    """从统一信封里取业务错误码。"""
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            code = error.get("code")
            if isinstance(code, int):
                return code
    return None


def login_as_admin() -> str:
    """登录管理员并返回 token; 拿不到就**直接失败**(旧实现返回 False ⇒ 假通过)。"""
    username, password = admin_credentials()
    status, payload = _api(
        "POST",
        "/auth/login",
        json_body={"username": username, "password": password},
    )
    assert status == 200, f"管理员登录 HTTP {status}: {payload}"
    assert isinstance(payload, dict), f"管理员登录响应不是对象: {payload!r}"
    token = payload.get("access_token")
    assert token, f"管理员登录成功但没有返回 access_token: {payload!r}"
    return token


def _register(username: str) -> int:
    """注册一个待审批用户, 返回 user_id。"""
    status, payload = _api(
        "POST",
        "/auth/register",
        json_body={
            "username": username,
            "email": f"{username}@test.com",
            "password": TEST_PASSWORD,
            "full_name": f"Integration {username}",
        },
    )
    assert status == 200, f"注册 HTTP {status}: {payload}"
    assert isinstance(payload, dict) and payload.get("success") is True, (
        f"注册失败: {payload!r}"
    )
    data = payload.get("data") or {}
    user_id = data.get("user_id")
    assert isinstance(user_id, int), f"注册响应缺少 user_id: {payload!r}"
    _CREATED_USER_IDS.append(user_id)
    return user_id


def _cleanup_created_users(token: str) -> None:
    """尽力把本模块创建的用户软删除(失败不影响用例结论)。"""
    for user_id in list(_CREATED_USER_IDS):
        try:
            requests.delete(
                f"{BASE_URL}{API_PREFIX}/users/{user_id}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=REQUEST_TIMEOUT,
            )
        except Exception:  # noqa: BLE001 - 清理是尽力而为
            pass
    _CREATED_USER_IDS.clear()


# ---------------------------------------------------------------------------
# 用例
# ---------------------------------------------------------------------------
def test_complete_registration_approval_login_flow():
    """完整流程: 注册 → pending 登录被拒 → 管理员批准 → 再次登录成功。"""
    username = f"it_{RUN_TAG}_flow"

    user_id = _register(username)

    # 步骤2: pending 状态应被拒绝登录(403 / 4005 AUTH_ACCOUNT_PENDING)
    status, payload = _api(
        "POST",
        "/auth/login",
        json_body={"username": username, "password": TEST_PASSWORD},
    )
    assert status == 403, f"pending 用户登录应被拒绝, 实际 HTTP {status}: {payload!r}"
    assert _error_code(payload) == 4005, f"错误码应为 4005, 实际: {payload!r}"

    # 步骤3: 管理员批准
    token = login_as_admin()
    status, payload = _api("POST", f"/users/{user_id}/approve", token=token, json_body={})
    assert status == 200, f"审批 HTTP {status}: {payload!r}"
    assert payload.get("success") is True, f"审批失败: {payload!r}"
    assert (payload.get("data") or {}).get("status") == "active", (
        f"审批后状态应为 active: {payload!r}"
    )

    # 步骤4: 再次登录应成功并拿到 token
    status, payload = _api(
        "POST",
        "/auth/login",
        json_body={"username": username, "password": TEST_PASSWORD},
    )
    assert status == 200, f"批准后登录 HTTP {status}: {payload!r}"
    assert payload.get("access_token"), f"批准后登录未返回 token: {payload!r}"

    _cleanup_created_users(token)


def test_admin_approval_workflow():
    """管理员审批工作流: 批量注册 → 待审批列表 → 批准一个 → 拒绝一个。"""
    token = login_as_admin()

    usernames = [f"it_{RUN_TAG}_wf_{index}" for index in range(3)]
    user_ids = [_register(name) for name in usernames]

    # [*] /api/users/pending 按接口设计返回 **JSON 数组**(不是统一信封)
    status, payload = _api("GET", "/users/pending", token=token)
    assert status == 200, f"获取待审批列表 HTTP {status}: {payload!r}"
    assert isinstance(payload, list), (
        f"待审批列表应为 JSON 数组, 实际类型 {type(payload).__name__}: {payload!r}"
    )
    pending_names = {item.get("username") for item in payload if isinstance(item, dict)}
    missing = [name for name in usernames if name not in pending_names]
    assert not missing, f"新建用户未出现在待审批列表里: {missing}"

    # 批准第一个
    status, payload = _api(
        "POST", f"/users/{user_ids[0]}/approve", token=token, json_body={}
    )
    assert status == 200 and payload.get("success") is True, f"批准失败: {payload!r}"

    # 拒绝第二个
    status, payload = _api(
        "POST",
        f"/users/{user_ids[1]}/reject",
        token=token,
        json_body={"reason": "集成测试拒绝原因"},
    )
    assert status == 200 and payload.get("success") is True, f"拒绝失败: {payload!r}"

    _cleanup_created_users(token)


def test_password_reset_and_unlock_flow():
    """密码重置 + 账户锁定/解锁。"""
    username = f"it_{RUN_TAG}_reset"

    user_id = _register(username)

    token = login_as_admin()

    # 批准用户(重置密码需要账号可用)
    status, payload = _api("POST", f"/users/{user_id}/approve", token=token, json_body={})
    assert status == 200 and payload.get("success") is True, f"审批失败: {payload!r}"

    # 步骤2: 重置密码(生成临时密码)
    status, payload = _api(
        "POST",
        f"/users/{user_id}/reset-password",
        token=token,
        json_body={"generate_temp_password": True},
    )
    assert status == 200, f"重置密码 HTTP {status}: {payload!r}"
    assert payload.get("success") is True, f"重置密码失败: {payload!r}"
    temp_password = (payload.get("data") or {}).get("temp_password")
    assert temp_password, f"未返回临时密码: {payload!r}"

    # 步骤3: 用临时密码登录
    status, payload = _api(
        "POST",
        "/auth/login",
        json_body={"username": username, "password": temp_password},
    )
    assert status == 200, f"临时密码登录 HTTP {status}: {payload!r}"
    assert payload.get("access_token"), f"临时密码登录未返回 token: {payload!r}"

    # 步骤4: 连续错误登录 → 锁定(403 / 4009 AUTH_ACCOUNT_LOCKED)
    lock_status = 0
    lock_payload: Any = None
    for _ in range(6):
        lock_status, lock_payload = _api(
            "POST",
            "/auth/login",
            json_body={"username": username, "password": "WrongPassword"},
        )
        if lock_status == 403 and _error_code(lock_payload) == 4009:
            break
    assert lock_status == 403, f"账户应被锁定, 实际 HTTP {lock_status}: {lock_payload!r}"
    assert _error_code(lock_payload) == 4009, f"错误码应为 4009: {lock_payload!r}"

    # 解锁
    status, payload = _api(
        "POST",
        f"/users/{user_id}/unlock",
        token=token,
        json_body={"reason": "集成测试解锁"},
    )
    assert status == 200 and payload.get("success") is True, f"解锁失败: {payload!r}"

    _cleanup_created_users(token)


def test_session_management_flow():
    """会话管理: 列出活跃会话 → 撤销其它会话。"""
    token = login_as_admin()

    status, payload = _api("GET", "/users/me/sessions", token=token)
    assert status == 200, f"获取会话列表 HTTP {status}: {payload!r}"
    assert payload.get("success") is True, f"获取会话列表失败: {payload!r}"
    sessions = payload.get("data")
    assert isinstance(sessions, list), f"会话列表应为数组: {payload!r}"
    assert sessions, "管理员登录后至少应有一个活跃会话"

    # 撤销所有其它会话
    status, payload = _api("DELETE", "/users/me/sessions", token=token)
    assert status == 200 and payload.get("success") is True, f"撤销会话失败: {payload!r}"

    # 当前会话仍然有效
    status, payload = _api("GET", "/users/me/sessions", token=token)
    assert status == 200 and payload.get("success") is True, f"会话列表读取失败: {payload!r}"


# ---------------------------------------------------------------------------
# 独立运行入口: python backend/tests/test_user_registration_integration.py
# ---------------------------------------------------------------------------
def main() -> int:
    """独立运行入口(不走 pytest)。"""
    print("=" * 70)
    print("  用户注册和审批流程 - 集成测试")
    print("=" * 70)
    print(f"测试目标: {BASE_URL}")
    print(f"开始时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    cases = [
        test_complete_registration_approval_login_flow,
        test_admin_approval_workflow,
        test_password_reset_and_unlock_flow,
        test_session_management_flow,
    ]
    failures = 0
    for case in cases:
        try:
            case()
        except AssertionError as error:
            failures += 1
            print(f"[FAIL] {case.__name__}: {error}")
        except Exception as error:  # noqa: BLE001
            failures += 1
            print(f"[ERROR] {case.__name__}: {error}")
        else:
            print(f"[PASS] {case.__name__}")

    print("=" * 70)
    print(f"总测试数: {len(cases)}  失败: {failures}")
    print("=" * 70)
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[INFO] 测试被用户中断")
        sys.exit(1)
