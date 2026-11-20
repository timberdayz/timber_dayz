"""财务页面契约：``/financial-management`` 现在是只读的「月度利润看板」。

⚠️ 旧版断言（预算比例输入、审批/回退按钮、跟投试算）随看板制下线，
   本文件改为守住「只读看板 + 唯一写入口（人工调整项）」这条契约。
"""

from pathlib import Path


def _read_dashboard_sources() -> str:
    files = [
        "frontend/src/domains/business/views/FinancialManagement.vue",
        "frontend/src/domains/business/views/finance-dashboard/FinanceDashboardView.vue",
        "frontend/src/domains/business/views/finance-dashboard/ProfitOverviewCards.vue",
        "frontend/src/domains/business/views/finance-dashboard/ShopAllocationTable.vue",
        "frontend/src/domains/business/views/finance-dashboard/AdjustmentPanel.vue",
    ]
    return "\n".join(Path(file).read_text(encoding="utf-8") for file in files)


def test_financial_management_page_no_longer_contains_legacy_finance_sections():
    text = _read_dashboard_sources()

    assert "accountsReceivable" not in text
    assert "paymentReceipts" not in text
    assert "overdueAlert" not in text
    assert "fetchOverview(" not in text
    assert "fetchAccountsReceivable(" not in text
    assert "fetchOverdueAlert(" not in text


def test_financial_management_page_is_monthly_profit_dashboard():
    text = _read_dashboard_sources()

    assert "月度利润看板" in text
    assert "本月结果" in text
    assert "店铺分布" in text
    assert "人工调整" in text
    assert "数据截止时间" in text


def test_financial_management_page_removes_budget_and_approval_interactions():
    text = _read_dashboard_sources()

    assert "target_ratio" not in text
    assert "预算(%)" not in text
    assert "审批通过" not in text
    assert "回退草稿" not in text
    assert "重建月结" not in text
    assert "跟投" not in text


def test_financial_management_page_renders_backend_amounts_without_recomputing():
    text = _read_dashboard_sources()

    for field in (
        "net_profit_amount",
        "performance_salary_amount",
        "commission_amount",
        "employee_allocation_amount",
        "manual_adjustment_amount",
        "company_retained_amount",
        "allocation_ratio",
        "over_allocation_flag",
    ):
        assert field in text, f"看板必须渲染后端字段：{field}"

    assert "company_retained_amount =" not in text
    assert "allocation_ratio =" not in text


def test_financial_management_page_shows_manual_adjustment_visibility():
    text = _read_dashboard_sources()

    assert "manual_adjustment_count" in text
    assert "笔人工调整" in text


def test_financial_management_page_shows_adjustment_sign_semantics():
    text = _read_dashboard_sources()

    assert "正数" in text
    assert "负数" in text
    assert "扣减" in text
    assert "追加" in text


def test_financial_management_page_surfaces_states_as_alerts():
    text = _read_dashboard_sources()

    assert "<el-alert" in text
    assert "store.error" in text
