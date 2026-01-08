from __future__ import annotations

import os
import time
from typing import Any, Sequence

from modules.components.base import ExecutionContext
from modules.components.login.base import LoginComponent, LoginResult


class TiktokLogin(LoginComponent):
    """TikTok Shop 登录组件（手机号登录 + 2FA 处理）。

    设计要点：
    - 仅使用 account.login_url 作为唯一入口（如：https://seller.tiktokglobalshop.com）
    - 首选"使用手机号登录"，填写手机号与密码
    - 出现双重验证页面时：勾选"在这台设备上不再询问"，然后输入验证码
    - 验证码来源顺序：ctx.config['otp'] > 环境变量 TIKTOK_OTP > 交互式 input()
    """

    # Component metadata (v4.8.0)
    platform = "tiktok"
    component_type = "login"
    data_domain = None

    def __init__(self, ctx: ExecutionContext) -> None:
        super().__init__(ctx)

    def _click_if_present(self, page: Any, selector: str, timeout: int = 3000) -> bool:
        try:
            loc = page.locator(selector)
            if loc.count() > 0:
                if self.logger:
                    self.logger.info(f"[TiktokLogin] click: {selector}")
                loc.first.click(timeout=timeout)
                return True
        except Exception as e:
            if self.logger:
                self.logger.warning(f"[TiktokLogin] click failed: {selector} ({e})")
        return False

    def _fill_first(self, page: Any, selectors: Sequence[str], value: str) -> bool:
        for sel in selectors:
            try:
                loc = page.locator(sel)
                if loc.count() > 0:
                    el = loc.first
                    if el.is_visible():
                        try:
                            el.click(timeout=1000)
                        except Exception:
                            pass
                        el.fill(value)
                        if self.logger:
                            self.logger.info(f"[TiktokLogin] filled with selector: {sel}")
                        return True
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"[TiktokLogin] fill attempt failed on {sel}: {e}")
                continue
        if self.logger:
            self.logger.warning("[TiktokLogin] no selector matched for fill")
    def _wait_any(self, page: Any, selectors: Sequence[str], timeout_ms: int = 10000) -> bool:
        """等待任一选择器出现并可见。"""
        deadline = time.time() + timeout_ms / 1000.0
        while time.time() < deadline:
            for sel in selectors:
                try:
                    loc = page.locator(sel)
                    if loc.count() > 0 and loc.first.is_visible():
                        return True
                except Exception:
                    pass
            try:
                page.wait_for_timeout(200)
            except Exception:
                time.sleep(0.2)
        return False

    def _click_text_if_present(self, page: Any, text: str, timeout: int = 2000) -> bool:
        try:
            loc = page.locator(f"text={text}")
            if loc.count() > 0:
                loc.first.click(timeout=timeout)
                if self.logger:
                    self.logger.info(f"[TiktokLogin] click text: {text}")
                return True
        except Exception as e:
            if self.logger:
                self.logger.warning(f"[TiktokLogin] click text failed: {text} ({e})")
        return False
    def _ensure_trust_device_checked(self, page: Any) -> bool:
        """
        确保“在这台设备上不再询问”被勾选；优先使用原生 checkbox 的 check()，
        若为自定义组件（role=checkbox），则依据 aria-checked 状态点击一次以置为 true。
        """
        # 0) TikTok 自定义 div 复选框（class 切换 checked）
        try:
            box = page.locator("#TT4B_TSV_Verify_Check")
            if box.count() > 0 and box.first.is_visible():
                cls = (box.first.get_attribute("class") or "")
                if "checked" in cls:
                    return True
                # 优先点击内部的 .check-box-inner，若不存在则点击容器本身
                try:
                    inner = box.first.locator(".check-box-inner")
                    if inner.count() > 0 and inner.first.is_visible():
                        inner.first.click()
                    else:
                        box.first.click()
                except Exception:
                    try:
                        box.first.click()
                    except Exception:
                        pass
                try:
                    page.wait_for_timeout(100)
                except Exception:
                    time.sleep(0.1)
                cls2 = (box.first.get_attribute("class") or "")
                if "checked" in cls2:
                    return True
        except Exception:
            pass

        # 1) 原生 checkbox 优先
        selectors = [
            "#TT4B_TSV_Verify_Check input[type='checkbox']",
            "label:has-text('在这台设备上不再询问') input[type='checkbox']",
            "input[type='checkbox'][name*='trust']",
            "input[type='checkbox']",
        ]
        for sel in selectors:
            try:
                loc = page.locator(sel)
                if loc.count() > 0 and loc.first.is_visible():
                    try:
                        if loc.first.is_checked():
                            return True
                    except Exception:
                        pass
                    try:
                        loc.first.check()
                        return True
                    except Exception:
                        # Fallback：点击关联文本后再次确认
                        self._click_text_if_present(page, "在这台设备上不再询问", timeout=1000)
                        try:
                            if loc.first.is_checked():
                                return True
                        except Exception:
                            pass
            except Exception:
                continue

        # 2) 自定义 role=checkbox 组件
        try:
            role = page.locator("[role='checkbox'][aria-checked]")
            if role.count() > 0 and role.first.is_visible():
                state = (role.first.get_attribute("aria-checked") or "").lower()
                if state != "true":
                    role.first.click()
                    try:
                        page.wait_for_timeout(200)
                    except Exception:
                        time.sleep(0.2)
                state2 = (role.first.get_attribute("aria-checked") or "").lower()
                return state2 == "true"
        except Exception:
            pass

        return False

    def _ensure_trust_device_checked_any(self, roots: Sequence[Any]) -> bool:
        """
        在所有可见 roots 中尝试确保“在这台设备上不再询问”被勾选；
        命中任意一个 root 即返回 True。
        """
        for r in roots:
            try:
                if self._ensure_trust_device_checked(r):
                    return True
            except Exception:
                continue
        return False

    def _wait_and_check_trust(self, root: Any, timeout_ms: int = 3000) -> bool:
        """在给定 root 内等待复选框/文案出现并确保已勾选。"""
        deadline = time.time() + max(0, timeout_ms) / 1000.0
        ok = False
        while time.time() < deadline and not ok:
            try:
                # 优先 ID
                box = root.locator("#TT4B_TSV_Verify_Check")
                if box.count() > 0 and box.first.is_visible():
                    ok = self._ensure_trust_device_checked(root)
                    if ok:
                        break
                # 文案兜底
                self._click_text_if_present(root, "在这台设备上不再询问", timeout=500)
                ok = self._ensure_trust_device_checked(root)
            except Exception:
                pass
            try:
                root.wait_for_timeout(150)
            except Exception:
                time.sleep(0.15)
        if self.logger:
            self.logger.info(f"[TiktokLogin] trust-device checked (waited): {ok}")
        else:
            print(f"[TiktokLogin] trust-device checked (waited): {ok}")
        return ok



    def _maybe_handle_2fa(self, page: Any) -> None:
        """处理TikTok二次验证（遍历所有 iframe）。"""
        # 若当前并不在登录页（account/login），直接跳过 2FA 处理，避免误触
        try:
            cur = str(page.url or "")
            if "account/login" not in cur:
                if self.logger:
                    self.logger.info("[TiktokLogin] skip 2FA: not on login page")
                return
        except Exception:
            pass
        # 遍历主页面与所有 iframe
        try:
            frames = list(getattr(page, 'frames', []))
        except Exception:
            frames = []
        roots = [page] + frames

        # “在这台设备上不再询问”复选框改为在识别出目标 root 后精确处理，避免误触导致取消勾选

        # 提前在所有 roots 中尝试勾选“在这台设备上不再询问”，确保不会遗漏
        try:
            self._ensure_trust_device_checked_any(roots)
        except Exception:
            pass

        # 检测验证码输入框（更鲁棒）
        code_inputs = [
            "#TT4B_TSV_Verify_Code_Input",
            "input[name='code']",


            "input[name*='otp']",
            "input[autocomplete='one-time-code']",
            "input[placeholder='验证码']",
            "input[placeholder*='验证码']",
            "input[placeholder*='驗證碼']",
            "input[placeholder*='Code']",
            "input[aria-label='验证码']",
            "input[aria-label*='验证码']",
            "input[aria-label*='code']",
            "input[type='tel']",
            "input[name*='code']",
            "input[type='text']",
        ]
        target_root = None
        for root in roots:
            for sel in code_inputs:
                try:
                    loc = root.locator(sel)
                    if loc.count() > 0 and loc.first.is_visible():
                        target_root = root
                        break
                except Exception:
                    continue
            if target_root:
                break
        if not target_root:
            # ffffffffffffffffffffffffffff
            def has_2fa_ui(root: Any) -> bool:
                try:
                    if root.locator("button:has-text('\u786e\u8ba4')").count() > 0:
                        return True
                except Exception:
                    pass
                for t in ["text=\u9a8c\u8bc1\u7801", "text=\u65e0\u6cd5\u83b7\u53d6\u9a8c\u8bc1\u7801", "text=\u53cc\u91cd\u9a8c\u8bc1"]:
                    try:
                        if root.locator(t).count() > 0 and root.locator(t).first.is_visible():
                            return True
                    except Exception:
                        continue
                return False
            for root in roots:
                if has_2fa_ui(root):
                    target_root = root
                    if self.logger:
                        self.logger.info("[TiktokLogin] 2FA UI detected without input-match; using UI root")
                    break
            if not target_root:
                if self.logger:
                    self.logger.warning("[TiktokLogin] 2FA suspected but no input/UI root found; keeping current page")
                # ffffffffffffff
                return

        # OTP 处理与重试
        cfg = self.ctx.config or {}
        max_attempts = int((cfg.get("otp_max_attempts") or os.getenv("TIKTOK_OTP_MAX_ATTEMPTS") or 3))
        preset_otp = cfg.get("otp") or os.getenv("TIKTOK_OTP")

        # 精确处理“在这台设备上不再询问”：等待至元素出现并确保勾选
        try:
            self._wait_and_check_trust(target_root, timeout_ms=3000)
        except Exception:
            pass

        def has_2fa_error(root: Any) -> bool:
            error_texts = [
                "text=请输入6位数字验证码",
                "text=验证码错误",
                "text=请输入正确的验证码",
                "text=校验码有问题",
                "text=验证码不正确",
                "text=验证码无效",
                "text=验证失败",
                "text=The code is incorrect",
                "text=Code is incorrect",
                "text=Please enter a 6-digit code",
                "text=Invalid code",
            ]
            for es in error_texts:
                try:
                    if root.locator(es).count() > 0 and root.locator(es).first.is_visible():
                        return True
                except Exception:
                    continue
            # 兜底：输入框标红 aria-invalid
            try:
                if root.locator("input[name*='code'][aria-invalid='true']").count() > 0:
                    return True
            except Exception:
                pass
            return False

        last_error = False
        otp = None

        # 验证码输入循环（错误时继续重试，不跳回自动登录流程）
        for attempt in range(max_attempts):
            # 第一次可使用预设 OTP，其余次数提示用户再次输入
            if attempt == 0 and preset_otp:
                otp = str(preset_otp).strip()
            else:
                try:
                    tip = "之前验证码错误，请重新输入" if last_error else "需要输入TikTok双重验证验证码"
                    print(f"[LOCK] {tip}（留空直接取消并返回）")
                    otp = input("请输入TikTok二次验证码: ").strip()
                except Exception:
                    otp = ""
            if not otp:
                if self.logger:
                    self.logger.warning("用户取消输入OTP，跳过2FA输入")
                else:
                    print("[TiktokLogin] 用户取消输入OTP，跳过2FA输入")
                return

            # 清空并填写
            try:
                target_root.locator("input[name*='code'], #TT4B_TSV_Verify_Code_Input, input[type='text']").first.fill("")
            except Exception:
                pass
            self._fill_first(target_root, code_inputs, otp)

            # 再次确保勾选（元素可能晚于输入框出现）
            try:
                self._wait_and_check_trust(target_root, timeout_ms=1200)
            except Exception:
                pass

            # 点击确认
            clicked = self._click_if_present(target_root, "button:has-text('确认')", timeout=3000)
            if not clicked:
                for root in roots:
                    if self._click_if_present(root, "button:has-text('确认')", timeout=2000) or self._click_text_if_present(root, "确认", timeout=1500):
                        clicked = True
                        break
                if not clicked:
                    try:
                        target_root.keyboard.press("Enter")
                    except Exception:
                        pass

            # 提交后轮询 3.5 秒：优先检测跳转与错误提示
            navigated = False
            saw_error = False
            deadline = time.time() + 3.5
            while time.time() < deadline:
                try:
                    # 只要离开 /account/login 即认为不在 2FA 页面
                    if "account/login" not in (page.url or ""):
                        navigated = True
                        break
                except Exception:
                    pass
                if has_2fa_error(target_root):
                    saw_error = True
                    break
                try:
                    target_root.wait_for_timeout(300)
                except Exception:
                    time.sleep(0.3)

            if saw_error:
                last_error = True
                remaining = max_attempts - attempt - 1
                msg = f"[FAIL] 验证码错误，请重新输入（剩余{remaining}次）"
                if self.logger:
                    self.logger.warning(msg)
                else:
                    print(msg)
                if remaining > 0:
                    continue

            if not navigated:
                # 仍停留在 2FA 页面且未捕获到明确错误文案，视为失败重试（兼容无错误提示版本）
                try:
                    still_has_input = target_root.locator(
                        ", ".join(code_inputs)
                    ).count() > 0
                except Exception:
                    still_has_input = True
                if still_has_input:
                    last_error = True
                    remaining = max_attempts - attempt - 1
                    msg = f"[FAIL] 验证码可能不正确（页面未跳转），请重试（剩余{remaining}次）"
                    if self.logger:
                        self.logger.warning(msg)
                    else:
                        print(msg)
                    if remaining > 0:
                        continue

            # 正常：已跳转或未检测到错误，结束循环，由上层判断是否成功
            break

    def _detect_login_mode(self, page: Any) -> str:
        """返回当前登录模式: 'phone' 或 'email'.
        检测优先级：输入框占位符/类型 > 顶部切换文案 > 默认手机号。
        注意：不要用通配“text=邮箱”以免误命中“使用邮箱登录”链接。
        """
        try:
            # 1) 通过输入框占位符/类型判断（更可靠）
            if (
                page.locator("input[placeholder*='邮箱']").count() > 0
                or page.locator("input[type='email']").count() > 0
            ):
                return "email"
            if (
                page.locator("input[placeholder*='手机号']").count() > 0
                or page.locator("input[placeholder*='你的手机号']").count() > 0
                or page.locator("input[placeholder*='手机']").count() > 0
                or page.locator("input[autocomplete='tel']").count() > 0
                or page.locator("input[type='tel']").count() > 0
            ):
                return "phone"

            # 2) 顶部切换文案作为辅助判断
            if page.locator("text=使用邮箱登录").count() > 0:
                return "phone"  # 能看到“使用邮箱登录”说明当前是手机号页
            if page.locator("text=使用手机号登录").count() > 0:
                return "email"
        except Exception:
            pass
        return "phone"  # 安全默认：手机号优先

    def run(self, page: Any) -> LoginResult:  # type: ignore[override]
        login_url = self.ctx.account.get("login_url", "https://seller.tiktokglobalshop.com")
        username = (
            self.ctx.account.get("phone")
            or self.ctx.account.get("username")
            or ""
        )
        password = self.ctx.account.get("password", "")

        if self.logger:
            self.logger.info(f"[TiktokLogin] goto: {login_url}")
        try:
            page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(800)
            if self.logger:
                self.logger.info(f"[TiktokLogin] loaded url: {page.url}")

            # 如果已处于卖家后台域且不在登录页，视为已登录，直接短路返回（兼容两个域名）
            try:
                cur = str(page.url or "")
                if (
                    ("tiktokshopglobalselling.com" in cur or "tiktokglobalshop.com" in cur)
                    and ("/homepage" in cur or "seller." in cur)
                    and ("account/login" not in cur)
                ):
                    if self.logger:
                        self.logger.info("[TiktokLogin] detected active session; skip login")
                    return LoginResult(success=True, message="session active")
            except Exception:
                pass

            # Unified LoginService hook (currently no-op for TikTok)
            try:
                from modules.services.platform_login_service import LoginService as _LS
                _LS().ensure_logged_in("tiktok", page, self.ctx.account or {})
            except Exception:
                pass

            # 决定当前模式并切换到“手机号登录”（如需）
            mode = self._detect_login_mode(page)
            if self.logger:
                self.logger.info(f"[TiktokLogin] detected mode: {mode}")

            if mode == "email":
                # 当前在邮箱登录页，需要切换到手机号登录
                switched = self._click_if_present(page, "text=使用手机号登录", timeout=4000)
                page.wait_for_timeout(400)
                # 再次确认是否已切换成功；若仍是邮箱页，再尝试一次
                if self._detect_login_mode(page) == "email":
                    if not self._click_if_present(page, "text=使用手机号登录", timeout=3000):
                        # 兜底：部分版本为“使用手机号码登录”或相近文案
                        self._click_if_present(page, "text=使用手机", timeout=2000)
                    page.wait_for_timeout(300)

            # 在主页面与所有 iframe 上尝试（避免元素在 iframe 内导致未命中）
            try:
                frames = list(getattr(page, 'frames', []))
            except Exception:
                frames = []
            if self.logger:
                self.logger.info(f"[TiktokLogin] frames detected: {len(frames)}")
            roots = [page] + frames

            # 等待登录表单关键元素出现，避免过早操作
            wait_targets = [
                "input[type='password']",
                "button:has-text('登录')",
                "text=使用邮箱登录",
                "text=使用手机号登录",
                "input[placeholder*='手机号']",
            ]
            for root in roots:
                if self._wait_any(root, wait_targets, timeout_ms=8000):
                    break

            # 填写手机号/密码（手机号优先）
            if username:
                phone_selectors = [
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
                filled_user = False
                for root in roots:
                    filled_user = self._fill_first(root, phone_selectors, username)
                    if not filled_user:
                        # 兜底：登录表单中的第一个可见文本框
                        try:
                            loc = root.locator("form:has-text('登录') input[type='text']").first
                            if loc and loc.is_visible():
                                loc.click(timeout=1000)
                                loc.fill(username)
                                filled_user = True
                        except Exception:
                            pass
                    if filled_user:
                        break
                if self.logger:
                    self.logger.info(f"[TiktokLogin] phone/username filled: {filled_user}")
                else:
                    print(f"[TiktokLogin] phone/username filled: {filled_user}")

            if password:
                pwd_selectors = [
                    "input[placeholder*='请输入您的密码']",
                    "input[placeholder*='请输入你的密码']",
                    "input[placeholder*='请输入密码']",
                    "div:has-text('密码') input",
                    "input[type='password']",
                    "input[name='password']",
                    "input[name*='password']",
                    "input[aria-label*='密码']",
                ]
                filled_pwd = False
                for root in roots:
                    filled_pwd = self._fill_first(root, pwd_selectors, password)
                    if filled_pwd:
                        break
                if self.logger:
                    self.logger.info(f"[TiktokLogin] password filled: {filled_pwd}")
                else:
                    print(f"[TiktokLogin] password filled: {filled_pwd}")

            # 点击登录（主页面与 iframe 内的按钮都尝试）+ 网络抖动重试
            def click_login_once() -> bool:
                ok = False
                for r in ([page] + (list(getattr(page, 'frames', [])) if hasattr(page, 'frames') else [])):
                    ok = (
                        self._click_if_present(r, "button:has-text('登录')", timeout=2500)
                        or self._click_if_present(r, "button[type='submit']", timeout=2500)
                        or self._click_text_if_present(r, "登录", timeout=2000)
                    )
                    if ok:
                        break
                if not ok:
                    try:
                        page.keyboard.press("Enter")
                        ok = True
                    except Exception:
                        pass
                return ok

            clicked = click_login_once()
            if self.logger:
                self.logger.info(f"[TiktokLogin] clicked login button: {clicked}")
            else:
                print(f"[TiktokLogin] clicked login button: {clicked}")

            # 点击后进行 5s 观察窗口；若仍在登录页且未出现 2FA，则再次点击，最多重试 3 次
            max_retries = 3
            attempt = 0
            while attempt <= max_retries:
                twofa_found = False
                left_login = False
                # 观察窗口：5s（10 * 500ms）
                for _ in range(10):
                    try:
                        frames = list(getattr(page, 'frames', []))
                    except Exception:
                        frames = []
                    roots = [page] + frames
                    for root in roots:
                        if (
                            root.locator("#TT4B_TSV_Verify_Code_Input").count() > 0
                            or root.locator("input[name='code']").count() > 0
                            or root.locator("input[placeholder*='验证码']").count() > 0
                            or root.locator("text=双重验证").count() > 0
                        ):
                            twofa_found = True
                            break
                    if twofa_found:
                        break
                    if "account/login" not in str(page.url):
                        left_login = True
                        break
                    page.wait_for_timeout(500)

                if twofa_found or left_login:
                    break

                attempt += 1
                if attempt <= max_retries:
                    if self.logger:
                        self.logger.info(f"[TiktokLogin] still on login without 2FA, retry click ({attempt}/{max_retries})")
                    clicked = click_login_once()
                    page.wait_for_timeout(500)

            # 处理双重验证（iframe 兼容）
            had_2fa = False
            try:
                frames = list(getattr(page, 'frames', []))
            except Exception:
                frames = []
            roots = [page] + frames
            for root in roots:
                if (
                    root.locator("#TT4B_TSV_Verify_Code_Input").count() > 0
                    or root.locator("input[name='code']").count() > 0
                    or root.locator("input[placeholder*='验证码']").count() > 0
                    or root.locator("input[aria-label*='验证码']").count() > 0
                    or root.locator("text=双重验证").count() > 0
                ):
                    had_2fa = True
                    break
            if self.logger:
                self.logger.info(f"[TiktokLogin] 2FA detected: {had_2fa} | url: {page.url}")
            else:
                print(f"[TiktokLogin] 2FA detected: {had_2fa} | url: {page.url}")

            # 仅当仍在登录页且检测到 2FA 时才进入 2FA 处理，避免已在首页却误触发输入
            if had_2fa and ("account/login" in str(page.url or "")):
                self._maybe_handle_2fa(page)
                page.wait_for_timeout(1200)

            # 成功条件：
            # 1) URL 已跳转离开登录页；或
            # 2) 刚才存在 2FA，现在 2FA 元素已消失（视为已通过）
            frames = list(getattr(page, 'frames', [])) if hasattr(page, 'frames') else []
            roots = [page] + list(frames)
            twofa_elements_present = False
            for root in roots:
                if (
                    root.locator("text=双重验证").count() > 0
                    or root.locator("button:has-text('确认')").count() > 0
                    or root.locator("input[placeholder*='验证码']").count() > 0
                    or root.locator("input[aria-label*='验证码']").count() > 0
                    or root.locator("input[name*='code']").count() > 0
                ):
                    twofa_elements_present = True
                    break

            success = ("account/login" not in str(page.url)) or (had_2fa and not twofa_elements_present)
            if self.logger:
                self.logger.info(f"[TiktokLogin] login success={success} | final url: {page.url}")
            else:
                print(f"[TiktokLogin] login success={success} | final url: {page.url}")

            return LoginResult(success=success, message="ok" if success else "可能仍在登录页/2FA未通过")
        except Exception as e:
            if self.logger:
                self.logger.error(f"[TiktokLogin] failed: {e}")
            return LoginResult(success=False, message=str(e))
