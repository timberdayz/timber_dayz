from __future__ import annotations

from pathlib import Path

import pytest

from modules.components.base import ExecutionContext
from modules.platforms.tiktok.components.export import TiktokExport


def _ctx(config: dict | None = None) -> ExecutionContext:
    return ExecutionContext(
        platform="tiktok",
        account={"label": "acc", "store_name": "shop", "region": "SG"},
        logger=None,
        config=config or {"shop_region": "SG"},
    )


class _FakeLocator:
    def __init__(self, *, visible: bool = False) -> None:
        self.visible = visible
        self.clicked = 0

    @property
    def first(self) -> "_FakeLocator":
        return self

    async def count(self) -> int:
        return 1 if self.visible else 0

    async def is_visible(self, timeout: int | None = None) -> bool:
        return self.visible

    async def click(self, timeout: int | None = None) -> None:
        self.clicked += 1

    async def scroll_into_view_if_needed(self, timeout: int | None = None) -> None:
        return None


class _FakeDownload:
    def __init__(self, suggested_filename: str) -> None:
        self.suggested_filename = suggested_filename
        self.saved_paths: list[str] = []

    async def save_as(self, path: str) -> None:
        self.saved_paths.append(path)
        Path(path).write_text("dummy", encoding="utf-8")


class _FakeDownloadHandle:
    def __init__(self, page: "_FakePage") -> None:
        self.page = page

    def __await__(self):
        async def _resolve():
            if self.page.download is None:
                raise RuntimeError("download not triggered")
            return self.page.download

        return _resolve().__await__()


class _FakeExpectDownload:
    def __init__(self, page: "_FakePage") -> None:
        self.page = page
        self.value = _FakeDownloadHandle(page)

    async def __aenter__(self) -> "_FakeExpectDownload":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001
        return False


class _FakePage:
    def __init__(self, url: str) -> None:
        self.url = url
        self.locators: dict[str, _FakeLocator] = {}
        self.timeout_calls: list[int] = []
        self.download: _FakeDownload | None = None

    def locator(self, selector: str) -> _FakeLocator:
        return self.locators.get(selector, _FakeLocator())

    async def wait_for_timeout(self, ms: int) -> None:
        self.timeout_calls.append(ms)

    def expect_download(self, timeout: int = 0):  # noqa: ARG002
        return _FakeExpectDownload(self)


def test_tiktok_export_manifest_prefers_runtime_shop_region(tmp_path: Path) -> None:
    component = TiktokExport(_ctx({"shop_region": "MY"}))
    target = tmp_path / "export.xlsx"
    target.write_text("dummy", encoding="utf-8")

    component._write_manifest(
        target=target,
        cfg=component.ctx.config or {},
        account_label="acc",
        shop_name="shop",
        data_type="products",
    )

    manifest = (Path(str(target) + ".json")).read_text(encoding="utf-8")
    assert '"region": "MY"' in manifest


@pytest.mark.asyncio
async def test_tiktok_export_auto_downloads_for_traffic_after_click() -> None:
    component = TiktokExport(_ctx({"shop_region": "SG", "downloads_path": "temp/tiktok-export-test"}))
    page = _FakePage("https://seller.tiktokshopglobalselling.com/compass/data-overview?shop_region=SG")
    export_button = _FakeLocator(visible=True)

    async def _click(timeout: int | None = None) -> None:
        export_button.clicked += 1
        page.download = _FakeDownload("traffic.xlsx")

    export_button.click = _click  # type: ignore[method-assign]
    page.locators['button:has-text("导出")'] = export_button

    result = await component.run(page)

    assert result.success is True
    assert export_button.clicked == 1
    assert result.file_path is not None
    assert result.file_path.endswith("traffic.xlsx")


@pytest.mark.asyncio
async def test_tiktok_export_auto_downloads_for_products_after_click() -> None:
    component = TiktokExport(_ctx({"shop_region": "SG", "downloads_path": "temp/tiktok-export-test"}))
    page = _FakePage("https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=SG")
    export_button = _FakeLocator(visible=True)

    async def _click(timeout: int | None = None) -> None:
        export_button.clicked += 1
        page.download = _FakeDownload("products.xlsx")

    export_button.click = _click  # type: ignore[method-assign]
    page.locators['button:has-text("导出")'] = export_button

    result = await component.run(page)

    assert result.success is True
    assert export_button.clicked == 1
    assert result.file_path is not None
    assert result.file_path.endswith("products.xlsx")


@pytest.mark.asyncio
async def test_tiktok_export_service_analytics_switches_chat_detail_before_auto_download() -> None:
    component = TiktokExport(_ctx({"shop_region": "SG", "downloads_path": "temp/tiktok-export-test"}))
    page = _FakePage("https://seller.tiktokshopglobalselling.com/compass/service-analytics?shop_region=SG")
    chat_tab = _FakeLocator(visible=True)
    export_button = _FakeLocator(visible=True)

    async def _click_export(timeout: int | None = None) -> None:
        export_button.clicked += 1
        page.download = _FakeDownload("services.xlsx")

    export_button.click = _click_export  # type: ignore[method-assign]
    page.locators['button:has-text("聊天详情")'] = chat_tab
    page.locators['button:has-text("导出")'] = export_button

    result = await component.run(page)

    assert result.success is True
    assert chat_tab.clicked == 1
    assert export_button.clicked == 1
    assert result.file_path is not None
    assert result.file_path.endswith("services.xlsx")
