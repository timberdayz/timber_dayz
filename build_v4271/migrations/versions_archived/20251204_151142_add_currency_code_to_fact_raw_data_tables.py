"""add_currency_code_to_fact_raw_data_tables

Revision ID: 20251204_151142
Revises: 20251126_132151
Create Date: 2025-12-04 15:11:42.000000

v4.15.0新增：为所有fact_raw_data_*表添加currency_code字段
- 支持货币代码提取和存储
- 添加索引以提升查询性能
- 字段类型：String(3), nullable=True
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20251204_151142'
down_revision = '20251126_132151'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 所有fact_raw_data_*表列表
    tables = [
        'fact_raw_data_orders_daily',
        'fact_raw_data_orders_weekly',
        'fact_raw_data_orders_monthly',
        'fact_raw_data_products_daily',
        'fact_raw_data_products_weekly',
        'fact_raw_data_products_monthly',
        'fact_raw_data_traffic_daily',
        'fact_raw_data_traffic_weekly',
        'fact_raw_data_traffic_monthly',
        'fact_raw_data_services_daily',
        'fact_raw_data_services_weekly',
        'fact_raw_data_services_monthly',
        'fact_raw_data_inventory_snapshot',
    ]
    
    # 为每个表添加currency_code字段和索引
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())
    
    for table_name in tables:
        # 检查表是否存在
        if table_name not in existing_tables:
            print(f"[SKIP] 表 {table_name} 不存在，跳过")
            continue
        
        # ⭐ 检查字段是否已存在（避免重复添加）
        try:
            columns = [col['name'] for col in inspector.get_columns(table_name)]
        except Exception as e:
            print(f"[SKIP] 无法获取表 {table_name} 的列信息: {e}")
            continue
        
        if 'currency_code' not in columns:
            # 添加currency_code字段
            op.add_column(
                table_name,
                sa.Column('currency_code', sa.String(length=3), nullable=True, comment='货币代码（ISO 3位代码，如BRL/COP/SGD）')
            )
        
        # 检查索引是否已存在
        indexes = [idx['name'] for idx in inspector.get_indexes(table_name)]
        index_name = f'ix_{table_name}_currency'
        if index_name not in indexes:
            # 添加索引
            op.create_index(
                index_name,
                table_name,
                ['currency_code']
            )


def downgrade() -> None:
    # 所有fact_raw_data_*表列表
    tables = [
        'fact_raw_data_orders_daily',
        'fact_raw_data_orders_weekly',
        'fact_raw_data_orders_monthly',
        'fact_raw_data_products_daily',
        'fact_raw_data_products_weekly',
        'fact_raw_data_products_monthly',
        'fact_raw_data_traffic_daily',
        'fact_raw_data_traffic_weekly',
        'fact_raw_data_traffic_monthly',
        'fact_raw_data_services_daily',
        'fact_raw_data_services_weekly',
        'fact_raw_data_services_monthly',
        'fact_raw_data_inventory_snapshot',
    ]
    
    # 为每个表删除索引和字段
    for table_name in tables:
        # 删除索引
        op.drop_index(f'ix_{table_name}_currency', table_name=table_name)
        
        # 删除currency_code字段
        op.drop_column(table_name, 'currency_code')

