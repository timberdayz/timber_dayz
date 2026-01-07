"""Add ERP core tables - inventory, finance, user permission

Revision ID: 20251023_0005
Revises: 20251016_0004
Create Date: 2025-10-23 14:00:00.000000

新增表：
- dim_users, dim_roles - 用户权限管理
- fact_inventory, fact_inventory_transactions - 库存管理
- fact_accounts_receivable, fact_payment_receipts, fact_expenses - 财务管理
- fact_order_items - 订单明细
- fact_audit_logs - 操作审计日志

增强表：
- fact_sales_orders - 添加财务、库存、成本利润字段
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251023_0005'
down_revision = '20251016_0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """应用迁移 - 创建新表和添加新字段"""
    
    # ==================== 1. 创建用户权限表 ====================
    print("[1/10] Creating user permission tables...")
    
    # 创建角色表
    op.create_table(
        'dim_roles',
        sa.Column('role_id', sa.BigInteger(), nullable=False),
        sa.Column('role_name', sa.String(length=100), nullable=False),
        sa.Column('role_code', sa.String(length=50), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('permissions', sa.Text(), nullable=False),
        sa.Column('data_scope', sa.String(length=50), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('is_system', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('role_id'),
        sa.UniqueConstraint('role_name'),
        sa.UniqueConstraint('role_code')
    )
    op.create_index('idx_roles_active', 'dim_roles', ['is_active'])
    
    # 创建用户表
    op.create_table(
        'dim_users',
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('username', sa.String(length=100), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=200), nullable=True),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('is_superuser', sa.Boolean(), nullable=False),
        sa.Column('allowed_platforms', sa.Text(), nullable=True),
        sa.Column('allowed_shops', sa.Text(), nullable=True),
        sa.Column('phone', sa.String(length=50), nullable=True),
        sa.Column('department', sa.String(length=100), nullable=True),
        sa.Column('position', sa.String(length=100), nullable=True),
        sa.Column('last_login', sa.DateTime(), nullable=True),
        sa.Column('login_count', sa.Integer(), nullable=True),
        sa.Column('failed_login_attempts', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('user_id'),
        sa.UniqueConstraint('username'),
        sa.UniqueConstraint('email')
    )
    op.create_index('idx_users_active', 'dim_users', ['is_active'])
    op.create_index('idx_users_email_active', 'dim_users', ['email', 'is_active'])
    
    # 创建用户-角色关联表
    op.create_table(
        'user_roles',
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('role_id', sa.BigInteger(), nullable=False),
        sa.Column('assigned_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('assigned_by', sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(['role_id'], ['dim_roles.role_id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['dim_users.user_id'], ),
        sa.PrimaryKeyConstraint('user_id', 'role_id')
    )
    
    # ==================== 2. 创建审计日志表 ====================
    print("[2/10] Creating audit log table...")
    
    op.create_table(
        'fact_audit_logs',
        sa.Column('log_id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('username', sa.String(length=100), nullable=False),
        sa.Column('action_type', sa.String(length=50), nullable=False),
        sa.Column('resource_type', sa.String(length=100), nullable=False),
        sa.Column('resource_id', sa.String(length=150), nullable=True),
        sa.Column('action_description', sa.Text(), nullable=True),
        sa.Column('changes_json', sa.Text(), nullable=True),
        sa.Column('ip_address', sa.String(length=50), nullable=True),
        sa.Column('user_agent', sa.String(length=500), nullable=True),
        sa.Column('is_success', sa.Boolean(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['dim_users.user_id'], ),
        sa.PrimaryKeyConstraint('log_id')
    )
    op.create_index('idx_audit_user_time', 'fact_audit_logs', ['user_id', 'created_at'])
    op.create_index('idx_audit_action_time', 'fact_audit_logs', ['action_type', 'created_at'])
    op.create_index('idx_audit_resource', 'fact_audit_logs', ['resource_type', 'resource_id'])
    op.create_index('idx_audit_recent', 'fact_audit_logs', ['created_at'])
    
    # ==================== 3. 创建库存管理表 ====================
    print("[3/10] Creating inventory tables...")
    
    # 创建库存主表
    op.create_table(
        'fact_inventory',
        sa.Column('inventory_id', sa.BigInteger(), nullable=False),
        sa.Column('platform_code', sa.String(length=50), nullable=False),
        sa.Column('shop_id', sa.String(length=100), nullable=False),
        sa.Column('warehouse_code', sa.String(length=50), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('quantity_on_hand', sa.Integer(), nullable=False),
        sa.Column('quantity_available', sa.Integer(), nullable=False),
        sa.Column('quantity_reserved', sa.Integer(), nullable=False),
        sa.Column('quantity_incoming', sa.Integer(), nullable=False),
        sa.Column('avg_cost', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('total_value', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('safety_stock', sa.Integer(), nullable=True),
        sa.Column('reorder_point', sa.Integer(), nullable=True),
        sa.Column('last_updated', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['product_id'], ['dim_product.product_surrogate_id'], ),
        sa.PrimaryKeyConstraint('inventory_id'),
        sa.UniqueConstraint('platform_code', 'shop_id', 'warehouse_code', 'product_id', name='uq_inventory_location_product')
    )
    op.create_index('idx_inventory_platform_shop', 'fact_inventory', ['platform_code', 'shop_id'])
    # Note: 部分索引(低库存)在PostgreSQL中手动创建
    
    # 创建库存流水表
    op.create_table(
        'fact_inventory_transactions',
        sa.Column('transaction_id', sa.BigInteger(), nullable=False),
        sa.Column('inventory_id', sa.BigInteger(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=True),
        sa.Column('transaction_type', sa.String(length=50), nullable=False),
        sa.Column('reference_type', sa.String(length=50), nullable=True),
        sa.Column('reference_id', sa.String(length=150), nullable=True),
        sa.Column('quantity_change', sa.Integer(), nullable=False),
        sa.Column('quantity_before', sa.Integer(), nullable=True),
        sa.Column('quantity_after', sa.Integer(), nullable=True),
        sa.Column('unit_cost', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('total_cost', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('operator_id', sa.String(length=100), nullable=True),
        sa.Column('transaction_time', sa.DateTime(), nullable=False),
        sa.Column('notes', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['inventory_id'], ['fact_inventory.inventory_id'], ),
        sa.ForeignKeyConstraint(['product_id'], ['dim_product.product_surrogate_id'], ),
        sa.PrimaryKeyConstraint('transaction_id')
    )
    op.create_index('idx_inv_trans_reference', 'fact_inventory_transactions', ['reference_type', 'reference_id'])
    op.create_index('idx_inv_trans_type_time', 'fact_inventory_transactions', ['transaction_type', 'transaction_time'])
    
    # ==================== 4. 创建财务管理表 ====================
    print("[4/10] Creating finance tables...")
    
    # 创建应收账款表
    op.create_table(
        'fact_accounts_receivable',
        sa.Column('ar_id', sa.BigInteger(), nullable=False),
        sa.Column('order_id', sa.BigInteger(), nullable=False),
        sa.Column('platform_code', sa.String(length=50), nullable=False),
        sa.Column('shop_id', sa.String(length=100), nullable=False),
        sa.Column('ar_amount_cny', sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column('received_amount_cny', sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column('outstanding_amount_cny', sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column('invoice_date', sa.Date(), nullable=True),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('payment_terms', sa.String(length=50), nullable=True),
        sa.Column('ar_status', sa.String(length=50), nullable=False),
        sa.Column('is_overdue', sa.Boolean(), nullable=True),
        sa.Column('overdue_days', sa.Integer(), nullable=True),
        sa.Column('last_payment_date', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['order_id'], ['fact_sales_orders.id'], ),
        sa.PrimaryKeyConstraint('ar_id')
    )
    op.create_index('idx_ar_status_due', 'fact_accounts_receivable', ['ar_status', 'due_date'])
    op.create_index('idx_ar_overdue', 'fact_accounts_receivable', ['is_overdue', 'overdue_days'])
    op.create_index('idx_ar_platform_shop', 'fact_accounts_receivable', ['platform_code', 'shop_id'])
    op.create_index('idx_ar_order', 'fact_accounts_receivable', ['order_id'])
    
    # 创建收款记录表
    op.create_table(
        'fact_payment_receipts',
        sa.Column('receipt_id', sa.BigInteger(), nullable=False),
        sa.Column('ar_id', sa.BigInteger(), nullable=False),
        sa.Column('receipt_date', sa.Date(), nullable=False),
        sa.Column('receipt_amount_cny', sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column('payment_method', sa.String(length=50), nullable=True),
        sa.Column('bank_account', sa.String(length=100), nullable=True),
        sa.Column('transaction_reference', sa.String(length=150), nullable=True),
        sa.Column('voucher_number', sa.String(length=100), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['ar_id'], ['fact_accounts_receivable.ar_id'], ),
        sa.PrimaryKeyConstraint('receipt_id')
    )
    op.create_index('idx_receipts_date', 'fact_payment_receipts', ['receipt_date'])
    op.create_index('idx_receipts_ar', 'fact_payment_receipts', ['ar_id'])
    op.create_index('idx_receipts_method', 'fact_payment_receipts', ['payment_method'])
    
    # 创建费用表
    op.create_table(
        'fact_expenses',
        sa.Column('expense_id', sa.BigInteger(), nullable=False),
        sa.Column('platform_code', sa.String(length=50), nullable=False),
        sa.Column('shop_id', sa.String(length=100), nullable=False),
        sa.Column('order_id', sa.BigInteger(), nullable=True),
        sa.Column('expense_type', sa.String(length=50), nullable=False),
        sa.Column('expense_category', sa.String(length=100), nullable=True),
        sa.Column('expense_description', sa.Text(), nullable=True),
        sa.Column('amount', sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column('currency', sa.String(length=10), nullable=False),
        sa.Column('amount_cny', sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column('expense_date', sa.Date(), nullable=False),
        sa.Column('voucher_number', sa.String(length=100), nullable=True),
        sa.Column('invoice_number', sa.String(length=100), nullable=True),
        sa.Column('is_approved', sa.Boolean(), nullable=True),
        sa.Column('approved_by', sa.String(length=100), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['order_id'], ['fact_sales_orders.id'], ),
        sa.PrimaryKeyConstraint('expense_id')
    )
    op.create_index('idx_expenses_platform_date', 'fact_expenses', ['platform_code', 'shop_id', 'expense_date'])
    op.create_index('idx_expenses_order', 'fact_expenses', ['order_id'])
    op.create_index('idx_expenses_category', 'fact_expenses', ['expense_category'])
    
    # ==================== 5. 创建订单明细表 ====================
    print("[5/10] Creating order items table...")
    
    op.create_table(
        'fact_order_items',
        sa.Column('item_id', sa.BigInteger(), nullable=False),
        sa.Column('order_id', sa.BigInteger(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('platform_sku', sa.String(length=150), nullable=True),
        sa.Column('product_name', sa.String(length=500), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('unit_price', sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column('unit_cost', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('line_amount', sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column('line_cost', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('line_profit', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('unit_price_cny', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('line_amount_cny', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('line_cost_cny', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('line_profit_cny', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('refund_quantity', sa.Integer(), nullable=True),
        sa.Column('refund_amount', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('refund_amount_cny', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.ForeignKeyConstraint(['order_id'], ['fact_sales_orders.id'], ),
        sa.ForeignKeyConstraint(['product_id'], ['dim_product.product_surrogate_id'], ),
        sa.PrimaryKeyConstraint('item_id')
    )
    op.create_index('idx_items_order', 'fact_order_items', ['order_id'])
    op.create_index('idx_items_product', 'fact_order_items', ['product_id'])
    op.create_index('idx_items_sku', 'fact_order_items', ['platform_sku'])
    
    # ==================== 6. 增强 fact_sales_orders 表 ====================
    print("[6/10] Enhancing fact_sales_orders table...")
    
    # 添加平台费用字段
    op.add_column('fact_sales_orders', sa.Column('platform_commission', sa.Numeric(precision=15, scale=2), nullable=True))
    op.add_column('fact_sales_orders', sa.Column('payment_fee', sa.Numeric(precision=15, scale=2), nullable=True))
    op.add_column('fact_sales_orders', sa.Column('shipping_fee', sa.Numeric(precision=15, scale=2), nullable=True))
    
    # 添加汇率和人民币金额
    op.add_column('fact_sales_orders', sa.Column('exchange_rate', sa.Numeric(precision=10, scale=4), nullable=True))
    op.add_column('fact_sales_orders', sa.Column('gmv_cny', sa.Numeric(precision=15, scale=2), nullable=True))
    
    # 添加成本和利润字段
    op.add_column('fact_sales_orders', sa.Column('cost_amount_cny', sa.Numeric(precision=15, scale=2), nullable=True))
    op.add_column('fact_sales_orders', sa.Column('gross_profit_cny', sa.Numeric(precision=15, scale=2), nullable=True))
    op.add_column('fact_sales_orders', sa.Column('net_profit_cny', sa.Numeric(precision=15, scale=2), nullable=True))
    
    # 添加财务关联字段
    op.add_column('fact_sales_orders', sa.Column('is_invoiced', sa.Boolean(), nullable=True))
    op.add_column('fact_sales_orders', sa.Column('invoice_id', sa.Integer(), nullable=True))
    op.add_column('fact_sales_orders', sa.Column('is_payment_received', sa.Boolean(), nullable=True))
    op.add_column('fact_sales_orders', sa.Column('payment_voucher_id', sa.Integer(), nullable=True))
    
    # 添加库存关联字段
    op.add_column('fact_sales_orders', sa.Column('inventory_deducted', sa.Boolean(), nullable=True))
    
    # 添加updated_at字段（如果不存在）
    op.add_column('fact_sales_orders', sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True))
    
    # 添加新索引
    op.create_index('ix_fact_sales_time', 'fact_sales_orders', ['platform_code', 'shop_id', 'order_ts'])
    op.create_index('ix_fact_sales_financial', 'fact_sales_orders', ['is_invoiced', 'is_payment_received'])
    
    print("[OK] Migration completed successfully!")


def downgrade() -> None:
    """回滚迁移 - 删除新表和字段"""
    
    print("[ROLLBACK] Rolling back migration...")
    
    # 删除索引
    op.drop_index('ix_fact_sales_financial', table_name='fact_sales_orders')
    op.drop_index('ix_fact_sales_time', table_name='fact_sales_orders')
    
    # 删除 fact_sales_orders 新增字段
    op.drop_column('fact_sales_orders', 'updated_at')
    op.drop_column('fact_sales_orders', 'inventory_deducted')
    op.drop_column('fact_sales_orders', 'payment_voucher_id')
    op.drop_column('fact_sales_orders', 'is_payment_received')
    op.drop_column('fact_sales_orders', 'invoice_id')
    op.drop_column('fact_sales_orders', 'is_invoiced')
    op.drop_column('fact_sales_orders', 'net_profit_cny')
    op.drop_column('fact_sales_orders', 'gross_profit_cny')
    op.drop_column('fact_sales_orders', 'cost_amount_cny')
    op.drop_column('fact_sales_orders', 'gmv_cny')
    op.drop_column('fact_sales_orders', 'exchange_rate')
    op.drop_column('fact_sales_orders', 'shipping_fee')
    op.drop_column('fact_sales_orders', 'payment_fee')
    op.drop_column('fact_sales_orders', 'platform_commission')
    
    # 删除表
    op.drop_table('fact_order_items')
    op.drop_table('fact_expenses')
    op.drop_table('fact_payment_receipts')
    op.drop_table('fact_accounts_receivable')
    op.drop_table('fact_inventory_transactions')
    op.drop_table('fact_inventory')
    op.drop_table('fact_audit_logs')
    op.drop_table('user_roles')
    op.drop_table('dim_users')
    op.drop_table('dim_roles')
    
    print("[OK] Rollback completed!")

