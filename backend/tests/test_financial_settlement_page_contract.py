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
