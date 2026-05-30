from pathlib import Path


def _read_settlement_sources() -> str:
    files = [
        "frontend/src/domains/business/views/FinancialManagement.vue",
        "frontend/src/domains/business/views/finance-settlement/MonthlySettlementPanel.vue",
        "frontend/src/domains/business/views/finance-settlement/SettlementWorkspacePanel.vue",
    ]
    return "\n".join(Path(file).read_text(encoding="utf-8") for file in files)


def test_financial_management_page_no_longer_contains_legacy_finance_sections():
    text = _read_settlement_sources()

    assert "accountsReceivable" not in text
    assert "paymentReceipts" not in text
    assert "overdueAlert" not in text
    assert "fetchOverview(" not in text
    assert "fetchAccountsReceivable(" not in text
    assert "fetchOverdueAlert(" not in text


def test_financial_management_page_focuses_on_settlement_workflow():
    text = _read_settlement_sources()

    assert "月度利润结算中心" in text
    assert "店铺结算净利润口径" in text
    assert "跟投收益试算" in text
    assert "跟投记录" in text
    assert "结算台账" in text


def test_financial_management_page_uses_platform_and_shop_list_workflow():
    text = _read_settlement_sources()

    assert "可用店铺列表" in text
    assert "当前店铺详情" in text
    assert "selectedShop" in text
    assert "getTargetShops" in text


def test_financial_management_page_shows_platform_level_shop_status_summary():
    text = _read_settlement_sources()

    assert "本平台店铺概览" in text
    assert "有跟投记录店铺" in text
    assert "有结算台账店铺" in text
    assert "待补经营数据" in text


def test_financial_management_page_supports_shop_filters_and_exception_visualization():
    text = _read_settlement_sources()

    assert "店铺筛选" in text
    assert "只看异常店铺" in text
    assert "只看待补经营数据" in text
    assert "当前店铺异常提示" in text
    assert "shopFilterMode" in text
    assert "shopExceptionItems" in text


def test_financial_management_page_exposes_formal_settlement_rules():
    text = _read_settlement_sources()

    assert "规则口径" in text
    assert "可继续结算店铺" in text
    assert "已具备结算信号" in text
    assert "canSettle" in text
    assert "pendingData" in text
    assert "hasException" in text


def test_financial_management_page_surfaces_explicit_next_steps():
    text = _read_settlement_sources()

    assert "推荐下一步" in text
    assert "先查或重算利润口径" in text
    assert "先完成跟投收益试算" in text
    assert "已审批时只能回退后再重建" in text


def test_financial_management_page_syncs_company_month_when_workspace_month_changes():
    text = _read_settlement_sources()

    assert "monthlyForm.value.period_month = selectedMonth.value" in text
