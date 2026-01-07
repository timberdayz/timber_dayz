from __future__ import annotations

from typing import Any

from modules.components.base import ExecutionContext
from modules.components.login.base import LoginComponent, LoginResult
from modules.services.platform_login_service import LoginService


class ShopeeLogin(LoginComponent):
    """Shopee login component (thin wrapper + unified auto-login).

    Strategy:
    - Use account.login_url as the only entry
    - Rely on persistent browser context outside (page provided by caller)
    - After navigation, delegate to LoginService.ensure_logged_in("shopee", ...)
    """

    # Component metadata
    platform = "shopee"
    component_type = "login"
    data_domain = None
    
    # Success criteria for validation (v4.8.0)
    success_criteria = [
        {
            'type': 'url_contains',
            'value': 'seller.shopee',
            'optional': False,
            'comment': 'Should be on Shopee seller platform'
        },
        {
            'type': 'url_not_contains',
            'value': '/login',
            'optional': False,
            'comment': 'Should have left login page'
        }
    ]

    def __init__(self, ctx: ExecutionContext) -> None:
        super().__init__(ctx)

    async def run(self, page: Any) -> LoginResult:  # type: ignore[override]
        login_url = self.ctx.account.get("login_url")
        if not login_url:
            return LoginResult(success=False, message="login_url is required in account")
        try:
            if self.logger:
                self.logger.info(f"[ShopeeLogin] goto: {login_url}")
            await page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(800)

            # Unified auto-login
            svc = LoginService()
            ok = await svc.ensure_logged_in("shopee", page, self.ctx.account)
            if not ok:
                if self.logger:
                    self.logger.warning("[ShopeeLogin] LoginService failed to login")
                return LoginResult(success=False, message="LoginService failed to login")

            return LoginResult(success=True, message="ok")
        except Exception as e:
            if self.logger:
                self.logger.error(f"[ShopeeLogin] failed: {e}")
            return LoginResult(success=False, message=str(e))

