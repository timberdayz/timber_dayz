#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""集成测试开关 —— 让「会写数据」的集成测试默认不跑。

为什么需要它
------------
``backend/tests/test_user_registration_integration.py`` 历史上同时踩了三个坑:

1. **假通过**: 每个用例用 ``return True/False`` 表示结果, 而 pytest 只把
   「抛异常」当失败。于是后端没启动时「拿不到管理员 token → return False」
   依然算**通过** —— 上一轮它就是这样混进回归基线的。
2. **污染真实业务库**: 默认目标写死 ``http://localhost:8001``, 而那台本地
   服务连的就是**真实业务库**, 测试注册的用户直接写进生产数据。
3. **断言与接口契约不符**: ``GET /api/users/pending`` 按接口设计返回 JSON
   **数组**(``response_model=List[PendingUserResponse]``), 旧测试却按统一信封
   断言 ``result.get("success")`` ⇒ 必然 AttributeError。

开关约定
--------
* **默认跳过**: 只有设了 ``XIHONG_RUN_INTEGRATION_TESTS=1`` 才启用;
* 启用时必须显式给出目标: ``XIHONG_INTEGRATION_BASE_URL=http://host:port``
  —— **不再有默认值**, 默认值正是「误打真实环境」的根源;
* 还必须显式确认目标可丢弃: ``XIHONG_INTEGRATION_DISPOSABLE=1``。
  两个开关都给出, 才表示「我知道这个测试会往目标环境写数据」。

环境变量
--------
``XIHONG_RUN_INTEGRATION_TESTS``    设为 1/true/yes/on 才会启用集成测试
``XIHONG_INTEGRATION_BASE_URL``     目标服务根地址(必填, 无默认值)
``XIHONG_INTEGRATION_DISPOSABLE``   设为 1/true/yes/on 表示目标可丢弃
``XIHONG_INTEGRATION_ADMIN_USERNAME`` 管理员账号(可选, 默认 ``xihong``)
``XIHONG_INTEGRATION_ADMIN_PASSWORD`` 管理员密码(可选, 默认见下方常量)

本模块**只做判断**, 不发请求、不连库, 因此可以被普通单元测试直接导入。
"""

from __future__ import annotations

import os

RUN_FLAG = "XIHONG_RUN_INTEGRATION_TESTS"
BASE_URL_VAR = "XIHONG_INTEGRATION_BASE_URL"
DISPOSABLE_VAR = "XIHONG_INTEGRATION_DISPOSABLE"
ADMIN_USERNAME_VAR = "XIHONG_INTEGRATION_ADMIN_USERNAME"
ADMIN_PASSWORD_VAR = "XIHONG_INTEGRATION_ADMIN_PASSWORD"

DEFAULT_ADMIN_USERNAME = "xihong"
DEFAULT_ADMIN_PASSWORD = "~!Qq1`1`"

_TRUTHY = {"1", "true", "yes", "on"}


class IntegrationGateError(RuntimeError):
    """集成测试开关不满足条件 —— 必须是**硬失败**, 不能退化成「跳过」或「通过」。"""


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in _TRUTHY


def integration_requested() -> bool:
    """是否显式要求运行集成测试(第一个开关)。"""
    return _truthy(os.environ.get(RUN_FLAG))


def integration_disposable() -> bool:
    """是否显式确认「目标环境可丢弃」(第二个开关)。"""
    return _truthy(os.environ.get(DISPOSABLE_VAR))


def integration_enabled() -> bool:
    """两个开关都给出才算启用。"""
    return integration_requested() and integration_disposable()


def resolve_base_url() -> str:
    """返回目标服务根地址(去掉尾部斜杠)。

    刻意**没有默认值**: 旧实现默认 ``http://localhost:8001``, 而那台本地服务
    连的是真实业务库 —— 默认值本身就是「误写生产数据」的来源。
    """
    raw = str(os.environ.get(BASE_URL_VAR) or "").strip()
    if not raw:
        raise IntegrationGateError(
            f"未设置 {BASE_URL_VAR}。集成测试会真实写入数据, 必须显式指定目标服务地址, "
            f"例如 {BASE_URL_VAR}=http://127.0.0.1:8001 (指向一次性/可丢弃环境)。"
        )
    if not raw.lower().startswith(("http://", "https://")):
        raise IntegrationGateError(
            f"{BASE_URL_VAR}={raw!r} 不是合法的 HTTP(S) 地址。"
        )
    return raw.rstrip("/")


def admin_credentials() -> tuple[str, str]:
    """管理员账号密码(可用环境变量覆盖)。"""
    username = str(os.environ.get(ADMIN_USERNAME_VAR) or "").strip() or DEFAULT_ADMIN_USERNAME
    password = os.environ.get(ADMIN_PASSWORD_VAR) or DEFAULT_ADMIN_PASSWORD
    return username, password


def skip_reason() -> str:
    """默认跳过时给出的原因(直接展示给开发者)。"""
    missing = []
    if not integration_requested():
        missing.append(f"{RUN_FLAG}=1")
    if not integration_disposable():
        missing.append(f"{DISPOSABLE_VAR}=1")
    if not str(os.environ.get(BASE_URL_VAR) or "").strip():
        missing.append(f"{BASE_URL_VAR}=<目标地址>")
    return (
        "集成测试默认跳过(它会真实注册/审批/拒绝用户并写入目标环境)。"
        "要运行请同时设置: " + ", ".join(missing)
    )


def require_integration_ready() -> str:
    """确保集成测试可以安全运行, 返回目标地址; 不满足条件就抛错。"""
    if not integration_requested():
        raise IntegrationGateError(
            f"集成测试未启用: 请设置 {RUN_FLAG}=1。"
        )
    if not integration_disposable():
        raise IntegrationGateError(
            f"集成测试会向目标环境写入数据: 请显式设置 {DISPOSABLE_VAR}=1 确认目标环境可丢弃。"
        )
    return resolve_base_url()
