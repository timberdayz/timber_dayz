"""create operational data tables

Revision ID: 20251121_132800
Revises: 20251120_181500
Create Date: 2025-11-21 13:28:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251121_132800'
down_revision = '20251120_181500'
branch_labels = None
depends_on = None


def upgrade():
    # 创建FactTraffic表（流量数据）
    op.create_table(
        'fact_traffic',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('platform_code', sa.String(length=50), nullable=False),
        sa.Column('shop_id', sa.String(length=100), nullable=True),
        sa.Column('account', sa.String(length=100), nullable=True),
        sa.Column('traffic_date', sa.Date(), nullable=False),
        sa.Column('granularity', sa.String(length=20), nullable=False),
        sa.Column('metric_type', sa.String(length=50), nullable=False),
        sa.Column('metric_value', sa.Numeric(precision=15, scale=2), nullable=False, server_default='0.0'),
        sa.Column('data_domain', sa.String(length=50), nullable=False, server_default='traffic'),
        sa.Column('attributes', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('file_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['file_id'], ['catalog_files.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # 创建索引
    op.create_index('ix_fact_traffic_platform_code', 'fact_traffic', ['platform_code'])
    op.create_index('ix_fact_traffic_shop_id', 'fact_traffic', ['shop_id'])
    op.create_index('ix_fact_traffic_traffic_date', 'fact_traffic', ['traffic_date'])
    op.create_index('ix_fact_traffic_file_id', 'fact_traffic', ['file_id'])
    
    # 创建业务唯一索引（运营数据主键设计规则：shop_id为核心）
    op.create_index(
        'uq_fact_traffic_business',
        'fact_traffic',
        ['platform_code', 'shop_id', 'traffic_date', 'granularity', 'metric_type', 'data_domain'],
        unique=True,
        postgresql_where=sa.text('shop_id IS NOT NULL')
    )
    
    # 创建account替代索引（当shop_id为NULL时）
    op.create_index(
        'uq_fact_traffic_account',
        'fact_traffic',
        ['platform_code', 'account', 'traffic_date', 'granularity', 'metric_type', 'data_domain'],
        unique=True,
        postgresql_where=sa.text('shop_id IS NULL AND account IS NOT NULL')
    )
    
    # 创建FactService表（服务数据）
    op.create_table(
        'fact_service',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('platform_code', sa.String(length=50), nullable=False),
        sa.Column('shop_id', sa.String(length=100), nullable=True),
        sa.Column('account', sa.String(length=100), nullable=True),
        sa.Column('service_date', sa.Date(), nullable=False),
        sa.Column('granularity', sa.String(length=20), nullable=False),
        sa.Column('metric_type', sa.String(length=50), nullable=False),
        sa.Column('metric_value', sa.Numeric(precision=15, scale=2), nullable=False, server_default='0.0'),
        sa.Column('data_domain', sa.String(length=50), nullable=False, server_default='services'),
        sa.Column('attributes', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('file_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['file_id'], ['catalog_files.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # 创建索引
    op.create_index('ix_fact_service_platform_code', 'fact_service', ['platform_code'])
    op.create_index('ix_fact_service_shop_id', 'fact_service', ['shop_id'])
    op.create_index('ix_fact_service_service_date', 'fact_service', ['service_date'])
    op.create_index('ix_fact_service_file_id', 'fact_service', ['file_id'])
    
    # 创建业务唯一索引
    op.create_index(
        'uq_fact_service_business',
        'fact_service',
        ['platform_code', 'shop_id', 'service_date', 'granularity', 'metric_type', 'data_domain'],
        unique=True,
        postgresql_where=sa.text('shop_id IS NOT NULL')
    )
    
    # 创建account替代索引
    op.create_index(
        'uq_fact_service_account',
        'fact_service',
        ['platform_code', 'account', 'service_date', 'granularity', 'metric_type', 'data_domain'],
        unique=True,
        postgresql_where=sa.text('shop_id IS NULL AND account IS NOT NULL')
    )
    
    # 创建FactAnalytics表（分析数据）
    op.create_table(
        'fact_analytics',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('platform_code', sa.String(length=50), nullable=False),
        sa.Column('shop_id', sa.String(length=100), nullable=True),
        sa.Column('account', sa.String(length=100), nullable=True),
        sa.Column('analytics_date', sa.Date(), nullable=False),
        sa.Column('granularity', sa.String(length=20), nullable=False),
        sa.Column('metric_type', sa.String(length=50), nullable=False),
        sa.Column('metric_value', sa.Numeric(precision=15, scale=2), nullable=False, server_default='0.0'),
        sa.Column('data_domain', sa.String(length=50), nullable=False, server_default='analytics'),
        sa.Column('attributes', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('file_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['file_id'], ['catalog_files.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # 创建索引
    op.create_index('ix_fact_analytics_platform_code', 'fact_analytics', ['platform_code'])
    op.create_index('ix_fact_analytics_shop_id', 'fact_analytics', ['shop_id'])
    op.create_index('ix_fact_analytics_analytics_date', 'fact_analytics', ['analytics_date'])
    op.create_index('ix_fact_analytics_file_id', 'fact_analytics', ['file_id'])
    
    # 创建业务唯一索引
    op.create_index(
        'uq_fact_analytics_business',
        'fact_analytics',
        ['platform_code', 'shop_id', 'analytics_date', 'granularity', 'metric_type', 'data_domain'],
        unique=True,
        postgresql_where=sa.text('shop_id IS NOT NULL')
    )
    
    # 创建account替代索引
    op.create_index(
        'uq_fact_analytics_account',
        'fact_analytics',
        ['platform_code', 'account', 'analytics_date', 'granularity', 'metric_type', 'data_domain'],
        unique=True,
        postgresql_where=sa.text('shop_id IS NULL AND account IS NOT NULL')
    )


def downgrade():
    # 删除索引
    op.drop_index('uq_fact_analytics_account', table_name='fact_analytics')
    op.drop_index('uq_fact_analytics_business', table_name='fact_analytics')
    op.drop_index('ix_fact_analytics_file_id', table_name='fact_analytics')
    op.drop_index('ix_fact_analytics_analytics_date', table_name='fact_analytics')
    op.drop_index('ix_fact_analytics_shop_id', table_name='fact_analytics')
    op.drop_index('ix_fact_analytics_platform_code', table_name='fact_analytics')
    
    op.drop_index('uq_fact_service_account', table_name='fact_service')
    op.drop_index('uq_fact_service_business', table_name='fact_service')
    op.drop_index('ix_fact_service_file_id', table_name='fact_service')
    op.drop_index('ix_fact_service_service_date', table_name='fact_service')
    op.drop_index('ix_fact_service_shop_id', table_name='fact_service')
    op.drop_index('ix_fact_service_platform_code', table_name='fact_service')
    
    op.drop_index('uq_fact_traffic_account', table_name='fact_traffic')
    op.drop_index('uq_fact_traffic_business', table_name='fact_traffic')
    op.drop_index('ix_fact_traffic_file_id', table_name='fact_traffic')
    op.drop_index('ix_fact_traffic_traffic_date', table_name='fact_traffic')
    op.drop_index('ix_fact_traffic_shop_id', table_name='fact_traffic')
    op.drop_index('ix_fact_traffic_platform_code', table_name='fact_traffic')
    
    # 删除表
    op.drop_table('fact_analytics')
    op.drop_table('fact_service')
    op.drop_table('fact_traffic')

