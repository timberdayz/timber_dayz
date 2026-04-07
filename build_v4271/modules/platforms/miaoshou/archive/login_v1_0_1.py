"""
Generated component: miaoshou/login
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


class MiaoshouLogin(LoginComponent):
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
        params = config.get("params") or {}
        # 恢复路径：若有回传的验证码/OTP，同页继续，不 goto
        captcha_code = params.get("captcha_code") or params.get("otp")
        if captcha_code:
            value = (captcha_code or "").strip()
            if value:
                try:
                    _cap_inp = page.locator('role=textbox[name="请输入验证码"], input[placeholder*=\'验证码\'], input[name*=\'captcha\' i], input[name*=\'code\' i]')
                    await expect(_cap_inp).to_have_count(1)
                    await _cap_inp.fill(value, timeout=5000)
                    _login_btn = page.locator('role=button[name="立即登录"], button.login.login-button, button:has-text(\'立即登录\'), button.login')
                    await expect(_login_btn).to_have_count(1)
                    await _login_btn.click(timeout=3000)
                    # 固定等待: 验证码回传后等待登录态回写/跳转
                    await asyncio.sleep(2.0)
                    cur = str(getattr(page, "url", ""))
                    # TODO: configure success URL condition via success_criteria
                    if "login" not in cur.lower():
                        return LoginResult(success=True, message="ok")
                    # 若验证码提交后仍停留在登录页，则视为失败，避免继续执行主流程再次触发验证码
                    return LoginResult(success=False, message="验证码提交后登录未跳转或仍在登录页")
                except Exception as e:
                    _ctx = "url=" + str(getattr(page, "url", "")) + " cap_sel=" + 'role=textbox[name="请输入验证码"], input[placeholder*=\'验证码\'], input[name*=\'captcha\' i], input[name*=\'code\' i]' + " login_sel=" + 'role=button[name="立即登录"], button.login.login-button, button:has-text(\'立即登录\'), button.login'
                    return LoginResult(success=False, message="验证码恢复失败: " + str(e) + " (" + _ctx + ")")
        


        _platform_defaults = {'miaoshou': 'https://erp.91miaoshou.com', 'shopee': 'https://seller.shopee.cn', 'tiktok': 'https://seller-us.tiktok.com'}
        _target_url = (
            str(params.get("login_url_override") or "").strip()
            or str(acc.get("login_url") or "").strip()
            or str(config.get("default_login_url") or "").strip()
            or _platform_defaults.get(self.platform, "").strip()
        )
        if _target_url:
            await page.goto(_target_url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_load_state("domcontentloaded", timeout=10000)
            await self.guard_overlays(page, label="after login navigation")
        # Container scope: defaults to page; narrow down if needed
        _form = page

        # Fill: 手机号/子账号/邮箱
        # 建议迁移到 get_by_*
        _el_1 = _form.locator('input.account-input')
        await expect(_el_1).to_be_visible()
        # Value from ctx.account - use acc.get("username") / acc.get("password")
        await _el_1.fill(acc.get("username", ""), timeout=10000)

        # Fill: 密码
        # 建议迁移到 get_by_*
        _el_3 = _form.locator('input.password-input')
        await expect(_el_3).to_be_visible()
        # Value from ctx.account - use acc.get("username") / acc.get("password")
        await _el_3.fill(acc.get("password", ""), timeout=10000)

        # Fill: 请输入验证码
        # [reorder] 以下步骤原在验证码 fill 之后录制，已前置到 raise 之前；可能需人工调整顺序
        _el_6 = page.get_by_role('button', name='立即登录')
        await _el_6.click(timeout=10000)
        # 验证码步骤：到达即暂停，等待用户回传后同页继续
        await asyncio.sleep(1)
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

        # 验证码回传后由上方的 captcha_code 分支处理登录与返回
