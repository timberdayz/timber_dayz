from __future__ import annotations

import asyncio
import os
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

    def _captcha_locator(self, form: Any) -> Any:
        return form.locator(
            "input.captcha-text, input[placeholder*='验证码'], input[name*='captcha' i], input[name*='code' i]"
        ).first

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

    async def _submit_captcha_from_resume(self, page: Any, value: str) -> LoginResult:
        form = page.locator("#J_loginRegisterForm")
        captcha_input = self._captcha_locator(form)
        await expect(captcha_input).to_be_visible(timeout=10000)
        await captcha_input.fill(value, timeout=5000)
        login_button = form.locator("button.login").first
        await expect(login_button).to_be_visible(timeout=10000)
        await login_button.click(timeout=5000)
        await asyncio.sleep(2.0)
        if self._login_looks_successful(str(getattr(page, "url", "") or "")):
            return LoginResult(success=True, message="ok")
        return LoginResult(success=False, message="captcha submit did not reach a logged-in page")

    async def run(self, page: Any) -> LoginResult:
        acc = self.ctx.account or {}
        config = self.ctx.config or {}
        current_url = str(getattr(page, "url", "") or "")
        if self._login_looks_successful(current_url):
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

        form = page.locator("#J_loginRegisterForm")

        username_input = form.locator("input.account-input").first
        await expect(username_input).to_be_visible(timeout=15000)
        await username_input.fill(acc.get("username", ""), timeout=10000)

        password_input = form.locator("input.password-input").first
        await expect(password_input).to_be_visible(timeout=10000)
        await password_input.fill(acc.get("password", ""), timeout=10000)

        captcha_input = self._captcha_locator(form)
        await expect(captcha_input).to_be_visible(timeout=10000)
        await captcha_input.click(timeout=10000)

        await asyncio.sleep(2.5)
        try:
            if await captcha_input.count() > 0 and await captcha_input.is_visible(timeout=3000):
                await self._raise_graphical_captcha(page, config)
        except VerificationRequiredError:
            raise
        except Exception:
            pass

        login_button = form.locator("button.login").first
        await expect(login_button).to_be_visible(timeout=10000)
        await login_button.click(timeout=10000)

        await asyncio.sleep(2.0)
        if self._login_looks_successful(str(getattr(page, "url", "") or "")):
            return LoginResult(success=True, message="ok")
        return LoginResult(success=False, message="login did not reach a logged-in page")
