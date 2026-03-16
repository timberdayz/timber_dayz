# -*- coding: utf-8 -*-
"""component_recorder lint 规则回归测试（8.10/8.11）。"""

from backend.routers.component_recorder import (
    _analyze_python_code_for_lints,
    _inject_login_success_criteria_block,
)


def _err_types(result):
    return {e.get("type") for e in result.get("errors", [])}


def _warn_types(result):
    return {w.get("type") for w in result.get("warnings", [])}


def test_wait_for_timeout_with_reason_not_blocked():
    code = """
async def run(page):
    # 固定等待: 动画结束
    await page.wait_for_timeout(1200)
"""
    result = _analyze_python_code_for_lints(code)
    assert "wait_for_timeout_usage" not in _err_types(result)
    assert "wait_for_timeout_with_reason" in _warn_types(result)


def test_wait_for_timeout_without_reason_blocked():
    code = """
async def run(page):
    await page.wait_for_timeout(1200)
"""
    result = _analyze_python_code_for_lints(code)
    assert "wait_for_timeout_usage" in _err_types(result)


def test_first_with_reason_not_blocked():
    code = """
async def run(page):
    # 业务语义: 第N项固定为“最新记录”，允许 first-nth-justified
    row = page.locator("tr").first
    await row.click()
"""
    result = _analyze_python_code_for_lints(code)
    assert "first_nth_usage" not in _err_types(result)
    assert "first_nth_with_reason" in _warn_types(result)


def test_first_without_reason_blocked():
    code = """
async def run(page):
    row = page.locator("tr").first
    await row.click()
"""
    result = _analyze_python_code_for_lints(code)
    assert "first_nth_usage" in _err_types(result)


def test_asyncio_sleep_with_reason_not_blocked():
    code = """
import asyncio
async def run(page):
    # 固定等待: 验证码回传后等待跳转
    await asyncio.sleep(2.0)
"""
    result = _analyze_python_code_for_lints(code)
    assert "fixed_sleep_usage" not in _err_types(result)
    assert "fixed_sleep_with_reason" in _warn_types(result)


def test_injected_success_criteria_no_first_nth_bypass():
    base_code = """
from modules.components.base import ExecutionContext, ResultBase
from modules.components.login.base import LoginComponent, LoginResult
class X(LoginComponent):
    async def run(self, page):
        # TODO: 根据实际成功条件校验 (e.g. URL / element)
        return LoginResult(success=True, message="ok")
"""
    injected = _inject_login_success_criteria_block(
        base_code,
        {"element_visible_selector": "#dashboard"},
    )
    # 注入后不应出现 .first/.nth
    assert ".first" not in injected
    assert ".nth(" not in injected
    lint = _analyze_python_code_for_lints(injected)
    assert "first_nth_usage" not in _err_types(lint)
