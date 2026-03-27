import pytest

from modules.apps.collection_center.python_component_adapter import PythonComponentAdapter


class _FakeExportResult:
    def __init__(self, success=True, message="ok", file_path="data/raw/2026/demo.xlsx"):
        self.success = success
        self.message = message
        self.file_path = file_path


class _FakeExportComponent:
    def __init__(self, ctx):
        self.ctx = ctx

    async def run(self, page):
        return _FakeExportResult()


class _FakeGenericExportComponent:
    def __init__(self, ctx):
        self.ctx = ctx

    async def run(self, page):
        return _FakeExportResult(file_path="data/raw/2026/generic.xlsx")


def _account():
    return {"username": "u", "password": "p"}


@pytest.mark.asyncio
async def test_tiktok_services_domain_uses_canonical_export(monkeypatch: pytest.MonkeyPatch):
    adapter = PythonComponentAdapter(platform="tiktok", account=_account(), config={})

    monkeypatch.setattr(adapter, "_load_component_class", lambda component_name: _FakeExportComponent)

    result = await adapter.export(page=object(), data_domain="services")

    assert result.success is True
    assert result.file_path == "data/raw/2026/demo.xlsx"


@pytest.mark.asyncio
async def test_miaoshou_inventory_domain_uses_canonical_export(monkeypatch: pytest.MonkeyPatch):
    adapter = PythonComponentAdapter(platform="miaoshou", account=_account(), config={})

    monkeypatch.setattr(adapter, "_load_component_class", lambda component_name: _FakeExportComponent)

    result = await adapter.export(page=object(), data_domain="inventory")

    assert result.success is True
    assert result.file_path == "data/raw/2026/demo.xlsx"


@pytest.mark.asyncio
async def test_export_does_not_fallback_to_generic_export_component_in_v2(monkeypatch: pytest.MonkeyPatch):
    adapter = PythonComponentAdapter(platform="tiktok", account=_account(), config={})

    def _loader(component_name: str):
        if component_name == "orders_export":
            return None
        if component_name == "export":
            return _FakeGenericExportComponent
        return None

    monkeypatch.setattr(adapter, "_load_component_class", _loader)

    result = await adapter.export(page=object(), data_domain="orders")

    assert result.success is False
    assert "Failed to load canonical export component" in result.message
