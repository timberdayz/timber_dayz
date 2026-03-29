from __future__ import annotations

import os
import re
import tempfile
from typing import Any

from modules.apps.collection_center.executor_v2 import VerificationRequiredError
from modules.components.base import ExecutionContext
from modules.components.login.base import LoginComponent, LoginResult


class TiktokLogin(LoginComponent):
    """Canonical TikTok Shop login component for V2.

    Current recording evidence confirms:
    - login entry page
    - phone/email login mode switch
    - credential submit flow
    - 2FA page with trust-device control
    - invalid OTP error signal

    Homepage-ready signals are not fully recorded yet, so success detection
    currently relies on leaving the login URL surface.
    """

    platform = "tiktok"
    component_type = "login"
    data_domain = None

    def __init__(self, ctx: ExecutionContext) -> None:
        super().__init__(ctx)

    def _login_looks_successful(self, url: str) -> bool:
        cur = str(url or "").strip().lower()
        if not cur:
            return False
        if "seller.tiktokshopglobalselling.com" not in cur and "seller.tiktokglobalshop.com" not in cur:
            return False
        if "/account/login" in cur:
            return False
        return True

    def _credential_value_for_mode(self, account: dict[str, Any], mode: str) -> str:
        if mode == "phone":
            return str(account.get("phone") or account.get("username") or "").strip()
        return str(account.get("email") or account.get("username") or account.get("phone") or "").strip()

    def _known_login_error_texts(self) -> tuple[str, ...]:
        return (
            "账号或密码错误",
            "用户名或密码错误",
            "Incorrect account or password",
            "Incorrect email or password",
            "Incorrect phone number or password",
            "登录失败",
        )

    def _known_otp_error_texts(self) -> tuple[str, ...]:
        return (
            "请输入6位数字验证码",
            "验证码错误",
            "验证码不正确",
            "请输入正确的验证码",
            "Please enter a 6-digit code",
            "The code is incorrect",
            "Invalid code",
        )

    def _phone_input_locator(self, page: Any) -> Any:
        return page.locator(
            'input[placeholder*="手机号"], input[placeholder*="手机号码"], input[type="tel"], input[autocomplete="tel"]'
        ).first

    def _email_input_locator(self, page: Any) -> Any:
        return page.locator('input[placeholder*="邮箱"], input[type="email"]').first

    def _password_locator(self, page: Any) -> Any:
        return page.locator('input[type="password"]').first

    def _login_button_locator(self, page: Any) -> Any:
        return page.get_by_role("button", name=re.compile("登录", re.IGNORECASE)).first

    def _email_login_switch_locator(self, page: Any) -> Any:
        return page.get_by_text("使用邮箱登录", exact=False).first

    def _phone_login_switch_locator(self, page: Any) -> Any:
        return page.get_by_text("使用手机号登录", exact=False).first

    def _otp_input_locator(self, page: Any) -> Any:
        return page.locator(
            '#TT4B_TSV_Verify_Code_Input, input[name="code"], input[name*="otp"], input[placeholder*="验证码"]'
        ).first

    def _otp_confirm_locator(self, page: Any) -> Any:
        return page.get_by_role("button", name=re.compile("确认", re.IGNORECASE)).first

    def _trust_device_container_locator(self, page: Any) -> Any:
        return page.locator("#TT4B_TSV_Verify_Check").first

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

    async def _current_login_mode(self, page: Any) -> str:
        if await self._locator_is_visible(self._email_input_locator(page), timeout=300):
            return "email"
        if await self._locator_is_visible(self._phone_input_locator(page), timeout=300):
            return "phone"
        if await self._locator_is_visible(self._phone_login_switch_locator(page), timeout=300):
            return "email"
        return "phone"

    async def _ensure_login_mode(self, page: Any, target_mode: str) -> None:
        current_mode = await self._current_login_mode(page)
        if current_mode == target_mode:
            return

        switch = (
            self._phone_login_switch_locator(page)
            if target_mode == "phone"
            else self._email_login_switch_locator(page)
        )
        if not await self._locator_is_visible(switch, timeout=1500):
            raise RuntimeError(f"cannot switch login mode to {target_mode}")
        await switch.click(timeout=5000)
        await page.wait_for_timeout(500)

        current_mode = await self._current_login_mode(page)
        if current_mode != target_mode:
            raise RuntimeError(f"failed to switch login mode to {target_mode}")

    async def _is_otp_visible(self, page: Any) -> bool:
        input_visible = await self._locator_is_visible(self._otp_input_locator(page), timeout=1000)
        confirm_visible = await self._locator_is_visible(self._otp_confirm_locator(page), timeout=1000)
        return input_visible and confirm_visible

    async def _fill_credentials(self, page: Any, account: dict[str, Any]) -> None:
        mode = await self._current_login_mode(page)
        credential = self._credential_value_for_mode(account, mode)
        if not credential:
            raise RuntimeError(f"missing credential value for {mode} login mode")

        locator = self._phone_input_locator(page) if mode == "phone" else self._email_input_locator(page)
        await locator.fill(credential, timeout=10000)
        await self._password_locator(page).fill(str(account.get("password") or "").strip(), timeout=10000)

    async def _submit_credentials(self, page: Any) -> None:
        await self._login_button_locator(page).click(timeout=5000)

    async def _fill_otp(self, page: Any, otp_value: str) -> None:
        await self._otp_input_locator(page).fill(otp_value, timeout=5000)

    async def _ensure_trust_device_checked(self, page: Any) -> None:
        try:
            container = self._trust_device_container_locator(page)
            if await self._locator_is_visible(container, timeout=1000):
                classes = (await container.get_attribute("class")) or ""
                if "checked" in classes:
                    return
                await container.click(timeout=3000)
                await page.wait_for_timeout(200)
                return
        except Exception:
            pass

        try:
            checkbox = page.locator('input[type="checkbox"]').first
            if await self._locator_is_visible(checkbox, timeout=500):
                await checkbox.check(timeout=3000)
                return
        except Exception:
            pass

        try:
            label = page.get_by_text("在这台设备上不再询问", exact=False).first
            if await self._locator_is_visible(label, timeout=500):
                await label.click(timeout=3000)
        except Exception:
            pass

    async def _confirm_otp(self, page: Any) -> None:
        await self._otp_confirm_locator(page).click(timeout=5000)

    async def _cleanup_after_login(self, page: Any) -> None:
        return None

    async def _raise_otp_verification_required(self, page: Any, config: dict[str, Any]) -> None:
        screenshot_dir = (config or {}).get("task", {}).get("screenshot_dir")
        if screenshot_dir:
            os.makedirs(screenshot_dir, exist_ok=True)
            screenshot_path = os.path.join(screenshot_dir, "tiktok-login-otp.png")
        else:
            fd, screenshot_path = tempfile.mkstemp(suffix=".png", prefix="tiktok_login_otp_")
            os.close(fd)
        await page.screenshot(path=screenshot_path, timeout=5000)
        raise VerificationRequiredError("otp", screenshot_path)

    async def _submit_resumed_otp(self, page: Any, otp_value: str) -> LoginResult:
        await self._fill_otp(page, otp_value)
        await self._ensure_trust_device_checked(page)
        await self._confirm_otp(page)
        await page.wait_for_timeout(800)

        otp_error = await self._find_visible_otp_error(page)
        if otp_error:
            return LoginResult(success=False, message=otp_error)

        if self._login_looks_successful(str(getattr(page, "url", "") or "")):
            await self._cleanup_after_login(page)
            return LoginResult(success=True, message="ok")

        if not await self._is_otp_visible(page):
            await self._cleanup_after_login(page)
            return LoginResult(success=True, message="ok")

        return LoginResult(success=False, message="otp did not leave verification screen")

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

            password = str(acc.get("password") or "").strip()
            if not password:
                return LoginResult(success=False, message="password is required in account")

            await page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(800)

            if self._login_looks_successful(str(getattr(page, "url", "") or "")):
                await self._cleanup_after_login(page)
                return LoginResult(success=True, message="ok")

            target_mode = "phone" if str(acc.get("phone") or "").strip() else "email"
            await self._ensure_login_mode(page, target_mode)
            await self._fill_credentials(page, acc)
            await self._submit_credentials(page)
            await page.wait_for_timeout(800)

            login_error = await self._find_visible_login_error(page)
            if login_error:
                return LoginResult(success=False, message=login_error)

            if self._login_looks_successful(str(getattr(page, "url", "") or "")):
                await self._cleanup_after_login(page)
                return LoginResult(success=True, message="ok")

            if await self._is_otp_visible(page):
                await self._ensure_trust_device_checked(page)
                if not otp_value:
                    await self._raise_otp_verification_required(page, config)
                return await self._submit_resumed_otp(page, otp_value)

            return LoginResult(success=False, message="login did not reach homepage or otp step")
        except VerificationRequiredError:
            raise
        except Exception as e:
            return LoginResult(success=False, message=str(e))
