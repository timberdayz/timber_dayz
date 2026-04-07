from pathlib import Path

from modules.components.base import ExecutionContext
from modules.platforms.shopee.components.analytics_export import ShopeeAnalyticsExport


def _ctx():
    return ExecutionContext(
        platform="shopee",
        account={"label": "acc", "store_name": "shop"},
        logger=None,
        config={},
    )


def test_shopee_analytics_export_returns_success_message_and_file_path():
    component = ShopeeAnalyticsExport(_ctx())

    result = type(component)._build_success_result("下载完成(UI)", "data/raw/2026/shopee_analytics_monthly_20260327_120000.xlsx")

    assert result.success is True
    assert result.message == "下载完成(UI)"
    assert result.file_path == "data/raw/2026/shopee_analytics_monthly_20260327_120000.xlsx"


def test_shopee_analytics_export_returns_error_message_in_message_field():
    component = ShopeeAnalyticsExport(_ctx())

    result = type(component)._build_error_result("未找到导出按钮")

    assert result.success is False
    assert result.message == "未找到导出按钮"
    assert result.file_path is None


def test_shopee_analytics_export_awaits_download_button_counts():
    source = Path("modules/platforms/shopee/components/analytics_export.py").read_text(encoding="utf-8")

    assert "base_count = await download_buttons_all.count()" in source
    assert "cur_count = await download_buttons_all.count()" in source
