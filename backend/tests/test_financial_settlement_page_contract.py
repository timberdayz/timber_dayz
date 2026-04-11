from pathlib import Path


def test_financial_management_page_no_longer_contains_legacy_finance_sections():
    text = Path("frontend/src/views/FinancialManagement.vue").read_text(encoding="utf-8")

    assert "accountsReceivable" not in text
    assert "paymentReceipts" not in text
    assert "overdueAlert" not in text
    assert "fetchOverview(" not in text
    assert "fetchAccountsReceivable(" not in text
    assert "fetchOverdueAlert(" not in text


def test_financial_management_page_focuses_on_settlement_workflow():
    text = Path("frontend/src/views/FinancialManagement.vue").read_text(encoding="utf-8")

    assert "月度利润结算中心" in text
    assert "店铺结算净利润口径" in text
    assert "跟投收益试算" in text
    assert "跟投记录" in text
    assert "结算台账" in text


def test_financial_management_page_uses_platform_and_shop_list_workflow():
    text = Path("frontend/src/views/FinancialManagement.vue").read_text(encoding="utf-8")

    assert "可用店铺列表" in text
    assert "当前店铺详情" in text
    assert "selectedShop" in text
    assert "getTargetShops" in text


def test_financial_management_page_shows_platform_level_shop_status_summary():
    text = Path("frontend/src/views/FinancialManagement.vue").read_text(encoding="utf-8")

    assert "本平台店铺概览" in text
    assert "有跟投记录店铺" in text
    assert "有结算台账店铺" in text
    assert "待补经营数据" in text


def test_financial_management_page_supports_shop_filters_and_exception_visualization():
    text = Path("frontend/src/views/FinancialManagement.vue").read_text(encoding="utf-8")

    assert "店铺筛选" in text
    assert "只看异常店铺" in text
    assert "只看待补经营数据" in text
    assert "当前店铺异常提示" in text
    assert "shopFilterMode" in text
    assert "shopExceptionItems" in text


def test_financial_management_page_exposes_formal_settlement_rules():
    text = Path("frontend/src/views/FinancialManagement.vue").read_text(encoding="utf-8")

    assert "规则口径" in text
    assert "可继续结算店铺" in text
    assert "已具备结算信号" in text
    assert "status.canSettle" in text
    assert "status.pendingData" in text
    assert "status.hasException" in text
