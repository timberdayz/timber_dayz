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

    async def run(self, page: Any) -> LoginResult:
        acc = self.ctx.account or {}
        config = self.ctx.config or {}
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
                    if "/welcome" in cur or "/dashboard" in cur or "login" not in cur.lower():
                        return LoginResult(success=True, message="ok")
                    # 若验证码提交后仍停留在登录页，则视为失败，避免继续执行主流程再次触发验证码
                    return LoginResult(success=False, message="验证码提交后登录未跳转或仍在登录页")
                except Exception as e:
                    return LoginResult(success=False, message=f"验证码填入失败: {e}")
        


        # Click: input
        # 建议迁移到 get_by_*
        _el_0 = page.locator('input.account-input')
        await expect(_el_0).to_be_visible()
        await _el_0.click(timeout=10000)

        # Fill: 手机号/子账号/邮箱
        # 建议迁移到 get_by_*
        _el_1 = page.locator('input.account-input')
        await expect(_el_1).to_be_visible()
        # Value from ctx.account - use acc.get("username") / acc.get("password")
        await _el_1.fill(acc.get("username", ""), timeout=10000)

        # Click: input
        # 建议迁移到 get_by_*
        _el_2 = page.locator('input.password-input')
        await expect(_el_2).to_be_visible()
        await _el_2.click(timeout=10000)

        # Fill: 密码
        # 建议迁移到 get_by_*
        _el_3 = page.locator('input.password-input')
        await expect(_el_3).to_be_visible()
        # Value from ctx.account - use acc.get("username") / acc.get("password")
        await _el_3.fill(acc.get("password", ""), timeout=10000)

        # Click: input
        # 建议迁移到 get_by_*
        _el_4 = page.locator('input.captcha-text')
        await expect(_el_4).to_be_visible()
        await _el_4.click(timeout=10000)

        # Fill: 请输入验证码
        # 验证码步骤：检测到验证码则暂停，等待用户回传后同页继续
        await asyncio.sleep(2.5)
        _cap_inp = page.locator("input.captcha-text, input[placeholder*='验证码'], input[name*='captcha' i], input[name*='code' i]")
        if await _cap_inp.count() > 0:
            try:
                if await _cap_inp.first.is_visible(timeout=3000):
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

        # Click: 立即登录
        # 建议迁移到 get_by_*
        _el_6 = page.locator('button.login')
        await expect(_el_6).to_be_visible()
        await _el_6.click(timeout=10000)

        # TODO: 根据实际成功条件校验 (e.g. URL / element)
        return LoginResult(success=True, message="ok")