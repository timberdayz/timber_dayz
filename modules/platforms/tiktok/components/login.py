from __future__ import annotations

import os
import re
import tempfile
from typing import Any

from modules.apps.collection_center.executor_v2 import VerificationRequiredError
from backend.services.platform_login_entry_service import get_platform_login_entry
from modules.components.base import ExecutionContext
from modules.components.login.base import LoginComponent, LoginResult
from modules.platforms.tiktok.archive.analytics_config import AnalyticsSelectors


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
            '#TT4B_TSV_Verify_Code_Input, input[name="code"], input[name*="otp"], input[placeholder*="验证码"], input[autocomplete="one-time-code"], input[inputmode="numeric"]'
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

    async def _count_visible_texts(self, page: Any, texts: tuple[str, ...]) -> int:
        count = 0
        for text in texts:
            try:
                locator = page.get_by_text(text, exact=False).first
                if await self._locator_is_visible(locator):
                    count += 1
            except Exception:
                continue
        return count

    async def _first_visible_locator(
        self,
        locators: tuple[Any, ...],
        *,
        timeout: int = 500,
    ) -> Any | None:
        for locator in locators:
            if await self._locator_is_visible(locator, timeout=timeout):
                return locator
        return None

    def _otp_input_locators(self, page: Any) -> tuple[Any, ...]:
        return (
            self._otp_input_locator(page),
            page.get_by_role("textbox", name=re.compile("验证码", re.IGNORECASE)).first,
        )

    def _otp_confirm_locators(self, page: Any) -> tuple[Any, ...]:
        return (
            self._otp_confirm_locator(page),
            page.locator('button:has-text("确认"), button:has-text("确定")').first,
        )

    def _otp_surface_texts(self) -> tuple[str, ...]:
        return (
            "双重验证",
            "在这台设备上不再询问",
            "本机不再询问",
            "没有收到验证码",
            "发送验证码",
        )

    async def _current_login_mode(self, page: Any) -> str:
        if await self._locator_is_visible(self._email_input_locator(page), timeout=300):
            return "email"
        if await self._locator_is_visible(self._phone_input_locator(page), timeout=300):
            return "phone"
        if await self._locator_is_visible(self._phone_login_switch_locator(page), timeout=300):
            return "email"
        return "phone"

    async def _wait_for_login_surface_ready(
        self,
        page: Any,
        *,
        timeout_ms: int = 10000,
        poll_ms: int = 500,
    ) -> bool:
        elapsed = 0
        while elapsed <= timeout_ms:
            probes = (
                self._phone_input_locator(page),
                self._email_input_locator(page),
                self._password_locator(page),
                self._login_button_locator(page),
                self._email_login_switch_locator(page),
                self._phone_login_switch_locator(page),
            )
            for probe in probes:
                if await self._locator_is_visible(probe, timeout=300):
                    return True
            await page.wait_for_timeout(poll_ms)
            elapsed += poll_ms
        return False

    async def _ensure_login_mode(self, page: Any, target_mode: str) -> None:
        for _ in range(6):
            current_mode = await self._current_login_mode(page)
            if current_mode == target_mode:
                return

            switch = (
                self._phone_login_switch_locator(page)
                if target_mode == "phone"
                else self._email_login_switch_locator(page)
            )
            if await self._locator_is_visible(switch, timeout=500):
                await switch.click(timeout=5000)
            await page.wait_for_timeout(500)

        current_mode = await self._current_login_mode(page)
        if current_mode != target_mode:
            raise RuntimeError(f"cannot switch login mode to {target_mode}")

    async def _is_otp_visible(self, page: Any) -> bool:
        input_locator = await self._first_visible_locator(self._otp_input_locators(page), timeout=1000)
        confirm_locator = await self._first_visible_locator(self._otp_confirm_locators(page), timeout=1000)
        input_visible = input_locator is not None
        confirm_visible = confirm_locator is not None
        surface_text = await self._find_visible_text(page, self._otp_surface_texts())
        surface_text_count = await self._count_visible_texts(page, self._otp_surface_texts())

        if input_visible and confirm_visible:
            return True
        if input_visible and surface_text:
            return True
        if confirm_visible and surface_text:
            return True
        if surface_text_count >= 2:
            return True
        return False

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
        locator = await self._first_visible_locator(self._otp_input_locators(page), timeout=1000)
        if locator is None:
            locator = self._otp_input_locator(page)
        await locator.fill(otp_value, timeout=5000)

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
        locator = await self._first_visible_locator(self._otp_confirm_locators(page), timeout=1000)
        if locator is None:
            locator = self._otp_confirm_locator(page)
        await locator.click(timeout=5000)

    async def _cleanup_after_login(self, page: Any) -> None:
        return None

    async def _homepage_dom_looks_ready(self, page: Any) -> bool:
        config = self.ctx.config or {}
        account = self.ctx.account or {}
        region = str(config.get("shop_region") or account.get("shop_region") or "").strip().upper()
        signal_count = 0
        current_url = str(getattr(page, "url", "") or "").strip().lower()

        if "/homepage" in current_url:
            signal_count += 1

        if region:
            for token in (region, f"{region} ", f"{region} Singapore"):
                try:
                    if await self._locator_is_visible(page.get_by_text(token, exact=False).first, timeout=300):
                        signal_count += 1
                        break
                except Exception:
                    continue

        for text in ("TikTok Shop", "首页", "数据分析", "订单", "商品"):
            try:
                if await self._locator_is_visible(page.get_by_text(text, exact=False).first, timeout=300):
                    signal_count += 1
            except Exception:
                continue

        for selector in (
            'a[href*="/homepage"]',
            'a[href*="/compass/"]',
            'a[href*="/product"]',
            'a[href*="/order"]',
        ):
            try:
                if await self._locator_is_visible(page.locator(selector).first, timeout=300):
                    signal_count += 1
            except Exception:
                continue

        if signal_count < 2:
            return False

        if await self._is_otp_visible(page):
            return False

        if await self._locator_is_visible(self._password_locator(page), timeout=300):
            return False

        if await self._locator_is_visible(self._login_button_locator(page), timeout=300):
            return False

        return True

    async def _data_overview_dom_looks_ready(self, page: Any) -> bool:
        for probe in AnalyticsSelectors.DATA_READY_PROBES:
            try:
                if await self._locator_is_visible(page.locator(probe).first, timeout=300):
                    return True
            except Exception:
                continue

        for text in ("GMV",):
            try:
                if await self._locator_is_visible(page.get_by_text(text, exact=False).first, timeout=300):
                    return True
            except Exception:
                continue

        return False

    async def _session_shell_looks_ready(self, page: Any) -> bool:
        current_url = str(getattr(page, "url", "") or "").strip().lower()
        if not self._login_looks_successful(current_url):
            return False
        if await self._target_looks_ready(page):
            return False
        if await self._is_otp_visible(page):
            return False
        if await self._locator_is_visible(self._password_locator(page), timeout=300):
            return False
        if await self._locator_is_visible(self._login_button_locator(page), timeout=300):
            return False

        signal_count = 0
        for text in ("TikTok Shop", "棣栭〉", "鏁版嵁鍒嗘瀽", "璁㈠崟", "鍟嗗搧", "Seller Center"):
            try:
                if await self._locator_is_visible(page.get_by_text(text, exact=False).first, timeout=300):
                    signal_count += 1
            except Exception:
                continue

        for selector in (
            'a[href*="/homepage"]',
            'a[href*="/compass/"]',
            'a[href*="/product"]',
            'a[href*="/order"]',
            'a[href*="/manage"]',
        ):
            try:
                if await self._locator_is_visible(page.locator(selector).first, timeout=300):
                    signal_count += 1
            except Exception:
                continue

        return signal_count >= 2

    def _login_success_target(self) -> str:
        config = self.ctx.config or {}
        params = config.get("params") or {}
        target = str(params.get("login_success_target") or "homepage").strip().lower()
        return target if target in {"homepage", "data_overview"} else "homepage"

    async def _target_looks_ready(self, page: Any) -> bool:
        cur = str(getattr(page, "url", "") or "").strip().lower()
        if not self._login_looks_successful(cur):
            return False

        if self._login_success_target() == "data_overview":
            if "/compass/data-overview" not in cur:
                return False
            return await self._data_overview_dom_looks_ready(page)

        if "/homepage" not in cur:
            return False
        return await self._homepage_dom_looks_ready(page)

    async def _wait_for_post_login_outcome(
        self,
        page: Any,
        *,
        phase: str,
        timeout_ms: int = 90000,
        poll_ms: int = 1000,
    ) -> str:
        elapsed = 0
        session_shell_hits = 0
        while elapsed <= timeout_ms:
            login_error = await self._find_visible_login_error(page)
            if login_error:
                return "login_error"

            otp_error = await self._find_visible_otp_error(page)
            if otp_error and phase == "post_otp_submit":
                return "otp_error"

            if await self._target_looks_ready(page):
                return "success"

            if await self._session_shell_looks_ready(page):
                session_shell_hits += 1
                if session_shell_hits >= 2:
                    return "success"
            else:
                session_shell_hits = 0

            if await self._is_otp_visible(page):
                if phase == "post_credentials":
                    return "otp"

            await page.wait_for_timeout(poll_ms)
            elapsed += poll_ms

        return "timeout"

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

    async def _raise_manual_intervention_required(self, page: Any, config: dict[str, Any]) -> None:
        screenshot_dir = (config or {}).get("task", {}).get("screenshot_dir")
        if screenshot_dir:
            os.makedirs(screenshot_dir, exist_ok=True)
            screenshot_path = os.path.join(
                screenshot_dir,
                "tiktok-login-manual-intervention.png",
            )
        else:
            fd, screenshot_path = tempfile.mkstemp(
                suffix=".png",
                prefix="tiktok_login_manual_",
            )
            os.close(fd)
        await page.screenshot(path=screenshot_path, timeout=5000)
        raise VerificationRequiredError("manual_intervention", screenshot_path)

    async def _submit_resumed_otp(self, page: Any, otp_value: str) -> LoginResult:
        await self._ensure_trust_device_checked(page)
        await self._fill_otp(page, otp_value)
        await self._confirm_otp(page)
        outcome = await self._wait_for_post_login_outcome(page, phase="post_otp_submit")
        if outcome == "success":
            await self._cleanup_after_login(page)
            return LoginResult(success=True, message="ok")
        if outcome == "otp_error":
            otp_error = await self._find_visible_otp_error(page)
            return LoginResult(success=False, message=otp_error or "otp verification failed")
        if outcome == "login_error":
            login_error = await self._find_visible_login_error(page)
            return LoginResult(success=False, message=login_error or "login failed after otp submit")
        if outcome == "timeout":
            await self._raise_manual_intervention_required(page, self.ctx.config or {})
        return LoginResult(success=False, message="otp did not leave verification screen")

    async def run(self, page: Any) -> LoginResult:
        acc = self.ctx.account or {}
        config = self.ctx.config or {}
        params = config.get("params") or {}
        current_url = str(getattr(page, "url", "") or "")
        otp_value = str(params.get("captcha_code") or params.get("otp") or "").strip()
        manual_completed = bool(params.get("manual_completed"))

        if self._login_looks_successful(current_url):
            await self._cleanup_after_login(page)
            return LoginResult(success=True, message="already logged in")

        try:
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
                    await self._ensure_trust_device_checked(page)
                    if not otp_value:
                        await self._raise_otp_verification_required(page, config)
                    return await self._submit_resumed_otp(page, otp_value)
                if outcome == "timeout":
                    await self._raise_manual_intervention_required(page, config)
                return LoginResult(
                    success=False,
                    message="manual verification did not reach otp or homepage",
                )

            login_url = str(acc.get("login_url") or get_platform_login_entry(self.platform)).strip()

            password = str(acc.get("password") or "").strip()
            if not password:
                return LoginResult(success=False, message="password is required in account")

            await page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(800)
            await self._wait_for_login_surface_ready(page)

            if self._login_looks_successful(str(getattr(page, "url", "") or "")):
                await self._cleanup_after_login(page)
                return LoginResult(success=True, message="ok")

            target_mode = "phone" if str(acc.get("phone") or "").strip() else "email"
            await self._ensure_login_mode(page, target_mode)
            await self._fill_credentials(page, acc)
            await self._submit_credentials(page)
            outcome = await self._wait_for_post_login_outcome(page, phase="post_credentials")
            if outcome == "success":
                await self._cleanup_after_login(page)
                return LoginResult(success=True, message="ok")
            if outcome == "login_error":
                login_error = await self._find_visible_login_error(page)
                return LoginResult(success=False, message=login_error or "login failed")
            if outcome == "otp":
                await self._ensure_trust_device_checked(page)
                if not otp_value:
                    await self._raise_otp_verification_required(page, config)
                return await self._submit_resumed_otp(page, otp_value)
            if outcome == "timeout":
                await self._raise_manual_intervention_required(page, config)

            return LoginResult(success=False, message="login did not reach homepage or otp step")
        except VerificationRequiredError:
            raise
        except Exception as e:
            return LoginResult(success=False, message=str(e))
