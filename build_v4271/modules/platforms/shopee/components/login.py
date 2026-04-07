from __future__ import annotations

import asyncio
import os
import re
import tempfile
from typing import Any

from modules.apps.collection_center.executor_v2 import VerificationRequiredError
from backend.services.platform_login_entry_service import get_platform_login_entry
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
        current = str(url or "").strip().lower()
        if not current:
            return False
        if "seller.shopee.cn" not in current:
            return False
        if "/account/signin" in current:
            return False
        return True

    def _homepage_looks_ready(self, url: str) -> bool:
        current = str(url or "").strip().lower()
        if not current:
            return False
        if not self._login_looks_successful(current):
            return False
        return current.startswith("https://seller.shopee.cn/?") and "cnsc_shop_id=" in current

    async def _homepage_dom_looks_ready(self, page: Any) -> bool:
        signal_count = 0
        for selector in (
            'a[href*="/datacenter/"]',
            'a[href*="/portal/sale/order"]',
            'a[href*="/portal/product"]',
        ):
            try:
                locator = page.locator(selector).first
                if await self._locator_is_visible(locator, timeout=500):
                    signal_count += 1
            except Exception:
                continue

        username = str((self.ctx.account or {}).get("username") or "").strip()
        if username:
            try:
                username_locator = page.get_by_text(username, exact=False).first
                if await self._locator_is_visible(username_locator, timeout=500):
                    signal_count += 1
            except Exception:
                pass

        if signal_count < 2:
            return False

        if await self._is_otp_visible(page):
            return False

        if await self._locator_is_visible(self._password_locator(page), timeout=300):
            return False

        if await self._locator_is_visible(self._login_button_locator(page), timeout=300):
            return False

        return True

    async def _session_shell_looks_ready(self, page: Any, url: str) -> bool:
        current = str(url or "").strip()
        if not self._login_looks_successful(current):
            return False
        if self._homepage_looks_ready(current):
            return False
        if await self._is_otp_visible(page):
            return False
        if await self._locator_is_visible(self._password_locator(page), timeout=300):
            return False
        if await self._locator_is_visible(self._login_button_locator(page), timeout=300):
            return False

        signal_count = 0
        username = str((self.ctx.account or {}).get("username") or "").strip()
        if username:
            try:
                username_locator = page.get_by_text(username, exact=False).first
                if await self._locator_is_visible(username_locator, timeout=500):
                    signal_count += 1
            except Exception:
                pass

        for selector in (
            'a[href="/"]',
            'button[aria-haspopup="menu"]',
        ):
            try:
                locator = page.locator(selector).first
                if await self._locator_is_visible(locator, timeout=500):
                    signal_count += 1
            except Exception:
                continue

        return signal_count >= 2

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
        )

    def _username_locator(self, page: Any) -> Any:
        return page.locator(
            'input[placeholder*="子母账号登录名"], input[placeholder*="手机"], input[placeholder*="邮箱"], input[name="loginKey"]'
        ).first

    def _password_locator(self, page: Any) -> Any:
        return page.locator('input[type="password"]').first

    def _remember_me_checkbox_locator(self, page: Any) -> Any:
        return page.locator('input[type="checkbox"], [role="checkbox"]').first

    def _remember_me_label_locator(self, page: Any) -> Any:
        return page.get_by_text("记住我", exact=False).first

    def _login_button_locator(self, page: Any) -> Any:
        return page.get_by_role("button", name=re.compile("登录|登入", re.IGNORECASE)).first

    def _otp_input_locator(self, page: Any) -> Any:
        return page.locator('input[placeholder*="请输入"]').first

    def _otp_confirm_locator(self, page: Any) -> Any:
        return page.get_by_role("button", name=re.compile("确认", re.IGNORECASE)).first

    def _phone_otp_switch_locator(self, page: Any) -> Any:
        return page.get_by_role("button", name=re.compile("发送至电话", re.IGNORECASE)).first

    async def _locator_is_visible(self, locator: Any, timeout: int = 500) -> bool:
        try:
            return bool(await locator.is_visible(timeout=timeout))
        except Exception:
            return False

    async def _is_slide_captcha_visible(self, page: Any) -> bool:
        indicators = (
            "滑动验证",
            "请拖动滑块",
            "拖动滑块",
            "向右滑动",
            "请滑动以完成拼图",
            "完成拼图",
            "Verification",
        )
        for text in indicators:
            try:
                locator = page.get_by_text(text, exact=False).first
                if await self._locator_is_visible(locator, timeout=500):
                    return True
            except Exception:
                continue
        selectors = (
            '[class*="captcha-slider"]',
            '[class*="slider"]',
            '[id*="captcha"]',
            '[data-nc-idx]',
            '.nc_wrapper',
            '.nc-container',
        )
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if await self._locator_is_visible(locator, timeout=500):
                    return True
            except Exception:
                continue
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

    async def _ensure_remember_me_checked(self, page: Any) -> None:
        checkbox = self._remember_me_checkbox_locator(page)
        try:
            if await checkbox.count() > 0:
                try:
                    if await checkbox.is_checked():
                        return
                except Exception:
                    pass
                try:
                    await checkbox.check(timeout=3000)
                    return
                except Exception:
                    try:
                        await checkbox.click(timeout=3000)
                        await page.wait_for_timeout(300)
                        return
                    except Exception:
                        pass
        except Exception:
            pass

        label = self._remember_me_label_locator(page)
        if await self._locator_is_visible(label, timeout=500):
            await label.click(timeout=3000)
            await page.wait_for_timeout(300)

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

    async def _raise_slide_captcha_verification_required(self, page: Any, config: dict[str, Any]) -> None:
        screenshot_dir = (config or {}).get("task", {}).get("screenshot_dir")
        if screenshot_dir:
            os.makedirs(screenshot_dir, exist_ok=True)
            screenshot_path = os.path.join(screenshot_dir, "shopee-login-slide-captcha.png")
        else:
            fd, screenshot_path = tempfile.mkstemp(suffix=".png", prefix="shopee_login_slide_")
            os.close(fd)
        await page.screenshot(path=screenshot_path, timeout=5000)
        raise VerificationRequiredError("slide_captcha", screenshot_path)

    async def _raise_manual_intervention_required(
        self,
        page: Any,
        config: dict[str, Any],
    ) -> None:
        screenshot_dir = (config or {}).get("task", {}).get("screenshot_dir")
        if screenshot_dir:
            os.makedirs(screenshot_dir, exist_ok=True)
            screenshot_path = os.path.join(
                screenshot_dir,
                "shopee-login-manual-intervention.png",
            )
        else:
            fd, screenshot_path = tempfile.mkstemp(
                suffix=".png",
                prefix="shopee_login_manual_",
            )
            os.close(fd)
        await page.screenshot(path=screenshot_path, timeout=5000)
        raise VerificationRequiredError("manual_intervention", screenshot_path)

    async def _wait_for_post_login_outcome(
        self,
        page: Any,
        *,
        phase: str = "post_credentials",
        timeout_ms: int = 30000,
        poll_ms: int = 500,
    ) -> str:
        waited = 0
        homepage_stable_hits = 0
        session_shell_hits = 0
        while waited <= timeout_ms:
            login_error = await self._find_visible_login_error(page)
            if login_error:
                return login_error

            current_url = str(getattr(page, "url", "") or "")
            if self._homepage_looks_ready(current_url):
                if await self._homepage_dom_looks_ready(page):
                    homepage_stable_hits += 1
                    if homepage_stable_hits >= 2:
                        return "success"
                else:
                    homepage_stable_hits = 0
            else:
                homepage_stable_hits = 0

            if await self._session_shell_looks_ready(page, current_url):
                session_shell_hits += 1
                if session_shell_hits >= 2:
                    return "manual_intervention"
            else:
                session_shell_hits = 0

            if phase == "post_credentials":
                if await self._is_slide_captcha_visible(page):
                    return "slide_captcha"
                if await self._is_otp_visible(page):
                    return "otp"
            elif phase == "post_manual_verification":
                if await self._is_otp_visible(page):
                    return "otp"
                if await self._is_slide_captcha_visible(page):
                    return "slide_captcha"
            else:
                otp_error = await self._find_visible_otp_error(page)
                if otp_error:
                    return otp_error
                if await self._is_slide_captcha_visible(page):
                    return "slide_captcha"
                if await self._is_otp_visible(page):
                    try:
                        await page.wait_for_timeout(poll_ms)
                    except Exception:
                        await asyncio.sleep(poll_ms / 1000)
                    waited += poll_ms
                    continue

            try:
                await page.wait_for_timeout(poll_ms)
            except Exception:
                await asyncio.sleep(poll_ms / 1000)
            waited += poll_ms

        return "timeout"

    async def _submit_resumed_otp(self, page: Any, otp_value: str) -> LoginResult:
        await self._ensure_phone_otp_mode(page)
        await self._fill_otp(page, otp_value)
        await self._confirm_otp(page)

        outcome = await self._wait_for_post_login_outcome(page, phase="post_otp_submit")
        if outcome == "success":
            await self._cleanup_after_login(page)
            return LoginResult(success=True, message="ok")
        if outcome == "manual_intervention":
            await self._raise_manual_intervention_required(page, self.ctx.config or {})
        if outcome not in {"timeout", "otp", "slide_captcha"}:
            return LoginResult(success=False, message=outcome)
        return LoginResult(success=False, message="otp did not reach homepage")

    async def run(self, page: Any) -> LoginResult:
        account = self.ctx.account or {}
        config = self.ctx.config or {}
        params = config.get("params") or {}
        current_url = str(getattr(page, "url", "") or "")
        otp_value = str(params.get("captcha_code") or params.get("otp") or "").strip()
        manual_completed = bool(params.get("manual_completed"))

        if self._login_looks_successful(current_url):
            await self._cleanup_after_login(page)
            return LoginResult(success=True, message="already logged in")

        try:
            if await self._is_otp_visible(page):
                await self._ensure_phone_otp_mode(page)
                if not otp_value:
                    await self._raise_otp_verification_required(page, config)
                return await self._submit_resumed_otp(page, otp_value)

            if otp_value and await self._is_otp_visible(page):
                return await self._submit_resumed_otp(page, otp_value)

            if manual_completed:
                outcome = await self._wait_for_post_login_outcome(
                    page,
                    phase="post_manual_verification",
                    timeout_ms=10000,
                    poll_ms=300,
                )
                if outcome == "success":
                    await self._cleanup_after_login(page)
                    return LoginResult(success=True, message="ok")
                if outcome == "otp":
                    await self._ensure_phone_otp_mode(page)
                    if not otp_value:
                        await self._raise_otp_verification_required(page, config)
                    return await self._submit_resumed_otp(page, otp_value)
                if outcome == "manual_intervention":
                    await self._raise_manual_intervention_required(page, config)
                if outcome == "slide_captcha":
                    await self._raise_slide_captcha_verification_required(page, config)
                if outcome != "timeout":
                    return LoginResult(success=False, message=outcome)
                return LoginResult(
                    success=False,
                    message="manual verification did not reach otp or homepage",
                )

            login_url = str(account.get("login_url") or get_platform_login_entry(self.platform)).strip()

            username = str(account.get("username") or "").strip()
            password = str(account.get("password") or "").strip()
            if not username or not password:
                return LoginResult(success=False, message="username and password are required in account")

            await page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(800)

            if self._login_looks_successful(str(getattr(page, "url", "") or "")):
                await self._cleanup_after_login(page)
                return LoginResult(success=True, message="ok")

            await self._fill_credentials(page, username, password)
            await self._ensure_remember_me_checked(page)
            await self._submit_credentials(page)

            outcome = await self._wait_for_post_login_outcome(page, phase="post_credentials")
            if outcome == "success":
                await self._cleanup_after_login(page)
                return LoginResult(success=True, message="ok")
            if outcome == "slide_captcha":
                if not manual_completed:
                    await self._raise_slide_captcha_verification_required(page, config)
                return LoginResult(success=False, message="slide captcha still present after manual completion")
            if outcome == "otp":
                await self._ensure_phone_otp_mode(page)
                if not otp_value:
                    await self._raise_otp_verification_required(page, config)
                return await self._submit_resumed_otp(page, otp_value)
            if outcome == "manual_intervention":
                await self._raise_manual_intervention_required(page, config)
            if outcome != "timeout":
                return LoginResult(success=False, message=outcome)

            return LoginResult(success=False, message="login did not reach homepage or otp step")
        except VerificationRequiredError:
            raise
        except Exception as e:
            return LoginResult(success=False, message=str(e))
