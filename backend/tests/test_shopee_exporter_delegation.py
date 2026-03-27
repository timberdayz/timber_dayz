import pytest

from modules.components.base import ExecutionContext
from modules.components.export.base import ExportResult
from modules.platforms.shopee.components.export import ShopeeExporterComponent


def _ctx(data_domain: str):
    return ExecutionContext(
        platform="shopee",
        account={"label": "acc", "store_name": "shop"},
        logger=None,
        config={"data_domain": data_domain},
    )


class _FakeProductsExport:
    def __init__(self, ctx):
        self.ctx = ctx

    async def run(self, page, mode=None):
        return ExportResult(success=True, message="delegated", file_path="downloads/shopee/products.xlsx")


@pytest.mark.asyncio
async def test_shopee_generic_exporter_delegates_to_products_export(monkeypatch: pytest.MonkeyPatch):
    component = ShopeeExporterComponent(_ctx("products"))

    monkeypatch.setattr(
        "modules.platforms.shopee.components.products_export.ShopeeProductsExport",
        _FakeProductsExport,
    )

    result = await component.run(page=object())

    assert result.success is True
    assert result.message == "delegated"
    assert result.file_path == "downloads/shopee/products.xlsx"
