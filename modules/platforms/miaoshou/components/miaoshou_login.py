"""
Generated component: miaoshou/miaoshou_login
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


class MiaoshouMiaoshouLogin(LoginComponent):
    """miaoshou login component - generated from recorder. Edit as needed."""

    platform = 'miaoshou'
    component_type = "login"
    data_domain = None

    def __init__(self, ctx: ExecutionContext) -> None:
        super().__init__(ctx)

    def _login_looks_successful(self, url: str) -> bool:
        cur = str(url or "").lower()
        if not cur:
            return False
        if any(marker in cur for marker in ("/welcome", "/dashboard")):
            return True
        if any(marker in cur for marker in ("/login", "account/login", "redirect=%2fwelcome")):
            return False
        return "miaoshou.com" in cur and "login" not in cur

    async def run(self, page: Any) -> LoginResult:
        acc = self.ctx.account or {}
        config = self.ctx.config or {}
        current_url = str(getattr(page, "url", "") or "")
        if self._login_looks_successful(current_url):
            return LoginResult(success=True, message="already logged in")
        # 若有弹窗在此 wait 再点击关闭
        # 恢复路径：若有回传的验证码/OTP，同页继续，不 goto
        params = config.get("params") or {}
        captcha_code = params.get("captcha_code") or params.get("otp")
        if captcha_code:
            value = (captcha_code or "").strip()
            if value:
                try:
                    _cap_inp = page.locator("input.captcha-text, input[placeholder*='验证码'], input[name*='captcha' i], input[name*='code' i]").first
                    await _cap_inp.fill(value, timeout=5000)
                    await page.locator("button.login, button.login.login-button, button:has-text('立即登录'), button.login").first.click(timeout=3000)
                    await asyncio.sleep(2.0)
                    cur = str(getattr(page, "url", ""))
                    if self._login_looks_successful(cur):
                        return LoginResult(success=True, message="ok")
                    # 若验证码提交后仍停留在登录页，则视为失败，避免继续执行主流程再次触发验证码
                    return LoginResult(success=False, message="验证码提交后登录未跳转或仍在登录页")
                except Exception as e:
                    return LoginResult(success=False, message=f"验证码填入失败: {e}")

        # 首次进入或非验证码回传：先导航到登录页，避免空白页找不到 input.account-input
        login_url = acc.get("login_url") or "https://erp.91miaoshou.com"
        try:
            await page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(1.0)
        except Exception as e:
            return LoginResult(success=False, message=f"打开登录页失败: {e}")

        # 限定在登录表单内操作，避免 strict mode violation（页上有多个同名/同 class 元素）
        form = page.locator("#J_loginRegisterForm")

        # 账号输入框
        _el_0 = form.locator("input.account-input").first
        await expect(_el_0).to_be_visible(timeout=15000)
        await _el_0.click(timeout=10000)
        await _el_0.fill(acc.get("username", ""), timeout=10000)

        # 密码输入框
        _el_2 = form.locator("input.password-input").first
        await expect(_el_2).to_be_visible(timeout=10000)
        await _el_2.click(timeout=10000)
        await _el_2.fill(acc.get("password", ""), timeout=10000)

        # 验证码输入框：表单内用 placeholder 唯一定位，避免 input.captcha-text 匹配到 2 个
        _el_4 = form.get_by_placeholder("请输入验证码")
        await expect(_el_4).to_be_visible(timeout=10000)
        await _el_4.click(timeout=10000)

        # 验证码步骤：检测到验证码则暂停，等待用户回传后同页继续
        await asyncio.sleep(2.5)
        _cap_inp = form.get_by_placeholder("请输入验证码")
        try:
            if await _cap_inp.count() > 0 and await _cap_inp.first.is_visible(timeout=3000):
                import os
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
                raise VerificationRequiredError("graphical_captcha", screenshot_path)
        except VerificationRequiredError:
            raise
        except Exception:
            pass

        # 立即登录（限定在表单内，避免多按钮 strict mode）
        _el_6 = form.locator("button.login").first
        await expect(_el_6).to_be_visible(timeout=10000)
        await _el_6.click(timeout=10000)

        await asyncio.sleep(2.0)
        cur = str(getattr(page, "url", ""))
        if self._login_looks_successful(cur):
            return LoginResult(success=True, message="ok")
        return LoginResult(success=False, message="登录后仍停留在登录页或未进入欢迎页")
