import pytest
import modules.core.db as core_db

from modules.core.db import (
    AllocationRule,
    ApprovalLog,
    EmployeeLaborCostAllocation,
    FactExpensesAllocated,
    FactExpensesMonth,
    FxRate,
    GLAccount,
    GRNHeader,
    GRNLine,
    InventoryLedger,
    InvoiceAttachment,
    InvoiceHeader,
    InvoiceLine,
    JournalEntry,
    JournalEntryLine,
    LogisticsAllocationRule,
    LogisticsCost,
    OpeningBalance,
    POHeader,
    POLine,
    ReturnOrder,
    ShopProfitBasis,
    TaxReport,
    TaxVoucher,
    ThreeWayMatchLog,
)


MonthlyProfitSettlement = getattr(core_db, "MonthlyProfitSettlement", None)
MonthlyProfitAdjustment = getattr(core_db, "MonthlyProfitAdjustment", None)

#: 已下线的月结快照 ORM —— **必须不再存在于 modules.core.db**。
#:
#: 「月度利润结算中心」已改造成只读的月度利润看板：不再冻结快照、不再审批。
#: 这 5 个模型连同对应表已随迁移
#: ``current_schema_20261242_drop_monthly_profit_snapshots`` 一并删除。
#: 这里保留**负向断言**（而不是把用例删光），是为了守护「不再复活」——
#: 一旦有人把类加回 ``modules.core.db``，本用例立刻变红。
RETIRED_MONTHLY_PROFIT_SNAPSHOT_MODELS = (
    "MonthlyProfitPersonnelDetail",
    "MonthlyProfitShopBasisSnapshot",
    "MonthlyProfitEmployeeCommissionSnapshot",
    "MonthlyProfitEmployeePerformanceSnapshot",
    "MonthlyProfitPayrollSnapshot",
)

#: ``finance.monthly_profit_settlements`` 上已废弃的列（预算制 / 差异告警 / 跟投实际额）。
#: 业务已确认「预算在系统外人工做」「不审批」「不设目标额」⇒ 全部废弃。
#: 同样用负向断言守护，避免有人把这批列重新加回 ORM。
RETIRED_MONTHLY_PROFIT_SETTLEMENT_COLUMNS = (
    "personnel_target_ratio",
    "follow_target_ratio",
    "company_target_ratio",
    "personnel_target_amount",
    "follow_target_amount",
    "company_target_amount",
    "difference_amount",
    "difference_ratio",
    "follow_actual_amount",
)


@pytest.mark.parametrize(
    ("model", "table_name"),
    [
        (AllocationRule, "allocation_rules"),
        (ApprovalLog, "approval_logs"),
        (EmployeeLaborCostAllocation, "employee_labor_cost_allocations"),
        (FactExpensesAllocated, "fact_expenses_allocated_day_shop_sku"),
        (FactExpensesMonth, "fact_expenses_month"),
        (FxRate, "fx_rates"),
        (GLAccount, "gl_accounts"),
        (GRNHeader, "grn_headers"),
        (GRNLine, "grn_lines"),
        (InventoryLedger, "inventory_ledger"),
        (InvoiceAttachment, "invoice_attachments"),
        (InvoiceHeader, "invoice_headers"),
        (InvoiceLine, "invoice_lines"),
        (JournalEntry, "journal_entries"),
        (JournalEntryLine, "journal_entry_lines"),
        (LogisticsAllocationRule, "logistics_allocation_rules"),
        (LogisticsCost, "logistics_costs"),
        (OpeningBalance, "opening_balances"),
        (POHeader, "po_headers"),
        (POLine, "po_lines"),
        (ReturnOrder, "return_orders"),
        (ShopProfitBasis, "shop_profit_basis"),
        (TaxReport, "tax_reports"),
        (TaxVoucher, "tax_vouchers"),
        (ThreeWayMatchLog, "three_way_match_log"),
    ],
)
def test_finance_tables_bind_explicitly_to_finance_schema(model, table_name):
    table = model.__table__

    assert table.name == table_name
    assert table.schema == "finance"
    assert table.fullname == f"finance.{table_name}"


@pytest.mark.parametrize(
    ("model_name", "model", "table_name"),
    [
        (
            "MonthlyProfitSettlement",
            MonthlyProfitSettlement,
            "monthly_profit_settlements",
        ),
        (
            "MonthlyProfitAdjustment",
            MonthlyProfitAdjustment,
            "monthly_profit_adjustments",
        ),
    ],
)
def test_monthly_profit_settlement_models_bind_explicitly_to_finance_schema(
    model_name, model, table_name
):
    assert model is not None, f"{model_name} model is missing from modules.core.db"

    table = model.__table__
    assert table.name == table_name
    assert table.schema == "finance"
    assert table.fullname == f"finance.{table_name}"


def test_finance_internal_foreign_keys_target_finance_tables():
    po_line_targets = {fk.target_fullname for fk in POLine.__table__.foreign_keys}
    grn_header_targets = {fk.target_fullname for fk in GRNHeader.__table__.foreign_keys}
    grn_line_targets = {fk.target_fullname for fk in GRNLine.__table__.foreign_keys}
    invoice_line_targets = {
        fk.target_fullname for fk in InvoiceLine.__table__.foreign_keys
    }
    invoice_attachment_targets = {
        fk.target_fullname for fk in InvoiceAttachment.__table__.foreign_keys
    }
    journal_line_targets = {
        fk.target_fullname for fk in JournalEntryLine.__table__.foreign_keys
    }
    logistics_cost_targets = {
        fk.target_fullname for fk in LogisticsCost.__table__.foreign_keys
    }
    tax_voucher_targets = {
        fk.target_fullname for fk in TaxVoucher.__table__.foreign_keys
    }
    assert (
        MonthlyProfitAdjustment is not None
    ), "MonthlyProfitAdjustment model is missing from modules.core.db"
    monthly_profit_adjustment_targets = {
        fk.target_fullname for fk in MonthlyProfitAdjustment.__table__.foreign_keys
    }

    assert "finance.po_headers.po_id" in po_line_targets
    assert "finance.po_headers.po_id" in grn_header_targets
    assert "finance.grn_headers.grn_id" in grn_line_targets
    assert "finance.po_lines.po_line_id" in grn_line_targets
    assert "finance.invoice_headers.invoice_id" in invoice_line_targets
    assert "finance.po_lines.po_line_id" in invoice_line_targets
    assert "finance.grn_lines.grn_line_id" in invoice_line_targets
    assert "finance.invoice_headers.invoice_id" in invoice_attachment_targets
    assert "finance.journal_entries.entry_id" in journal_line_targets
    assert "finance.gl_accounts.account_code" in journal_line_targets
    assert "finance.grn_headers.grn_id" in logistics_cost_targets
    assert "finance.invoice_headers.invoice_id" in logistics_cost_targets
    assert "finance.invoice_headers.invoice_id" in tax_voucher_targets
    assert "finance.monthly_profit_settlements.id" in monthly_profit_adjustment_targets


def test_finance_external_foreign_keys_keep_core_targets():
    po_header_targets = {fk.target_fullname for fk in POHeader.__table__.foreign_keys}
    invoice_header_targets = {
        fk.target_fullname for fk in InvoiceHeader.__table__.foreign_keys
    }
    tax_report_targets = {fk.target_fullname for fk in TaxReport.__table__.foreign_keys}
    tax_voucher_targets = {
        fk.target_fullname for fk in TaxVoucher.__table__.foreign_keys
    }
    journal_entry_targets = {
        fk.target_fullname for fk in JournalEntry.__table__.foreign_keys
    }
    shop_profit_basis_targets = {
        fk.target_fullname for fk in ShopProfitBasis.__table__.foreign_keys
    }

    assert "core.dim_vendors.vendor_code" in po_header_targets
    assert "core.dim_vendors.vendor_code" in invoice_header_targets
    assert "core.dim_fiscal_calendar.period_code" in tax_report_targets
    assert "core.dim_fiscal_calendar.period_code" in tax_voucher_targets
    assert "core.dim_fiscal_calendar.period_code" in journal_entry_targets
    assert "core.dim_fiscal_calendar.period_code" in shop_profit_basis_targets


@pytest.mark.parametrize("model_name", RETIRED_MONTHLY_PROFIT_SNAPSHOT_MODELS)
def test_retired_monthly_profit_snapshot_models_are_not_revived(model_name):
    """月结快照已下线：模型必须不再存在于 modules.core.db（守护「不再复活」）。"""
    message = f"{model_name} 是已下线的月结快照模型，不应再出现在 modules.core.db"
    assert not hasattr(core_db, model_name), message
    assert model_name not in core_db.__all__, message


@pytest.mark.parametrize("column_name", RETIRED_MONTHLY_PROFIT_SETTLEMENT_COLUMNS)
def test_retired_monthly_profit_settlement_columns_are_not_revived(column_name):
    """预算制 / 差异告警 / 跟投实际额已废弃：列必须不再出现在 ORM 上。"""
    message = f"{column_name} 是已废弃的月结列，不应再出现在 MonthlyProfitSettlement 上"
    assert column_name not in MonthlyProfitSettlement.__table__.c, message


def test_monthly_profit_settlement_keeps_ledger_columns():
    """主台账表保留的列（历史 approved 记录要留痕）必须还在。"""
    columns = MonthlyProfitSettlement.__table__.c

    for name in (
        "id",
        "period_month",
        "net_profit_amount",
        "personnel_actual_amount",
        "company_actual_amount",
        "adjustment_amount",
        "status",
        "locked_at",
        "approved_by",
        "approved_at",
        "remark",
        "created_at",
        "updated_at",
    ):
        assert name in columns, f"MonthlyProfitSettlement 缺少保留列 {name}"


def test_employee_labor_cost_allocation_keeps_pre_and_post_commission_components_separate():
    columns = EmployeeLaborCostAllocation.__table__.c

    assert columns["period_month"].nullable is False
    assert columns["employee_code"].nullable is False
    assert columns["allocation_scope"].nullable is False
    assert columns["pre_commission_amount"].nullable is False
    assert columns["performance_amount"].nullable is False
    assert columns["commission_amount"].nullable is False
    assert columns["total_amount"].nullable is False
    assert columns["pre_commission_locked_at"].nullable is True
