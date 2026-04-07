from modules.components.base import ExecutionContext
from modules.platforms.shopee.components.products_export import ShopeeProductsExport


def _ctx():
    return ExecutionContext(
        platform="shopee",
        account={"label": "acc", "store_name": "shop"},
        logger=None,
        config={},
    )


def test_shopee_products_export_returns_error_message_in_message_field():
    component = ShopeeProductsExport(_ctx())

    result = type(component)._build_error_result("未捕获到下载事件")

    assert result.success is False
    assert result.message == "未捕获到下载事件"
    assert result.file_path is None


def test_shopee_products_export_returns_success_message_and_file_path():
    component = ShopeeProductsExport(_ctx())

    result = type(component)._build_success_result("下载完成(UI)", "data/raw/2026/shopee_products_monthly_20260327_120000.xlsx")

    assert result.success is True
    assert result.message == "下载完成(UI)"
    assert result.file_path == "data/raw/2026/shopee_products_monthly_20260327_120000.xlsx"


def test_shopee_products_export_processing_status_detection_covers_task_states():
    component = ShopeeProductsExport(_ctx())

    assert component._row_is_processing("执行中") is True
    assert component._row_is_processing("生成中") is True
    assert component._row_is_processing("队列中") is True
    assert component._row_is_processing("处理中") is True
    assert component._row_is_processing("导出中") is True
    assert component._row_is_processing("in progress") is True
    assert component._row_is_processing("queued") is True
    assert component._row_is_processing("exporting") is True
    assert component._row_is_processing("下载") is False
