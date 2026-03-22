from pathlib import Path

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
