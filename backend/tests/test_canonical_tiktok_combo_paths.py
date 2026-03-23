import pytest

from modules.apps.collection_center.python_component_adapter import create_adapter


class _FakeLoginResult:
    def __init__(self):
        self.success = True
        self.message = "logged-in"
        self.details = {"phase": "login"}


class _FakeShopSwitchResult:
    def __init__(self):
        self.success = True
        self.message = "shop-selected"
        self.details = {"phase": "shop_switch"}


class _FakeExportResult:
    def __init__(self):
        self.success = True
        self.message = "exported"
        self.file_path = "temp/outputs/tiktok/services.xlsx"


class _FakeLoginComponent:
    def __init__(self, ctx):
        self.ctx = ctx

    async def run(self, page):
        self.ctx.config["session_ready"] = True
        return _FakeLoginResult()


class _FakeShopSwitchComponent:
    def __init__(self, ctx):
        self.ctx = ctx

    async def run(self, page):
        assert self.ctx.config["session_ready"] is True
        self.ctx.config["shop_region"] = "MY"
        self.ctx.config["shop_name"] = "acc_my"
        return _FakeShopSwitchResult()


class _FakeExportComponent:
    def __init__(self, ctx):
        self.ctx = ctx

    async def run(self, page):
        assert self.ctx.config["data_domain"] == "services"
        assert self.ctx.config["session_ready"] is True
        assert self.ctx.config["shop_region"] == "MY"
        assert self.ctx.config["shop_name"] == "acc_my"
        return _FakeExportResult()


@pytest.mark.asyncio
async def test_tiktok_login_shop_switch_export_combo_uses_shared_context():
    adapter = create_adapter(
        platform="tiktok",
        account={"username": "u", "password": "p"},
        config={"data_domain": "services"},
        override_login_class=_FakeLoginComponent,
        override_shop_switch_class=_FakeShopSwitchComponent,
        override_export_class=_FakeExportComponent,
    )

    login_result = await adapter.login(page=object())
    switch_result = await adapter.call_component("shop_switch", page=object())
    export_result = await adapter.export(page=object(), data_domain="services")

    assert login_result.success is True
    assert switch_result.success is True
    assert switch_result.message == "shop-selected"
    assert export_result.success is True
    assert export_result.file_path == "temp/outputs/tiktok/services.xlsx"
