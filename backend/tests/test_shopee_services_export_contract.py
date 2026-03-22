from pathlib import Path

from modules.components.base import ExecutionContext
from modules.platforms.shopee.components.services_export import ShopeeServicesExport


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
    assert "if await download_buttons_all.count() > 0:" in source


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
