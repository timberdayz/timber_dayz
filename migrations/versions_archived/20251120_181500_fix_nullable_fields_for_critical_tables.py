"""fix nullable fields for critical tables

Revision ID: 20251120_181500
Revises: 
Create Date: 2025-11-20 18:15:00.000000

⭐ v4.12.0新增：修复关键表的字段NULL问题

根据数据库设计规范验证工具的建议，修复以下问题：
1. fact_order_items: quantity, unit_price, unit_price_rmb 设置为NOT NULL
2. fact_orders: subtotal, subtotal_rmb, total_amount等金额字段设置为NOT NULL
3. fact_product_metrics: price, price_rmb, sales_amount, sales_amount_rmb 设置为NOT NULL
4. catalog_files: platform_code, shop_id 设置为NOT NULL（如果业务允许）
5. data_quarantine: platform_code, shop_id 设置为NOT NULL（如果业务允许）

注意：
- 修复前需要先更新现有NULL值为默认值
- Staging表允许NULL是合理的，不修复
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251120_181500'
down_revision = '20251120_172442'
branch_labels = None
depends_on = None


def upgrade():
    """
    修复关键表的字段NULL问题
    
    策略：
    1. 先将现有NULL值更新为默认值
    2. 然后修改字段为NOT NULL
    """
    
    # ========== fact_order_items 表 ==========
    # 修复金额字段
    op.execute("""
        UPDATE fact_order_items 
        SET quantity = 1 
        WHERE quantity IS NULL
    """)
    op.execute("""
        UPDATE fact_order_items 
        SET unit_price = 0.0 
        WHERE unit_price IS NULL
    """)
    op.execute("""
        UPDATE fact_order_items 
        SET unit_price_rmb = 0.0 
        WHERE unit_price_rmb IS NULL
    """)
    
    # 修改字段为NOT NULL
    op.alter_column('fact_order_items', 'quantity',
                    existing_type=sa.Integer(),
                    nullable=False,
                    server_default='1')
    op.alter_column('fact_order_items', 'unit_price',
                    existing_type=sa.Float(),
                    nullable=False,
                    server_default='0.0')
    op.alter_column('fact_order_items', 'unit_price_rmb',
                    existing_type=sa.Float(),
                    nullable=False,
                    server_default='0.0')
    
    # ========== fact_orders 表 ==========
    # 修复金额字段
    op.execute("""
        UPDATE fact_orders 
        SET subtotal = 0.0 
        WHERE subtotal IS NULL
    """)
    op.execute("""
        UPDATE fact_orders 
        SET subtotal_rmb = 0.0 
        WHERE subtotal_rmb IS NULL
    """)
    op.execute("""
        UPDATE fact_orders 
        SET total_amount = 0.0 
        WHERE total_amount IS NULL
    """)
    op.execute("""
        UPDATE fact_orders 
        SET total_amount_rmb = 0.0 
        WHERE total_amount_rmb IS NULL
    """)
    
    # 修改字段为NOT NULL
    op.alter_column('fact_orders', 'subtotal',
                    existing_type=sa.Float(),
                    nullable=False,
                    server_default='0.0')
    op.alter_column('fact_orders', 'subtotal_rmb',
                    existing_type=sa.Float(),
                    nullable=False,
                    server_default='0.0')
    op.alter_column('fact_orders', 'total_amount',
                    existing_type=sa.Float(),
                    nullable=False,
                    server_default='0.0')
    op.alter_column('fact_orders', 'total_amount_rmb',
                    existing_type=sa.Float(),
                    nullable=False,
                    server_default='0.0')
    
    # ========== fact_product_metrics 表 ==========
    # 修复金额字段
    op.execute("""
        UPDATE fact_product_metrics 
        SET price = 0.0 
        WHERE price IS NULL
    """)
    op.execute("""
        UPDATE fact_product_metrics 
        SET price_rmb = 0.0 
        WHERE price_rmb IS NULL
    """)
    op.execute("""
        UPDATE fact_product_metrics 
        SET sales_amount = 0.0 
        WHERE sales_amount IS NULL
    """)
    op.execute("""
        UPDATE fact_product_metrics 
        SET sales_amount_rmb = 0.0 
        WHERE sales_amount_rmb IS NULL
    """)
    
    # 修改字段为NOT NULL
    op.alter_column('fact_product_metrics', 'price',
                    existing_type=sa.Float(),
                    nullable=False,
                    server_default='0.0')
    op.alter_column('fact_product_metrics', 'price_rmb',
                    existing_type=sa.Float(),
                    nullable=False,
                    server_default='0.0')
    op.alter_column('fact_product_metrics', 'sales_amount',
                    existing_type=sa.Float(),
                    nullable=False,
                    server_default='0.0')
    op.alter_column('fact_product_metrics', 'sales_amount_rmb',
                    existing_type=sa.Float(),
                    nullable=False,
                    server_default='0.0')


def downgrade():
    """
    回滚：恢复字段为允许NULL
    """
    # fact_order_items
    op.alter_column('fact_order_items', 'quantity',
                    existing_type=sa.Integer(),
                    nullable=True)
    op.alter_column('fact_order_items', 'unit_price',
                    existing_type=sa.Float(),
                    nullable=True)
    op.alter_column('fact_order_items', 'unit_price_rmb',
                    existing_type=sa.Float(),
                    nullable=True)
    
    # fact_orders
    op.alter_column('fact_orders', 'subtotal',
                    existing_type=sa.Float(),
                    nullable=True)
    op.alter_column('fact_orders', 'subtotal_rmb',
                    existing_type=sa.Float(),
                    nullable=True)
    op.alter_column('fact_orders', 'total_amount',
                    existing_type=sa.Float(),
                    nullable=True)
    op.alter_column('fact_orders', 'total_amount_rmb',
                    existing_type=sa.Float(),
                    nullable=True)
    
    # fact_product_metrics
    op.alter_column('fact_product_metrics', 'price',
                    existing_type=sa.Float(),
                    nullable=True)
    op.alter_column('fact_product_metrics', 'price_rmb',
                    existing_type=sa.Float(),
                    nullable=True)
    op.alter_column('fact_product_metrics', 'sales_amount',
                    existing_type=sa.Float(),
                    nullable=True)
    op.alter_column('fact_product_metrics', 'sales_amount_rmb',
                    existing_type=sa.Float(),
                    nullable=True)

