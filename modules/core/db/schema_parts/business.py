from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base, JSON_COMPAT

class DimMetricFormula(Base):
    """
    计算指标公式辞典(自动计算指标)
    
    存储计算类指标的SQL表达式和依赖关系,如:
    - CTR = clicks / NULLIF(impressions, 0)
    - conversion_rate = orders / NULLIF(sessions, 0)
    """
    __tablename__ = "dim_metric_formulas"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 指标标识
    metric_code = Column(String(128), nullable=False, unique=True, index=True)
    cn_name = Column(String(128), nullable=False)
    en_name = Column(String(128), nullable=True)
    description = Column(Text, nullable=True)
    
    # 数据域与分组
    data_domain = Column(String(64), nullable=False, index=True)  # sales/traffic/inventory
    metric_type = Column(String(32), nullable=False)  # ratio/amount/count
    
    # 计算公式
    sql_expr = Column(Text, nullable=False)  # SQL表达式
    depends_on = Column(JSON, nullable=True)  # 依赖的原子字段列表 ["clicks", "impressions"]
    aggregator = Column(String(32), nullable=True)  # SUM/AVG/MAX/MIN/CUSTOM
    
    # 元数据
    unit = Column(String(32), nullable=True)  # %/CNY/count
    display_format = Column(String(64), nullable=True)  # 0.00%/0.00
    
    # 审计
    active = Column(Boolean, default=True)
    version = Column(Integer, default=1, nullable=False)
    created_by = Column(String(64), default="system")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        Index("ix_metric_formula_domain", "data_domain", "active"),
        {"schema": "core"},
    )

class DimCurrency(Base):
    """货币维度表"""
    __tablename__ = "dim_currencies"
    
    currency_code = Column(String(8), primary_key=True)  # CNY/USD/SGD
    currency_name = Column(String(64), nullable=False)
    symbol = Column(String(8), nullable=True)
    is_base = Column(Boolean, default=False)  # CNY为基准货币
    active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        {"schema": "core"},
    )

class FxRate(Base):
    """汇率表(CNY基准)"""
    __tablename__ = "fx_rates"
    
    rate_date = Column(Date, primary_key=True)
    from_currency = Column(String(8), primary_key=True)
    to_currency = Column(String(8), primary_key=True)
    
    rate = Column(Float, nullable=False)  # Decimal(18,6) precision
    source = Column(String(64), nullable=True, default="manual")  # manual/ecb/api
    version = Column(Integer, default=1, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_fx_rates_date_from", "rate_date", "from_currency"),
        {"schema": "finance"},
    )

class DimFiscalCalendar(Base):
    """会计期间日历表"""
    __tablename__ = "dim_fiscal_calendar"
    
    period_id = Column(Integer, primary_key=True, autoincrement=True)
    
    period_year = Column(Integer, nullable=False)
    period_month = Column(Integer, nullable=False)  # 1-12
    period_code = Column(String(16), nullable=False, unique=True)  # 2025-01
    
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    
    status = Column(String(32), default="open", nullable=False)  # open/closed
    closed_by = Column(String(64), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_fiscal_calendar_year_month", "period_year", "period_month"),
        Index("ix_fiscal_calendar_status", "status"),
        UniqueConstraint("period_year", "period_month", name="uq_fiscal_period"),
        {"schema": "core"},
    )

class DimVendor(Base):
    """供应商维度表"""
    __tablename__ = "dim_vendors"
    
    vendor_code = Column(String(64), primary_key=True)
    vendor_name = Column(String(256), nullable=False)
    
    country = Column(String(64), nullable=True)
    tax_id = Column(String(128), nullable=True)
    payment_terms = Column(String(64), nullable=True)  # NET30/NET60
    credit_limit = Column(Float, default=0.0)
    
    status = Column(String(32), default="active", nullable=False)  # active/suspended/blocked
    
    contact_person = Column(String(128), nullable=True)
    contact_phone = Column(String(64), nullable=True)
    contact_email = Column(String(128), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        Index("ix_vendors_status", "status"),
        {"schema": "core"},
    )

class POHeader(Base):
    """采购订单头表"""
    __tablename__ = "po_headers"
    
    po_id = Column(String(64), primary_key=True)
    
    vendor_code = Column(String(64), ForeignKey("core.dim_vendors.vendor_code"), nullable=False)
    po_date = Column(Date, nullable=False)
    expected_date = Column(Date, nullable=True)
    
    currency = Column(String(8), nullable=False)
    total_amt = Column(Float, default=0.0)
    base_amt = Column(Float, default=0.0)  # CNY
    
    status = Column(String(32), default="draft", nullable=False)  # draft/pending_approval/approved/closed
    approval_threshold = Column(Float, nullable=True)
    approved_by = Column(String(64), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    
    created_by = Column(String(64), default="system")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        Index("ix_po_headers_vendor_date", "vendor_code", "po_date"),
        Index("ix_po_headers_status", "status"),
        {"schema": "finance"},
    )

class POLine(Base):
    """采购订单行表"""
    __tablename__ = "po_lines"
    
    po_line_id = Column(Integer, primary_key=True, autoincrement=True)
    
    po_id = Column(String(64), ForeignKey("finance.po_headers.po_id", ondelete="CASCADE"), nullable=False)
    line_number = Column(Integer, nullable=False)
    
    platform_sku = Column(String(128), nullable=False)  # 关联到BridgeProductKeys
    product_title = Column(String(512), nullable=True)
    
    qty_ordered = Column(Integer, default=0)
    qty_received = Column(Integer, default=0)
    
    unit_price = Column(Float, nullable=False)
    currency = Column(String(8), nullable=False)
    line_amt = Column(Float, default=0.0)
    base_amt = Column(Float, default=0.0)  # CNY
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_po_lines_po_id", "po_id"),
        Index("ix_po_lines_sku", "platform_sku"),
        UniqueConstraint("po_id", "line_number", name="uq_po_line"),
        {"schema": "finance"},
    )

class GRNHeader(Base):
    """入库单头表(Goods Receipt Note)"""
    __tablename__ = "grn_headers"
    
    grn_id = Column(String(64), primary_key=True)
    
    po_id = Column(String(64), ForeignKey("finance.po_headers.po_id"), nullable=False)
    receipt_date = Column(Date, nullable=False)
    warehouse = Column(String(64), nullable=True)
    
    status = Column(String(32), default="pending", nullable=False)  # pending/completed/cancelled
    
    created_by = Column(String(64), default="system")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_grn_headers_po_id", "po_id"),
        Index("ix_grn_headers_date", "receipt_date"),
        {"schema": "finance"},
    )

class GRNLine(Base):
    """入库单行表"""
    __tablename__ = "grn_lines"
    
    grn_line_id = Column(Integer, primary_key=True, autoincrement=True)
    
    grn_id = Column(String(64), ForeignKey("finance.grn_headers.grn_id", ondelete="CASCADE"), nullable=False)
    po_line_id = Column(Integer, ForeignKey("finance.po_lines.po_line_id"), nullable=False)
    
    platform_sku = Column(String(128), nullable=False)
    qty_received = Column(Integer, default=0)
    
    unit_cost = Column(Float, nullable=False)
    currency = Column(String(8), nullable=False)
    ext_value = Column(Float, default=0.0)  # 原币
    base_ext_value = Column(Float, default=0.0)  # CNY
    
    weight_kg = Column(Float, nullable=True)
    volume_m3 = Column(Float, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_grn_lines_grn_id", "grn_id"),
        Index("ix_grn_lines_po_line", "po_line_id"),
        Index("ix_grn_lines_sku", "platform_sku"),
        {"schema": "finance"},
    )

class InventoryLedger(Base):
    """
    库存流水账表(Universal Journal模式)
    
    唯一库存真源,记录所有出入库事务:
    - receipt: 采购入库
    - sale: 销售出库
    - return: 退货入库
    - adjustment: 盘点调整
    
    支持移动加权平均成本计算
    """
    __tablename__ = "inventory_ledger"
    
    ledger_id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 业务标识
    platform_code = Column(String(32), nullable=False)
    shop_id = Column(String(64), nullable=False)
    platform_sku = Column(String(128), nullable=False)
    received_date = Column(Date, nullable=True)
    opening_age_days = Column(Integer, nullable=True)
    
    # 交易日期与类型
    transaction_date = Column(Date, nullable=False)
    movement_type = Column(String(32), nullable=False)  # receipt/sale/return/adjustment
    
    # 数量与成本
    qty_in = Column(Integer, default=0)
    qty_out = Column(Integer, default=0)
    unit_cost_wac = Column(Float, nullable=False)  # 移动加权平均成本
    ext_value = Column(Float, default=0.0)
    base_ext_value = Column(Float, default=0.0)  # CNY
    
    # 成本计算辅助(移动加权平均)
    qty_before = Column(Integer, default=0)
    avg_cost_before = Column(Float, default=0.0)
    qty_after = Column(Integer, default=0)
    avg_cost_after = Column(Float, default=0.0)
    
    # 来源追踪
    link_grn_id = Column(String(64), nullable=True)  # 关联入库单
    link_order_id = Column(String(128), nullable=True)  # 关联销售订单
    original_sale_line_id = Column(Integer, nullable=True)  # 退货关联原销售行
    return_reason = Column(String(256), nullable=True)
    
    # 审计
    created_by = Column(String(64), default="system")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_inventory_ledger_sku_date", "platform_code", "shop_id", "platform_sku", "transaction_date"),
        Index("ix_inventory_ledger_type", "movement_type", "transaction_date"),
        Index("ix_inventory_ledger_grn", "link_grn_id"),
        Index("ix_inventory_ledger_order", "link_order_id"),
        {"schema": "finance"},
    )

class InvoiceHeader(Base):
    """发票头表"""
    __tablename__ = "invoice_headers"
    
    invoice_id = Column(Integer, primary_key=True, autoincrement=True)
    
    vendor_code = Column(String(64), ForeignKey("core.dim_vendors.vendor_code"), nullable=False)
    invoice_no = Column(String(128), nullable=False, unique=True)
    invoice_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=True)
    
    currency = Column(String(8), nullable=False)
    total_amt = Column(Float, default=0.0)
    tax_amt = Column(Float, default=0.0)
    base_total_amt = Column(Float, default=0.0)  # CNY
    
    status = Column(String(32), default="pending", nullable=False)  # pending/matched/paid
    
    # OCR结果
    source_file_id = Column(Integer, ForeignKey("catalog_files.id", ondelete="SET NULL"), nullable=True)
    ocr_result = Column(JSON, nullable=True)
    ocr_confidence = Column(Float, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        Index("ix_invoice_headers_vendor_date", "vendor_code", "invoice_date"),
        Index("ix_invoice_headers_status", "status"),
        {"schema": "finance"},
    )

class InvoiceLine(Base):
    """发票行表"""
    __tablename__ = "invoice_lines"
    
    invoice_line_id = Column(Integer, primary_key=True, autoincrement=True)
    
    invoice_id = Column(Integer, ForeignKey("finance.invoice_headers.invoice_id", ondelete="CASCADE"), nullable=False)
    po_line_id = Column(Integer, ForeignKey("finance.po_lines.po_line_id"), nullable=True)
    grn_line_id = Column(Integer, ForeignKey("finance.grn_lines.grn_line_id"), nullable=True)
    
    platform_sku = Column(String(128), nullable=False)
    qty = Column(Integer, default=0)
    
    unit_price = Column(Float, nullable=False)
    line_amt = Column(Float, default=0.0)
    tax_amt = Column(Float, default=0.0)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_invoice_lines_invoice", "invoice_id"),
        Index("ix_invoice_lines_po_line", "po_line_id"),
        Index("ix_invoice_lines_grn_line", "grn_line_id"),
        {"schema": "finance"},
    )

class InvoiceAttachment(Base):
    """发票附件表(扫描件)"""
    __tablename__ = "invoice_attachments"
    
    attachment_id = Column(Integer, primary_key=True, autoincrement=True)
    
    invoice_id = Column(Integer, ForeignKey("finance.invoice_headers.invoice_id", ondelete="CASCADE"), nullable=False)
    
    file_path = Column(String(1024), nullable=False)
    file_type = Column(String(32), nullable=True)  # pdf/jpg/png
    file_size = Column(Integer, nullable=True)
    
    ocr_text = Column(Text, nullable=True)
    ocr_fields = Column(JSON, nullable=True)  # 提取的结构化字段
    
    uploaded_by = Column(String(64), default="system")
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_invoice_attachments_invoice", "invoice_id"),
        {"schema": "finance"},
    )

class ThreeWayMatchLog(Base):
    """三单匹配日志表(PO-GRN-Invoice)"""
    __tablename__ = "three_way_match_log"
    
    match_id = Column(Integer, primary_key=True, autoincrement=True)
    
    po_line_id = Column(Integer, ForeignKey("finance.po_lines.po_line_id"), nullable=False)
    grn_line_id = Column(Integer, ForeignKey("finance.grn_lines.grn_line_id"), nullable=True)
    invoice_line_id = Column(Integer, ForeignKey("finance.invoice_lines.invoice_line_id"), nullable=True)
    
    match_status = Column(String(32), default="unmatched", nullable=False)  # matched/variance/unmatched
    
    variance_qty = Column(Integer, default=0)
    variance_amt = Column(Float, default=0.0)
    variance_reason = Column(Text, nullable=True)
    
    approved_by = Column(String(64), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_three_way_match_po", "po_line_id"),
        Index("ix_three_way_match_status", "match_status"),
        {"schema": "finance"},
    )

class FactExpensesMonth(Base):
    """月度运营费用事实表"""
    __tablename__ = "fact_expenses_month"
    
    expense_id = Column(Integer, primary_key=True, autoincrement=True)
    
    period_month = Column(String(16), ForeignKey("core.dim_fiscal_calendar.period_code"), nullable=False)
    
    cost_center = Column(String(64), nullable=True)  # 成本中心
    expense_type = Column(String(128), nullable=False)  # 从FieldMappingDictionary
    vendor = Column(String(256), nullable=True)
    
    currency = Column(String(8), nullable=False)
    currency_amt = Column(Float, default=0.0)
    base_amt = Column(Float, default=0.0)  # CNY
    tax_amt = Column(Float, default=0.0)
    
    # 可选:指定店铺(不指定则需分摊)
    platform_code = Column(String(32), nullable=True)
    shop_id = Column(String(64), nullable=True)
    
    source_file_id = Column(Integer, ForeignKey("catalog_files.id", ondelete="SET NULL"), nullable=True)
    memo = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_expenses_month_period", "period_month"),
        Index("ix_expenses_month_type", "expense_type"),
        Index("ix_expenses_month_shop", "platform_code", "shop_id"),
        {"schema": "finance"},
    )

class AllocationRule(Base):
    """分摊规则表"""
    __tablename__ = "allocation_rules"
    
    rule_id = Column(Integer, primary_key=True, autoincrement=True)
    
    rule_name = Column(String(256), nullable=False)
    scope = Column(String(64), nullable=False)  # expense/logistics
    driver = Column(String(64), nullable=False)  # revenue_share/orders_share/units_share/weight/volume/manual
    
    # 权重配置(JSON格式)
    weights = Column(JSON, nullable=True)  # {"shop_a": 0.4, "shop_b": 0.6}
    
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True)
    
    active = Column(Boolean, default=True)
    created_by = Column(String(64), default="system")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_allocation_rules_scope", "scope", "active"),
        {"schema": "finance"},
    )

class FactExpensesAllocated(Base):
    """费用分摊结果表(日-店铺-SKU粒度)"""
    __tablename__ = "fact_expenses_allocated_day_shop_sku"
    
    allocation_id = Column(Integer, primary_key=True, autoincrement=True)
    
    expense_id = Column(Integer, ForeignKey("finance.fact_expenses_month.expense_id"), nullable=False)
    allocation_date = Column(Date, nullable=False)
    
    platform_code = Column(String(32), nullable=False)
    shop_id = Column(String(64), nullable=False)
    platform_sku = Column(String(128), nullable=True)  # NULL表示店铺级
    
    allocated_amt = Column(Float, default=0.0)  # CNY
    allocation_driver = Column(String(64), nullable=True)
    allocation_weight = Column(Float, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_expenses_allocated_date", "allocation_date"),
        Index("ix_expenses_allocated_shop", "platform_code", "shop_id", "allocation_date"),
        Index("ix_expenses_allocated_sku", "platform_code", "shop_id", "platform_sku", "allocation_date"),
        {"schema": "finance"},
    )

class LogisticsCost(Base):
    """物流成本表"""
    __tablename__ = "logistics_costs"
    
    logistics_id = Column(Integer, primary_key=True, autoincrement=True)
    
    grn_id = Column(String(64), ForeignKey("finance.grn_headers.grn_id"), nullable=True)  # 入库物流
    order_id = Column(String(128), nullable=True)  # 销售物流
    
    logistics_provider = Column(String(128), nullable=True)
    tracking_no = Column(String(128), nullable=True)
    cost_type = Column(String(64), nullable=False)  # freight/customs/insurance
    
    currency = Column(String(8), nullable=False)
    currency_amt = Column(Float, default=0.0)
    base_amt = Column(Float, default=0.0)  # CNY
    
    weight_kg = Column(Float, nullable=True)
    volume_m3 = Column(Float, nullable=True)
    
    invoice_id = Column(Integer, ForeignKey("finance.invoice_headers.invoice_id"), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_logistics_costs_grn", "grn_id"),
        Index("ix_logistics_costs_order", "order_id"),
        Index("ix_logistics_costs_invoice", "invoice_id"),
        {"schema": "finance"},
    )

class LogisticsAllocationRule(Base):
    """物流成本分摊规则表"""
    __tablename__ = "logistics_allocation_rules"
    
    rule_id = Column(Integer, primary_key=True, autoincrement=True)
    
    rule_name = Column(String(256), nullable=False)
    scope = Column(String(64), nullable=False)  # domestic/international
    driver = Column(String(64), nullable=False)  # weight/volume/revenue/order
    
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True)
    
    active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_logistics_alloc_rules_scope", "scope", "active"),
        {"schema": "finance"},
    )

class TaxVoucher(Base):
    """税务凭证表"""
    __tablename__ = "tax_vouchers"
    
    voucher_id = Column(Integer, primary_key=True, autoincrement=True)
    
    period_month = Column(String(16), ForeignKey("core.dim_fiscal_calendar.period_code"), nullable=False)
    voucher_type = Column(String(32), nullable=False)  # input_tax/output_tax
    
    invoice_id = Column(Integer, ForeignKey("finance.invoice_headers.invoice_id"), nullable=True)
    
    tax_amt = Column(Float, default=0.0)
    deductible_amt = Column(Float, default=0.0)  # 可抵扣金额
    
    status = Column(String(32), default="pending", nullable=False)  # pending/filed/rejected
    filing_status = Column(String(64), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_tax_vouchers_period", "period_month"),
        Index("ix_tax_vouchers_type", "voucher_type", "status"),
        {"schema": "finance"},
    )

class TaxReport(Base):
    """报税清单表"""
    __tablename__ = "tax_reports"
    
    report_id = Column(Integer, primary_key=True, autoincrement=True)
    
    period_month = Column(String(16), ForeignKey("core.dim_fiscal_calendar.period_code"), nullable=False)
    report_type = Column(String(64), nullable=False)  # vat/export_refund
    
    status = Column(String(32), default="draft", nullable=False)  # draft/submitted
    export_file_path = Column(String(1024), nullable=True)
    
    generated_by = Column(String(64), default="system")
    generated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    
    __table_args__ = (
        Index("ix_tax_reports_period", "period_month"),
        Index("ix_tax_reports_status", "status"),
        {"schema": "finance"},
    )

class GLAccount(Base):
    """总账科目表"""
    __tablename__ = "gl_accounts"
    
    account_code = Column(String(64), primary_key=True)
    account_name = Column(String(256), nullable=False)
    account_type = Column(String(64), nullable=False)  # asset/liability/equity/revenue/expense
    parent_account = Column(String(64), nullable=True)
    
    is_debit_normal = Column(Boolean, default=True)  # 借方为正常余额
    active = Column(Boolean, default=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_gl_accounts_type", "account_type", "active"),
        {"schema": "finance"},
    )

class JournalEntry(Base):
    """总账凭证头表"""
    __tablename__ = "journal_entries"
    
    entry_id = Column(Integer, primary_key=True, autoincrement=True)
    
    entry_no = Column(String(64), nullable=False, unique=True)
    entry_date = Column(Date, nullable=False)
    period_month = Column(String(16), ForeignKey("core.dim_fiscal_calendar.period_code"), nullable=False)
    
    entry_type = Column(String(64), nullable=False)  # revenue/expense/asset/adjustment
    description = Column(Text, nullable=True)
    
    status = Column(String(32), default="draft", nullable=False)  # draft/posted/reversed
    
    created_by = Column(String(64), default="system")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    posted_at = Column(DateTime(timezone=True), nullable=True)
    
    __table_args__ = (
        Index("ix_journal_entries_date", "entry_date"),
        Index("ix_journal_entries_period", "period_month"),
        Index("ix_journal_entries_status", "status"),
        {"schema": "finance"},
    )

class JournalEntryLine(Base):
    """总账凭证行表(双分录)"""
    __tablename__ = "journal_entry_lines"
    
    line_id = Column(Integer, primary_key=True, autoincrement=True)
    
    entry_id = Column(Integer, ForeignKey("finance.journal_entries.entry_id", ondelete="CASCADE"), nullable=False)
    line_number = Column(Integer, nullable=False)
    
    account_code = Column(String(64), ForeignKey("finance.gl_accounts.account_code"), nullable=False)
    
    debit_amt = Column(Float, default=0.0)
    credit_amt = Column(Float, default=0.0)
    
    currency = Column(String(8), default="CNY")
    currency_amt = Column(Float, default=0.0)
    base_amt = Column(Float, default=0.0)  # CNY
    
    # 来源追踪
    link_order_id = Column(String(128), nullable=True)
    link_expense_id = Column(Integer, nullable=True)
    link_invoice_id = Column(Integer, nullable=True)
    
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_journal_lines_entry", "entry_id"),
        Index("ix_journal_lines_account", "account_code"),
        UniqueConstraint("entry_id", "line_number", name="uq_journal_line"),
        {"schema": "finance"},
    )

class OpeningBalance(Base):
    """期初余额表(数据迁移用)"""
    __tablename__ = "opening_balances"
    
    balance_id = Column(Integer, primary_key=True, autoincrement=True)
    
    period = Column(String(16), nullable=False)  # 期初期间 2025-01
    
    platform_code = Column(String(32), nullable=False)
    shop_id = Column(String(64), nullable=False)
    platform_sku = Column(String(128), nullable=False)
    received_date = Column(Date, nullable=True)
    opening_age_days = Column(Integer, nullable=True)
    
    opening_qty = Column(Integer, default=0)
    opening_cost = Column(Float, default=0.0)  # 单位成本
    opening_value = Column(Float, default=0.0)  # 总价值 CNY
    
    source = Column(String(64), default="migration")  # migration/manual
    migration_batch_id = Column(String(64), nullable=True)
    
    created_by = Column(String(64), default="system")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_opening_balances_period", "period"),
        Index("ix_opening_balances_sku", "platform_code", "shop_id", "platform_sku"),
        UniqueConstraint("period", "platform_code", "shop_id", "platform_sku", name="uq_opening_balance"),
        {"schema": "finance"},
    )

class InventoryLayer(Base):
    """库存入库层表"""
    __tablename__ = "inventory_layers"

    layer_id = Column(Integer, primary_key=True, autoincrement=True)

    source_type = Column(String(32), nullable=False)
    source_id = Column(String(64), nullable=False)
    source_line_id = Column(String(64), nullable=True)

    platform_code = Column(String(32), nullable=False)
    shop_id = Column(String(64), nullable=False)
    platform_sku = Column(String(128), nullable=False)
    warehouse = Column(String(64), nullable=True)

    received_date = Column(Date, nullable=False)
    original_qty = Column(Integer, nullable=False, default=0)
    remaining_qty = Column(Integer, nullable=False, default=0)

    unit_cost = Column(Float, nullable=False, default=0.0)
    base_unit_cost = Column(Float, nullable=False, default=0.0)

    created_by = Column(String(64), default="system")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_inventory_layers_sku", "platform_code", "shop_id", "platform_sku"),
        Index("ix_inventory_layers_received", "received_date"),
        Index("ix_inventory_layers_source", "source_type", "source_id"),
        {"schema": "finance"},
    )

class InventoryLayerConsumption(Base):
    """库存层消耗记录表"""
    __tablename__ = "inventory_layer_consumptions"

    id = Column(Integer, primary_key=True, autoincrement=True)

    outbound_ledger_id = Column(
        Integer,
        ForeignKey("finance.inventory_ledger.ledger_id"),
        nullable=False,
    )
    layer_id = Column(
        Integer,
        ForeignKey("finance.inventory_layers.layer_id"),
        nullable=False,
    )
    platform_code = Column(String(32), nullable=False)
    shop_id = Column(String(64), nullable=False)
    platform_sku = Column(String(128), nullable=False)
    consumed_qty = Column(Integer, nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    age_days_at_consumption = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("ix_inventory_layer_consumptions_ledger", "outbound_ledger_id"),
        Index("ix_inventory_layer_consumptions_layer", "layer_id"),
        Index("ix_inventory_layer_consumptions_sku", "platform_code", "shop_id", "platform_sku"),
        {"schema": "finance"},
    )

class InventoryAdjustmentHeader(Base):
    """库存调整单头表"""
    __tablename__ = "inventory_adjustment_headers"

    adjustment_id = Column(String(64), primary_key=True)

    adjustment_date = Column(Date, nullable=False)
    status = Column(String(32), nullable=False, default="draft")  # draft/posted/cancelled
    reason = Column(String(64), nullable=False)
    notes = Column(Text, nullable=True)

    created_by = Column(String(64), nullable=False, default="system")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_inventory_adjustment_headers_date", "adjustment_date"),
        Index("ix_inventory_adjustment_headers_status", "status"),
        {"schema": "finance"},
    )

class InventoryAdjustmentLine(Base):
    """库存调整单行表"""
    __tablename__ = "inventory_adjustment_lines"

    adjustment_line_id = Column(Integer, primary_key=True, autoincrement=True)

    adjustment_id = Column(
        String(64),
        ForeignKey("finance.inventory_adjustment_headers.adjustment_id", ondelete="CASCADE"),
        nullable=False,
    )
    platform_code = Column(String(32), nullable=False)
    shop_id = Column(String(64), nullable=False)
    platform_sku = Column(String(128), nullable=False)
    qty_delta = Column(Integer, nullable=False)
    unit_cost = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_inventory_adjustment_lines_adjustment_id", "adjustment_id"),
        Index("ix_inventory_adjustment_lines_sku", "platform_code", "shop_id", "platform_sku"),
        {"schema": "finance"},
    )

class ApprovalLog(Base):
    """审批日志表(PO/费用审批)"""
    __tablename__ = "approval_logs"
    
    log_id = Column(Integer, primary_key=True, autoincrement=True)
    
    entity_type = Column(String(64), nullable=False)  # PO/expense
    entity_id = Column(String(128), nullable=False)
    
    approver = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False)  # pending/approved/rejected
    comment = Column(Text, nullable=True)
    
    approved_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_approval_logs_entity", "entity_type", "entity_id"),
        Index("ix_approval_logs_approver", "approver", "status"),
        {"schema": "finance"},
    )

class ShopProfitBasis(Base):
    """店铺月度统一结算利润快照表"""
    __tablename__ = "shop_profit_basis"

    id = Column(Integer, primary_key=True, autoincrement=True)

    period_month = Column(String(16), ForeignKey("core.dim_fiscal_calendar.period_code"), nullable=False)
    platform_code = Column(String(32), nullable=False)
    shop_id = Column(String(64), nullable=False)

    orders_profit_amount = Column(Float, default=0.0, nullable=False)
    a_class_cost_amount = Column(Float, default=0.0, nullable=False)
    b_class_cost_amount = Column(Float, default=0.0, nullable=False)
    profit_basis_amount = Column(Float, default=0.0, nullable=False)

    basis_version = Column(String(64), default="A_ONLY_V1", nullable=False)
    is_locked = Column(Boolean, default=False, nullable=False)

    created_by = Column(String(64), default="system")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("period_month", "platform_code", "shop_id", "basis_version", name="uq_shop_profit_basis"),
        Index("ix_shop_profit_basis_period", "period_month"),
        Index("ix_shop_profit_basis_shop", "platform_code", "shop_id"),
        {"schema": "finance"},
    )

class FollowInvestment(Base):
    """店铺跟投本金记录表"""
    __tablename__ = "follow_investments"

    id = Column(Integer, primary_key=True, autoincrement=True)

    investor_user_id = Column(BigInteger, ForeignKey("core.dim_users.user_id"), nullable=False)
    platform_code = Column(String(32), nullable=False)
    shop_id = Column(String(64), nullable=False)

    contribution_amount = Column(Float, default=0.0, nullable=False)
    contribution_date = Column(Date, nullable=False)
    withdraw_date = Column(Date, nullable=True)

    capital_type = Column(String(32), default="working_capital", nullable=False)
    status = Column(String(32), default="active", nullable=False)
    remark = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_follow_investments_user", "investor_user_id", "status"),
        Index("ix_follow_investments_shop", "platform_code", "shop_id", "contribution_date"),
        {"schema": "finance"},
    )

class FollowInvestmentSettlement(Base):
    """店铺月度跟投结算头表"""
    __tablename__ = "follow_investment_settlements"

    id = Column(Integer, primary_key=True, autoincrement=True)

    profit_basis_id = Column(Integer, ForeignKey("finance.shop_profit_basis.id"), nullable=False)
    period_month = Column(String(16), nullable=False)
    platform_code = Column(String(32), nullable=False)
    shop_id = Column(String(64), nullable=False)

    profit_basis_amount = Column(Float, default=0.0, nullable=False)
    distribution_ratio = Column(Float, default=0.0, nullable=False)
    distributable_amount = Column(Float, default=0.0, nullable=False)

    status = Column(String(32), default="draft", nullable=False)
    approved_by = Column(String(64), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_follow_investment_settlements_period", "period_month", "status"),
        Index("ix_follow_investment_settlements_shop", "platform_code", "shop_id"),
        {"schema": "finance"},
    )

class FollowInvestmentDetail(Base):
    """店铺月度跟投结算明细表"""
    __tablename__ = "follow_investment_details"

    id = Column(Integer, primary_key=True, autoincrement=True)

    settlement_id = Column(Integer, ForeignKey("finance.follow_investment_settlements.id", ondelete="CASCADE"), nullable=False)
    investor_user_id = Column(BigInteger, ForeignKey("core.dim_users.user_id"), nullable=False)

    contribution_amount_snapshot = Column(Float, default=0.0, nullable=False)
    occupied_days = Column(Integer, default=0, nullable=False)
    weighted_capital = Column(Float, default=0.0, nullable=False)
    share_ratio = Column(Float, default=0.0, nullable=False)

    estimated_income = Column(Float, default=0.0, nullable=False)
    approved_income = Column(Float, default=0.0, nullable=False)
    paid_income = Column(Float, default=0.0, nullable=False)

    payment_status = Column(String(32), default="pending", nullable=False)
    paid_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_follow_investment_details_settlement", "settlement_id"),
        Index("ix_follow_investment_details_user", "investor_user_id", "settlement_id"),
        {"schema": "finance"},
    )

class MonthlyProfitSettlement(Base):
    """公司级月度利润结算主表"""
    __tablename__ = "monthly_profit_settlements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    period_month = Column(String(16), ForeignKey("core.dim_fiscal_calendar.period_code"), nullable=False)

    net_profit_amount = Column(Float, default=0.0, nullable=False)

    personnel_target_ratio = Column(Float, default=0.0, nullable=False)
    follow_target_ratio = Column(Float, default=0.0, nullable=False)
    company_target_ratio = Column(Float, default=0.0, nullable=False)

    personnel_target_amount = Column(Float, default=0.0, nullable=False)
    follow_target_amount = Column(Float, default=0.0, nullable=False)
    company_target_amount = Column(Float, default=0.0, nullable=False)

    personnel_actual_amount = Column(Float, default=0.0, nullable=False)
    follow_actual_amount = Column(Float, default=0.0, nullable=False)
    company_actual_amount = Column(Float, default=0.0, nullable=False)

    adjustment_amount = Column(Float, default=0.0, nullable=False)
    difference_amount = Column(Float, default=0.0, nullable=False)
    difference_ratio = Column(Float, default=0.0, nullable=False)

    status = Column(String(32), default="draft", nullable=False)
    locked_at = Column(DateTime(timezone=True), nullable=True)
    approved_by = Column(String(64), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    remark = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("period_month", name="uq_monthly_profit_settlements_period"),
        Index("ix_monthly_profit_settlements_status", "status"),
        {"schema": "finance"},
    )

class MonthlyProfitPersonnelDetail(Base):
    """公司级月度利润结算人员成本明细表"""
    __tablename__ = "monthly_profit_personnel_details"

    id = Column(Integer, primary_key=True, autoincrement=True)
    settlement_id = Column(Integer, ForeignKey("finance.monthly_profit_settlements.id", ondelete="CASCADE"), nullable=False)
    detail_type = Column(String(64), nullable=False)
    employee_code = Column(String(64), nullable=True)
    platform_code = Column(String(32), nullable=True)
    shop_id = Column(String(64), nullable=True)
    source_module = Column(String(64), nullable=True)
    source_record_id = Column(String(64), nullable=True)
    amount = Column(Float, default=0.0, nullable=False)
    remark = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_monthly_profit_personnel_details_settlement", "settlement_id"),
        {"schema": "finance"},
    )

class MonthlyProfitFollowDetail(Base):
    """公司级月度利润结算跟投收益明细表"""
    __tablename__ = "monthly_profit_follow_details"

    id = Column(Integer, primary_key=True, autoincrement=True)
    settlement_id = Column(Integer, ForeignKey("finance.monthly_profit_settlements.id", ondelete="CASCADE"), nullable=False)
    investor_user_id = Column(BigInteger, ForeignKey("core.dim_users.user_id"), nullable=True)
    source_settlement_id = Column(Integer, ForeignKey("finance.follow_investment_settlements.id"), nullable=True)
    amount = Column(Float, default=0.0, nullable=False)
    status = Column(String(32), default="approved", nullable=False)
    remark = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_monthly_profit_follow_details_settlement", "settlement_id"),
        {"schema": "finance"},
    )

class MonthlyProfitAdjustment(Base):
    """公司级月度利润结算调整项表"""
    __tablename__ = "monthly_profit_adjustments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    settlement_id = Column(Integer, ForeignKey("finance.monthly_profit_settlements.id", ondelete="CASCADE"), nullable=False)
    adjustment_type = Column(String(64), nullable=False)
    amount = Column(Float, default=0.0, nullable=False)
    reason = Column(Text, nullable=True)
    created_by = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_monthly_profit_adjustments_settlement", "settlement_id"),
        {"schema": "finance"},
    )

class ReturnOrder(Base):
    """退货单表"""
    __tablename__ = "return_orders"
    
    return_id = Column(Integer, primary_key=True, autoincrement=True)
    
    original_order_id = Column(String(128), nullable=False)
    return_type = Column(String(32), nullable=False)  # customer/vendor
    
    platform_code = Column(String(32), nullable=False)
    shop_id = Column(String(64), nullable=False)
    platform_sku = Column(String(128), nullable=False)
    
    qty = Column(Integer, default=0)
    refund_amt = Column(Float, default=0.0)
    restocking_fee = Column(Float, default=0.0)
    
    reason = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_return_orders_original", "original_order_id"),
        Index("ix_return_orders_shop", "platform_code", "shop_id"),
        {"schema": "finance"},
    )

class SalesCampaign(Base):
    """
    销售战役管理表(A类数据:用户配置)
    
    用途:存储销售战役配置信息,用户在系统中创建和编辑
    达成数据:从fact_orders表自动计算(C类数据)
    """
    __tablename__ = "sales_campaigns"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 战役基本信息
    campaign_name = Column(String(200), nullable=False, comment="战役名称")
    campaign_type = Column(String(32), nullable=False, comment="战役类型:holiday/new_product/special_event")
    start_date = Column(Date, nullable=False, comment="开始日期")
    end_date = Column(Date, nullable=False, comment="结束日期")
    
    # 目标值(A类:用户配置)
    target_amount = Column(Float, nullable=False, default=0.0, comment="目标销售额(CNY)")
    target_quantity = Column(Integer, nullable=False, default=0, comment="目标订单数/销量")
    
    # 达成值(C类:系统自动计算)
    actual_amount = Column(Float, nullable=False, default=0.0, comment="实际销售额(CNY)")
    actual_quantity = Column(Integer, nullable=False, default=0, comment="实际订单数/销量")
    achievement_rate = Column(Float, nullable=False, default=0.0, comment="达成率(百分比)")
    
    # 状态
    status = Column(String(32), nullable=False, default="pending", comment="状态:active/completed/pending/cancelled")
    description = Column(Text, nullable=True, comment="战役描述")
    
    # 审计字段
    created_by = Column(String(64), nullable=True, comment="创建人")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="chk_campaign_dates"),
        CheckConstraint("target_amount >= 0", name="chk_campaign_amount"),
        CheckConstraint("target_quantity >= 0", name="chk_campaign_quantity"),
        Index("ix_sales_campaigns_status", "status"),
        Index("ix_sales_campaigns_dates", "start_date", "end_date"),
        Index("ix_sales_campaigns_type", "campaign_type"),
        {"schema": "a_class"},
    )

class SalesCampaignShop(Base):
    """
    销售战役参与店铺表(A类数据:用户配置)
    
    用途:存储战役参与店铺及其目标配置
    达成数据:从fact_orders表自动计算(C类数据)
    """
    __tablename__ = "sales_campaign_shops"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 关联字段
    campaign_id = Column(Integer, ForeignKey("a_class.sales_campaigns.id", ondelete="CASCADE"), nullable=False)
    platform_code = Column(String(32), nullable=True)
    shop_id = Column(String(64), nullable=True)
    
    # 目标值(A类:用户配置)
    target_amount = Column(Float, nullable=False, default=0.0, comment="目标销售额(CNY)")
    target_quantity = Column(Integer, nullable=False, default=0, comment="目标订单数/销量")
    
    # 达成值(C类:系统自动计算)
    actual_amount = Column(Float, nullable=False, default=0.0, comment="实际销售额(CNY)")
    actual_quantity = Column(Integer, nullable=False, default=0, comment="实际订单数/销量")
    achievement_rate = Column(Float, nullable=False, default=0.0, comment="达成率(百分比)")
    
    # 排名
    rank = Column(Integer, nullable=True, comment="排名")
    
    # 审计字段
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    __table_args__ = (
        UniqueConstraint("campaign_id", "platform_code", "shop_id", name="uq_campaign_shop"),
        ForeignKeyConstraint(
            ["platform_code", "shop_id"],
            ["core.dim_shops.platform_code", "core.dim_shops.shop_id"],
            name="fk_campaign_shop"
        ),
        Index("ix_campaign_shops_campaign", "campaign_id"),
        Index("ix_campaign_shops_shop", "platform_code", "shop_id"),
        {"schema": "a_class"},
    )

class SalesTarget(Base):
    """
    目标管理表(A类数据:用户配置)
    
    用途:存储绩效目标配置(店铺/产品/战役/运营级别)
    达成数据:从fact_orders表自动计算(C类数据)
    
    表结构以本模型为 SSOT:增删改列须在 migrations/versions 中新增迁移,
    本地 alembic upgrade head 验证后再发布;云端在部署时自动执行迁移。
    """
    __tablename__ = "sales_targets"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 目标基本信息
    target_name = Column(String(200), nullable=False, comment="目标名称")
    target_type = Column(String(32), nullable=False, comment="目标类型:shop/product/campaign/operation")
    period_start = Column(Date, nullable=False, comment="开始时间")
    period_end = Column(Date, nullable=False, comment="结束时间")
    
    # 目标值(A类:用户配置)
    target_amount = Column(Float, nullable=False, default=0.0, comment="目标销售额(CNY)")
    target_quantity = Column(Integer, nullable=False, default=0, comment="目标订单数/销量")
    target_profit_amount = Column(Float, nullable=False, default=0.0, comment="目标毛利(CNY)")
    product_id = Column(Integer, nullable=True, comment="产品ID")
    platform_sku = Column(String(128), nullable=True, comment="平台SKU")
    company_sku = Column(String(128), nullable=True, comment="公司SKU")
    
    # 达成值(C类:系统自动计算)
    achieved_amount = Column(Float, nullable=False, default=0.0, comment="实际销售额(CNY)")
    achieved_quantity = Column(Integer, nullable=False, default=0, comment="实际订单数/销量")
    achieved_profit_amount = Column(Float, nullable=False, default=0.0, comment="实际毛利(CNY)")
    achievement_rate = Column(Float, nullable=False, default=0.0, comment="达成率(百分比)")

    # 运营目标字段
    metric_code = Column(String(64), nullable=True, comment="运营指标编码")
    metric_name = Column(String(128), nullable=True, comment="运营指标名称")
    metric_direction = Column(String(32), nullable=True, comment="指标方向:higher_better/lower_better/manual_score")
    target_value = Column(Float, nullable=True, comment="运营指标目标值")
    achieved_value = Column(Float, nullable=True, comment="运营指标实际值")
    max_score = Column(Float, nullable=True, comment="指标满分")
    penalty_enabled = Column(Boolean, nullable=False, default=False, comment="是否启用罚分")
    penalty_threshold = Column(Float, nullable=True, comment="罚分阈值")
    penalty_per_unit = Column(Float, nullable=True, comment="每超出一单位罚分")
    penalty_max = Column(Float, nullable=True, comment="最大罚分")
    manual_score_enabled = Column(Boolean, nullable=False, default=False, comment="是否允许人工打分")
    manual_score_value = Column(Float, nullable=True, comment="人工打分值")
    
    # 状态
    status = Column(String(32), nullable=False, default="active", comment="状态:active/completed/cancelled")
    description = Column(Text, nullable=True, comment="目标描述")
    
    # 日度分解：周一到周日拆分比例（1=周一...7=周日，和为1），用于一键生成日度时按比例分配
    weekday_ratios = Column(JSON, nullable=True, comment="周一到周日拆分比例 {\"1\":0.14,...,\"7\":0.14} 和为1")
    
    # 审计字段
    created_by = Column(String(64), nullable=True, comment="创建人")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    __table_args__ = (
        CheckConstraint("period_end >= period_start", name="chk_target_dates"),
        CheckConstraint("target_amount >= 0", name="chk_target_amount"),
        CheckConstraint("target_quantity >= 0", name="chk_target_quantity"),
        CheckConstraint("target_profit_amount >= 0", name="chk_target_profit_amount"),
        Index("ix_sales_targets_type", "target_type"),
        Index("ix_sales_targets_status", "status"),
        Index("ix_sales_targets_period", "period_start", "period_end"),
        {"schema": "a_class"},
    )

class TargetBreakdown(Base):
    """
    目标分解表(A类数据:用户配置)
    
    用途:存储目标分解配置(按店铺/按时间)
    达成数据:从fact_orders表自动计算(C类数据)
    
    表结构以本模型为 SSOT:增删改列须在 migrations/versions 中新增迁移,
    本地 alembic upgrade head 验证后再发布;云端在部署时自动执行迁移。
    """
    __tablename__ = "target_breakdown"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 关联字段 (sales_targets 在 a_class schema)
    target_id = Column(Integer, ForeignKey("a_class.sales_targets.id", ondelete="CASCADE"), nullable=False)
    
    # 分解类型
    breakdown_type = Column(String(32), nullable=False, comment="分解类型:shop/time")
    
    # 店铺分解字段(breakdown_type='shop'时使用)
    platform_code = Column(String(32), nullable=True)
    shop_id = Column(String(64), nullable=True)
    
    # 时间分解字段(breakdown_type='time'时使用)
    period_start = Column(Date, nullable=True, comment="周期开始")
    period_end = Column(Date, nullable=True, comment="周期结束")
    period_label = Column(String(64), nullable=True, comment="周期标签,如'第1周'、'2025-01'")
    
    # 目标值(A类:用户配置)
    target_amount = Column(Float, nullable=False, default=0.0, comment="目标销售额(CNY)")
    target_quantity = Column(Integer, nullable=False, default=0, comment="目标订单数/销量")
    target_profit_amount = Column(Float, nullable=False, default=0.0, comment="目标毛利(CNY)")
    product_id = Column(Integer, nullable=True, comment="产品ID")
    platform_sku = Column(String(128), nullable=True, comment="平台SKU")
    company_sku = Column(String(128), nullable=True, comment="公司SKU")
    
    # 达成值(C类:系统自动计算)
    achieved_amount = Column(Float, nullable=False, default=0.0, comment="实际销售额(CNY)")
    achieved_quantity = Column(Integer, nullable=False, default=0, comment="实际订单数/销量")
    achieved_profit_amount = Column(Float, nullable=False, default=0.0, comment="实际毛利(CNY)")
    achievement_rate = Column(Float, nullable=False, default=0.0, comment="达成率(百分比)")

    # 运营目标/人工评分扩展字段
    target_value = Column(Float, nullable=True, comment="运营指标目标值")
    achieved_value = Column(Float, nullable=True, comment="运营指标实际值")
    manual_score_value = Column(Float, nullable=True, comment="人工打分值")
    
    # 审计字段
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    __table_args__ = (
        CheckConstraint("breakdown_type IN ('shop', 'time', 'shop_time')", name="chk_breakdown_type"),
        Index("ix_target_breakdown_target", "target_id"),
        Index("ix_target_breakdown_shop", "platform_code", "shop_id"),
        Index("ix_target_breakdown_period", "period_start", "period_end"),
        # A类数据表,放在 a_class schema 中
        {"schema": "a_class"},
    )

class ShopHealthScore(Base):
    """
    店铺健康度评分表(C类数据:系统自动计算)
    
    用途:存储店铺健康度评分和各项指标得分
    数据来源:基于fact_orders和fact_product_metrics计算得出
    """
    __tablename__ = "shop_health_scores"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 业务标识
    platform_code = Column(String(32), nullable=False)
    shop_id = Column(String(64), nullable=False)
    metric_date = Column(Date, nullable=False)
    granularity = Column(String(16), nullable=False, default="daily", comment="粒度:daily/weekly/monthly")
    
    # 健康度总分(0-100)
    health_score = Column(Float, nullable=False, default=0.0, comment="健康度总分(0-100)")
    
    # 各项得分(0-100)
    gmv_score = Column(Float, nullable=False, default=0.0, comment="GMV得分")
    conversion_score = Column(Float, nullable=False, default=0.0, comment="转化得分")
    inventory_score = Column(Float, nullable=False, default=0.0, comment="库存得分")
    service_score = Column(Float, nullable=False, default=0.0, comment="服务得分")
    
    # 基础指标(用于计算得分)
    gmv = Column(Float, nullable=False, default=0.0, comment="GMV(CNY)")
    conversion_rate = Column(Float, nullable=False, default=0.0, comment="转化率(百分比)")
    inventory_turnover = Column(Float, nullable=False, default=0.0, comment="库存周转率")
    customer_satisfaction = Column(Float, nullable=False, default=0.0, comment="客户满意度(0-5分)")
    
    # 风险等级
    risk_level = Column(String(16), nullable=False, default="low", comment="风险等级:low/medium/high")
    risk_factors = Column(JSON, nullable=True, comment="风险因素列表")
    
    # 审计字段
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    __table_args__ = (
        UniqueConstraint("platform_code", "shop_id", "metric_date", "granularity", name="uq_shop_health"),
        ForeignKeyConstraint(
            ["platform_code", "shop_id"],
            ["core.dim_shops.platform_code", "core.dim_shops.shop_id"],
            name="fk_shop_health"
        ),
        CheckConstraint("health_score >= 0 AND health_score <= 100", name="chk_health_score"),
        CheckConstraint("risk_level IN ('low', 'medium', 'high')", name="chk_risk_level"),
        Index("ix_shop_health_shop", "platform_code", "shop_id"),
        Index("ix_shop_health_date", "metric_date"),
        Index("ix_shop_health_score", "health_score"),
        Index("ix_shop_health_risk", "risk_level"),
        {"schema": "c_class"},
    )

class ShopAlert(Base):
    """
    店铺预警提醒表(C类数据:系统自动计算)
    
    用途:存储店铺运营预警信息
    数据来源:基于shop_health_scores和业务规则自动生成
    """
    __tablename__ = "shop_alerts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 业务标识
    platform_code = Column(String(32), nullable=False)
    shop_id = Column(String(64), nullable=False)
    
    # 预警信息
    alert_type = Column(String(64), nullable=False, comment="预警类型:inventory_turnover/conversion_rate/gmv_drop/...")
    alert_level = Column(String(16), nullable=False, comment="预警级别:critical/warning/info")
    title = Column(String(200), nullable=False, comment="预警标题")
    message = Column(Text, nullable=False, comment="预警内容")
    
    # 指标值
    metric_value = Column(Float, nullable=True, comment="当前指标值")
    threshold = Column(Float, nullable=True, comment="阈值")
    metric_unit = Column(String(32), nullable=True, comment="指标单位")
    
    # 处理状态
    is_resolved = Column(Boolean, nullable=False, default=False, comment="是否已解决")
    resolved_at = Column(DateTime(timezone=True), nullable=True, comment="解决时间")
    resolved_by = Column(String(64), nullable=True, comment="解决人")
    
    # 审计字段
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    __table_args__ = (
        ForeignKeyConstraint(
            ["platform_code", "shop_id"],
            ["core.dim_shops.platform_code", "core.dim_shops.shop_id"],
            name="fk_shop_alert"
        ),
        CheckConstraint("alert_level IN ('critical', 'warning', 'info')", name="chk_alert_level"),
        Index("ix_shop_alerts_shop", "platform_code", "shop_id"),
        Index("ix_shop_alerts_level", "alert_level"),
        Index("ix_shop_alerts_resolved", "is_resolved"),
        Index("ix_shop_alerts_created", "created_at"),
        {"schema": "c_class"},
    )

class PerformanceScore(Base):
    """
    绩效评分表(C类数据:系统自动计算)
    
    用途:存储店铺绩效评分和明细
    数据来源:基于fact_orders、fact_product_metrics和sales_targets计算得出
    """
    __tablename__ = "performance_scores"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 业务标识
    platform_code = Column(String(32), nullable=False)
    shop_id = Column(String(64), nullable=False)
    period = Column(String(16), nullable=False, comment="考核周期,如'2025-01'")
    
    # 总分(0-100)
    total_score = Column(Float, nullable=False, default=0.0, comment="总分(0-100)")
    
    # 各项得分(权重 × 达成率)
    sales_score = Column(Float, nullable=False, default=0.0, comment="销售额得分(权重30%)")
    profit_score = Column(Float, nullable=False, default=0.0, comment="毛利得分(权重25%)")
    key_product_score = Column(Float, nullable=False, default=0.0, comment="重点产品得分(权重25%)")
    operation_score = Column(Float, nullable=False, default=0.0, comment="运营得分(权重20%)")
    
    # 得分明细(JSONB存储详细计算过程)
    score_details = Column(JSON, nullable=True, comment="得分明细(JSON格式)")
    
    # 排名和系数
    rank = Column(Integer, nullable=True, comment="排名")
    performance_coefficient = Column(Float, nullable=False, default=1.0, comment="绩效系数")
    
    # 审计字段
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    __table_args__ = (
        UniqueConstraint("platform_code", "shop_id", "period", name="uq_performance_shop_period"),
        ForeignKeyConstraint(
            ["platform_code", "shop_id"],
            ["core.dim_shops.platform_code", "core.dim_shops.shop_id"],
            name="fk_performance_shop"
        ),
        CheckConstraint("total_score >= 0 AND total_score <= 100", name="chk_total_score"),
        Index("ix_performance_shop", "platform_code", "shop_id"),
        Index("ix_performance_period", "period"),
        Index("ix_performance_score", "total_score"),
        Index("ix_performance_rank", "rank"),
        {"schema": "c_class"},
    )

class PerformanceConfig(Base):
    """
    绩效权重配置表(A类数据:用户配置)
    
    用途:存储绩效计算规则和权重配置
    """
    __tablename__ = "performance_config"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 配置信息
    config_name = Column(String(64), nullable=False, default="default", comment="配置名称")
    
    # 权重配置(百分比,总和必须为100)
    sales_weight = Column(Integer, nullable=False, default=30, comment="销售额权重(%)")
    profit_weight = Column(Integer, nullable=False, default=25, comment="毛利权重(%)")
    key_product_weight = Column(Integer, nullable=False, default=25, comment="重点产品权重(%)")
    operation_weight = Column(Integer, nullable=False, default=20, comment="运营权重(%)")
    # 得分比例配置(达成率>100%得满分,<=100%得达成率*满分)
    sales_max_score = Column(Integer, nullable=False, default=30, comment="销售额满分")
    profit_max_score = Column(Integer, nullable=False, default=25, comment="毛利满分")
    key_product_max_score = Column(Integer, nullable=False, default=25, comment="重点产品满分")
    operation_max_score = Column(Integer, nullable=False, default=20, comment="运营满分")
    
    # 生效时间
    is_active = Column(Boolean, nullable=False, default=True, comment="是否启用")
    effective_from = Column(Date, nullable=False, comment="生效开始日期")
    effective_to = Column(Date, nullable=True, comment="生效结束日期(NULL表示永久有效)")
    
    # 审计字段
    created_by = Column(String(64), nullable=True, comment="创建人")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    __table_args__ = (
        CheckConstraint(
            "sales_weight + profit_weight + key_product_weight + operation_weight = 100",
            name="chk_weights_sum"
        ),
        CheckConstraint(
            "sales_weight >= 0 AND sales_weight <= 100 AND "
            "profit_weight >= 0 AND profit_weight <= 100 AND "
            "key_product_weight >= 0 AND key_product_weight <= 100 AND "
            "operation_weight >= 0 AND operation_weight <= 100",
            name="chk_weights_range"
        ),
        Index("ix_performance_config_active", "is_active", "effective_from"),
        {"schema": "a_class"},
    )

class ClearanceRanking(Base):
    """
    滞销清理排名表(C类数据:系统自动计算)
    
    用途:存储店铺滞销清理排名数据
    数据来源:基于fact_product_metrics和fact_orders计算得出
    """
    __tablename__ = "clearance_rankings"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 业务标识
    platform_code = Column(String(32), nullable=False)
    shop_id = Column(String(64), nullable=False)
    metric_date = Column(Date, nullable=False)
    granularity = Column(String(16), nullable=False, comment="粒度:monthly/weekly")
    
    # 清理数据
    clearance_amount = Column(Float, nullable=False, default=0.0, comment="清理金额(CNY)")
    clearance_quantity = Column(Integer, nullable=False, default=0, comment="清理数量")
    
    # 激励金额
    incentive_amount = Column(Float, nullable=False, default=0.0, comment="激励金额(CNY)")
    total_incentive = Column(Float, nullable=False, default=0.0, comment="总计激励(CNY)")
    
    # 排名
    rank = Column(Integer, nullable=True, comment="排名")
    
    # 审计字段
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    __table_args__ = (
        UniqueConstraint("platform_code", "shop_id", "metric_date", "granularity", name="uq_clearance_ranking"),
        ForeignKeyConstraint(
            ["platform_code", "shop_id"],
            ["core.dim_shops.platform_code", "core.dim_shops.shop_id"],
            name="fk_clearance_ranking"
        ),
        Index("ix_clearance_ranking_date", "metric_date", "granularity"),
        Index("ix_clearance_ranking_rank", "rank"),
        Index("ix_clearance_ranking_amount", "clearance_amount"),
        {"schema": "c_class"},
    )


# -------------------- Materialized View Management --------------------

class MaterializedViewRefreshLog(Base):
    """物化视图刷新日志表
    
    v4.11.4新增:
    - 记录每次物化视图刷新的详细信息
    - 用于监控刷新性能和审计追踪
    - 与MaterializedViewService中的使用保持一致
    """
    __tablename__ = "mv_refresh_log"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    view_name = Column(String(128), nullable=False, index=True, comment="物化视图名称")
    refresh_started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, comment="刷新开始时间")
    refresh_completed_at = Column(DateTime(timezone=True), nullable=True, comment="刷新完成时间")
    duration_seconds = Column(Float, nullable=True, comment="刷新耗时(秒)")
    row_count = Column(Integer, nullable=True, comment="刷新后行数")
    status = Column(String(20), default="running", nullable=False, comment="状态:running/success/failed")
    error_message = Column(Text, nullable=True, comment="错误信息(如果失败)")
    triggered_by = Column(String(64), default="scheduler", nullable=False, comment="触发方式:scheduler/manual/api")
    
    __table_args__ = (
        CheckConstraint("status IN ('running', 'success', 'failed')", name="chk_mv_refresh_status"),
        Index("ix_mv_refresh_log_view", "view_name", "refresh_started_at"),
        Index("ix_mv_refresh_log_status", "status", "refresh_started_at"),
    )


# -------------------- User and Permission Tables (v4.12.0 SSOT Migration) --------------------

# 用户-角色关联表(多对多)
user_roles = Table(
    'user_roles',
    Base.metadata,
    Column('user_id', BigInteger, ForeignKey('core.dim_users.user_id'), primary_key=True),
    Column('role_id', BigInteger, ForeignKey('core.dim_roles.role_id'), primary_key=True),
    Column('assigned_at', DateTime(timezone=True), server_default=func.now()),
    Column('assigned_by', String(100))
)

class DimUser(Base):
    """
    用户表
    
    v4.12.0迁移:从backend/models/users.py迁移到schema.py(SSOT合规性)
    """
    __tablename__ = "dim_users"
    
    user_id = Column(BigInteger, primary_key=True, index=True)
    
    # 用户信息
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(200))
    password_hash = Column(String(255), nullable=False)  # 存储hash后的密码
    
    # 状态
    is_active = Column(Boolean, default=True, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)
    status = Column(
        String(20),
        default="pending",
        nullable=False,
        index=True,
        comment="用户状态: pending/active/rejected/suspended/deleted"
    )
    
    # 审批信息
    approved_at = Column(DateTime(timezone=True), nullable=True, comment="审批时间")
    approved_by = Column(
        BigInteger,
        ForeignKey('core.dim_users.user_id'),
        nullable=True,
        comment="审批人ID"
    )
    rejection_reason = Column(Text, nullable=True, comment="拒绝原因")
    
    # 数据权限(可见的平台和店铺)
    allowed_platforms = Column(Text)  # JSON数组,如:["shopee", "tiktok"]
    allowed_shops = Column(Text)  # JSON数组,如:["shop1", "shop2"]
    
    # 联系信息
    phone = Column(String(50))
    department = Column(String(100))
    position = Column(String(100))
    
    # 登录信息
    last_login = Column(DateTime(timezone=True))
    login_count = Column(Integer, default=0)
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime(timezone=True), nullable=True, comment="账户锁定到期时间")
    
    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        Index("idx_users_active", "is_active"),
        Index("idx_users_email_active", "email", "is_active"),
        {"schema": "core"},
    )
    
    # 关系
    roles = relationship(
        "DimRole",
        secondary=user_roles,
        back_populates="users"
    )
    audit_logs = relationship(
        "FactAuditLog",
        back_populates="user",
        cascade="all, delete-orphan"
    )

class DimRole(Base):
    """
    角色表
    
    v4.12.0迁移:从backend/models/users.py迁移到schema.py(SSOT合规性)
    """
    __tablename__ = "dim_roles"
    
    role_id = Column(BigInteger, primary_key=True, index=True)
    
    # 角色信息
    role_name = Column(String(100), unique=True, nullable=False, index=True)
    role_code = Column(String(50), unique=True, nullable=False)  # 角色代码,如:admin, finance, warehouse
    description = Column(Text)
    
    # 权限(JSON格式)
    permissions = Column(Text, nullable=False)  # JSON数组,如:["view_sales", "edit_inventory"]
    
    # 数据权限范围
    data_scope = Column(String(50), default='all')  # all/platform/shop/self
    
    # 状态
    is_active = Column(Boolean, default=True, nullable=False)
    is_system = Column(Boolean, default=False)  # 是否系统角色(不可删除)
    
    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        Index("idx_roles_active", "is_active"),
        {"schema": "core"},
    )
    
    # 关系
    users = relationship(
        "DimUser",
        secondary=user_roles,
        back_populates="roles"
    )

class UserSession(Base):
    """
    用户会话表(用于会话管理)
    
    v4.19.0新增:会话管理功能
    用于跟踪和管理用户的活跃会话,支持强制登出其他设备
    """
    __tablename__ = "user_sessions"
    
    session_id = Column(String(64), primary_key=True, index=True, comment="会话ID(Token的哈希值)")
    user_id = Column(
        BigInteger,
        ForeignKey('core.dim_users.user_id'),
        nullable=False,
        index=True
    )
    
    # 会话信息
    device_info = Column(String(255), nullable=True, comment="设备信息(User-Agent)")
    ip_address = Column(String(45), nullable=True, comment="IP地址")
    location = Column(String(100), nullable=True, comment="登录位置(可选)")
    
    # 时间戳
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="创建时间(登录时间)"
    )
    expires_at = Column(
        DateTime(timezone=True),
        nullable=False,
        comment="过期时间"
    )
    last_active_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="最后活跃时间"
    )
    
    # 状态
    is_active = Column(Boolean, default=True, nullable=False, comment="是否有效")
    revoked_at = Column(DateTime(timezone=True), nullable=True, comment="撤销时间")
    revoked_reason = Column(String(100), nullable=True, comment="撤销原因")
    
    __table_args__ = (
        Index("idx_session_user_active", "user_id", "is_active"),
        Index("idx_session_expires", "expires_at"),
    )
    
    # 关系
    user = relationship("DimUser", backref="sessions")

class UserApprovalLog(Base):
    """
    用户审批记录表(用于审计)
    
    v4.19.0新增:用户注册和审批流程
    用于记录所有用户审批操作,支持审计追踪
    """
    __tablename__ = "user_approval_logs"
    
    log_id = Column(BigInteger, primary_key=True, index=True)
    
    # 用户信息
    user_id = Column(
        BigInteger,
        ForeignKey('core.dim_users.user_id'),
        nullable=False,
        index=True
    )
    
    # 审批信息
    action = Column(
        String(20),
        nullable=False,
        index=True,
        comment="操作类型: approve/reject/suspend"
    )
    approved_by = Column(
        BigInteger,
        ForeignKey('core.dim_users.user_id'),
        nullable=False,
        comment="操作人ID"
    )
    reason = Column(
        Text,
        nullable=True,
        comment="操作原因/备注"
    )
    
    # 时间戳
    created_at = Column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        index=True
    )
    
    __table_args__ = (
        Index("idx_approval_user_time", "user_id", "created_at"),
        Index("idx_approval_action_time", "action", "created_at"),
    )

class FactAuditLog(Base):
    """
    操作审计日志表
    
    v4.12.0迁移:从backend/models/users.py迁移到schema.py(SSOT合规性)
    
    用于记录所有用户操作,支持企业级ERP的审计追溯要求。
    """
    __tablename__ = "fact_audit_logs"
    
    log_id = Column(BigInteger, primary_key=True, index=True)
    
    # 用户信息
    user_id = Column(BigInteger, ForeignKey("core.dim_users.user_id"), nullable=False)
    username = Column(String(100), nullable=False)  # 冗余字段,便于查询
    
    # 操作信息
    action_type = Column(String(50), nullable=False, index=True)  # create/update/delete/view/export
    resource_type = Column(String(100), nullable=False)  # order/product/inventory/finance
    resource_id = Column(String(150))  # 资源ID
    
    # 详细信息
    action_description = Column(Text)  # 操作描述
    changes_json = Column(Text)  # JSON格式的变更详情(before/after)
    
    # IP和设备信息
    ip_address = Column(String(50))
    user_agent = Column(String(500))
    
    # 结果
    is_success = Column(Boolean, default=True)
    error_message = Column(Text)
    
    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    
    __table_args__ = (
        Index("idx_audit_user_time", "user_id", "created_at"),
        Index("idx_audit_action_time", "action_type", "created_at"),
        Index("idx_audit_resource", "resource_type", "resource_id"),
        Index(
            "idx_audit_recent",
            "created_at",
            postgresql_using='btree',
            postgresql_ops={'created_at': 'DESC'}
        ),
    )
    
    # 关系
    user = relationship("DimUser", back_populates="audit_logs")

class SalesTargetA(Base):
    """
    A类数据表:销售目标(中文字段名)
    
    注意:字段名在Alembic迁移脚本中将使用中文(如"店铺ID", "年月"等)
    注意:此表将替代旧的SalesTarget表(v4.11.0),使用中文字段名
    """
    __tablename__ = "sales_targets_a"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    shop_id = Column(String(256), nullable=False)  # 迁移时将重命名为"店铺ID"
    year_month = Column(String(7), nullable=False)  # 迁移时将重命名为"年月",格式:'2025-01'
    target_sales_amount = Column(Numeric(15, 2), nullable=False)  # 迁移时将重命名为"目标销售额"
    target_quantity = Column(Integer, nullable=False)  # 迁移时将重命名为"目标订单数"
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)  # 迁移时将重命名为"创建时间"
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)  # 迁移时将重命名为"更新时间"
    
    __table_args__ = (
        UniqueConstraint("shop_id", "year_month", name="uq_sales_targets_a_shop_month"),
        Index("ix_sales_targets_a_shop", "shop_id"),
        Index("ix_sales_targets_a_month", "year_month"),
        {"schema": "a_class"},
    )

class SalesCampaignA(Base):
    """
    A类数据表:销售战役(中文字段名)
    
    注意:此表将替代旧的SalesCampaign表(v4.11.0),使用中文字段名
    """
    __tablename__ = "sales_campaigns_a"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    campaign_name = Column(String(200), nullable=False)  # 迁移时将重命名为"战役名称"
    campaign_type = Column(String(32), nullable=False)  # 迁移时将重命名为"战役类型"
    start_date = Column(Date, nullable=False)  # 迁移时将重命名为"开始日期"
    end_date = Column(Date, nullable=False)  # 迁移时将重命名为"结束日期"
    target_amount = Column(Numeric(15, 2), nullable=False, default=0.0)  # 迁移时将重命名为"目标销售额"
    target_quantity = Column(Integer, nullable=False, default=0)  # 迁移时将重命名为"目标订单数"
    status = Column(String(32), nullable=False, default="pending")  # 迁移时将重命名为"状态"
    description = Column(Text, nullable=True)  # 迁移时将重命名为"描述"
    created_by = Column(String(64), nullable=True)  # 迁移时将重命名为"创建人"
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="chk_sales_campaigns_a_dates"),
        Index("ix_sales_campaigns_a_type", "campaign_type"),
        Index("ix_sales_campaigns_a_status", "status"),
        {"schema": "a_class"},
    )

class OperatingCost(Base):
    """
    A类数据表:运营成本
    
    注意:数据库表使用中文字段名,ORM 通过 name 参数映射
    表结构(a_class.operating_costs):
    - id: bigint (PK)
    - 店铺ID: character varying(256)
    - platform_code: character varying(32)
    - 年月: character varying(7)
    - 租金: numeric(15,2)
    - 营销费用: numeric(15,2)
    - 水电费: numeric(15,2)
    - AI Token费用: numeric(15,2)
    - 其他成本: numeric(15,2)
    - 成本合计: numeric(15,2)
    - 备注: text
    - 附件: jsonb
    - 是否锁定: boolean
    - 创建时间: timestamp
    - 更新时间: timestamp
    """
    __tablename__ = "operating_costs"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    # 使用 name 参数映射到数据库中的中文列名
    shop_id = Column("店铺ID", String(256), nullable=False)
    platform_code = Column(String(32), nullable=True)
    year_month = Column("年月", String(7), nullable=False)
    rent = Column("租金", Numeric(15, 2), nullable=False, default=0.0)
    marketing_fee = Column("营销费用", Numeric(15, 2), nullable=False, default=0.0)
    utilities = Column("水电费", Numeric(15, 2), nullable=False, default=0.0)
    ai_token_cost = Column("AI Token费用", Numeric(15, 2), nullable=False, default=0.0)
    other_costs = Column("其他成本", Numeric(15, 2), nullable=False, default=0.0)
    total_cost = Column("成本合计", Numeric(15, 2), nullable=False, default=0.0)
    note = Column("备注", Text, nullable=True)
    attachments = Column("附件", JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    locked = Column("是否锁定", Boolean, nullable=False, server_default=text("false"))
    deleted_at = Column("删除时间", DateTime(timezone=True), nullable=True)
    deleted_by = Column("删除人", BigInteger, nullable=True)
    created_at = Column("创建时间", DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column("更新时间", DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    __table_args__ = (
        UniqueConstraint("platform_code", "店铺ID", "年月", name="uq_operating_costs_a_platform_shop_month"),
        Index("ix_operating_costs_a_shop", "店铺ID"),
        Index("ix_operating_costs_a_platform_shop", "platform_code", "店铺ID"),
        Index("ix_operating_costs_a_month", "年月"),
        Index("ix_operating_costs_locked", "是否锁定"),
        Index("ix_operating_costs_deleted_at", "删除时间"),
        {"schema": "a_class"},
    )


# ============================================================================
# A类数据表:HR人力资源模块(业界标准设计)
# ============================================================================

class Department(Base):
    """
    A类数据表:部门表(树形结构)
    
    支持多级部门架构，通过 parent_id 实现层级关系
    """
    __tablename__ = "departments"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    department_code = Column(String(64), nullable=False, unique=True)  # 部门编码
    department_name = Column(String(128), nullable=False)  # 部门名称
    parent_id = Column(BigInteger, nullable=True)  # 上级部门ID(NULL表示顶级部门)
    level = Column(Integer, nullable=False, default=1)  # 部门层级(1=顶级)
    sort_order = Column(Integer, nullable=False, default=0)  # 排序序号
    manager_id = Column(BigInteger, nullable=True)  # 部门负责人ID
    description = Column(Text, nullable=True)  # 部门描述
    status = Column(String(32), nullable=False, default="active")  # 状态:active/inactive
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_departments_a_code", "department_code"),
        Index("ix_departments_a_parent", "parent_id"),
        Index("ix_departments_a_status", "status"),
        {"schema": "a_class"},
    )

class Position(Base):
    """
    A类数据表:职位表(职级体系)
    
    定义公司职位/职级体系，支持职级薪资范围配置
    """
    __tablename__ = "positions"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    position_code = Column(String(64), nullable=False, unique=True)  # 职位编码
    position_name = Column(String(128), nullable=False)  # 职位名称
    position_level = Column(Integer, nullable=False, default=1)  # 职级(1-10)
    department_id = Column(BigInteger, nullable=True)  # 所属部门ID(可选)
    min_salary = Column(Numeric(15, 2), nullable=True)  # 薪资下限
    max_salary = Column(Numeric(15, 2), nullable=True)  # 薪资上限
    description = Column(Text, nullable=True)  # 职位描述/职责
    requirements = Column(Text, nullable=True)  # 任职要求
    status = Column(String(32), nullable=False, default="active")  # 状态:active/inactive
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_positions_a_code", "position_code"),
        Index("ix_positions_a_level", "position_level"),
        Index("ix_positions_a_department", "department_id"),
        {"schema": "a_class"},
    )

class Employee(Base):
    """
    A类数据表:员工档案(业界标准设计)
    
    包含员工基本信息、联系方式、合同信息、银行账户等完整字段
    """
    __tablename__ = "employees"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    
    # === 基本信息 ===
    employee_code = Column(String(64), nullable=False, unique=True)  # 员工编号
    name = Column(String(128), nullable=False)  # 姓名
    gender = Column(String(16), nullable=True)  # 性别:male/female/other
    birth_date = Column(Date, nullable=True)  # 出生日期
    id_type = Column(String(32), nullable=True, default="id_card")  # 证件类型:id_card/passport/other
    id_number = Column(String(64), nullable=True)  # 证件号码
    avatar_url = Column(String(512), nullable=True)  # 头像URL
    
    # === 联系方式 ===
    phone = Column(String(32), nullable=True)  # 手机号码
    email = Column(String(128), nullable=True)  # 邮箱
    address = Column(String(512), nullable=True)  # 现居地址
    emergency_contact = Column(String(128), nullable=True)  # 紧急联系人
    emergency_phone = Column(String(32), nullable=True)  # 紧急联系人电话
    
    # === 组织架构 ===
    department_id = Column(BigInteger, nullable=True)  # 所属部门ID(关联departments表)
    position_id = Column(BigInteger, nullable=True)  # 职位ID(关联positions表)
    manager_id = Column(BigInteger, nullable=True)  # 直属上级ID(关联employees表)
    
    # === 入职信息 ===
    hire_date = Column(Date, nullable=True)  # 入职日期
    probation_end_date = Column(Date, nullable=True)  # 试用期结束日期
    regularization_date = Column(Date, nullable=True)  # 转正日期
    leave_date = Column(Date, nullable=True)  # 离职日期
    
    # === 合同信息 ===
    contract_type = Column(String(32), nullable=True)  # 合同类型:fixed_term/indefinite/internship/part_time
    contract_start_date = Column(Date, nullable=True)  # 合同开始日期
    contract_end_date = Column(Date, nullable=True)  # 合同结束日期
    
    # === 薪资账户 ===
    bank_name = Column(String(128), nullable=True)  # 开户银行
    bank_account = Column(String(64), nullable=True)  # 银行账号
    
    # === 状态 ===
    status = Column(String(32), nullable=False, default="active")  # 状态:active/inactive/probation/leave
    employee_identity_type = Column(
        String(32),
        nullable=False,
        default="employee",
        server_default=text("'employee'"),
    )
    
    # === 用户关联（add-link-user-employee-management）===
    user_id = Column(BigInteger, nullable=True)  # 关联 dim_users.user_id，应用层唯一性校验
    
    # === 元数据 ===
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_employees_a_code", "employee_code"),
        Index("ix_employees_a_department", "department_id"),
        Index("ix_employees_a_position", "position_id"),
        Index("ix_employees_a_manager", "manager_id"),
        Index("ix_employees_a_status", "status"),
        Index("ix_employees_a_hire_date", "hire_date"),
        {"schema": "a_class"},
    )

class EmployeeTarget(Base):
    """A类数据表:员工目标(中文字段名)"""
    __tablename__ = "employee_targets"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    employee_code = Column(String(64), nullable=False)  # 迁移时将重命名为"员工编号"
    year_month = Column(String(7), nullable=False)  # 迁移时将重命名为"年月"
    target_type = Column(String(32), nullable=False)  # 迁移时将重命名为"目标类型"
    target_value = Column(Numeric(15, 2), nullable=False)  # 迁移时将重命名为"目标值"
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    __table_args__ = (
        UniqueConstraint("employee_code", "year_month", "target_type", name="uq_employee_targets_a"),
        Index("ix_employee_targets_a_employee", "employee_code"),
        Index("ix_employee_targets_a_month", "year_month"),
        {"schema": "a_class"},
    )

class EmployeeShopAssignment(Base):
    """
    A类数据表:员工店铺归属与提成比
    
    配置员工负责的店铺及该店铺对应的提成比例，供提成计算使用。
    按月份配置：year_month 表示该条配置适用的月份(YYYY-MM)，每月可不同比例。
    add-employee-shop-assignment-page 提案
    """
    __tablename__ = "employee_shop_assignments"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    year_month = Column(String(7), nullable=False)  # 适用月份 YYYY-MM
    employee_code = Column(String(64), nullable=False)  # 员工编号，逻辑引用 a_class.employees
    platform_code = Column(String(32), nullable=False)  # 平台编码
    shop_id = Column(String(256), nullable=False)  # 店铺ID
    
    commission_ratio = Column(Float, nullable=True)  # 提成比例(0-1)，NULL时使用薪资结构默认
    role = Column(String(32), nullable=True)  # 角色：supervisor/operator
    effective_from = Column(Date, nullable=True)  # 保留，可选
    effective_to = Column(Date, nullable=True)  # 保留，可选
    status = Column(String(32), nullable=False, default="active")  # active/inactive
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    __table_args__ = (
        UniqueConstraint("employee_code", "platform_code", "shop_id", "year_month", name="uq_employee_shop_assignments_a"),
        ForeignKeyConstraint(
            ["platform_code", "shop_id"],
            ["core.dim_shops.platform_code", "core.dim_shops.shop_id"],
            ondelete="RESTRICT",
            name="fk_employee_shop_assignments_shop_a",
        ),
        Index("ix_employee_shop_assignments_a_employee", "employee_code"),
        Index("ix_employee_shop_assignments_a_shop", "platform_code", "shop_id"),
        Index("ix_employee_shop_assignments_a_year_month", "year_month"),
        Index("ix_employee_shop_assignments_a_status", "status"),
        {"schema": "a_class"},
    )

class ShopCommissionConfig(Base):
    """
    A类数据表:店铺可分配利润率配置（按月）

    店铺利润的百分之多少用于主管+操作员分配。按 year_month 月度更新，与 employee_shop_assignments 一致。
    add-employee-shop-assignment-page Phase 2, 方案B 按月维度
    """
    __tablename__ = "shop_commission_config"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    year_month = Column(String(7), nullable=False)  # YYYY-MM，与 employee_shop_assignments 一致
    platform_code = Column(String(32), nullable=False)
    shop_id = Column(String(256), nullable=False)
    allocatable_profit_rate = Column(Float, nullable=False, default=0)  # 0-1，如 0.8 表示 80%

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("year_month", "platform_code", "shop_id", name="uq_shop_commission_config_a"),
        ForeignKeyConstraint(
            ["platform_code", "shop_id"],
            ["core.dim_shops.platform_code", "core.dim_shops.shop_id"],
            ondelete="RESTRICT",
            name="fk_shop_commission_config_shop_a",
        ),
        Index("ix_shop_commission_config_a_shop_month", "year_month", "platform_code", "shop_id"),
        {"schema": "a_class"},
    )

class EmployeePerformanceAdjustment(Base):
    """
    A类数据表: 员工绩效调整项(月度)

    用于承接考试、培训检核、人工奖惩等个人绩效加减分。
    """

    __tablename__ = "employee_performance_adjustments"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    employee_code = Column(String(64), nullable=False)
    year_month = Column(String(7), nullable=False)
    adjustment_type = Column(String(32), nullable=False)
    score_delta = Column(Float, nullable=False, default=0.0)
    source = Column(String(64), nullable=True)
    reason = Column(String(512), nullable=True)
    status = Column(String(32), nullable=False, default="active")
    created_by = Column(String(64), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_employee_performance_adjustments_employee", "employee_code"),
        Index("ix_employee_performance_adjustments_month", "year_month"),
        Index("ix_employee_performance_adjustments_status", "status"),
        {"schema": "a_class"},
    )

class WorkShift(Base):
    """
    A类数据表:排班班次配置
    
    定义不同的工作班次（如早班、晚班、弹性工时等）
    """
    __tablename__ = "work_shifts"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    shift_code = Column(String(64), nullable=False, unique=True)  # 班次编码
    shift_name = Column(String(128), nullable=False)  # 班次名称(如:早班/晚班/弹性)
    start_time = Column(String(8), nullable=False)  # 上班时间(HH:MM格式)
    end_time = Column(String(8), nullable=False)  # 下班时间(HH:MM格式)
    work_hours = Column(Float, nullable=False, default=8.0)  # 标准工作时长
    break_hours = Column(Float, nullable=False, default=1.0)  # 休息时长
    late_tolerance = Column(Integer, nullable=False, default=15)  # 迟到容忍时间(分钟)
    early_leave_tolerance = Column(Integer, nullable=False, default=15)  # 早退容忍时间(分钟)
    is_flexible = Column(Boolean, nullable=False, default=False)  # 是否弹性工时
    status = Column(String(32), nullable=False, default="active")  # 状态:active/inactive
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_work_shifts_a_code", "shift_code"),
        Index("ix_work_shifts_a_status", "status"),
        {"schema": "a_class"},
    )

class AttendanceRecord(Base):
    """
    A类数据表:考勤记录(业界标准设计)
    
    支持排班、外勤打卡、加班记录等完整考勤功能
    """
    __tablename__ = "attendance_records"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    employee_code = Column(String(64), nullable=False)  # 员工编号
    attendance_date = Column(Date, nullable=False)  # 考勤日期
    
    # === 打卡信息 ===
    clock_in_time = Column(DateTime(timezone=True), nullable=True)  # 上班打卡时间
    clock_out_time = Column(DateTime(timezone=True), nullable=True)  # 下班打卡时间
    clock_in_location = Column(String(256), nullable=True)  # 上班打卡位置
    clock_out_location = Column(String(256), nullable=True)  # 下班打卡位置
    clock_in_type = Column(String(32), nullable=True, default="normal")  # 打卡类型:normal/field/supplement
    clock_out_type = Column(String(32), nullable=True, default="normal")  # 打卡类型:normal/field/supplement
    
    # === 工时信息 ===
    shift_id = Column(BigInteger, nullable=True)  # 排班班次ID
    work_hours = Column(Float, nullable=True)  # 实际工作时长
    overtime_hours = Column(Float, nullable=True, default=0.0)  # 加班时长
    
    # === 状态 ===
    status = Column(String(32), nullable=False, default="normal")  # 状态:normal/late/early_leave/absent/leave
    remark = Column(String(512), nullable=True)  # 备注
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    __table_args__ = (
        UniqueConstraint("employee_code", "attendance_date", name="uq_attendance_records_a"),
        Index("ix_attendance_records_a_employee", "employee_code"),
        Index("ix_attendance_records_a_date", "attendance_date"),
        Index("ix_attendance_records_a_status", "status"),
        {"schema": "a_class"},
    )

class LeaveType(Base):
    """
    A类数据表:假期类型配置
    
    定义公司支持的假期类型（年假、病假、事假等）
    """
    __tablename__ = "leave_types"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    leave_code = Column(String(64), nullable=False, unique=True)  # 假期编码
    leave_name = Column(String(128), nullable=False)  # 假期名称
    is_paid = Column(Boolean, nullable=False, default=True)  # 是否带薪
    max_days_per_year = Column(Float, nullable=True)  # 年度最大天数(NULL表示无限制)
    requires_approval = Column(Boolean, nullable=False, default=True)  # 是否需要审批
    description = Column(Text, nullable=True)  # 假期说明
    status = Column(String(32), nullable=False, default="active")  # 状态:active/inactive
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_leave_types_a_code", "leave_code"),
        Index("ix_leave_types_a_status", "status"),
        {"schema": "a_class"},
    )

class LeaveRecord(Base):
    """
    A类数据表:请假记录
    
    记录员工请假申请和审批信息
    """
    __tablename__ = "leave_records"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    employee_code = Column(String(64), nullable=False)  # 员工编号
    leave_type_id = Column(BigInteger, nullable=False)  # 假期类型ID
    start_date = Column(Date, nullable=False)  # 开始日期
    end_date = Column(Date, nullable=False)  # 结束日期
    days = Column(Float, nullable=False)  # 请假天数
    reason = Column(Text, nullable=True)  # 请假原因
    
    # === 审批信息 ===
    approver_id = Column(BigInteger, nullable=True)  # 审批人ID
    approval_status = Column(String(32), nullable=False, default="pending")  # 审批状态:pending/approved/rejected
    approval_time = Column(DateTime(timezone=True), nullable=True)  # 审批时间
    approval_remark = Column(String(512), nullable=True)  # 审批备注
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_leave_records_a_employee", "employee_code"),
        Index("ix_leave_records_a_date", "start_date", "end_date"),
        Index("ix_leave_records_a_status", "approval_status"),
        {"schema": "a_class"},
    )

class OvertimeRecord(Base):
    """
    A类数据表:加班记录
    
    记录员工加班申请和审批信息
    """
    __tablename__ = "overtime_records"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    employee_code = Column(String(64), nullable=False)  # 员工编号
    overtime_date = Column(Date, nullable=False)  # 加班日期
    start_time = Column(DateTime(timezone=True), nullable=False)  # 开始时间
    end_time = Column(DateTime(timezone=True), nullable=False)  # 结束时间
    hours = Column(Float, nullable=False)  # 加班时长
    overtime_type = Column(String(32), nullable=False, default="workday")  # 类型:workday/weekend/holiday
    reason = Column(Text, nullable=True)  # 加班原因
    
    # === 审批信息 ===
    approver_id = Column(BigInteger, nullable=True)  # 审批人ID
    approval_status = Column(String(32), nullable=False, default="pending")  # 审批状态:pending/approved/rejected
    approval_time = Column(DateTime(timezone=True), nullable=True)  # 审批时间
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_overtime_records_a_employee", "employee_code"),
        Index("ix_overtime_records_a_date", "overtime_date"),
        Index("ix_overtime_records_a_status", "approval_status"),
        {"schema": "a_class"},
    )


# ============================================================================
# A类数据表:薪酬管理模块
# ============================================================================

class SalaryStructure(Base):
    """
    A类数据表:薪资结构配置
    
    定义员工薪资组成结构（基本工资、绩效工资、津贴等）
    """
    __tablename__ = "salary_structures"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    employee_code = Column(String(64), nullable=False, unique=True)  # 员工编号
    
    # === 固定薪资 ===
    base_salary = Column(Numeric(15, 2), nullable=False, default=0.0)  # 基本工资
    position_salary = Column(Numeric(15, 2), nullable=False, default=0.0)  # 岗位工资
    
    # === 津贴 ===
    housing_allowance = Column(Numeric(15, 2), nullable=False, default=0.0)  # 住房补贴
    transport_allowance = Column(Numeric(15, 2), nullable=False, default=0.0)  # 交通补贴
    meal_allowance = Column(Numeric(15, 2), nullable=False, default=0.0)  # 餐饮补贴
    communication_allowance = Column(Numeric(15, 2), nullable=False, default=0.0)  # 通讯补贴
    other_allowance = Column(Numeric(15, 2), nullable=False, default=0.0)  # 其他补贴
    
    # === 绩效相关 ===
    performance_ratio = Column(Float, nullable=False, default=0.0)  # 绩效工资比例(0-1)
    commission_ratio = Column(Float, nullable=False, default=0.0)  # 提成比例(0-1)
    
    # === 社保公积金 ===
    social_insurance_base = Column(Numeric(15, 2), nullable=True)  # 社保基数
    housing_fund_base = Column(Numeric(15, 2), nullable=True)  # 公积金基数
    
    effective_date = Column(Date, nullable=False)  # 生效日期
    status = Column(String(32), nullable=False, default="active")  # 状态:active/inactive
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_salary_structures_a_employee", "employee_code"),
        Index("ix_salary_structures_a_status", "status"),
        {"schema": "a_class"},
    )

class PayrollRecord(Base):
    """
    A类数据表:工资单记录
    
    记录每月工资计算结果
    """
    __tablename__ = "payroll_records"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    employee_code = Column(String(64), nullable=False)  # 员工编号
    year_month = Column(String(7), nullable=False)  # 工资月份(YYYY-MM)
    
    # === 应发项 ===
    base_salary = Column(Numeric(15, 2), nullable=False, default=0.0)  # 基本工资
    position_salary = Column(Numeric(15, 2), nullable=False, default=0.0)  # 岗位工资
    performance_salary = Column(Numeric(15, 2), nullable=False, default=0.0)  # 绩效工资
    overtime_pay = Column(Numeric(15, 2), nullable=False, default=0.0)  # 加班费
    commission = Column(Numeric(15, 2), nullable=False, default=0.0)  # 提成
    allowances = Column(Numeric(15, 2), nullable=False, default=0.0)  # 津贴合计
    bonus = Column(Numeric(15, 2), nullable=False, default=0.0)  # 奖金
    gross_salary = Column(Numeric(15, 2), nullable=False, default=0.0)  # 应发合计
    
    # === 扣除项 ===
    social_insurance_personal = Column(Numeric(15, 2), nullable=False, default=0.0)  # 社保个人部分
    housing_fund_personal = Column(Numeric(15, 2), nullable=False, default=0.0)  # 公积金个人部分
    income_tax = Column(Numeric(15, 2), nullable=False, default=0.0)  # 个人所得税
    other_deductions = Column(Numeric(15, 2), nullable=False, default=0.0)  # 其他扣款
    total_deductions = Column(Numeric(15, 2), nullable=False, default=0.0)  # 扣款合计
    
    # === 实发工资 ===
    net_salary = Column(Numeric(15, 2), nullable=False, default=0.0)  # 实发工资
    
    # === 公司成本 ===
    social_insurance_company = Column(Numeric(15, 2), nullable=False, default=0.0)  # 社保公司部分
    housing_fund_company = Column(Numeric(15, 2), nullable=False, default=0.0)  # 公积金公司部分
    total_cost = Column(Numeric(15, 2), nullable=False, default=0.0)  # 公司总成本
    
    # === 状态 ===
    status = Column(String(32), nullable=False, default="draft")  # 状态:draft/confirmed/paid
    pay_date = Column(Date, nullable=True)  # 发薪日期
    remark = Column(Text, nullable=True)  # 备注
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    __table_args__ = (
        UniqueConstraint("employee_code", "year_month", name="uq_payroll_records_a"),
        Index("ix_payroll_records_a_employee", "employee_code"),
        Index("ix_payroll_records_a_month", "year_month"),
        Index("ix_payroll_records_a_status", "status"),
        {"schema": "a_class"},
    )

class SocialInsuranceConfig(Base):
    """
    A类数据表:社保公积金配置
    
    配置社保和公积金的缴纳比例
    """
    __tablename__ = "social_insurance_config"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    config_name = Column(String(128), nullable=False, unique=True)  # 配置名称(如:北京2024)
    city = Column(String(64), nullable=True)  # 所属城市
    
    # === 养老保险 ===
    pension_company_ratio = Column(Float, nullable=False, default=0.16)  # 单位缴纳比例
    pension_personal_ratio = Column(Float, nullable=False, default=0.08)  # 个人缴纳比例
    
    # === 医疗保险 ===
    medical_company_ratio = Column(Float, nullable=False, default=0.10)  # 单位缴纳比例
    medical_personal_ratio = Column(Float, nullable=False, default=0.02)  # 个人缴纳比例
    
    # === 失业保险 ===
    unemployment_company_ratio = Column(Float, nullable=False, default=0.008)  # 单位缴纳比例
    unemployment_personal_ratio = Column(Float, nullable=False, default=0.002)  # 个人缴纳比例
    
    # === 工伤保险 ===
    injury_company_ratio = Column(Float, nullable=False, default=0.002)  # 单位缴纳比例(个人不缴)
    
    # === 生育保险 ===
    maternity_company_ratio = Column(Float, nullable=False, default=0.008)  # 单位缴纳比例(个人不缴)
    
    # === 住房公积金 ===
    housing_fund_company_ratio = Column(Float, nullable=False, default=0.12)  # 单位缴纳比例
    housing_fund_personal_ratio = Column(Float, nullable=False, default=0.12)  # 个人缴纳比例
    
    # === 基数范围 ===
    min_base = Column(Numeric(15, 2), nullable=True)  # 最低基数
    max_base = Column(Numeric(15, 2), nullable=True)  # 最高基数
    
    effective_date = Column(Date, nullable=False)  # 生效日期
    status = Column(String(32), nullable=False, default="active")  # 状态:active/inactive
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_social_insurance_config_a_name", "config_name"),
        Index("ix_social_insurance_config_a_city", "city"),
        {"schema": "a_class"},
    )

class PerformanceConfigA(Base):
    """
    A类数据表:绩效权重配置(中文字段名)
    
    注意:此表将替代旧的PerformanceConfig表(v4.11.0),使用中文字段名
    """
    __tablename__ = "performance_config_a"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    config_name = Column(String(128), nullable=False)  # 迁移时将重命名为"配置名称"
    sales_weight = Column(Float, nullable=False, default=0.0)  # 迁移时将重命名为"销售额权重"
    quantity_weight = Column(Float, nullable=False, default=0.0)  # 迁移时将重命名为"订单数权重"
    quality_weight = Column(Float, nullable=False, default=0.0)  # 迁移时将重命名为"质量权重"
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    __table_args__ = (
        UniqueConstraint("config_name", name="uq_performance_config_a_name"),
        Index("ix_performance_config_a_active", "active"),
        {"schema": "a_class"},
    )


# C类数据表(使用中文字段名,由Metabase定时计算更新)

class EmployeePerformance(Base):
    """C类数据表:员工绩效(中文字段名,Metabase每20分钟更新)"""
    __tablename__ = "employee_performance"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    employee_code = Column(String(64), nullable=False)  # 迁移时将重命名为"员工编号"
    year_month = Column(String(7), nullable=False)  # 迁移时将重命名为"年月"
    actual_sales = Column(Numeric(15, 2), nullable=False, default=0.0)  # 迁移时将重命名为"实际销售额"
    achievement_rate = Column(Float, nullable=False, default=0.0)  # 迁移时将重命名为"达成率"
    performance_score = Column(Float, nullable=False, default=0.0)  # 迁移时将重命名为"绩效得分"
    calculated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)  # 迁移时将重命名为"计算时间"
    
    __table_args__ = (
        UniqueConstraint("employee_code", "year_month", name="uq_employee_performance_c"),
        Index("ix_employee_performance_c_employee", "employee_code"),
        Index("ix_employee_performance_c_month", "year_month"),
        {"schema": "c_class"},
    )

class EmployeeCommission(Base):
    """C类数据表:员工提成(中文字段名,Metabase每20分钟更新)"""
    __tablename__ = "employee_commissions"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    employee_code = Column(String(64), nullable=False)  # 迁移时将重命名为"员工编号"
    year_month = Column(String(7), nullable=False)  # 迁移时将重命名为"年月"
    sales_amount = Column(Numeric(15, 2), nullable=False, default=0.0)  # 迁移时将重命名为"销售额"
    commission_amount = Column(Numeric(15, 2), nullable=False, default=0.0)  # 迁移时将重命名为"提成金额"
    commission_rate = Column(Float, nullable=False, default=0.0)  # 迁移时将重命名为"提成比例"
    calculated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)  # 迁移时将重命名为"计算时间"
    
    __table_args__ = (
        UniqueConstraint("employee_code", "year_month", name="uq_employee_commissions_c"),
        Index("ix_employee_commissions_c_employee", "employee_code"),
        Index("ix_employee_commissions_c_month", "year_month"),
        {"schema": "c_class"},
    )

class ShopCommission(Base):
    """C类数据表:店铺提成(中文字段名,Metabase每20分钟更新)"""
    __tablename__ = "shop_commissions"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    shop_id = Column(String(256), nullable=False)  # 迁移时将重命名为"店铺ID"
    year_month = Column(String(7), nullable=False)  # 迁移时将重命名为"年月"
    sales_amount = Column(Numeric(15, 2), nullable=False, default=0.0)  # 迁移时将重命名为"销售额"
    commission_amount = Column(Numeric(15, 2), nullable=False, default=0.0)  # 迁移时将重命名为"提成金额"
    commission_rate = Column(Float, nullable=False, default=0.0)  # 迁移时将重命名为"提成比例"
    calculated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)  # 迁移时将重命名为"计算时间"
    
    __table_args__ = (
        UniqueConstraint("shop_id", "year_month", name="uq_shop_commissions_c"),
        Index("ix_shop_commissions_c_shop", "shop_id"),
        Index("ix_shop_commissions_c_month", "year_month"),
        {"schema": "c_class"},
    )


# [REMOVED] PerformanceScoreC: 表已由迁移 20260131 合并入 c_class.performance_scores 并删除，不再定义 ORM


# v4.19.0: 系统通知表

class Notification(Base):
    """
    系统通知表 (v4.19.0)
    
    用于存储系统内部通知,如:
    - 新用户注册通知(发给管理员)
    - 审批结果通知(发给用户)
    - 系统告警通知
    """
    __tablename__ = "notifications"
    
    notification_id = Column(BigInteger, primary_key=True, autoincrement=True)
    recipient_id = Column(
        BigInteger,
        ForeignKey('core.dim_users.user_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        comment="接收者用户ID"
    )
    
    # 通知内容
    notification_type = Column(
        String(50),
        nullable=False,
        index=True,
        comment="通知类型:user_registered, user_approved, user_rejected, system_alert"
    )
    title = Column(String(200), nullable=False, comment="通知标题")
    content = Column(Text, nullable=False, comment="通知内容")
    extra_data = Column(JSON, nullable=True, comment="扩展数据(JSON格式)")
    
    # 关联数据
    related_user_id = Column(
        BigInteger,
        ForeignKey('core.dim_users.user_id', ondelete='SET NULL'),
        nullable=True,
        comment="关联用户ID(如被审批的用户)"
    )
    
    # v4.19.0: 优先级
    priority = Column(
        String(10),
        default="medium",
        nullable=False,
        index=True,
        comment="优先级:high, medium, low"
    )
    
    # 状态
    is_read = Column(Boolean, default=False, nullable=False, index=True, comment="是否已读")
    read_at = Column(DateTime(timezone=True), nullable=True, comment="阅读时间")
    
    # 时间戳
    created_at = Column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        index=True,
        comment="创建时间"
    )
    
    # 关系
    recipient = relationship(
        "DimUser",
        foreign_keys=[recipient_id],
        backref="notifications"
    )
    
    __table_args__ = (
        Index("idx_notification_user_unread", "recipient_id", "is_read"),
        Index("idx_notification_type_created", "notification_type", "created_at"),
    )


# v4.19.0: 用户通知偏好表

class UserNotificationPreference(Base):
    """
    用户通知偏好表 (v4.19.0)
    
    用于存储用户对不同类型通知的偏好设置,如:
    - 是否启用通知
    - 是否启用桌面通知
    """
    __tablename__ = "user_notification_preferences"
    
    preference_id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(
        BigInteger,
        ForeignKey('core.dim_users.user_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        comment="用户ID"
    )
    notification_type = Column(
        String(50),
        nullable=False,
        comment="通知类型:user_registered, user_approved, user_rejected, system_alert等"
    )
    enabled = Column(
        Boolean,
        default=True,
        nullable=False,
        comment="是否启用通知(应用内通知)"
    )
    desktop_enabled = Column(
        Boolean,
        default=False,
        nullable=False,
        comment="是否启用桌面通知(浏览器原生通知)"
    )
    
    # 时间戳
    created_at = Column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        comment="创建时间"
    )
    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="更新时间"
    )
    
    # 关系
    user = relationship(
        "DimUser",
        foreign_keys=[user_id],
        backref="notification_preferences"
    )
    
    __table_args__ = (
        UniqueConstraint("user_id", "notification_type", name="uq_user_notification_preference"),
        Index("idx_user_notification_user", "user_id"),
    )


# [*] v4.19.4 新增:限流配置表(Phase 3)

class DimRateLimitConfig(Base):
    """
    限流配置维度表
    
    用途:存储基于角色的限流配置,支持运行时动态调整
    - 支持多角色、多端点类型配置
    - 支持配置启用/禁用
    - 支持配置版本管理
    
    v4.19.4 新增:Phase 3 数据库配置支持
    """
    __tablename__ = "dim_rate_limit_config"
    
    config_id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 配置维度
    role_code = Column(String(50), nullable=False, index=True)  # admin/manager/finance/operator/normal/anonymous
    endpoint_type = Column(String(50), nullable=False, index=True)  # default/data_sync/auth
    
    # 限流值
    limit_value = Column(String(50), nullable=False)  # "200/minute", "100/minute"
    
    # 配置状态
    is_active = Column(Boolean, default=True, nullable=False, index=True)  # 是否启用
    
    # 配置描述
    description = Column(Text, nullable=True)  # 配置说明
    
    # 审计字段
    created_by = Column(String(100), nullable=True)  # 创建者
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    updated_by = Column(String(100), nullable=True)  # 最后更新者
    
    __table_args__ = (
        UniqueConstraint("role_code", "endpoint_type", name="uq_rate_limit_config_role_endpoint"),
        Index("ix_rate_limit_config_active", "is_active", "role_code"),
        Index("ix_rate_limit_config_role", "role_code", "endpoint_type"),
    )


# [*] v4.19.4 新增:限流配置审计日志表(Phase 3)

class FactRateLimitConfigAudit(Base):
    """
    限流配置变更审计日志表
    
    用途:记录所有限流配置的变更历史,支持审计追溯
    - 记录配置创建、更新、删除操作
    - 记录变更前后的值
    - 记录操作人和操作时间
    
    v4.19.4 新增:Phase 3 配置变更审计
    """
    __tablename__ = "fact_rate_limit_config_audit"
    
    audit_id = Column(BigInteger, primary_key=True, autoincrement=True, index=True)
    
    # 配置信息
    config_id = Column(Integer, ForeignKey("dim_rate_limit_config.config_id"), nullable=True)  # 配置ID(删除时为NULL)
    role_code = Column(String(50), nullable=False, index=True)  # 角色代码
    endpoint_type = Column(String(50), nullable=False, index=True)  # 端点类型
    
    # 操作信息
    action_type = Column(String(50), nullable=False, index=True)  # create/update/delete
    old_limit_value = Column(String(50), nullable=True)  # 变更前的限流值
    new_limit_value = Column(String(50), nullable=True)  # 变更后的限流值
    old_is_active = Column(Boolean, nullable=True)  # 变更前的启用状态
    new_is_active = Column(Boolean, nullable=True)  # 变更后的启用状态
    
    # 操作人信息
    operator_id = Column(BigInteger, ForeignKey("core.dim_users.user_id"), nullable=True)  # 操作人ID
    operator_username = Column(String(100), nullable=False)  # 操作人用户名(冗余字段)
    
    # IP和设备信息
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(500), nullable=True)
    
    # 操作结果
    is_success = Column(Boolean, default=True, nullable=False)
    error_message = Column(Text, nullable=True)  # 错误信息(如果操作失败)
    
    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    
    __table_args__ = (
        Index("idx_rate_limit_audit_config", "config_id", "created_at"),
        Index("idx_rate_limit_audit_role", "role_code", "endpoint_type", "created_at"),
        Index("idx_rate_limit_audit_operator", "operator_id", "created_at"),
        Index("idx_rate_limit_audit_action", "action_type", "created_at"),
    )


# ==================== System Management Tables (v4.20.0) ====================

class SystemLog(Base):
    """
    系统日志表
    
    用于存储应用运行时产生的结构化日志。
    与文件日志、审计日志、任务日志不同:
    - 文件日志:modules/core/logger.py 写入文件
    - 审计日志:FactAuditLog 表记录用户操作
    - 任务日志:CollectionTaskLog 表记录采集任务
    - 系统日志:本表记录应用运行时的结构化日志
    """
    __tablename__ = "system_logs"
    
    id = Column(Integer, primary_key=True)
    level = Column(String(10), nullable=False)  # ERROR, WARN, INFO, DEBUG
    module = Column(String(64), nullable=False)  # 模块名称
    message = Column(Text, nullable=False)  # 日志消息
    user_id = Column(Integer, ForeignKey("core.dim_users.user_id"), nullable=True)
    ip_address = Column(String(45), nullable=True)  # IPv4/IPv6
    user_agent = Column(String(512), nullable=True)
    details = Column(JSONB, nullable=True)  # 详细信息(JSON格式)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_system_logs_level", "level"),
        Index("ix_system_logs_module", "module"),
        Index("ix_system_logs_created_at", "created_at"),
        ForeignKeyConstraint(['user_id'], ['core.dim_users.user_id'], name='fk_system_logs_user_id'),
    )

class SecurityConfig(Base):
    """
    安全配置表
    
    用于存储系统安全相关配置(密码策略、登录限制、会话配置、2FA配置等)
    使用JSONB存储配置值,支持灵活的配置结构
    """
    __tablename__ = "security_config"
    
    id = Column(Integer, primary_key=True)
    config_key = Column(String(64), unique=True, nullable=False)  # password_policy, login_restrictions, session_config, 2fa_config
    config_value = Column(JSONB, nullable=False)  # 配置值(JSON格式)
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    updated_by = Column(Integer, ForeignKey("core.dim_users.user_id"), nullable=True)
    
    __table_args__ = (
        UniqueConstraint('config_key', name='uq_security_config_key'),  # 唯一约束
        Index('ix_security_config_key', 'config_key'),  # 索引
        ForeignKeyConstraint(['updated_by'], ['core.dim_users.user_id'], name='fk_security_config_updated_by'),
    )

class BackupRecord(Base):
    """
    备份记录表
    
    用于记录系统备份操作的历史记录
    """
    __tablename__ = "backup_records"
    
    id = Column(Integer, primary_key=True)
    backup_type = Column(String(32), nullable=False)  # full, incremental
    backup_path = Column(String(512), nullable=False)  # 备份文件路径(容器内路径)
    backup_size = Column(BigInteger, nullable=False)  # 备份大小(字节)
    checksum = Column(String(64), nullable=True)  # 文件校验和(SHA-256)
    status = Column(String(32), nullable=False)  # pending, completed, failed
    description = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("core.dim_users.user_id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    __table_args__ = (
        Index("ix_backup_records_status", "status"),
        Index("ix_backup_records_created_at", "created_at"),
        ForeignKeyConstraint(['created_by'], ['core.dim_users.user_id'], name='fk_backup_records_created_by'),
        {"schema": "core"},
    )

class SMTPConfig(Base):
    """
    SMTP配置表
    
    用于存储邮件服务器配置(密码加密存储)
    """
    __tablename__ = "smtp_config"
    
    id = Column(Integer, primary_key=True)
    smtp_server = Column(String(256), nullable=False)
    smtp_port = Column(Integer, nullable=False)
    use_tls = Column(Boolean, default=True, nullable=False)
    username = Column(String(256), nullable=False)
    password_encrypted = Column(Text, nullable=False)  # 加密存储
    from_email = Column(String(256), nullable=False)
    from_name = Column(String(128), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    updated_by = Column(Integer, ForeignKey("core.dim_users.user_id"), nullable=True)
    
    __table_args__ = (
        ForeignKeyConstraint(['updated_by'], ['core.dim_users.user_id'], name='fk_smtp_config_updated_by'),
    )

class NotificationTemplate(Base):
    """
    通知模板表
    
    用于存储通知内容模板(支持变量替换)
    """
    __tablename__ = "notification_templates"
    
    id = Column(Integer, primary_key=True)
    template_name = Column(String(128), unique=True, nullable=False)
    template_type = Column(String(64), nullable=False)  # email/sms/push
    subject = Column(String(256), nullable=True)  # 邮件主题(email类型)
    content = Column(Text, nullable=False)  # 模板内容(支持变量如 {{user_name}})
    variables = Column(JSONB, nullable=True)  # 可用变量说明(JSON格式)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by = Column(Integer, ForeignKey("core.dim_users.user_id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("core.dim_users.user_id"), nullable=True)
    
    __table_args__ = (
        Index("ix_notification_templates_template_name", "template_name"),
        Index("ix_notification_templates_template_type", "template_type"),
        ForeignKeyConstraint(['created_by'], ['core.dim_users.user_id'], name='fk_notification_templates_created_by'),
        ForeignKeyConstraint(['updated_by'], ['core.dim_users.user_id'], name='fk_notification_templates_updated_by'),
    )

class AlertRule(Base):
    """
    告警规则表
    
    用于配置系统告警规则(何时触发通知)
    """
    __tablename__ = "alert_rules"
    
    id = Column(Integer, primary_key=True)
    rule_name = Column(String(128), unique=True, nullable=False)
    rule_type = Column(String(64), nullable=False)  # system/performance/security/business
    condition = Column(JSONB, nullable=False)  # 触发条件(JSON格式)
    template_id = Column(Integer, ForeignKey("notification_templates.id"), nullable=True)
    recipients = Column(JSONB, nullable=True)  # 收件人列表(JSON格式,支持用户ID、邮箱等)
    enabled = Column(Boolean, default=True, nullable=False)
    priority = Column(String(16), nullable=False, default="medium")  # low/medium/high/critical
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by = Column(Integer, ForeignKey("core.dim_users.user_id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("core.dim_users.user_id"), nullable=True)
    
    __table_args__ = (
        Index("ix_alert_rules_rule_name", "rule_name"),
        Index("ix_alert_rules_rule_type", "rule_type"),
        Index("ix_alert_rules_enabled", "enabled"),
        ForeignKeyConstraint(['template_id'], ['notification_templates.id'], name='fk_alert_rules_template_id'),
        ForeignKeyConstraint(['created_by'], ['core.dim_users.user_id'], name='fk_alert_rules_created_by'),
        ForeignKeyConstraint(['updated_by'], ['core.dim_users.user_id'], name='fk_alert_rules_updated_by'),
    )

class SystemConfig(Base):
    """
    系统配置表
    
    用于存储系统基础配置(系统名称、版本、时区、语言、货币等)
    使用键值对存储,支持灵活的配置项
    """
    __tablename__ = "system_config"
    
    id = Column(Integer, primary_key=True)
    config_key = Column(String(64), unique=True, nullable=False)  # system_name, version, timezone, language, currency
    config_value = Column(String(512), nullable=False)
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    updated_by = Column(Integer, ForeignKey("core.dim_users.user_id"), nullable=True)
    
    __table_args__ = (
        UniqueConstraint('config_key', name='uq_system_config_key'),  # 唯一约束
        Index('ix_system_config_key', 'config_key'),  # 索引
        ForeignKeyConstraint(['updated_by'], ['core.dim_users.user_id'], name='fk_system_config_updated_by'),
    )
