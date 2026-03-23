import pytest

from modules.apps.collection_center.python_component_adapter import PythonComponentAdapter


class _FakeExportResult:
    def __init__(self, success=True, message="ok", file_path="temp/outputs/demo.xlsx"):
        self.success = success
        self.message = message
        self.file_path = file_path


class _FakeExportComponent:
    def __init__(self, ctx):
        self.ctx = ctx

    async def run(self, page):
        return _FakeExportResult()


def _account():
    return {"username": "u", "password": "p"}


@pytest.mark.asyncio
async def test_tiktok_services_domain_uses_canonical_export(monkeypatch: pytest.MonkeyPatch):
    adapter = PythonComponentAdapter(platform="tiktok", account=_account(), config={})

    monkeypatch.setattr(adapter, "_load_component_class", lambda component_name: _FakeExportComponent)

    result = await adapter.export(page=object(), data_domain="services")

    assert result.success is True
    assert result.file_path == "temp/outputs/demo.xlsx"


@pytest.mark.asyncio
async def test_miaoshou_inventory_domain_uses_canonical_export(monkeypatch: pytest.MonkeyPatch):
    adapter = PythonComponentAdapter(platform="miaoshou", account=_account(), config={})

    monkeypatch.setattr(adapter, "_load_component_class", lambda component_name: _FakeExportComponent)

    result = await adapter.export(page=object(), data_domain="inventory")

    assert result.success is True
    assert result.file_path == "temp/outputs/demo.xlsx"
