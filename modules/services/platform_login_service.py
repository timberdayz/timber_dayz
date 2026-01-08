from __future__ import annotations

"""
Unified Platform Login Service

- Single entry to ensure a page is logged in for a given platform
- Compliant with login_url-only entry rule
- No import-time side effects

Initial implementation covers Shopee; other platforms can plug in later.
"""
from typing import Any, Dict, Optional, List

from modules.core.logger import get_logger


class LoginService:
    """Unified login orchestrator for all platforms.

    Usage:
        svc = LoginService()
        ok = svc.ensure_logged_in("shopee", page, account_dict)
    """

    def __init__(self) -> None:
        self.logger = get_logger("login_service")

    # -------- Public API --------
    def ensure_logged_in(self, platform: str, page: Any, account: Dict[str, Any]) -> bool:
        """Ensure the page is logged in for the given platform.

        Args:
            platform: e.g., 'shopee', 'tiktok'
            page: Playwright page (sync)
            account: dict that MUST include 'login_url' and credentials
        Returns:
            True if considered logged in or not on login page; False if login failed.
        """
        key = (platform or "").lower()
        try:
            if key == "shopee":
                return self._ensure_shopee_logged_in(page, account)
            if key == "tiktok":
                return self._ensure_tiktok_logged_in(page, account)
            # Default: no-op (treat as success) until platforms are implemented
            self.logger.info(f"[LoginService] platform '{platform}' not implemented; skipping")
            return True
        except Exception as e:
            self.logger.error(f"[LoginService] ensure_logged_in failed for {platform}: {e}")
            return False

    # -------- Shopee implementation --------
    def _ensure_shopee_logged_in(self, page: Any, account: Dict[str, Any]) -> bool:
        """Best-effort Shopee auto-login aligned with the corrected flow.

        Strategy:
        - If not on login page, assume already logged in
        - If on login page: fill credentials -> remember-me -> submit -> handle verification (plugin chain) -> validate
        """
        if not self._shopee_is_on_login_page(page):
            return True

        # Feature flags (read from account; defaults are safe)
        flags = {}
        try:
            flags = (account.get("login_flags") or {}) if isinstance(account, dict) else {}
        except Exception:
            flags = {}
        mode = str(flags.get("shopee_verification_mode", "auto")).lower()  # auto|browser|off
        use_v2 = bool(flags.get("shopee_use_v2_verification", True))
        use_fallback = bool(flags.get("shopee_use_fallback_handler", True))

        self.logger.info("[ShopeeLogin] On login page; attempting auto-login")

        username = self._pick_first_value(account, [
            "username", "user", "email", "account", "account_name", "login_name",
            "Username", "Email",
        ])
        password = self._pick_first_value(account, ["password", "pwd", "Password"]) or ""

        if not username or not password:
            self.logger.warning("[ShopeeLogin] Missing credentials (username/password).")
            return False

        # Fill username
        user_selectors: List[str] = [
            'input[name="loginKey"]',
            'input[id="loginKey"]',
            '#loginKey',
            'input[name="email"]',
            'input[name="account"]',
            'input[autocomplete="username"]',
            'input[placeholder*="邮箱" i]',
            'input[placeholder*="Email" i]',
            'input[placeholder*="手机号" i]',
            'input[placeholder*="手机" i]',
            'input[placeholder*="用户名" i]',
            'input[aria-label*="邮箱" i]',
            'input[aria-label*="手机号" i]',
            'input[aria-label*="用户名" i]',
            'input[type="text"]',
        ]
        # Wait briefly for the login form to render
        try:
            for sel in user_selectors:
                try:
                    node = page.locator(sel).first
                    if node and node.count() > 0:
                        node.wait_for(state="visible", timeout=3000)
                        break
                except Exception:
                    continue
        except Exception:
            pass
        user_ok = self._fill_first_available(page, user_selectors, username)
        if not user_ok:
            self.logger.warning("[ShopeeLogin] Failed to fill username")

        # Fill password
        pass_selectors: List[str] = [
            'input[name="password"]',
            'input[id="password"]',
            '#password',
            'input[autocomplete="current-password"]',
            'input[type="password"]',
            'input[placeholder*="密码" i]',
            'input[placeholder*="Password" i]',
            'input[placeholder*="请输入密码" i]',
            'input[aria-label*="密码" i]',
        ]
        pass_ok = self._fill_first_available(page, pass_selectors, password)
        if not pass_ok:
            self.logger.warning("[ShopeeLogin] Failed to fill password")
        if user_ok and pass_ok:
            self.logger.info("[ShopeeLogin] Step 2/4: 用户名与密码已填写")

        # Remember me: ensure checked if present (robust: input + container/SVG fallbacks)
        verbose = bool(flags.get("verbose_login", False))
        remember_input_selectors = [
            'input[type="checkbox"][name="rememberMe"]',
            'input.eds-checkbox__input[value="记住我"]',
            'input.eds-checkbox__input[value="true"]',
            'input.eds-checkbox__input',
        ]
        if not self._ensure_checkbox_checked(page, remember_input_selectors):
            # Fallback A: try clicking label/container/SVG (custom checkbox where input is hidden)
            container_clicks = [
                'label:has-text("记住我")',
                'label:has-text("记住我") svg',
                '[role="checkbox"]:has-text("记住我")',
                '.eds-checkbox:has-text("记住我")',
                '.eds-checkbox__box:has(svg)',
                'svg path[d^="M4.03033009"]',
                'text=记住我',
            ]
            clicked = False
            for sel in container_clicks:
                if self._click_first_available(page, [sel]):
                    clicked = True
                    if verbose:
                        self.logger.info(f"[ShopeeLogin] clicked remember-me container: {sel}")
                    page.wait_for_timeout(250)
                    # Re-check via input attributes or ARIA on container
                    if self._ensure_checkbox_checked(page, remember_input_selectors):
                        break
            if not clicked:
                # Fallback B: still try labels (legacy)
                self._click_first_available(page, ['label:has-text("记住我")', 'label:has-text("记住")', 'label:has-text("Remember")'])
                self._ensure_checkbox_checked(page, remember_input_selectors)

        # Click submit/login
        login_buttons = [
            'button:has-text("登录")',
            'button:has-text("登入")',
            'button:has-text("Login")',
            '[role="button"]:has-text("登录")',
            '[role="button"]:has-text("登入")',
            '[role="button"]:has-text("Login")',
            'button[type="submit"]',
        ]
        if not self._click_first_available(page, login_buttons):
            self.logger.warning("[ShopeeLogin] Could not click login button; retry with ENTER")
            # In verification mode 'off', do not attempt ENTER fallback to avoid unintended navigation in tests
            if mode != "off":
                try:
                    page.keyboard.press("Enter")
                except Exception:
                    pass
        # Step 3: verification if needed
        self.logger.info("[ShopeeLogin] Step 3/4: 开始处理验证码/验证页面")
        # Proactively detect OTP modal and prompt user early (short polling)
        manual_otp_attempted = False
        try:
            for _ in range(5):  # ~2.5s
                if self._shopee_handle_manual_otp_if_present(page):
                    manual_otp_attempted = True
                    break
                page.wait_for_timeout(500)
        except Exception:
            pass

        # Wait for navigation or state change
        page.wait_for_timeout(1500)

        # If still on login page, try verification handlers (best-effort)
        # IMPORTANT: If we already attempted manual phone OTP, do not run other handlers to avoid email flow or excessive clicks
        if self._shopee_is_on_login_page(page) and not manual_otp_attempted:
            # Mode 'off' means skip all verification handlers
            if mode == "off":
                self.logger.info("[ShopeeLogin] verification mode=off; skipping handlers")
            else:
                # Prefer V2 unless disabled or mode forces 'browser'
                if use_v2 and mode != "browser":
                    self.logger.info("[ShopeeLogin] invoking SmartVerificationHandlerV2")
                    try:
                        from modules.utils.smart_verification_handler_v2 import (
                            SmartVerificationHandlerV2,
                        )
                        SmartVerificationHandlerV2(page, account).handle_verification()
                    except Exception as e:
                        self.logger.warning(f"[ShopeeLogin] V2 verification handler failed/unavailable: {e}")

                # Fallback browser-mode handler
                if use_fallback and self._shopee_is_on_login_page(page):
                    try:
                        from modules.utils.shopee_verification_handler import ShopeeVerificationHandler
                        self.logger.info("[ShopeeLogin] Trying fallback ShopeeVerificationHandler (browser-mode)")
                        ShopeeVerificationHandler(page, account).handle_shopee_verification()
                    except Exception as e:
                        self.logger.warning(f"[ShopeeLogin] Fallback ShopeeVerificationHandler failed/unavailable: {e}")


            # Manual phone/SMS OTP fallback — regardless of prior handlers, if OTP modal present, prompt and fill
            try:
                self._shopee_handle_manual_otp_if_present(page)
            except Exception:
                pass

            # Give page a brief moment for state change after handlers
            try:
                page.wait_for_timeout(800)
            except Exception:
                pass

        # Final validation: away from login URL or presence of seller-center/dashboard hints
        ok = self._shopee_login_success(page)
        if ok:
            self.logger.info("[ShopeeLogin] Step 4/4: [0m[0m[0m[32m[1m[0m[0m[32m[1m[0m[0m[32m[1m[0m[0m[32m[1m[0m[0m[32m[1m[0m[0m[32m[1m[0m[0m[32m[1m[0m[0m[32m[1m[0m[0m[32m[1m[0m[0m[32m[1m[0m[0m[32m[1m[0m[0m[32m[1m[0m[0m[32m[1m[0m[0m[32m[1m[0m[0m[32m[1m[0m[0m[32m[1m[0m[0m[32m[1m[0m[0m[32m[1m[0m[0m[32m[1m[0m[0m[32m[1m[0m[0m[32m[1m[0m[0m[32m[1m[0m[0m[32m[1m[0m[0m [0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m[0m登录成功")
        else:
            self.logger.info("[ShopeeLogin] 登录状态未通过或仍在登录页")
        return ok

    # -------- Helpers --------
    def _pick_first_value(self, m: Dict[str, Any], keys: List[str]) -> Optional[str]:
        for k in keys:
            v = m.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return None

    def _is_visible(self, page: Any, selector: str, timeout: int = 500) -> bool:
        try:
            el = page.locator(selector).first
            if el and el.count() > 0:
                el.wait_for(state="visible", timeout=timeout)
                return True
        except Exception:
            return False
        return False

    def _fill_first_available(self, page: Any, selectors: List[str], text: str) -> bool:
        for sel in selectors:
            try:
                el = page.locator(sel).first
                if el and el.count() > 0:
                    try:
                        # Improve robustness: ensure visibility and bring into view
                        if hasattr(el, 'scroll_into_view_if_needed'):
                            el.scroll_into_view_if_needed()
                        el.wait_for(state="visible", timeout=2000)
                    except Exception:
                        pass
                    el.click()
                    el.fill("")
                    el.type(text, delay=20)
                    return True
            except Exception:
                continue
        return False

    def _click_first_available(self, page: Any, selectors: List[str]) -> bool:
        for sel in selectors:
            try:
                loc = page.locator(sel)
                if not loc or loc.count() == 0:
                    continue
                node = loc.first
                # Try to ensure visibility and bring into view
                try:
                    if hasattr(node, 'scroll_into_view_if_needed'):
                        node.scroll_into_view_if_needed()
                except Exception:
                    pass
                try:
                    # Prefer waiting briefly for visibility
                    if hasattr(node, 'is_visible'):
                        # If not visible, still attempt click to trigger
                        pass
                    node.click()
                    return True
                except Exception:
                    # Last resort: force click if supported
                    try:
                        node.click(force=True)
                        return True
                    except Exception:
                        continue
            except Exception:
                continue
        return False

    def _ensure_checkbox_checked(self, page: Any, selectors: List[str]) -> bool:
        """Try to ensure a checkbox is checked. Returns True if already/now checked.
        Strategy:
        - Prefer Locator.is_checked() if available
        - Fallback by reading attributes like 'checked', 'aria-checked', or 'value' == 'true'
        - Click to toggle when not checked
        """
        truthy = {"true", "checked", "on", "1"}
        for sel in selectors:
            try:
                loc = page.locator(sel)
                if not loc or loc.count() == 0:
                    continue
                node = loc.first
                # Try is_checked
                try:
                    if hasattr(node, "is_checked") and node.is_checked():
                        return True
                except Exception:
                    pass
                # Attribute-based check
                val = None
                try:
                    for attr in ("checked", "aria-checked", "value"):
                        v = node.get_attribute(attr)
                        if v is not None:
                            val = v.strip().lower()
                            break
                except Exception:
                    val = None
                if val in truthy:
                    return True
                # Not checked -> click
                try:
                    node.click()
                    page.wait_for_timeout(100)
                except Exception:
                    pass
                # Re-check once
                try:
                    if hasattr(node, "is_checked") and node.is_checked():
                        return True
                except Exception:
                    pass
                try:
                    val2 = node.get_attribute("value") or node.get_attribute("checked") or node.get_attribute("aria-checked")
                    if val2 and str(val2).strip().lower() in truthy:
                        return True
                except Exception:
                    pass
            except Exception:
                continue
        return False

    def _shopee_is_on_login_page(self, page: Any) -> bool:
        try:
            url = (page.url or "").lower()
            if "login" in url or "signin" in url:
                return True
            # heuristic by elements
            login_hints = [
                'input[name="loginKey"]',
                'input[name="password"]',
                'button:has-text("登录")',
                'button:has-text("登入")',
                'button:has-text("Login")',
                '[role="button"]:has-text("登录")',
                '[role="button"]:has-text("登入")',
                '[role="button"]:has-text("Login")',
            ]
            return any(self._is_visible(page, s, timeout=300) for s in login_hints)
        except Exception:
            return False

    # ----- Phone/SMS OTP helpers (manual) -----
    def _shopee_detect_phone_verification(self, page: Any) -> bool:
        try:
            # 关键词检测（覆盖“验证电话号码”弹窗）
            hints = [
                'text=验证电话号码', 'text=验证手机号', 'text=验证手机号码',
                'text=短信', 'text=手机', 'text=验证码', 'text=安全验证',
                'text=发送验证码', 'text=获取验证码', 'text=重新发送', 'text=发送到邮箱',
                "text=Confirm", "text=Verify",
            ]
            for sel in hints:
                if self._is_visible(page, sel, timeout=300):
                    return True

            # 弹窗容器 + 内部输入框（role=dialog 或 aria-modal=true）
            dialog_selectors = [
                'div[role="dialog"]', 'div[aria-modal="true"]',
                '.modal', '.shopee-modal', '.shopee-modal__container',
            ]
            input_in_dialog = [
                'input[type="tel"]', 'input[autocomplete="one-time-code"]',
                'input[name*="otp" i]', 'input[id*="otp" i]',
                'input[placeholder*="请输入" i]', 'input[type="text"]',
            ]
            try:
                for dlg in dialog_selectors:
                    for ip in input_in_dialog:
                        sel = f"{dlg} >> {ip}"
                        if self._is_visible(page, sel, timeout=300):
                            return True
            except Exception:
                pass

            # 页面直接存在典型 OTP 输入控件
            otp_inputs = [
                'input[autocomplete="one-time-code"]',
                'input[name*="otp" i]',
                'input[id*="otp" i]',
                'input[type="tel"]',
                'input[aria-label*="验证码" i]',
                'input[placeholder*="请输入" i]',
            ]
            for sel in otp_inputs:
                if self._is_visible(page, sel, timeout=300):
                    return True
            return False
        except Exception:
            return False

    def _shopee_detect_otp_error(self, page: Any) -> bool:
        try:
            error_selectors = [
                "text=验证码填写错误",
                "text=验证吗填写错误",  # 兼容误写
                "text=请输入正确的验证码",
                "text=验证码错误",
                "text=验证码不正确",
                ".toast:has-text('验证码')",
                ".ant-message:has-text('验证码')",
                ".shopee-toast:has-text('验证码')",
            ]
            return any(self._is_visible(page, sel, timeout=200) for sel in error_selectors)
        except Exception:
            return False

    def _shopee_try_manual_phone_otp(self, page: Any) -> bool:
        try:
            # Limit attempts to avoid suspicious behavior
            login_flags = (account or {}).get("login_flags", {}) if 'account' in locals() else {}
            max_attempts = int(login_flags.get("shopee_otp_max_attempts", 3))

            for attempt in range(1, max_attempts + 1):
                code = input(f"请输入短信验证码（第{attempt}/{max_attempts}次，留空取消）：").strip()
                if not code:
                    return False

                filled = False

                # Prefer filling inside visible dialog container
                dialog_selectors = [
                    'div[role="dialog"]', 'div[aria-modal="true"]',
                    '.modal', '.shopee-modal', '.shopee-modal__container',
                ]
                input_selectors = [
                    'input[type="tel"]', 'input[autocomplete="one-time-code"]',
                    'input[name*="otp" i]', 'input[id*="otp" i]',
                    'input[placeholder*="请输入" i]', 'input[type="text"]',
                ]
                try:
                    for dlg in dialog_selectors:
                        for ip in input_selectors:
                            sel = f"{dlg} >> {ip}"
                            el = page.locator(sel).first
                            if el and el.count() > 0:
                                try:
                                    if hasattr(el, 'scroll_into_view_if_needed'):
                                        el.scroll_into_view_if_needed()
                                    el.wait_for(state="visible", timeout=2000)
                                except Exception:
                                    pass
                                el.click()
                                el.fill('')
                                el.type(code, delay=20)
                                filled = True
                                break
                        if filled:
                            break
                except Exception:
                    pass

                # Fallbacks
                if not filled:
                    digit_boxes = page.locator('input[type="tel"]').all() if hasattr(page, 'locator') else []
                    if digit_boxes and len(digit_boxes) >= 4:
                        for i, ch in enumerate(code):
                            if i >= len(digit_boxes):
                                break
                            try:
                                digit_boxes[i].fill('')
                                digit_boxes[i].type(ch)
                                filled = True
                            except Exception:
                                pass

                if not filled:
                    for sel in [
                        'input[autocomplete="one-time-code"]',
                        'input[name*="otp" i]',
                        'input[id*="otp" i]',
                        'input[placeholder*="请输入" i]',
                        'input[type="text"]',
                    ]:
                        try:
                            el = page.locator(sel).first
                            if el and el.count() > 0:
                                el.click()
                                el.fill('')
                                el.type(code, delay=20)
                                filled = True
                                break
                        except Exception:
                            continue

                # Click confirm/verify (prefer inside dialog), but throttle
                confirm_selectors = [
                    "div[role='dialog'] button:has-text('确认')",
                    "div[aria-modal='true'] button:has-text('确认')",
                    "button:has-text('确认')",
                    "button:has-text('验证')",
                    "button:has-text('提交')",
                ]
                for btn in confirm_selectors:
                    if self._click_first_available(page, [btn]):
                        break

                # Wait for server validation
                try:
                    page.wait_for_timeout(1500)
                except Exception:
                    pass

                # If error toast appears, retry (do NOT spam clicks)
                if self._shopee_detect_otp_error(page):
                    self.logger.warning("[ShopeeLogin] 验证码错误，准备重试...")
                    continue

                # If we left login page or OTP modal disappeared, treat as success
                if not self._shopee_is_on_login_page(page) or not self._shopee_detect_phone_verification(page):
                    return True

            # Attempts exhausted
            self.logger.warning("[ShopeeLogin] 已达到验证码最大重试次数，放弃以避免异常检测")
            return False
        except Exception:
            return False

    def _shopee_handle_manual_otp_if_present(self, page: Any) -> bool:
        """If a phone/SMS OTP modal is present, prompt user for code and submit.
        Returns True if we filled something, else False.
        """
        try:
            if self._shopee_detect_phone_verification(page):
                self.logger.info("[ShopeeLogin] 检测到手机/短信验证码页面，等待用户输入并代为提交...")
                try:
                    if self._shopee_try_manual_phone_otp(page):
                        page.wait_for_timeout(800)
                        return True
                except Exception as e:
                    self.logger.warning(f"[ShopeeLogin] 手动短信验证码处理失败: {e}")
        except Exception:
            pass
        return False



    def _shopee_login_success(self, page: Any) -> bool:
        try:
            # If still on the login page by URL or element hints, definitely NOT success
            if self._shopee_is_on_login_page(page):
                return False

            url = (page.url or "").lower()
            # Primary signal: away from login/signin URLs
            if ("login" not in url) and ("signin" not in url):
                return True

            # Secondary signal: elements that only exist AFTER login (avoid generic texts on login page)
            success_indicators = [
                '#portal',
                '.seller-dashboard',
                '.seller-center-layout',
                '.navigation',
                'header .user-menu',
                'a[href*="/portal/"]',
            ]
            return any(self._is_visible(page, s, timeout=800) for s in success_indicators)
        except Exception:
            return False

    # -------- TikTok implementation (minimal) --------
    def _ensure_tiktok_logged_in(self, page: Any, account: Dict[str, Any]) -> bool:
        """Minimal TikTok auto-login.

        Strategy:
        - If not on login page, treat as already logged in
        - If on login page: fill phone/username + password -> submit -> validate by URL
        - 2FA is handled by higher-level component for now
        """
        if not self._tiktok_is_on_login_page(page):
            return True

        self.logger.info("[TikTokLogin] On login page; attempting auto-login (minimal)")

        # Feature flags
        flags = {}
        try:
            flags = (account.get("login_flags") or {}) if isinstance(account, dict) else {}
        except Exception:
            flags = {}
        trust_device = bool(flags.get("tiktok_trust_device_enabled", False))
        min_2fa_prompt = bool(flags.get("tiktok_min_2fa_prompt", True))

        username = self._pick_first_value(account, [
            "phone", "username", "email", "account", "login_name",
            "Phone", "Username", "Email",
        ])
        password = self._pick_first_value(account, ["password", "pwd", "Password"]) or ""

        if not username or not password:
            self.logger.warning("[TikTokLogin] Missing credentials (username/password).")
            return False

        # Fill phone/username (prefer phone-like selectors)
        phone_selectors: List[str] = [
            "input[placeholder*='请输入你的手机号']",
            "input[placeholder*='请输入您的手机号']",
            "input[placeholder*='请输入手機號']",
            "input[placeholder*='请输入手机']",
            "input[placeholder*='输入你的手机号']",
            "input[placeholder*='输入手机号']",
            "input[placeholder*='手机号码']",
            "input[placeholder*='手机号']",
            "input[aria-label*='手机号']",
            "div:has-text('手机号') input",
            "form:has-text('登录') input[type='text']",
            "input[autocomplete='tel']",
            "input[type='tel']",
            "input[name*='phone']",
            "input[name='account']",
            "input[data-testid*='phone']",
        ]
        # If none matches, fallback to a generic text input
        if not self._fill_first_available(page, phone_selectors, username):
            self._fill_first_available(page, ["input[type='text']", "input[name='username']"], username)

        # Fill password
        pwd_selectors: List[str] = [
            "input[placeholder*='请输入您的密码']",
            "input[placeholder*='请输入你的密码']",
            "input[placeholder*='请输入密码']",
            "div:has-text('密码') input",
            "input[type='password']",
            "input[name='password']",
            "input[name*='password']",
            "input[aria-label*='密码']",
        ]
        self._fill_first_available(page, pwd_selectors, password)

        # Click login
        login_buttons = [
            "button:has-text('登录')",
            "button[type='submit']",
            "text=登录",
        ]
        if not self._click_first_available(page, login_buttons):
            try:
                page.keyboard.press("Enter")
            except Exception:
                pass

        # Wait for navigation/state change
        try:
            page.wait_for_timeout(1500)
        except Exception:
            pass

        # If still on login page, detect 2FA and optionally ensure trust-device
        if self._tiktok_is_on_login_page(page):
            if self._tiktok_2fa_present(page):
                if trust_device:
                    try:
                        self._tiktok_trust_device_check(page)
                    except Exception:
                        pass
                if min_2fa_prompt:
                    try:
                        self.logger.info("[TikTokLogin] 2FA detected; OTP will be handled by component.")
                    except Exception:
                        pass

        return self._tiktok_login_success(page)

    def _tiktok_is_on_login_page(self, page: Any) -> bool:
        try:
            url = str(getattr(page, "url", "") or "").lower()
            if "account/login" in url:
                return True
            login_hints = [
                "input[type='password']",
                "button:has-text('登录')",
                "input[placeholder*='手机号']",
            ]
            return any(self._is_visible(page, s, timeout=300) for s in login_hints)
        except Exception:
            return False

    def _tiktok_login_success(self, page: Any) -> bool:
        try:
            url = str(getattr(page, "url", "") or "").lower()
            # Consider success if no longer on account/login
            return "account/login" not in url
        except Exception:
            return False


    def _tiktok_2fa_present(self, page: Any) -> bool:
        selectors = [
            "#TT4B_TSV_Verify_Code_Input",
            "input[name='code']",
            "input[placeholder*='验证码']",
            "input[aria-label*='验证码']",
            "text=双重验证",
        ]
        try:
            return any(self._is_visible(page, s, timeout=200) for s in selectors)
        except Exception:
            return False

    def _tiktok_trust_device_check(self, page: Any) -> None:
        # Try various checkbox patterns to enable 'trust this device'
        selectors = [
            "#TT4B_TSV_Verify_Check",
            "#TT4B_TSV_Verify_Check input[type='checkbox']",
            "label:has-text('在这台设备上不再询问')",
            "[role='checkbox'][aria-checked]",
        ]
        for sel in selectors:
            try:
                loc = page.locator(sel)
                if loc.count() > 0 and getattr(loc.first, "is_visible", lambda: True)():
                    # If ARIA checkbox and already checked, return
                    try:
                        if loc.first.get_attribute("aria-checked") == "true":
                            return
                    except Exception:
                        pass
                    try:
                        loc.first.click()
                        page.wait_for_timeout(150)
                    except Exception:
                        pass
                    return
            except Exception:
                continue
