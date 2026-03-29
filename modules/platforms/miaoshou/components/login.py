from __future__ import annotations

import asyncio
import os
import re
from typing import Any

from playwright.async_api import expect

from modules.apps.collection_center.executor_v2 import VerificationRequiredError
from modules.components.base import ExecutionContext
from modules.components.login.base import LoginComponent, LoginResult


class MiaoshouLogin(LoginComponent):
    """Canonical Miaoshou login component for V2."""

    platform = "miaoshou"
    component_type = "login"
    data_domain = None

    def __init__(self, ctx: ExecutionContext) -> None:
        super().__init__(ctx)

    def _login_looks_successful(self, url: str) -> bool:
        cur = str(url or "").lower().strip()
        if not cur:
            return False
        if any(marker in cur for marker in ("/login", "account/login", "redirect=%2fwelcome")):
            return False
        if cur.rstrip("/") == "https://erp.91miaoshou.com":
            return False
        return any(marker in cur for marker in ("/welcome", "/dashboard"))

    def _known_login_error_texts(self) -> tuple[str, ...]:
        return (
            "图形验证码不正确",
            "账号或密码错误",
            "用户名或密码错误",
            "验证码错误",
            "登录失败",
        )

    def _homepage_ready_texts(self) -> tuple[str, ...]:
        return (
            "待办事项",
            "常用功能",
            "首页",
            "产品",
            "订单",
            "采购",
        )

    def _username_locator(self, page: Any) -> Any:
        return page.get_by_role("textbox", name=re.compile(r"手机|子账户|邮箱", re.IGNORECASE)).first

    def _password_locator(self, page: Any) -> Any:
        return page.get_by_role("textbox", name=re.compile(r"密码", re.IGNORECASE)).first

    def _captcha_locator(self, page: Any) -> Any:
        return page.get_by_role("textbox", name=re.compile(r"验证码", re.IGNORECASE)).first

    def _login_button_locator(self, page: Any) -> Any:
        return page.get_by_role("button", name=re.compile(r"立即登录|登录", re.IGNORECASE)).first

    async def _homepage_ready(self, page: Any) -> bool:
        if not self._login_looks_successful(str(getattr(page, "url", "") or "")):
            return False

        for text in self._homepage_ready_texts():
            try:
                locator = page.get_by_text(text, exact=False).first
                if await locator.is_visible(timeout=1500):
                    return True
            except Exception:
                pass
        return False

    async def _raise_graphical_captcha(self, page: Any, config: dict[str, Any]) -> None:
        screenshot_dir = config.get("task", {}).get("screenshot_dir")
        if screenshot_dir:
            os.makedirs(screenshot_dir, exist_ok=True)
            screenshot_path = os.path.join(screenshot_dir, "captcha.png")
        else:
            import tempfile

            fd, screenshot_path = tempfile.mkstemp(suffix=".png", prefix="captcha_")
            os.close(fd)
        await page.screenshot(path=screenshot_path, timeout=5000)
        raise VerificationRequiredError("graphical_captcha", screenshot_path)

    async def _find_visible_login_error(self, page: Any) -> str | None:
        for text in self._known_login_error_texts():
            try:
                locator = page.get_by_text(text, exact=False).first
                if await locator.is_visible(timeout=500):
                    return text
            except Exception:
                pass
        return None

    async def _cleanup_after_login(self, page: Any) -> None:
        try:
            from modules.platforms.miaoshou.components.overlay_guard import OverlayGuard

            await OverlayGuard().run(page, label="post-login cleanup")
        except Exception:
            pass

    async def _wait_for_login_outcome(
        self,
        page: Any,
        *,
        timeout_ms: int = 30000,
        poll_ms: int = 500,
    ) -> str:
        waited = 0
        while waited <= timeout_ms:
            try:
                remaining = max(timeout_ms - waited, 1)
                await page.wait_for_load_state("domcontentloaded", timeout=min(2000, remaining))
            except Exception:
                pass

            error_text = await self._find_visible_login_error(page)
            if error_text:
                return error_text

            if await self._homepage_ready(page):
                return "success"

            await asyncio.sleep(poll_ms / 1000)
            waited += poll_ms

        return "timeout"

    async def _submit_with_current_page_values(self, page: Any) -> LoginResult:
        login_button = self._login_button_locator(page)
        await expect(login_button).to_be_visible(timeout=10000)
        await login_button.click(timeout=5000)
        outcome = await self._wait_for_login_outcome(page)
        if outcome == "success":
            await self._cleanup_after_login(page)
            return LoginResult(success=True, message="ok")
        if outcome != "timeout":
            return LoginResult(success=False, message=outcome)
        current_url = str(getattr(page, "url", "") or "")
        return LoginResult(success=False, message=f"login did not reach a logged-in home page (url={current_url})")

    async def _submit_captcha_from_resume(self, page: Any, value: str) -> LoginResult:
        captcha_input = self._captcha_locator(page)
        await expect(captcha_input).to_be_visible(timeout=10000)
        await captcha_input.fill(value, timeout=5000)
        return await self._submit_with_current_page_values(page)

    async def run(self, page: Any) -> LoginResult:
        acc = self.ctx.account or {}
        config = self.ctx.config or {}
        if await self._homepage_ready(page):
            await self._cleanup_after_login(page)
            return LoginResult(success=True, message="already logged in")

        params = config.get("params") or {}
        resumed_code = (params.get("captcha_code") or params.get("otp") or "").strip()
        if resumed_code:
            return await self._submit_captcha_from_resume(page, resumed_code)

        login_url = acc.get("login_url") or "https://erp.91miaoshou.com"
        try:
            await page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(1.0)
        except Exception as e:
            return LoginResult(success=False, message=f"failed to open login page: {e}")

        if await self._homepage_ready(page):
            await self._cleanup_after_login(page)
            return LoginResult(success=True, message="ok")

        username_input = self._username_locator(page)
        await expect(username_input).to_be_visible(timeout=15000)
        await username_input.fill(acc.get("username", ""), timeout=10000)

        password_input = self._password_locator(page)
        await expect(password_input).to_be_visible(timeout=10000)
        await password_input.fill(acc.get("password", ""), timeout=10000)

        captcha_input = self._captcha_locator(page)
        await expect(captcha_input).to_be_visible(timeout=10000)
        await self._raise_graphical_captcha(page, config)

        return await self._submit_with_current_page_values(page)
