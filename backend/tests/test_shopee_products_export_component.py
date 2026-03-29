from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from modules.components.base import ExecutionContext
from modules.components.export.base import ExportMode
from modules.platforms.shopee.components.products_export import ShopeeProductsExport


def _ctx(config: dict | None = None) -> ExecutionContext:
    return ExecutionContext(
        platform="shopee",
        account={
            "username": "user",
            "store_name": "shop-a",
            "login_url": "https://seller.shopee.cn/account/signin?next=%2F",
        },
        logger=None,
        config=config or {
            "shop_name": "shop-a",
            "granularity": "daily",
        },
    )


class _FakePage:
    def __init__(self, url: str) -> None:
        self.url = url
        self.wait_calls: list[int] = []

    async def wait_for_timeout(self, ms: int) -> None:
        self.wait_calls.append(ms)


def test_shopee_products_export_accepts_products_overview_url() -> None:
    component = ShopeeProductsExport(_ctx())

    assert component._products_page_looks_ready(
        "https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1"
    ) is True


def test_shopee_products_export_rejects_non_products_url() -> None:
    component = ShopeeProductsExport(_ctx())

    assert component._products_page_looks_ready(
        "https://seller.shopee.cn/datacenter/home?cnsc_shop_id=1"
    ) is False


def test_shopee_products_export_detects_throttled_text() -> None:
    component = ShopeeProductsExport(_ctx())

    assert component._is_export_throttled("点击过快，请稍后再试") is True
    assert component._is_export_throttled("导出成功") is False


@pytest.mark.asyncio
async def test_shopee_products_export_succeeds_when_download_completes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1")
    component = ShopeeProductsExport(_ctx())

    monkeypatch.setattr(component, "_ensure_products_page_ready", AsyncMock())
    monkeypatch.setattr(component, "_ensure_shop_selected", AsyncMock())
    monkeypatch.setattr(component, "_ensure_date_selection", AsyncMock())
    monkeypatch.setattr(component, "_trigger_export", AsyncMock())
    monkeypatch.setattr(component, "_detect_export_throttled", AsyncMock(return_value=False))
    monkeypatch.setattr(
        component,
        "_wait_download_complete",
        AsyncMock(return_value="F:/tmp/products.xlsx"),
    )

    result = await component.run(page, mode=ExportMode.STANDARD)

    assert result.success is True
    assert result.file_path == "F:/tmp/products.xlsx"


@pytest.mark.asyncio
async def test_shopee_products_export_retries_after_throttled_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1")
    component = ShopeeProductsExport(_ctx())

    monkeypatch.setattr(component, "_ensure_products_page_ready", AsyncMock())
    monkeypatch.setattr(component, "_ensure_shop_selected", AsyncMock())
    monkeypatch.setattr(component, "_ensure_date_selection", AsyncMock())
    monkeypatch.setattr(component, "_trigger_export", AsyncMock())
    monkeypatch.setattr(
        component,
        "_detect_export_throttled",
        AsyncMock(side_effect=[True, False]),
    )
    monkeypatch.setattr(component, "_wait_export_retry_ready", AsyncMock(return_value=True))
    monkeypatch.setattr(
        component,
        "_wait_download_complete",
        AsyncMock(return_value="F:/tmp/products.xlsx"),
    )

    result = await component.run(page, mode=ExportMode.STANDARD)

    assert result.success is True
    assert result.file_path == "F:/tmp/products.xlsx"
    assert component._trigger_export.await_count == 2


@pytest.mark.asyncio
async def test_shopee_products_export_fails_when_throttled_and_never_recovers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _FakePage("https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1")
    component = ShopeeProductsExport(_ctx())

    monkeypatch.setattr(component, "_ensure_products_page_ready", AsyncMock())
    monkeypatch.setattr(component, "_ensure_shop_selected", AsyncMock())
    monkeypatch.setattr(component, "_ensure_date_selection", AsyncMock())
    monkeypatch.setattr(component, "_trigger_export", AsyncMock())
    monkeypatch.setattr(component, "_detect_export_throttled", AsyncMock(return_value=True))
    monkeypatch.setattr(component, "_wait_export_retry_ready", AsyncMock(return_value=False))

    result = await component.run(page, mode=ExportMode.STANDARD)

    assert result.success is False
    assert "throttled" in result.message
