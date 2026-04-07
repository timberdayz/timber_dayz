import pytest

from pathlib import Path

from modules.apps.collection_center.python_component_adapter import create_adapter


class _FakeLoginResult:
    def __init__(self):
        self.success = True
        self.message = "logged-in"
        self.details = {"phase": "login"}


class _FakeExportResult:
    def __init__(self):
        self.success = True
        self.message = "exported"
        self.file_path = "data/raw/2026/miaoshou_analytics_monthly_20260327_120000.xlsx"


class _FakeLoginComponent:
    def __init__(self, ctx):
        self.ctx = ctx

    async def run(self, page):
        self.ctx.config["session_ready"] = True
        return _FakeLoginResult()


class _FakeExportComponent:
    def __init__(self, ctx):
        self.ctx = ctx

    async def run(self, page):
        assert self.ctx.config["data_domain"] == "analytics"
        assert self.ctx.config["session_ready"] is True
        return _FakeExportResult()


@pytest.mark.asyncio
async def test_miaoshou_login_export_combo_uses_shared_context():
    adapter = create_adapter(
        platform="miaoshou",
        account={"username": "u", "password": "p"},
        config={"data_domain": "analytics"},
        override_login_class=_FakeLoginComponent,
        override_export_class=_FakeExportComponent,
    )

    login_result = await adapter.login(page=object())
    export_result = await adapter.export(page=object(), data_domain="analytics")

    assert login_result.success is True
    assert login_result.message == "logged-in"
    assert export_result.success is True
    assert export_result.file_path == "data/raw/2026/miaoshou_analytics_monthly_20260327_120000.xlsx"


def test_miaoshou_inventory_domain_routes_to_inventory_snapshot_export_component():
    source = Path("modules/apps/collection_center/python_component_adapter.py").read_text(encoding="utf-8")

    assert '"inventory": "MiaoshouInventorySnapshotExport"' in source
    assert 'module_name = "inventory_snapshot_export"' in source


class _FakeInventoryExportResult:
    def __init__(self):
        self.success = True
        self.message = "inventory exported"
        self.file_path = "downloads/miaoshou/acc/shop/inventory/snapshot/file.xlsx"


class _FakeInventoryExportComponent:
    def __init__(self, ctx):
        self.ctx = ctx

    async def run(self, page):
        assert self.ctx.config["data_domain"] == "inventory"
        assert self.ctx.config["session_ready"] is True
        return _FakeInventoryExportResult()


@pytest.mark.asyncio
async def test_miaoshou_login_inventory_export_combo_uses_shared_context():
    adapter = create_adapter(
        platform="miaoshou",
        account={"username": "u", "password": "p"},
        config={"data_domain": "inventory"},
        override_login_class=_FakeLoginComponent,
        override_export_class=_FakeInventoryExportComponent,
    )

    login_result = await adapter.login(page=object())
    export_result = await adapter.export(page=object(), data_domain="inventory")

    assert login_result.success is True
    assert export_result.success is True
    assert export_result.file_path.endswith(".xlsx")
