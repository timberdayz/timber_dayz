from pathlib import Path


def _read_settlement_sources() -> str:
    files = [
        "frontend/src/domains/business/views/FinancialManagement.vue",
        "frontend/src/domains/business/views/finance-settlement/MonthlySettlementPanel.vue",
        "frontend/src/domains/business/views/finance-settlement/SettlementWorkspacePanel.vue",
    ]
    return "\n".join(Path(file).read_text(encoding="utf-8") for file in files)


def test_financial_management_page_exposes_monthly_profit_settlement_center():
    text = _read_settlement_sources()

    assert "月度利润结算中心" in text
    assert "公司月结" in text
    assert "查询月结" in text
    assert "重建月结" in text
    assert "审批通过" in text
    assert "回退草稿" in text
    assert "调整原因" in text
    assert "投资人ID" in text
    assert "结算ID" in text


def test_financial_management_page_displays_budget_inputs_as_percentages():
    text = _read_settlement_sources()

    assert "人员成本预算(%)" in text
    assert "跟投收益预算(%)" in text
    assert "公司留存预算(%)" in text
    assert ':formatter="formatRatioInput"' in text
    assert ':parser="parseRatioInput"' in text


def test_finance_api_exposes_monthly_profit_settlement_endpoints():
    text = Path("frontend/src/api/finance.js").read_text(encoding="utf-8")

    assert "getMonthlyProfitSettlement" in text
    assert "rebuildMonthlyProfitSettlement" in text
    assert "updateMonthlyProfitSettlementTargets" in text
    assert "approveMonthlyProfitSettlement" in text
    assert "reopenMonthlyProfitSettlement" in text


def test_finance_settlement_store_exposes_monthly_profit_settlement_state_and_actions():
    text = Path("frontend/src/stores/financeSettlement.js").read_text(encoding="utf-8")

    assert "monthlyProfitSettlement" in text
    assert "fetchMonthlyProfitSettlement" in text
    assert "rebuildMonthlyProfitSettlement" in text
    assert "updateMonthlyProfitSettlementTargets" in text
    assert "approveMonthlyProfitSettlement" in text
    assert "reopenMonthlyProfitSettlement" in text


def test_financial_management_page_queries_follow_investments_with_period_month():
    text = Path("frontend/src/domains/business/views/FinancialManagement.vue").read_text(encoding="utf-8")

    assert "period_month: selectedMonth.value" in text
