from pathlib import Path

from modules.components.base import ExecutionContext
from modules.platforms.miaoshou.components.orders_config import OrdersSelectors
from modules.platforms.miaoshou.components.orders_export import MiaoshouOrdersExport


def _ctx():
    return ExecutionContext(
        platform="miaoshou",
        account={"label": "acc", "store_name": "shop"},
        logger=None,
        config={},
    )


def test_miaoshou_orders_export_builds_orders_detail_url_by_subtype():
    component = MiaoshouOrdersExport(_ctx())

    assert component._orders_detail_url("shopee") == "https://erp.91miaoshou.com/stat/profit_statistics/detail?platform=shopee"
    assert component._orders_detail_url("tiktok") == "https://erp.91miaoshou.com/stat/profit_statistics/detail?platform=tiktok"


def test_miaoshou_orders_export_returns_success_message_and_file_path():
    component = MiaoshouOrdersExport(_ctx())

    result = type(component)._build_success_result("ok", "data/raw/2026/miaoshou_orders_monthly_20260327_120000.xlsx")

    assert result.success is True
    assert result.message == "ok"
    assert result.file_path == "data/raw/2026/miaoshou_orders_monthly_20260327_120000.xlsx"


def test_miaoshou_orders_export_returns_error_message_in_message_field():
    component = MiaoshouOrdersExport(_ctx())

    result = type(component)._build_error_result("download timeout")

    assert result.success is False
    assert result.message == "download timeout"
    assert result.file_path is None


def test_miaoshou_orders_config_declares_export_menu_entries_and_progress_titles():
    selectors = OrdersSelectors()

    assert "导出全部订单" in selectors.export_menu_items
    assert "正在导出" in selectors.export_progress_titles
    assert "正在导出订单" in selectors.export_progress_texts


def test_miaoshou_orders_config_declares_date_shortcuts_and_custom_inputs():
    selectors = OrdersSelectors()

    assert "昨天" in selectors.date_shortcuts
    assert "近7天" in selectors.date_shortcuts
    assert "近30天" in selectors.date_shortcuts
    assert "开始日期" in selectors.custom_date_input_names
    assert "结束日期" in selectors.custom_date_input_names
    assert "开始时间" in selectors.custom_time_input_names
    assert "结束时间" in selectors.custom_time_input_names


def test_miaoshou_orders_export_source_captures_download_before_menu_click():
    source = Path("modules/platforms/miaoshou/components/orders_export.py").read_text(encoding="utf-8")

    assert "async with page.context.expect_download(" in source
    assert "导出全部订单" in source
    assert "正在导出" in source
    assert "await self._click_search(page)" in source
