"""
Generated component: shopee/recorder_test_login
Please align with docs/guides/COLLECTION_SCRIPT_WRITING_GUIDE.md
Complex interactions, popups, download handling: add explicit wait/comment as needed.
"""

from __future__ import annotations

from typing import Any

from playwright.async_api import expect

from modules.components.base import ExecutionContext, ResultBase
from modules.components.login.base import LoginComponent, LoginResult


class ShopeeRecorderTestLogin(LoginComponent):
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

        # open login page
        await page.goto('https://example.com/login', wait_until="domcontentloaded", timeout=60000)

        await page.wait_for_load_state("domcontentloaded", timeout=10000)

        # fill username
        # 建议迁移到 get_by_*
        _el_1 = page.locator("input[name='username']")
        await expect(_el_1).to_be_visible()
        # Value from ctx.account - use acc.get("username") / acc.get("password")
        await _el_1.fill(acc.get("username", ""), timeout=10000)

        # click submit
        # 建议迁移到 get_by_*
        _el_2 = page.locator("button[type='submit']")
        await expect(_el_2).to_be_visible()
        await _el_2.click(timeout=10000)

        # close optional popup
        # 可选步骤，执行失败可跳过
        try:
            # 建议迁移到 get_by_*
            _el_3 = page.locator('.optional-popup-close')
            await expect(_el_3).to_be_visible()
            await _el_3.click(timeout=10000)
        except Exception:
            pass

        # TODO: 根据实际成功条件校验 (e.g. URL / element)
        return LoginResult(success=True, message="ok")