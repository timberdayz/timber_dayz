from pathlib import Path

from modules.components.base import ExecutionContext
from modules.platforms.shopee.components.services_export import ShopeeServicesExport, _VariantSpec


def _ctx():
    return ExecutionContext(
        platform="shopee",
        account={"label": "acc", "store_name": "shop"},
        logger=None,
        config={},
    )


def test_shopee_services_export_returns_success_message_and_file_path():
    component = ShopeeServicesExport(_ctx())

    result = type(component)._build_success_result("全部成功(UI)", "temp/outputs/services.xlsx")

    assert result.success is True
    assert result.message == "全部成功(UI)"
    assert result.file_path == "temp/outputs/services.xlsx"


def test_shopee_services_export_returns_error_message_in_message_field():
    component = ShopeeServicesExport(_ctx())

    result = type(component)._build_error_result("services 全部导出失败")

    assert result.success is False
    assert result.message == "services 全部导出失败"
    assert result.file_path is None


def test_shopee_services_export_awaits_download_button_counts():
    source = Path("modules/platforms/shopee/components/services_export.py").read_text(encoding="utf-8")

    assert "base_count = await download_buttons_all.count()" in source
    assert "cur_count = await download_buttons_all.count()" in source


def test_shopee_services_export_awaits_other_key_count_comparisons():
    source = Path("modules/platforms/shopee/components/services_export.py").read_text(encoding="utf-8")

    assert "if rows.count() > 0:" not in source
    assert "if download_buttons.count() > 0:" not in source
    assert "if btn_top.count() > 0" not in source
    assert "if download_btn.count() > 0:" not in source


def test_shopee_services_export_row_matches_subtype():
    component = ShopeeServicesExport(_ctx())

    assert component._row_matches_subtype("AI助手 导出成功", "ai_assistant") is True
    assert component._row_matches_subtype("chatbot exporting", "ai_assistant") is True
    assert component._row_matches_subtype("人工聊天 导出成功", "agent") is True
    assert component._row_matches_subtype("agent exporting", "agent") is True

    assert component._row_matches_subtype("人工聊天 导出成功", "ai_assistant") is False
    assert component._row_matches_subtype("AI助手 导出成功", "agent") is False


def test_shopee_services_export_awaits_download_save_as_and_page_evaluate():
    source = Path("modules/platforms/shopee/components/services_export.py").read_text(encoding="utf-8")

    assert "await download.save_as(str(tmp_path))" in source
    assert "await page.evaluate(script, " in source


def test_shopee_services_export_awaits_auxiliary_count_checks():
    source = Path("modules/platforms/shopee/components/services_export.py").read_text(encoding="utf-8")

    assert "if el.count() > 0 and await el.is_visible()" not in source
    assert "if loc.count() > 0:" not in source
    assert "if scope.count() > 0 and await scope.is_visible()" not in source
    assert "if cont.count() > 0 and await cont.is_visible()" not in source
    assert "if btn.count() > 0 and await btn.is_visible()" not in source


def test_shopee_services_export_output_root_includes_subtype():
    ctx = ExecutionContext(
        platform="shopee",
        account={"label": "acc", "store_name": "shop"},
        logger=None,
        config={"granularity": "daily"},
    )
    component = ShopeeServicesExport(ctx)

    out_root = component._build_services_output_root("daily", "ai_assistant")

    assert "services" in str(out_root)
    assert "ai_assistant" in str(out_root)


def test_shopee_services_export_uses_async_expect_download():
    source = Path("modules/platforms/shopee/components/services_export.py").read_text(encoding="utf-8")

    assert "async with page.expect_download(" in source
    assert "with page.expect_download(" not in source.replace("async with page.expect_download(", "")
    assert "download = dl_info.value" not in source
    assert "download = await dl_info.value" in source


def test_shopee_services_export_does_not_fallback_to_global_first_download_button():
    source = Path("modules/platforms/shopee/components/services_export.py").read_text(encoding="utf-8")

    assert "return download_buttons_all.first" not in source


class _FakeShopeeRow:
    def __init__(self, text: str):
        self._text = text

    async def text_content(self):
        return self._text


class _FakeShopeeRows:
    def __init__(self, texts: list[str]):
        self._rows = [_FakeShopeeRow(text) for text in texts]

    async def count(self):
        return len(self._rows)

    def nth(self, index: int):
        return self._rows[index]

    @property
    def first(self):
        return self._rows[0]


async def test_shopee_services_export_prefers_first_matching_subtype_row():
    component = ShopeeServicesExport(_ctx())
    rows = _FakeShopeeRows([
        "agent exporting",
        "assistant exporting",
    ])

    picked = await component._pick_latest_matching_row(rows, "ai_assistant")

    assert picked is rows.nth(1)


async def test_shopee_services_export_falls_back_to_first_row_when_no_subtype_match():
    component = ShopeeServicesExport(_ctx())
    rows = _FakeShopeeRows([
        "latest row 1",
        "latest row 2",
    ])

    picked = await component._pick_latest_matching_row(rows, "agent")

    assert picked is rows.first


def test_shopee_services_export_awaits_container_count_check():
    source = Path("modules/platforms/shopee/components/services_export.py").read_text(encoding="utf-8")

    assert "if cand_row.count() > 0:" not in source


class _FakeShopeeDownload:
    def __init__(self, suggested_filename: str):
        self.suggested_filename = suggested_filename

    async def save_as(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text("downloaded", encoding="utf-8")


class _FakeShopeeDownloadWaiter:
    def __init__(self, download):
        self._download = download

    @property
    def value(self):
        async def _resolve():
            return self._download

        return _resolve()


class _FakeShopeeExpectDownload:
    def __init__(self, waiter):
        self._waiter = waiter

    async def __aenter__(self):
        return self._waiter

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeShopeeApiPage:
    def __init__(self, download):
        self.download = download
        self.evaluate_calls: list[tuple[str, dict]] = []

    def expect_download(self, timeout: int):
        return _FakeShopeeExpectDownload(_FakeShopeeDownloadWaiter(self.download))

    async def evaluate(self, script: str, payload: dict):
        self.evaluate_calls.append((script, payload))
        return {"mode": "blob"}


async def test_shopee_services_api_fallback_preserves_download_suffix(tmp_path: Path):
    ctx = ExecutionContext(
        platform="shopee",
        account={"label": "acc", "store_name": "shop"},
        logger=None,
        config={"granularity": "daily"},
    )
    component = ShopeeServicesExport(ctx)
    page = _FakeShopeeApiPage(_FakeShopeeDownload("services_agent.csv"))

    component._latest_har_path = lambda: None  # type: ignore[method-assign]
    component._build_services_output_root = lambda granularity, subtype: (tmp_path / subtype)  # type: ignore[method-assign]
    component._write_manifest = lambda *args, **kwargs: None  # type: ignore[method-assign]

    ok, target = await component._api_fallback(
        page,
        _VariantSpec(key="agent", path="/dummy"),
        account_label="acc",
        shop_name="shop",
    )

    assert ok is True
    assert target is not None
    assert target.suffix == ".csv"
