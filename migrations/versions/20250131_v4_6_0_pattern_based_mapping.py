"""v4.6.0: Pattern-based Mapping and Multi-currency Support

Revision ID: v4_6_0
Revises: 20250131_0013_add_template_parsing_config
Create Date: 2025-01-31 00:00:00.000000

Changes:
1. 新增表：
   - dim_exchange_rates: 汇率维度表（全球180+货币支持）
   - fact_order_amounts: 订单金额维度表（零字段爆炸设计）

2. 扩展表：
   - field_mapping_dictionary: 添加pattern-based mapping字段

3. 架构改进：
   - 维度表设计（替代宽表）
   - 配置驱动映射（零硬编码）
   - CNY本位币标准

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'v4_6_0'
down_revision = '20250131_0013'
branch_labels = None
depends_on = None


def upgrade():
    """Apply v4.6.0 schema changes"""
    
    # 1. 创建DimExchangeRate表（汇率维度表）
    op.create_table(
        'dim_exchange_rates',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('from_currency', sa.String(length=3), nullable=False),
        sa.Column('to_currency', sa.String(length=3), nullable=False),
        sa.Column('rate_date', sa.Date(), nullable=False),
        sa.Column('rate', sa.Float(), nullable=False),
        sa.Column('source', sa.String(length=50), nullable=True),
        sa.Column('priority', sa.Integer(), nullable=True, server_default='99'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('from_currency', 'to_currency', 'rate_date', name='uq_exchange_rate')
    )
    
    # 创建索引
    op.create_index('ix_exchange_rate_lookup', 'dim_exchange_rates', 
                    ['from_currency', 'to_currency', 'rate_date'], unique=False)
    op.create_index('ix_exchange_rate_date', 'dim_exchange_rates', ['rate_date'], unique=False)
    op.create_index('ix_exchange_rates_from', 'dim_exchange_rates', ['from_currency'], unique=False)
    op.create_index('ix_exchange_rates_to', 'dim_exchange_rates', ['to_currency'], unique=False)
    
    # 2. 创建FactOrderAmount表（订单金额维度表）
    op.create_table(
        'fact_order_amounts',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('order_id', sa.String(length=128), nullable=False),
        sa.Column('metric_type', sa.String(length=32), nullable=False),
        sa.Column('metric_subtype', sa.String(length=32), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('amount_original', sa.Float(), nullable=False),
        sa.Column('amount_cny', sa.Float(), nullable=True),
        sa.Column('exchange_rate', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['order_id'], ['fact_orders.order_id'], ondelete='CASCADE')
    )
    
    # 创建索引
    op.create_index('ix_order_amounts_order', 'fact_order_amounts', ['order_id'], unique=False)
    op.create_index('ix_order_amounts_metric', 'fact_order_amounts', 
                    ['metric_type', 'metric_subtype'], unique=False)
    op.create_index('ix_order_amounts_currency', 'fact_order_amounts', 
                    ['currency', 'created_at'], unique=False)
    op.create_index('ix_order_amounts_composite', 'fact_order_amounts', 
                    ['order_id', 'metric_type', 'metric_subtype', 'currency'], unique=False)
    op.create_index('ix_order_amounts_metric_type', 'fact_order_amounts', ['metric_type'], unique=False)
    
    # 3. 扩展FieldMappingDictionary表（添加pattern-based mapping字段）
    op.add_column('field_mapping_dictionary', 
                  sa.Column('is_pattern_based', sa.Boolean(), nullable=False, 
                           server_default='false', comment='是否启用模式匹配'))
    op.add_column('field_mapping_dictionary', 
                  sa.Column('field_pattern', sa.Text(), nullable=True, 
                           comment='字段匹配正则表达式（支持命名组）'))
    op.add_column('field_mapping_dictionary', 
                  sa.Column('dimension_config', postgresql.JSONB(astext_type=sa.Text()), nullable=True, 
                           comment='维度提取配置（如订单状态、货币映射）'))
    op.add_column('field_mapping_dictionary', 
                  sa.Column('target_table', sa.String(length=64), nullable=True, 
                           comment='目标表名（如fact_order_amounts）'))
    op.add_column('field_mapping_dictionary', 
                  sa.Column('target_columns', postgresql.JSONB(astext_type=sa.Text()), nullable=True, 
                           comment='目标列映射配置（如metric_type/metric_subtype）'))
    
    # 创建索引
    op.create_index('ix_dictionary_pattern_based', 'field_mapping_dictionary', 
                    ['is_pattern_based'], unique=False)


def downgrade():
    """Revert v4.6.0 schema changes"""
    
    # 删除索引
    op.drop_index('ix_dictionary_pattern_based', table_name='field_mapping_dictionary')
    
    # 删除FieldMappingDictionary扩展字段
    op.drop_column('field_mapping_dictionary', 'target_columns')
    op.drop_column('field_mapping_dictionary', 'target_table')
    op.drop_column('field_mapping_dictionary', 'dimension_config')
    op.drop_column('field_mapping_dictionary', 'field_pattern')
    op.drop_column('field_mapping_dictionary', 'is_pattern_based')
    
    # 删除FactOrderAmount表
    op.drop_index('ix_order_amounts_metric_type', table_name='fact_order_amounts')
    op.drop_index('ix_order_amounts_composite', table_name='fact_order_amounts')
    op.drop_index('ix_order_amounts_currency', table_name='fact_order_amounts')
    op.drop_index('ix_order_amounts_metric', table_name='fact_order_amounts')
    op.drop_index('ix_order_amounts_order', table_name='fact_order_amounts')
    op.drop_table('fact_order_amounts')
    
    # 删除DimExchangeRate表
    op.drop_index('ix_exchange_rates_to', table_name='dim_exchange_rates')
    op.drop_index('ix_exchange_rates_from', table_name='dim_exchange_rates')
    op.drop_index('ix_exchange_rate_date', table_name='dim_exchange_rates')
    op.drop_index('ix_exchange_rate_lookup', table_name='dim_exchange_rates')
    op.drop_table('dim_exchange_rates')



