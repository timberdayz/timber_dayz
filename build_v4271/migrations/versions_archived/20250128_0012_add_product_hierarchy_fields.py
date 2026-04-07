"""Add product hierarchy and governance fields to fact_product_metrics

Revision ID: 20250128_0012
Revises: 20251027_0011
Create Date: 2025-01-28 10:00:00

产品层级与数据治理增强：
1. 添加sku_scope字段（product/variant，支持商品级与规格级并存）
2. 添加parent_platform_sku字段（规格级指向商品级SKU）
3. 添加source_catalog_id字段（数据血缘：来源文件ID）
4. 添加period_start字段（周/月区间起始）
5. 添加metric_date_utc字段（UTC日期，跨时区）
6. 添加order_count字段（订单数统计）
7. 更新唯一索引（加入sku_scope，避免商品级与规格级互相覆盖）
8. 创建新索引（支持父SKU聚合查询）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '20250128_0012'
down_revision: Union[str, None] = '20251027_0011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """升级到产品层级与治理架构"""
    
    # 1. 添加层级与主从关系字段
    op.add_column('fact_product_metrics',
        sa.Column('sku_scope', sa.String(8), nullable=False,
                 server_default='product',
                 comment='SKU粒度：product(商品级) | variant(规格级)'))
    
    op.add_column('fact_product_metrics',
        sa.Column('parent_platform_sku', sa.String(128), nullable=True,
                 comment='父级SKU（当sku_scope=variant时指向商品级SKU）'))
    
    # 2. 添加数据血缘字段
    op.add_column('fact_product_metrics',
        sa.Column('source_catalog_id', sa.Integer, nullable=True,
                 comment='来源文件ID（外键到catalog_files.id）'))
    
    # 3. 添加跨时区与区间留痕字段
    op.add_column('fact_product_metrics',
        sa.Column('period_start', sa.Date, nullable=True,
                 comment='周/月统计区间起始日（用于追溯）'))
    
    op.add_column('fact_product_metrics',
        sa.Column('metric_date_utc', sa.Date, nullable=True,
                 comment='UTC日期（按店铺时区换算）'))
    
    # 4. 添加订单统计字段（流量/店铺报表常见）
    op.add_column('fact_product_metrics',
        sa.Column('order_count', sa.Integer, nullable=True,
                 server_default='0',
                 comment='订单数统计'))
    
    # 5. 删除旧的唯一索引（不包含sku_scope）
    try:
        op.drop_index('ix_product_unique', table_name='fact_product_metrics')
    except Exception:
        pass  # 可能不存在
    
    # 6. 创建新的唯一索引（加入sku_scope，避免商品级与规格级互相覆盖）
    op.create_index('ix_product_unique_with_scope', 'fact_product_metrics',
                   ['platform_code', 'shop_id', 'platform_sku', 'metric_date', 'granularity', 'sku_scope'],
                   unique=True)
    
    # 7. 创建父SKU聚合查询索引（支持规格级→商品级聚合）
    op.create_index('ix_product_parent_date', 'fact_product_metrics',
                   ['platform_code', 'shop_id', 'parent_platform_sku', 'metric_date'],
                   unique=False)
    
    # 8. 创建外键约束（数据血缘）
    try:
        op.create_foreign_key('fk_product_metrics_catalog', 'fact_product_metrics',
                             'catalog_files', ['source_catalog_id'], ['id'],
                             ondelete='SET NULL')
    except Exception:
        pass  # PostgreSQL可能已自动创建


def downgrade() -> None:
    """回滚到旧架构"""
    
    # 删除外键约束
    try:
        op.drop_constraint('fk_product_metrics_catalog', 'fact_product_metrics', type_='foreignkey')
    except Exception:
        pass
    
    # 删除新索引
    op.drop_index('ix_product_parent_date', table_name='fact_product_metrics')
    op.drop_index('ix_product_unique_with_scope', table_name='fact_product_metrics')
    
    # 恢复旧的唯一索引
    op.create_index('ix_product_unique', 'fact_product_metrics',
                   ['platform_code', 'shop_id', 'platform_sku', 'metric_date', 'granularity'],
                   unique=True)
    
    # 删除新增字段
    op.drop_column('fact_product_metrics', 'order_count')
    op.drop_column('fact_product_metrics', 'metric_date_utc')
    op.drop_column('fact_product_metrics', 'period_start')
    op.drop_column('fact_product_metrics', 'source_catalog_id')
    op.drop_column('fact_product_metrics', 'parent_platform_sku')
    op.drop_column('fact_product_metrics', 'sku_scope')

