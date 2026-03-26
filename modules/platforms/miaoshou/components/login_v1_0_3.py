"""
Generated component: miaoshou/login
Please align with docs/guides/COLLECTION_SCRIPT_WRITING_GUIDE.md
Complex interactions, popups, download handling: add explicit wait/comment as needed.
"""

from __future__ import annotations

from typing import Any

from playwright.async_api import expect

from modules.components.base import ExecutionContext, ResultBase
import asyncio
import os
from modules.components.login.base import LoginComponent, LoginResult
from modules.apps.collection_center.executor_v2 import VerificationRequiredError


class MiaoshouLogin(LoginComponent):
    """miaoshou login component - generated from recorder. Edit as needed."""

    platform = 'miaoshou'
    component_type = "login"
    data_domain = None

    def __init__(self, ctx: ExecutionContext) -> None:
        super().__init__(ctx)

    def _debug(self, message: str, *, page: Any = None) -> None:
        current_url = str(getattr(page, "url", "") or "") if page is not None else ""
        full_message = f"[MiaoshouLogin v1.0.3] {message}"
        if current_url:
            full_message += f" | url={current_url}"
        print(full_message)
        if self.logger:
            self.logger.info(full_message)

    async def run(self, page: Any) -> LoginResult:
        acc = self.ctx.account or {}
        config = self.ctx.config or {}
        self._debug("run() start", page=page)

        params = config.get("params") or {}
        captcha_code = (params.get("captcha_code") or params.get("otp") or "").strip()
        self._debug(
            f"params loaded: has_captcha_code={bool(captcha_code)} has_login_url={bool(acc.get('login_url'))}",
            page=page,
        )
        _platform_defaults = {'miaoshou': 'https://erp.91miaoshou.com', 'shopee': 'https://seller.shopee.cn', 'tiktok': 'https://seller-us.tiktok.com'}
        _target_url = (
            str(params.get("login_url_override") or "").strip()
            or str(acc.get("login_url") or "").strip()
            or str(config.get("default_login_url") or "").strip()
            or _platform_defaults.get(self.platform, "").strip()
        )
        if _target_url and not captcha_code:
            self._debug(f"navigating to target url: {_target_url}", page=page)
            await page.goto(_target_url, wait_until="domcontentloaded", timeout=60000)
            self._debug("page.goto completed", page=page)
            await page.wait_for_load_state("domcontentloaded", timeout=10000)
            self._debug("domcontentloaded reached", page=page)
            await self.guard_overlays(page, label="after login navigation")
            self._debug("guard_overlays completed", page=page)
        # Container scope: defaults to page; narrow down if needed
        _form = page

        # Fill: 手机号/子账号/邮箱
        # 建议迁移到 get_by_*
        _el_1 = _form.locator('input.account-input')
        self._debug("waiting username input visible", page=page)
        await expect(_el_1).to_be_visible()
        self._debug("username input visible", page=page)
        # Value from ctx.account - use acc.get("username") / acc.get("password")
        await _el_1.fill(acc.get("username", ""), timeout=10000)
        self._debug("username filled", page=page)

        # Fill: 密码
        # 建议迁移到 get_by_*
        _el_3 = _form.locator('input.password-input')
        self._debug("waiting password input visible", page=page)
        await expect(_el_3).to_be_visible()
        self._debug("password input visible", page=page)
        # Value from ctx.account - use acc.get("username") / acc.get("password")
        await _el_3.fill(acc.get("password", ""), timeout=10000)
        self._debug("password filled", page=page)

        # Fill: 请输入验证码
        _el_5 = page.get_by_role('textbox', name='请输入验证码')
        self._debug("waiting captcha textbox visible", page=page)
        await expect(_el_5).to_be_visible()
        self._debug("captcha textbox visible", page=page)
        value = captcha_code
        if not value:
            self._debug("no captcha_code provided, preparing screenshot and raising VerificationRequiredError", page=page)
            screenshot_path = None
            screenshot_dir = config.get("task", {}).get("screenshot_dir")
            if screenshot_dir:
                os.makedirs(screenshot_dir, exist_ok=True)
                screenshot_path = os.path.join(screenshot_dir, "captcha.png")
            else:
                import tempfile
                fd, screenshot_path = tempfile.mkstemp(suffix=".png", prefix="captcha_")
                os.close(fd)
            await page.screenshot(path=screenshot_path, timeout=5000)
            self._debug(f"captcha screenshot saved: {screenshot_path}", page=page)
            raise VerificationRequiredError('graphical_captcha', screenshot_path)
        await _el_5.fill(value, timeout=10000)
        self._debug("captcha filled from callback value", page=page)

        # Click: 立即登录
        _el_6 = _form.get_by_role('button', name='立即登录')
        self._debug("waiting login button visible", page=page)
        await expect(_el_6).to_be_visible()
        self._debug("login button visible", page=page)
        await _el_6.click(timeout=10000)
        self._debug("login button clicked", page=page)

        # TODO: edit success condition - check URL change or dashboard element
        # Example: await page.wait_for_url("**/dashboard**", timeout=15000)
        # Example: await expect(page.get_by_text("Welcome")).to_be_visible(timeout=10000)
        self._debug("returning success placeholder without post-login gate", page=page)
        return LoginResult(success=True, message="ok")
