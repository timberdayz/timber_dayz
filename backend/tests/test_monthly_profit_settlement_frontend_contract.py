"""月度利润看板前端契约：API 封装、专用 store 与调整项写入口。

⚠️ 旧版断言（rebuild / targets / approve / reopen 与旧 store）随看板制下线。
"""

from pathlib import Path


def _read_dashboard_store() -> str:
    return Path("frontend/src/stores/financeDashboard.js").read_text(encoding="utf-8")


def _read_dashboard_view() -> str:
    return Path(
        "frontend/src/domains/business/views/finance-dashboard/FinanceDashboardView.vue"
    ).read_text(encoding="utf-8")


def _read_adjustment_panel() -> str:
    return Path(
        "frontend/src/domains/business/views/finance-dashboard/AdjustmentPanel.vue"
    ).read_text(encoding="utf-8")


def test_finance_api_exposes_monthly_profit_dashboard_endpoints():
    text = Path("frontend/src/api/finance.js").read_text(encoding="utf-8")

    assert "getFinanceDashboard" in text
    assert "createFinanceAdjustment" in text
    assert "deleteFinanceAdjustment" in text
    assert "/finance/monthly-profit-settlement" in text


def test_finance_api_drops_retired_settlement_workflow_endpoints():
    text = Path("frontend/src/api/finance.js").read_text(encoding="utf-8")

    assert "rebuildMonthlyProfitSettlement" not in text
    assert "updateMonthlyProfitSettlementTargets" not in text
    assert "approveMonthlyProfitSettlement" not in text
    assert "reopenMonthlyProfitSettlement" not in text


def test_finance_dashboard_store_exposes_read_and_adjustment_actions():
    text = _read_dashboard_store()

    assert "fetchDashboard" in text
    assert "addAdjustment" in text
    assert "removeAdjustment" in text
    assert "follow" not in text


def test_finance_dashboard_store_writes_failures_into_visible_error_state():
    text = _read_dashboard_store()

    assert "this.error =" in text
    assert "this.actionError =" in text
    assert "catch (error)" in text
    assert "detail" in text


def test_finance_dashboard_view_renders_states_and_sections():
    text = _read_dashboard_view()

    assert "<el-alert" in text
    assert "store.error" in text
    assert "store.loading" in text
    assert "ProfitOverviewCards" in text
    assert "ShopAllocationTable" in text
    assert "AdjustmentPanel" in text


def test_finance_dashboard_adjustment_panel_covers_all_adjustment_types():
    text = _read_adjustment_panel()

    for adjustment_type in (
        "manual_adjustment",
        "cross_period_expense",
        "one_off_gain_loss",
        "correction",
    ):
        assert adjustment_type in text, f"调整类型必须覆盖：{adjustment_type}"

    assert "请写明调整原因" in text
