from pathlib import Path


def test_financial_management_page_exposes_monthly_profit_settlement_center():
    text = Path("frontend/src/views/FinancialManagement.vue").read_text(encoding="utf-8")

    assert "月度利润结算中心" in text
    assert "公司月结" in text
    assert "查询月结" in text
    assert "重建月结" in text
    assert "审批通过" in text
    assert "回退草稿" in text
    assert "调整原因" in text
    assert "投资人ID" in text
    assert "结算ID" in text


def test_finance_api_exposes_monthly_profit_settlement_endpoints():
    text = Path("frontend/src/api/finance.js").read_text(encoding="utf-8")

    assert "getMonthlyProfitSettlement" in text
    assert "rebuildMonthlyProfitSettlement" in text
    assert "updateMonthlyProfitSettlementTargets" in text
    assert "approveMonthlyProfitSettlement" in text
    assert "reopenMonthlyProfitSettlement" in text


def test_finance_store_exposes_monthly_profit_settlement_state_and_actions():
    text = Path("frontend/src/stores/finance.js").read_text(encoding="utf-8")

    assert "monthlyProfitSettlement" in text
    assert "fetchMonthlyProfitSettlement" in text
    assert "rebuildMonthlyProfitSettlement" in text
    assert "updateMonthlyProfitSettlementTargets" in text
    assert "approveMonthlyProfitSettlement" in text
    assert "reopenMonthlyProfitSettlement" in text
