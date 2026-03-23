from modules.components.base import ExecutionContext
from modules.platforms.shopee.components.login import ShopeeLogin
from modules.platforms.tiktok.components.login import TiktokLogin
from modules.platforms.tiktok.components.shop_switch import TiktokShopSwitch


def _ctx(platform: str, account: dict | None = None, config: dict | None = None):
    return ExecutionContext(
        platform=platform,
        account=account or {},
        logger=None,
        config=config or {},
    )


class _FakePage:
    def __init__(self, url: str):
        self.url = url
        self.goto_calls: list[str] = []

    async def goto(self, url: str, **kwargs):
        self.goto_calls.append(url)

    async def wait_for_timeout(self, ms: int):
        return None


async def test_shopee_login_requires_login_url():
    component = ShopeeLogin(_ctx("shopee", account={}))

    result = await component.run(_FakePage("https://example.com"))

    assert result.success is False
    assert result.message == "login_url is required in account"


async def test_shopee_login_reused_session_short_circuits(monkeypatch):
    page = _FakePage("https://seller.shopee.com/homepage")
    component = ShopeeLogin(
        _ctx(
            "shopee",
            account={"login_url": "https://seller.shopee.com/login"},
            config={"reused_session": True},
        )
    )

    async def _should_not_run(*args, **kwargs):
        raise AssertionError("LoginService should not run when reused session is already active")

    monkeypatch.setattr("modules.platforms.shopee.components.login.LoginService.ensure_logged_in", _should_not_run)

    result = await component.run(page)

    assert result.success is True
    assert result.message == "already logged in"


async def test_tiktok_login_active_session_short_circuits():
    page = _FakePage("https://seller.tiktokshopglobalselling.com/homepage")
    component = TiktokLogin(
        _ctx(
            "tiktok",
            account={"login_url": "https://seller.tiktokglobalshop.com", "username": "u", "password": "p"},
        )
    )

    result = await component.run(page)

    assert result.success is True
    assert result.message == "session active"


def test_tiktok_shop_switch_uses_canonical_metadata():
    assert TiktokShopSwitch.platform == "tiktok"
    assert TiktokShopSwitch.component_type == "shop_switch"
    assert TiktokShopSwitch.data_domain is None


def test_tiktok_login_key_helpers_await_count_checks():
    source = open("modules/platforms/tiktok/components/login.py", "r", encoding="utf-8").read()

    assert "if loc.count() > 0:" not in source
    assert "if loc.count() > 0 and await loc.first.is_visible()" not in source
    assert "if box.count() > 0 and await box.first.is_visible()" not in source
    assert "if role.count() > 0 and await role.first.is_visible()" not in source


def test_python_login_component_test_navigates_before_readiness_check():
    source = open("tools/test_component.py", "r", encoding="utf-8").read()

    assert "if component_type == 'login':" in source
    assert "login_url = account_info.get('login_url')" in source
    assert "await page.goto(login_url" in source
