"""
Generated component: shopee/login
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


class ShopeeLogin(LoginComponent):
    """shopee login component - generated from recorder. Edit as needed."""

    platform = 'shopee'
    component_type = "login"
    data_domain = None

    def __init__(self, ctx: ExecutionContext) -> None:
        super().__init__(ctx)

    async def run(self, page: Any) -> LoginResult:
        acc = self.ctx.account or {}
        config = self.ctx.config or {}
        # 若有弹窗在此 wait 再点击关闭

        params = config.get("params") or {}
        captcha_code = (params.get("captcha_code") or params.get("otp") or "").strip()
        _platform_defaults = {'miaoshou': 'https://erp.91miaoshou.com', 'shopee': 'https://seller.shopee.cn', 'tiktok': 'https://seller-us.tiktok.com'}
        _target_url = (
            str(params.get("login_url_override") or "").strip()
            or str(acc.get("login_url") or "").strip()
            or str(config.get("default_login_url") or "").strip()
            or _platform_defaults.get(self.platform, "").strip()
        )
        if _target_url and not captcha_code:
            await page.goto(_target_url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_load_state("domcontentloaded", timeout=10000)
            await self.guard_overlays(page, label="after login navigation")
        # Container scope: defaults to page; narrow down if needed
        _form = page

        # Fill: 子母账号登录名(XX:main)/手机/邮箱
        _el_1 = _form.get_by_role('textbox', name='子母账号登录名(XX:main)/手机/邮箱')
        await expect(_el_1).to_be_visible()
        # Value from ctx.account - use acc.get("username") / acc.get("password")
        await _el_1.fill(acc.get("username", ""), timeout=10000)

        # Click: span
        _el_2 = _form.get_by_label('记住我')
        await expect(_el_2).to_be_visible()
        await _el_2.click(timeout=10000)

        # Fill: input
        _el_4 = _form.get_by_role('checkbox', name='记住我')
        await expect(_el_4).to_be_visible()
        await _el_4.fill('记住我', timeout=10000)

        # Click: 登入
        _el_5 = _form.get_by_role('button', name='登入')
        await expect(_el_5).to_be_visible()
        await _el_5.click(timeout=10000)

        # TODO: edit success condition - check URL change or dashboard element
        # Example: await page.wait_for_url("**/dashboard**", timeout=15000)
        # Example: await expect(page.get_by_text("Welcome")).to_be_visible(timeout=10000)
        return LoginResult(success=True, message="ok")