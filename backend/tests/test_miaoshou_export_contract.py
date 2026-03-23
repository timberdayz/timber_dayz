from pathlib import Path
import re

from modules.components.base import ExecutionContext
from modules.platforms.miaoshou.components.export import MiaoshouExporterComponent


def _ctx():
    return ExecutionContext(
        platform="miaoshou",
        account={"label": "acc", "store_name": "shop"},
        logger=None,
        config={},
    )


def test_miaoshou_export_infers_analytics_domain_not_traffic():
    component = MiaoshouExporterComponent(_ctx())

    assert component._infer_data_type("https://erp.91miaoshou.com/traffic/overview", None) == "analytics"
    assert component._infer_data_type("https://erp.91miaoshou.com/analytics", None) == "analytics"


def test_miaoshou_export_awaits_download_save_as():
    source = Path("modules/platforms/miaoshou/components/export.py").read_text(encoding="utf-8")

    assert "await download.save_as(str(tmp_path))" in source


def test_miaoshou_export_has_no_impossible_count_comparisons():
    source = Path("modules/platforms/miaoshou/components/export.py").read_text(encoding="utf-8")

    assert ".count() >= 0" not in source
    assert ".count() < 0" not in source


def test_miaoshou_export_awaits_count_comparisons():
    source = Path("modules/platforms/miaoshou/components/export.py").read_text(encoding="utf-8")

    assert "if el.count() > 0" not in source
    assert "if el2.count() > 0" not in source
    assert "if inputs.count() < 2" not in source
    assert "if footer and footer.count() > 0" not in source


def test_miaoshou_export_cleans_up_context_download_listener():
    source = Path("modules/platforms/miaoshou/components/export.py").read_text(encoding="utf-8")

    assert 'page.context.off("download", _on_download)' in source


def test_miaoshou_export_uses_async_expect_download():
    source = Path("modules/platforms/miaoshou/components/export.py").read_text(encoding="utf-8")

    assert "async with page.context.expect_download(" in source
    assert re.search(r"(?<!async )with page\.context\.expect_download\(", source) is None


def test_miaoshou_export_does_not_use_body_or_page_as_dropdown_scope():
    source = Path("modules/platforms/miaoshou/components/export.py").read_text(encoding="utf-8")

    dropdown_section = source[source.index("async def _export_via_dropdown"):source.index("async def run(")]
    assert 'page.locator("body")' not in source
    assert "scope_list.extend([\n" in dropdown_section
    assert "page,\n" not in dropdown_section


def test_miaoshou_export_has_no_blind_second_menu_item_fallback():
    source = Path("modules/platforms/miaoshou/components/export.py").read_text(encoding="utf-8")

    assert "items[1].click" not in source
