from __future__ import annotations

import os
import re
import tempfile
from typing import Any

from modules.apps.collection_center.executor_v2 import VerificationRequiredError
from modules.components.base import ExecutionContext
from modules.components.login.base import LoginComponent, LoginResult


class ShopeeLogin(LoginComponent):
    """Canonical Shopee China login component for V2."""

    platform = "shopee"
    component_type = "login"
    data_domain = None

    def __init__(self, ctx: ExecutionContext) -> None:
        super().__init__(ctx)

    def _login_looks_successful(self, url: str) -> bool:
        cur = str(url or "").strip().lower()
        if not cur:
            return False
        if "seller.shopee.cn" not in cur:
            return False
        if "/account/signin" in cur:
            return False
        return True

    def _otp_mode_from_title(self, title: str) -> str | None:
        text = str(title or "").strip()
        if not text:
            return None
        if "验证电话号码" in text or "发送至您电话" in text or "发送至电话" in text:
            return "phone"
        if "邮箱验证" in text or "发送至您邮箱" in text or "发送至邮箱" in text:
            return "email"
        return None

    def _known_login_error_texts(self) -> tuple[str, ...]:
        return (
            "账号或密码有误",
            "账号或密码有误，请检查后重试",
            "登录失败",
        )

    def _known_otp_error_texts(self) -> tuple[str, ...]:
        return (
            "验证码填错了",
            "请填入正确的验证码",
            "验证码错误",
            "OTP",
        )

    def _username_locator(self, page: Any) -> Any:
        return page.locator('input[placeholder*="子母账号登录名"], input[placeholder*="手机"], input[placeholder*="邮箱"]').first

    def _password_locator(self, page: Any) -> Any:
        return page.locator('input[type="password"]').first

    def _login_button_locator(self, page: Any) -> Any:
        return page.get_by_role("button", name=re.compile("登录|登入", re.IGNORECASE)).first

    def _otp_input_locator(self, page: Any) -> Any:
        return page.locator('input[placeholder*="请输入"]').first

    def _otp_confirm_locator(self, page: Any) -> Any:
        return page.get_by_role("button", name=re.compile("确认", re.IGNORECASE)).first

    def _phone_otp_switch_locator(self, page: Any) -> Any:
        return page.get_by_role("button", name=re.compile("发送至电话", re.IGNORECASE)).first

    def _email_otp_switch_locator(self, page: Any) -> Any:
        return page.get_by_role("button", name=re.compile("发送至邮箱", re.IGNORECASE)).first

    async def _locator_is_visible(self, locator: Any, timeout: int = 500) -> bool:
        try:
            return bool(await locator.is_visible(timeout=timeout))
        except Exception:
            return False

    async def _find_visible_text(self, page: Any, texts: tuple[str, ...]) -> str | None:
        for text in texts:
            try:
                locator = page.get_by_text(text, exact=False).first
                if await self._locator_is_visible(locator):
                    return text
            except Exception:
                continue
        return None

    async def _find_visible_login_error(self, page: Any) -> str | None:
        return await self._find_visible_text(page, self._known_login_error_texts())

    async def _find_visible_otp_error(self, page: Any) -> str | None:
        return await self._find_visible_text(page, self._known_otp_error_texts())

    async def _otp_mode(self, page: Any) -> str | None:
        texts = (
            "验证电话号码",
            "请输入已发送至您电话的OTP码以验证身份",
            "邮箱验证",
            "请输入已发送至您邮箱的OTP以验证您的身份",
            "发送至电话",
            "发送至邮箱",
        )
        for text in texts:
            try:
                locator = page.get_by_text(text, exact=False).first
                if await self._locator_is_visible(locator):
                    mode = self._otp_mode_from_title(text)
                    if mode:
                        return mode
            except Exception:
                continue
        return None

    async def _is_otp_visible(self, page: Any) -> bool:
        input_visible = await self._locator_is_visible(self._otp_input_locator(page), timeout=1000)
        confirm_visible = await self._locator_is_visible(self._otp_confirm_locator(page), timeout=1000)
        return input_visible and confirm_visible

    async def _fill_credentials(self, page: Any, username: str, password: str) -> None:
        await self._username_locator(page).fill(username, timeout=10000)
        await self._password_locator(page).fill(password, timeout=10000)

    async def _submit_credentials(self, page: Any) -> None:
        await self._login_button_locator(page).click(timeout=5000)

    async def _fill_otp(self, page: Any, otp_value: str) -> None:
        await self._otp_input_locator(page).fill(otp_value, timeout=5000)

    async def _confirm_otp(self, page: Any) -> None:
        await self._otp_confirm_locator(page).click(timeout=5000)

    async def _ensure_phone_otp_mode(self, page: Any) -> None:
        mode = await self._otp_mode(page)
        if mode != "email":
            return
        switch_button = self._phone_otp_switch_locator(page)
        if not await self._locator_is_visible(switch_button, timeout=1500):
            raise RuntimeError("otp page is in email mode but cannot switch back to phone")
        await switch_button.click(timeout=5000)
        await page.wait_for_timeout(500)
        if await self._otp_mode(page) != "phone":
            raise RuntimeError("failed to switch otp mode back to phone")

    async def _cleanup_after_login(self, page: Any) -> None:
        return None

    async def _raise_otp_verification_required(self, page: Any, config: dict[str, Any]) -> None:
        screenshot_dir = (config or {}).get("task", {}).get("screenshot_dir")
        if screenshot_dir:
            os.makedirs(screenshot_dir, exist_ok=True)
            screenshot_path = os.path.join(screenshot_dir, "shopee-login-otp.png")
        else:
            fd, screenshot_path = tempfile.mkstemp(suffix=".png", prefix="shopee_login_otp_")
            os.close(fd)
        await page.screenshot(path=screenshot_path, timeout=5000)
        raise VerificationRequiredError("otp", screenshot_path)

    async def _submit_resumed_otp(self, page: Any, otp_value: str) -> LoginResult:
        await self._ensure_phone_otp_mode(page)
        await self._fill_otp(page, otp_value)
        await self._confirm_otp(page)
        await page.wait_for_timeout(800)

        otp_error = await self._find_visible_otp_error(page)
        if otp_error:
            return LoginResult(success=False, message=otp_error)

        if self._login_looks_successful(str(getattr(page, "url", "") or "")):
            await self._cleanup_after_login(page)
            return LoginResult(success=True, message="ok")

        return LoginResult(success=False, message="otp did not reach homepage")

    async def run(self, page: Any) -> LoginResult:
        acc = self.ctx.account or {}
        config = self.ctx.config or {}
        params = config.get("params") or {}
        current_url = str(getattr(page, "url", "") or "")
        otp_value = str(params.get("captcha_code") or params.get("otp") or "").strip()

        if self._login_looks_successful(current_url):
            await self._cleanup_after_login(page)
            return LoginResult(success=True, message="already logged in")

        try:
            if otp_value and await self._is_otp_visible(page):
                return await self._submit_resumed_otp(page, otp_value)

            login_url = str(acc.get("login_url") or "").strip()
            if not login_url:
                return LoginResult(success=False, message="login_url is required in account")

            username = str(acc.get("username") or "").strip()
            password = str(acc.get("password") or "").strip()
            if not username or not password:
                return LoginResult(success=False, message="username and password are required in account")

            await page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(800)

            if self._login_looks_successful(str(getattr(page, "url", "") or "")):
                await self._cleanup_after_login(page)
                return LoginResult(success=True, message="ok")

            await self._fill_credentials(page, username, password)
            await self._submit_credentials(page)
            await page.wait_for_timeout(800)

            login_error = await self._find_visible_login_error(page)
            if login_error:
                return LoginResult(success=False, message=login_error)

            if self._login_looks_successful(str(getattr(page, "url", "") or "")):
                await self._cleanup_after_login(page)
                return LoginResult(success=True, message="ok")

            if await self._is_otp_visible(page):
                await self._ensure_phone_otp_mode(page)
                if not otp_value:
                    await self._raise_otp_verification_required(page, config)
                return await self._submit_resumed_otp(page, otp_value)

            return LoginResult(success=False, message="login did not reach homepage or otp step")
        except VerificationRequiredError:
            raise
        except Exception as e:
            return LoginResult(success=False, message=str(e))
