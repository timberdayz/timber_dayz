import pytest

from modules.core.db import (
    AllocationRule,
    ApprovalLog,
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
    TaxReport,
    TaxVoucher,
    ThreeWayMatchLog,
)


@pytest.mark.parametrize(
    ("model", "table_name"),
    [
        (AllocationRule, "allocation_rules"),
        (ApprovalLog, "approval_logs"),
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


def test_finance_internal_foreign_keys_target_finance_tables():
    po_line_targets = {fk.target_fullname for fk in POLine.__table__.foreign_keys}
    grn_header_targets = {fk.target_fullname for fk in GRNHeader.__table__.foreign_keys}
    grn_line_targets = {fk.target_fullname for fk in GRNLine.__table__.foreign_keys}
    invoice_line_targets = {fk.target_fullname for fk in InvoiceLine.__table__.foreign_keys}
    invoice_attachment_targets = {fk.target_fullname for fk in InvoiceAttachment.__table__.foreign_keys}
    journal_line_targets = {fk.target_fullname for fk in JournalEntryLine.__table__.foreign_keys}
    logistics_cost_targets = {fk.target_fullname for fk in LogisticsCost.__table__.foreign_keys}
    tax_voucher_targets = {fk.target_fullname for fk in TaxVoucher.__table__.foreign_keys}

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


def test_finance_external_foreign_keys_keep_core_targets():
    po_header_targets = {fk.target_fullname for fk in POHeader.__table__.foreign_keys}
    invoice_header_targets = {fk.target_fullname for fk in InvoiceHeader.__table__.foreign_keys}
    tax_report_targets = {fk.target_fullname for fk in TaxReport.__table__.foreign_keys}
    tax_voucher_targets = {fk.target_fullname for fk in TaxVoucher.__table__.foreign_keys}
    journal_entry_targets = {fk.target_fullname for fk in JournalEntry.__table__.foreign_keys}

    assert "core.dim_vendors.vendor_code" in po_header_targets
    assert "core.dim_vendors.vendor_code" in invoice_header_targets
    assert "core.dim_fiscal_calendar.period_code" in tax_report_targets
    assert "core.dim_fiscal_calendar.period_code" in tax_voucher_targets
    assert "core.dim_fiscal_calendar.period_code" in journal_entry_targets
