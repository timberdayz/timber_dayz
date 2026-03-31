from pathlib import Path

from modules.components.base import ExecutionContext
from modules.components.date_picker.base import DateOption
from modules.platforms.miaoshou.components.orders_config import OrdersSelectors
from modules.platforms.miaoshou.components.orders_export_base import MiaoshouOrdersExportBase
from modules.platforms.miaoshou.components.orders_shopee_export import MiaoshouOrdersShopeeExport
from modules.platforms.miaoshou.components.orders_tiktok_export import MiaoshouOrdersTiktokExport


def _ctx():
    return ExecutionContext(
        platform="miaoshou",
        account={"label": "acc", "store_name": "shop"},
        logger=None,
        config={},
    )


def test_miaoshou_orders_export_builds_orders_detail_url_by_subtype():
    component = MiaoshouOrdersExportBase(_ctx())

    assert component._orders_detail_url("shopee") == "https://erp.91miaoshou.com/stat/profit_statistics/detail?platform=shopee"
    assert component._orders_detail_url("tiktok") == "https://erp.91miaoshou.com/stat/profit_statistics/detail?platform=tiktok"


def test_miaoshou_orders_export_returns_success_message_and_file_path():
    component = MiaoshouOrdersExportBase(_ctx())

    result = type(component)._build_success_result("ok", "data/raw/2026/miaoshou_orders_monthly_20260327_120000.xlsx")

    assert result.success is True
    assert result.message == "ok"
    assert result.file_path == "data/raw/2026/miaoshou_orders_monthly_20260327_120000.xlsx"


def test_miaoshou_orders_export_returns_error_message_in_message_field():
    component = MiaoshouOrdersExportBase(_ctx())

    result = type(component)._build_error_result("download timeout")

    assert result.success is False
    assert result.message == "download timeout"
    assert result.file_path is None


def test_miaoshou_orders_export_resolves_preset_aliases_from_ui_runtime_config():
    component = MiaoshouOrdersExportBase(_ctx())

    assert component._resolve_preset_option("last_7_days") is DateOption.LAST_7_DAYS
    assert component._resolve_preset_option("last_30_days") is DateOption.LAST_30_DAYS
    assert component._resolve_preset_option("yesterday") is DateOption.YESTERDAY
    assert component._resolve_preset_option("今天") is DateOption.TODAY_REALTIME


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
    source = Path("modules/platforms/miaoshou/components/orders_export_base.py").read_text(encoding="utf-8")

    assert "async with page.expect_download(" in source
    assert "导出全部订单" in source
    assert "正在导出" in source
    assert "await self._click_search(page)" in source


def test_miaoshou_orders_export_scopes_orders_subtype_to_platform_row_instead_of_global_text_match():
    source = Path("modules/platforms/miaoshou/components/orders_export_base.py").read_text(encoding="utf-8")

    assert 'target = page.get_by_text(label, exact=True).first' not in source
    assert "platform_label = page.get_by_text(\"平台\", exact=True).first" in source
    assert "platform_row" in source
    assert "平台" in source


def test_miaoshou_order_export_wrappers_fix_sub_domains():
    assert MiaoshouOrdersShopeeExport.sub_domain == "shopee"
    assert MiaoshouOrdersTiktokExport.sub_domain == "tiktok"


def test_miaoshou_orders_export_maps_platform_subtype_to_ui_labels():
    component = MiaoshouOrdersExportBase(_ctx())

    assert component._orders_subtype_label("shopee") == "Shopee"
    assert component._orders_subtype_label("tiktok") == "TikTok"
    assert component._orders_subtype_label("lazada") == "Lazada"
