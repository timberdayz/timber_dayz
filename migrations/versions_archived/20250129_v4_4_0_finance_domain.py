"""v4.4.0 Finance Domain Tables - Modern ERP

Revision ID: v4_4_0_finance
Revises: (last_revision)
Create Date: 2025-01-29

新增财务域完整表结构：
- 扩展FieldMappingDictionary（version, status）
- 指标公式辞典
- 采购管理（PO/GRN）
- 发票管理（三单匹配）
- 库存流水账（Universal Journal）
- 费用分摊
- 物流成本
- 税务管理
- 总账（双分录）
- 期初余额

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'v4_4_0_finance'
down_revision = '20250128_0012'  # 基于最新的product hierarchy迁移
branch_labels = None
depends_on = None


def upgrade():
    """升级数据库schema"""
    
    # 1. 扩展FieldMappingDictionary
    op.add_column('field_mapping_dictionary', 
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('field_mapping_dictionary',
        sa.Column('status', sa.String(32), nullable=False, server_default='active'))
    op.create_index('ix_dictionary_status', 'field_mapping_dictionary', ['status', 'data_domain'])
    
    # 2. 计算指标公式辞典
    op.create_table('dim_metric_formulas',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('metric_code', sa.String(128), nullable=False),
        sa.Column('cn_name', sa.String(128), nullable=False),
        sa.Column('en_name', sa.String(128), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('data_domain', sa.String(64), nullable=False),
        sa.Column('metric_type', sa.String(32), nullable=False),
        sa.Column('sql_expr', sa.Text(), nullable=False),
        sa.Column('depends_on', sa.JSON(), nullable=True),
        sa.Column('aggregator', sa.String(32), nullable=True),
        sa.Column('unit', sa.String(32), nullable=True),
        sa.Column('display_format', sa.String(64), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_by', sa.String(64), nullable=True, server_default='system'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=True, onupdate=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('metric_code')
    )
    op.create_index('ix_metric_formula_domain', 'dim_metric_formulas', ['data_domain', 'active'])
    
    # 3. 货币与汇率
    op.create_table('dim_currencies',
        sa.Column('currency_code', sa.String(8), nullable=False),
        sa.Column('currency_name', sa.String(64), nullable=False),
        sa.Column('symbol', sa.String(8), nullable=True),
        sa.Column('is_base', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('active', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('currency_code')
    )
    
    op.create_table('fx_rates',
        sa.Column('rate_date', sa.Date(), nullable=False),
        sa.Column('from_currency', sa.String(8), nullable=False),
        sa.Column('to_currency', sa.String(8), nullable=False),
        sa.Column('rate', sa.Float(), nullable=False),
        sa.Column('source', sa.String(64), nullable=True, server_default='manual'),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('rate_date', 'from_currency', 'to_currency')
    )
    op.create_index('ix_fx_rates_date_from', 'fx_rates', ['rate_date', 'from_currency'])
    
    # 4. 会计期间
    op.create_table('dim_fiscal_calendar',
        sa.Column('period_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('period_year', sa.Integer(), nullable=False),
        sa.Column('period_month', sa.Integer(), nullable=False),
        sa.Column('period_code', sa.String(16), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(32), nullable=False, server_default='open'),
        sa.Column('closed_by', sa.String(64), nullable=True),
        sa.Column('closed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('period_id'),
        sa.UniqueConstraint('period_code'),
        sa.UniqueConstraint('period_year', 'period_month', name='uq_fiscal_period')
    )
    op.create_index('ix_fiscal_calendar_year_month', 'dim_fiscal_calendar', ['period_year', 'period_month'])
    op.create_index('ix_fiscal_calendar_status', 'dim_fiscal_calendar', ['status'])
    
    # 5. 供应商
    op.create_table('dim_vendors',
        sa.Column('vendor_code', sa.String(64), nullable=False),
        sa.Column('vendor_name', sa.String(256), nullable=False),
        sa.Column('country', sa.String(64), nullable=True),
        sa.Column('tax_id', sa.String(128), nullable=True),
        sa.Column('payment_terms', sa.String(64), nullable=True),
        sa.Column('credit_limit', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('status', sa.String(32), nullable=False, server_default='active'),
        sa.Column('contact_person', sa.String(128), nullable=True),
        sa.Column('contact_phone', sa.String(64), nullable=True),
        sa.Column('contact_email', sa.String(128), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=True, onupdate=sa.text('now()')),
        sa.PrimaryKeyConstraint('vendor_code')
    )
    op.create_index('ix_vendors_status', 'dim_vendors', ['status'])
    
    # 6. 采购订单
    op.create_table('po_headers',
        sa.Column('po_id', sa.String(64), nullable=False),
        sa.Column('vendor_code', sa.String(64), nullable=False),
        sa.Column('po_date', sa.Date(), nullable=False),
        sa.Column('expected_date', sa.Date(), nullable=True),
        sa.Column('currency', sa.String(8), nullable=False),
        sa.Column('total_amt', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('base_amt', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('status', sa.String(32), nullable=False, server_default='draft'),
        sa.Column('approval_threshold', sa.Float(), nullable=True),
        sa.Column('approved_by', sa.String(64), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.String(64), nullable=True, server_default='system'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=True, onupdate=sa.text('now()')),
        sa.PrimaryKeyConstraint('po_id'),
        sa.ForeignKeyConstraint(['vendor_code'], ['dim_vendors.vendor_code'])
    )
    op.create_index('ix_po_headers_vendor_date', 'po_headers', ['vendor_code', 'po_date'])
    op.create_index('ix_po_headers_status', 'po_headers', ['status'])
    
    op.create_table('po_lines',
        sa.Column('po_line_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('po_id', sa.String(64), nullable=False),
        sa.Column('line_number', sa.Integer(), nullable=False),
        sa.Column('platform_sku', sa.String(128), nullable=False),
        sa.Column('product_title', sa.String(512), nullable=True),
        sa.Column('qty_ordered', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('qty_received', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('unit_price', sa.Float(), nullable=False),
        sa.Column('currency', sa.String(8), nullable=False),
        sa.Column('line_amt', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('base_amt', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('po_line_id'),
        sa.ForeignKeyConstraint(['po_id'], ['po_headers.po_id'], ondelete='CASCADE'),
        sa.UniqueConstraint('po_id', 'line_number', name='uq_po_line')
    )
    op.create_index('ix_po_lines_po_id', 'po_lines', ['po_id'])
    op.create_index('ix_po_lines_sku', 'po_lines', ['platform_sku'])
    
    # 7. 入库单
    op.create_table('grn_headers',
        sa.Column('grn_id', sa.String(64), nullable=False),
        sa.Column('po_id', sa.String(64), nullable=False),
        sa.Column('receipt_date', sa.Date(), nullable=False),
        sa.Column('warehouse', sa.String(64), nullable=True),
        sa.Column('status', sa.String(32), nullable=False, server_default='pending'),
        sa.Column('created_by', sa.String(64), nullable=True, server_default='system'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('grn_id'),
        sa.ForeignKeyConstraint(['po_id'], ['po_headers.po_id'])
    )
    op.create_index('ix_grn_headers_po_id', 'grn_headers', ['po_id'])
    op.create_index('ix_grn_headers_date', 'grn_headers', ['receipt_date'])
    
    op.create_table('grn_lines',
        sa.Column('grn_line_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('grn_id', sa.String(64), nullable=False),
        sa.Column('po_line_id', sa.Integer(), nullable=False),
        sa.Column('platform_sku', sa.String(128), nullable=False),
        sa.Column('qty_received', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('unit_cost', sa.Float(), nullable=False),
        sa.Column('currency', sa.String(8), nullable=False),
        sa.Column('ext_value', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('base_ext_value', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('weight_kg', sa.Float(), nullable=True),
        sa.Column('volume_m3', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('grn_line_id'),
        sa.ForeignKeyConstraint(['grn_id'], ['grn_headers.grn_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['po_line_id'], ['po_lines.po_line_id'])
    )
    op.create_index('ix_grn_lines_grn_id', 'grn_lines', ['grn_id'])
    op.create_index('ix_grn_lines_po_line', 'grn_lines', ['po_line_id'])
    op.create_index('ix_grn_lines_sku', 'grn_lines', ['platform_sku'])
    
    # 8. 库存流水账（Universal Journal）
    op.create_table('inventory_ledger',
        sa.Column('ledger_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('platform_code', sa.String(32), nullable=False),
        sa.Column('shop_id', sa.String(64), nullable=False),
        sa.Column('platform_sku', sa.String(128), nullable=False),
        sa.Column('transaction_date', sa.Date(), nullable=False),
        sa.Column('movement_type', sa.String(32), nullable=False),
        sa.Column('qty_in', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('qty_out', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('unit_cost_wac', sa.Float(), nullable=False),
        sa.Column('ext_value', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('base_ext_value', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('qty_before', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('avg_cost_before', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('qty_after', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('avg_cost_after', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('link_grn_id', sa.String(64), nullable=True),
        sa.Column('link_order_id', sa.String(128), nullable=True),
        sa.Column('original_sale_line_id', sa.Integer(), nullable=True),
        sa.Column('return_reason', sa.String(256), nullable=True),
        sa.Column('created_by', sa.String(64), nullable=True, server_default='system'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('ledger_id')
    )
    op.create_index('ix_inventory_ledger_sku_date', 'inventory_ledger', 
                    ['platform_code', 'shop_id', 'platform_sku', 'transaction_date'])
    op.create_index('ix_inventory_ledger_type', 'inventory_ledger', ['movement_type', 'transaction_date'])
    op.create_index('ix_inventory_ledger_grn', 'inventory_ledger', ['link_grn_id'])
    op.create_index('ix_inventory_ledger_order', 'inventory_ledger', ['link_order_id'])
    
    # 9. 发票管理
    op.create_table('invoice_headers',
        sa.Column('invoice_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('vendor_code', sa.String(64), nullable=False),
        sa.Column('invoice_no', sa.String(128), nullable=False),
        sa.Column('invoice_date', sa.Date(), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('currency', sa.String(8), nullable=False),
        sa.Column('total_amt', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('tax_amt', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('base_total_amt', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('status', sa.String(32), nullable=False, server_default='pending'),
        sa.Column('source_file_id', sa.Integer(), nullable=True),
        sa.Column('ocr_result', sa.JSON(), nullable=True),
        sa.Column('ocr_confidence', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=True, onupdate=sa.text('now()')),
        sa.PrimaryKeyConstraint('invoice_id'),
        sa.UniqueConstraint('invoice_no'),
        sa.ForeignKeyConstraint(['vendor_code'], ['dim_vendors.vendor_code']),
        sa.ForeignKeyConstraint(['source_file_id'], ['catalog_files.id'], ondelete='SET NULL')
    )
    op.create_index('ix_invoice_headers_vendor_date', 'invoice_headers', ['vendor_code', 'invoice_date'])
    op.create_index('ix_invoice_headers_status', 'invoice_headers', ['status'])
    
    op.create_table('invoice_lines',
        sa.Column('invoice_line_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('invoice_id', sa.Integer(), nullable=False),
        sa.Column('po_line_id', sa.Integer(), nullable=True),
        sa.Column('grn_line_id', sa.Integer(), nullable=True),
        sa.Column('platform_sku', sa.String(128), nullable=False),
        sa.Column('qty', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('unit_price', sa.Float(), nullable=False),
        sa.Column('line_amt', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('tax_amt', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('invoice_line_id'),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoice_headers.invoice_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['po_line_id'], ['po_lines.po_line_id']),
        sa.ForeignKeyConstraint(['grn_line_id'], ['grn_lines.grn_line_id'])
    )
    op.create_index('ix_invoice_lines_invoice', 'invoice_lines', ['invoice_id'])
    op.create_index('ix_invoice_lines_po_line', 'invoice_lines', ['po_line_id'])
    op.create_index('ix_invoice_lines_grn_line', 'invoice_lines', ['grn_line_id'])
    
    op.create_table('invoice_attachments',
        sa.Column('attachment_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('invoice_id', sa.Integer(), nullable=False),
        sa.Column('file_path', sa.String(1024), nullable=False),
        sa.Column('file_type', sa.String(32), nullable=True),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('ocr_text', sa.Text(), nullable=True),
        sa.Column('ocr_fields', sa.JSON(), nullable=True),
        sa.Column('uploaded_by', sa.String(64), nullable=True, server_default='system'),
        sa.Column('uploaded_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('attachment_id'),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoice_headers.invoice_id'], ondelete='CASCADE')
    )
    op.create_index('ix_invoice_attachments_invoice', 'invoice_attachments', ['invoice_id'])
    
    # 10. 三单匹配
    op.create_table('three_way_match_log',
        sa.Column('match_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('po_line_id', sa.Integer(), nullable=False),
        sa.Column('grn_line_id', sa.Integer(), nullable=True),
        sa.Column('invoice_line_id', sa.Integer(), nullable=True),
        sa.Column('match_status', sa.String(32), nullable=False, server_default='unmatched'),
        sa.Column('variance_qty', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('variance_amt', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('variance_reason', sa.Text(), nullable=True),
        sa.Column('approved_by', sa.String(64), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('match_id'),
        sa.ForeignKeyConstraint(['po_line_id'], ['po_lines.po_line_id']),
        sa.ForeignKeyConstraint(['grn_line_id'], ['grn_lines.grn_line_id']),
        sa.ForeignKeyConstraint(['invoice_line_id'], ['invoice_lines.invoice_line_id'])
    )
    op.create_index('ix_three_way_match_po', 'three_way_match_log', ['po_line_id'])
    op.create_index('ix_three_way_match_status', 'three_way_match_log', ['match_status'])
    
    # 11. 费用管理
    op.create_table('fact_expenses_month',
        sa.Column('expense_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('period_month', sa.String(16), nullable=False),
        sa.Column('cost_center', sa.String(64), nullable=True),
        sa.Column('expense_type', sa.String(128), nullable=False),
        sa.Column('vendor', sa.String(256), nullable=True),
        sa.Column('currency', sa.String(8), nullable=False),
        sa.Column('currency_amt', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('base_amt', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('tax_amt', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('platform_code', sa.String(32), nullable=True),
        sa.Column('shop_id', sa.String(64), nullable=True),
        sa.Column('source_file_id', sa.Integer(), nullable=True),
        sa.Column('memo', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('expense_id'),
        sa.ForeignKeyConstraint(['period_month'], ['dim_fiscal_calendar.period_code']),
        sa.ForeignKeyConstraint(['source_file_id'], ['catalog_files.id'], ondelete='SET NULL')
    )
    op.create_index('ix_expenses_month_period', 'fact_expenses_month', ['period_month'])
    op.create_index('ix_expenses_month_type', 'fact_expenses_month', ['expense_type'])
    op.create_index('ix_expenses_month_shop', 'fact_expenses_month', ['platform_code', 'shop_id'])
    
    # 12. 分摊规则与结果
    op.create_table('allocation_rules',
        sa.Column('rule_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('rule_name', sa.String(256), nullable=False),
        sa.Column('scope', sa.String(64), nullable=False),
        sa.Column('driver', sa.String(64), nullable=False),
        sa.Column('weights', sa.JSON(), nullable=True),
        sa.Column('effective_from', sa.Date(), nullable=False),
        sa.Column('effective_to', sa.Date(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('created_by', sa.String(64), nullable=True, server_default='system'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('rule_id')
    )
    op.create_index('ix_allocation_rules_scope', 'allocation_rules', ['scope', 'active'])
    
    op.create_table('fact_expenses_allocated_day_shop_sku',
        sa.Column('allocation_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('expense_id', sa.Integer(), nullable=False),
        sa.Column('allocation_date', sa.Date(), nullable=False),
        sa.Column('platform_code', sa.String(32), nullable=False),
        sa.Column('shop_id', sa.String(64), nullable=False),
        sa.Column('platform_sku', sa.String(128), nullable=True),
        sa.Column('allocated_amt', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('allocation_driver', sa.String(64), nullable=True),
        sa.Column('allocation_weight', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('allocation_id'),
        sa.ForeignKeyConstraint(['expense_id'], ['fact_expenses_month.expense_id'])
    )
    op.create_index('ix_expenses_allocated_date', 'fact_expenses_allocated_day_shop_sku', ['allocation_date'])
    op.create_index('ix_expenses_allocated_shop', 'fact_expenses_allocated_day_shop_sku', 
                    ['platform_code', 'shop_id', 'allocation_date'])
    op.create_index('ix_expenses_allocated_sku', 'fact_expenses_allocated_day_shop_sku',
                    ['platform_code', 'shop_id', 'platform_sku', 'allocation_date'])
    
    # 13. 物流成本
    op.create_table('logistics_costs',
        sa.Column('logistics_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('grn_id', sa.String(64), nullable=True),
        sa.Column('order_id', sa.String(128), nullable=True),
        sa.Column('logistics_provider', sa.String(128), nullable=True),
        sa.Column('tracking_no', sa.String(128), nullable=True),
        sa.Column('cost_type', sa.String(64), nullable=False),
        sa.Column('currency', sa.String(8), nullable=False),
        sa.Column('currency_amt', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('base_amt', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('weight_kg', sa.Float(), nullable=True),
        sa.Column('volume_m3', sa.Float(), nullable=True),
        sa.Column('invoice_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('logistics_id'),
        sa.ForeignKeyConstraint(['grn_id'], ['grn_headers.grn_id']),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoice_headers.invoice_id'])
    )
    op.create_index('ix_logistics_costs_grn', 'logistics_costs', ['grn_id'])
    op.create_index('ix_logistics_costs_order', 'logistics_costs', ['order_id'])
    op.create_index('ix_logistics_costs_invoice', 'logistics_costs', ['invoice_id'])
    
    op.create_table('logistics_allocation_rules',
        sa.Column('rule_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('rule_name', sa.String(256), nullable=False),
        sa.Column('scope', sa.String(64), nullable=False),
        sa.Column('driver', sa.String(64), nullable=False),
        sa.Column('effective_from', sa.Date(), nullable=False),
        sa.Column('effective_to', sa.Date(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('rule_id')
    )
    op.create_index('ix_logistics_alloc_rules_scope', 'logistics_allocation_rules', ['scope', 'active'])
    
    # 14. 税务管理
    op.create_table('tax_vouchers',
        sa.Column('voucher_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('period_month', sa.String(16), nullable=False),
        sa.Column('voucher_type', sa.String(32), nullable=False),
        sa.Column('invoice_id', sa.Integer(), nullable=True),
        sa.Column('tax_amt', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('deductible_amt', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('status', sa.String(32), nullable=False, server_default='pending'),
        sa.Column('filing_status', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('voucher_id'),
        sa.ForeignKeyConstraint(['period_month'], ['dim_fiscal_calendar.period_code']),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoice_headers.invoice_id'])
    )
    op.create_index('ix_tax_vouchers_period', 'tax_vouchers', ['period_month'])
    op.create_index('ix_tax_vouchers_type', 'tax_vouchers', ['voucher_type', 'status'])
    
    op.create_table('tax_reports',
        sa.Column('report_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('period_month', sa.String(16), nullable=False),
        sa.Column('report_type', sa.String(64), nullable=False),
        sa.Column('status', sa.String(32), nullable=False, server_default='draft'),
        sa.Column('export_file_path', sa.String(1024), nullable=True),
        sa.Column('generated_by', sa.String(64), nullable=True, server_default='system'),
        sa.Column('generated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('submitted_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('report_id'),
        sa.ForeignKeyConstraint(['period_month'], ['dim_fiscal_calendar.period_code'])
    )
    op.create_index('ix_tax_reports_period', 'tax_reports', ['period_month'])
    op.create_index('ix_tax_reports_status', 'tax_reports', ['status'])
    
    # 15. 总账（GL）
    op.create_table('gl_accounts',
        sa.Column('account_code', sa.String(64), nullable=False),
        sa.Column('account_name', sa.String(256), nullable=False),
        sa.Column('account_type', sa.String(64), nullable=False),
        sa.Column('parent_account', sa.String(64), nullable=True),
        sa.Column('is_debit_normal', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('active', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('account_code')
    )
    op.create_index('ix_gl_accounts_type', 'gl_accounts', ['account_type', 'active'])
    
    op.create_table('journal_entries',
        sa.Column('entry_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('entry_no', sa.String(64), nullable=False),
        sa.Column('entry_date', sa.Date(), nullable=False),
        sa.Column('period_month', sa.String(16), nullable=False),
        sa.Column('entry_type', sa.String(64), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(32), nullable=False, server_default='draft'),
        sa.Column('created_by', sa.String(64), nullable=True, server_default='system'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('posted_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('entry_id'),
        sa.UniqueConstraint('entry_no'),
        sa.ForeignKeyConstraint(['period_month'], ['dim_fiscal_calendar.period_code'])
    )
    op.create_index('ix_journal_entries_date', 'journal_entries', ['entry_date'])
    op.create_index('ix_journal_entries_period', 'journal_entries', ['period_month'])
    op.create_index('ix_journal_entries_status', 'journal_entries', ['status'])
    
    op.create_table('journal_entry_lines',
        sa.Column('line_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('entry_id', sa.Integer(), nullable=False),
        sa.Column('line_number', sa.Integer(), nullable=False),
        sa.Column('account_code', sa.String(64), nullable=False),
        sa.Column('debit_amt', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('credit_amt', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('currency', sa.String(8), nullable=True, server_default='CNY'),
        sa.Column('currency_amt', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('base_amt', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('link_order_id', sa.String(128), nullable=True),
        sa.Column('link_expense_id', sa.Integer(), nullable=True),
        sa.Column('link_invoice_id', sa.Integer(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('line_id'),
        sa.ForeignKeyConstraint(['entry_id'], ['journal_entries.entry_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['account_code'], ['gl_accounts.account_code']),
        sa.UniqueConstraint('entry_id', 'line_number', name='uq_journal_line')
    )
    op.create_index('ix_journal_lines_entry', 'journal_entry_lines', ['entry_id'])
    op.create_index('ix_journal_lines_account', 'journal_entry_lines', ['account_code'])
    
    # 16. 期初余额
    op.create_table('opening_balances',
        sa.Column('balance_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('period', sa.String(16), nullable=False),
        sa.Column('platform_code', sa.String(32), nullable=False),
        sa.Column('shop_id', sa.String(64), nullable=False),
        sa.Column('platform_sku', sa.String(128), nullable=False),
        sa.Column('opening_qty', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('opening_cost', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('opening_value', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('source', sa.String(64), nullable=True, server_default='migration'),
        sa.Column('migration_batch_id', sa.String(64), nullable=True),
        sa.Column('created_by', sa.String(64), nullable=True, server_default='system'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('balance_id'),
        sa.UniqueConstraint('period', 'platform_code', 'shop_id', 'platform_sku', name='uq_opening_balance')
    )
    op.create_index('ix_opening_balances_period', 'opening_balances', ['period'])
    op.create_index('ix_opening_balances_sku', 'opening_balances', ['platform_code', 'shop_id', 'platform_sku'])
    
    # 17. 审批日志
    op.create_table('approval_logs',
        sa.Column('log_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('entity_type', sa.String(64), nullable=False),
        sa.Column('entity_id', sa.String(128), nullable=False),
        sa.Column('approver', sa.String(64), nullable=False),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('log_id')
    )
    op.create_index('ix_approval_logs_entity', 'approval_logs', ['entity_type', 'entity_id'])
    op.create_index('ix_approval_logs_approver', 'approval_logs', ['approver', 'status'])
    
    # 18. 退货单
    op.create_table('return_orders',
        sa.Column('return_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('original_order_id', sa.String(128), nullable=False),
        sa.Column('return_type', sa.String(32), nullable=False),
        sa.Column('platform_code', sa.String(32), nullable=False),
        sa.Column('shop_id', sa.String(64), nullable=False),
        sa.Column('platform_sku', sa.String(128), nullable=False),
        sa.Column('qty', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('refund_amt', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('restocking_fee', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('return_id')
    )
    op.create_index('ix_return_orders_original', 'return_orders', ['original_order_id'])
    op.create_index('ix_return_orders_shop', 'return_orders', ['platform_code', 'shop_id'])


def downgrade():
    """回滚schema变更"""
    
    # 按依赖顺序逆序删除表
    op.drop_table('return_orders')
    op.drop_table('approval_logs')
    op.drop_table('opening_balances')
    op.drop_table('journal_entry_lines')
    op.drop_table('journal_entries')
    op.drop_table('gl_accounts')
    op.drop_table('tax_reports')
    op.drop_table('tax_vouchers')
    op.drop_table('logistics_allocation_rules')
    op.drop_table('logistics_costs')
    op.drop_table('fact_expenses_allocated_day_shop_sku')
    op.drop_table('allocation_rules')
    op.drop_table('fact_expenses_month')
    op.drop_table('three_way_match_log')
    op.drop_table('invoice_attachments')
    op.drop_table('invoice_lines')
    op.drop_table('invoice_headers')
    op.drop_table('inventory_ledger')
    op.drop_table('grn_lines')
    op.drop_table('grn_headers')
    op.drop_table('po_lines')
    op.drop_table('po_headers')
    op.drop_table('dim_vendors')
    op.drop_table('dim_fiscal_calendar')
    op.drop_table('fx_rates')
    op.drop_table('dim_currencies')
    op.drop_table('dim_metric_formulas')
    
    # 回滚FieldMappingDictionary扩展
    op.drop_index('ix_dictionary_status', 'field_mapping_dictionary')
    op.drop_column('field_mapping_dictionary', 'status')
    op.drop_column('field_mapping_dictionary', 'version')


