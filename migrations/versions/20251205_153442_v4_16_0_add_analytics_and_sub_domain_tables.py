"""v4_16_0_add_analytics_and_sub_domain_tables

Revision ID: 20251205_153442
Revises: 20251204_151142
Create Date: 2025-12-05 15:34:42.000000

v4.16.0架构调整：
1. 创建fact_raw_data_analytics_*表（traffic域已迁移到analytics）
2. 创建按sub_domain分表的fact_raw_data_services_*表（ai_assistant和agent子类型）
3. 为services子类型表添加sub_domain字段和索引
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251205_153442'
down_revision = '20251204_151142'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==================== Analytics数据域表（traffic域已迁移到analytics）====================
    
    # Analytics Daily
    op.create_table(
        'fact_raw_data_analytics_daily',
        sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('platform_code', sa.String(length=32), nullable=False),
        sa.Column('shop_id', sa.String(length=256), nullable=True),
        sa.Column('data_domain', sa.String(length=64), nullable=False, server_default='analytics'),
        sa.Column('granularity', sa.String(length=32), nullable=False, server_default='daily'),
        sa.Column('metric_date', sa.Date(), nullable=False),
        sa.Column('file_id', sa.Integer(), nullable=True),
        sa.Column('raw_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('header_columns', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('data_hash', sa.String(length=64), nullable=False),
        sa.Column('ingest_timestamp', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('currency_code', sa.String(length=3), nullable=True, comment='货币代码（ISO 3位代码，如BRL/COP/SGD）'),
        sa.ForeignKeyConstraint(['file_id'], ['catalog_files.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('data_domain', 'granularity', 'data_hash', name='uq_raw_data_analytics_daily_hash')
    )
    op.create_index('ix_raw_data_analytics_daily_hash', 'fact_raw_data_analytics_daily', ['data_hash'])
    op.create_index('ix_raw_data_analytics_daily_domain_gran_date', 'fact_raw_data_analytics_daily', ['data_domain', 'granularity', 'metric_date'])
    op.create_index('ix_raw_data_analytics_daily_gin', 'fact_raw_data_analytics_daily', ['raw_data'], postgresql_using='gin')
    op.create_index('ix_raw_data_analytics_daily_currency', 'fact_raw_data_analytics_daily', ['currency_code'])
    op.create_index('ix_raw_data_analytics_daily_platform_code', 'fact_raw_data_analytics_daily', ['platform_code'])
    op.create_index('ix_raw_data_analytics_daily_shop_id', 'fact_raw_data_analytics_daily', ['shop_id'])
    op.create_index('ix_raw_data_analytics_daily_metric_date', 'fact_raw_data_analytics_daily', ['metric_date'])
    op.create_index('ix_raw_data_analytics_daily_file_id', 'fact_raw_data_analytics_daily', ['file_id'])
    op.create_index('ix_raw_data_analytics_daily_data_domain', 'fact_raw_data_analytics_daily', ['data_domain'])
    
    # Analytics Weekly
    op.create_table(
        'fact_raw_data_analytics_weekly',
        sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('platform_code', sa.String(length=32), nullable=False),
        sa.Column('shop_id', sa.String(length=256), nullable=True),
        sa.Column('data_domain', sa.String(length=64), nullable=False, server_default='analytics'),
        sa.Column('granularity', sa.String(length=32), nullable=False, server_default='weekly'),
        sa.Column('metric_date', sa.Date(), nullable=False),
        sa.Column('file_id', sa.Integer(), nullable=True),
        sa.Column('raw_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('header_columns', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('data_hash', sa.String(length=64), nullable=False),
        sa.Column('ingest_timestamp', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('currency_code', sa.String(length=3), nullable=True, comment='货币代码（ISO 3位代码，如BRL/COP/SGD）'),
        sa.ForeignKeyConstraint(['file_id'], ['catalog_files.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('data_domain', 'granularity', 'data_hash', name='uq_raw_data_analytics_weekly_hash')
    )
    op.create_index('ix_raw_data_analytics_weekly_hash', 'fact_raw_data_analytics_weekly', ['data_hash'])
    op.create_index('ix_raw_data_analytics_weekly_domain_gran_date', 'fact_raw_data_analytics_weekly', ['data_domain', 'granularity', 'metric_date'])
    op.create_index('ix_raw_data_analytics_weekly_gin', 'fact_raw_data_analytics_weekly', ['raw_data'], postgresql_using='gin')
    op.create_index('ix_raw_data_analytics_weekly_currency', 'fact_raw_data_analytics_weekly', ['currency_code'])
    op.create_index('ix_raw_data_analytics_weekly_platform_code', 'fact_raw_data_analytics_weekly', ['platform_code'])
    op.create_index('ix_raw_data_analytics_weekly_shop_id', 'fact_raw_data_analytics_weekly', ['shop_id'])
    op.create_index('ix_raw_data_analytics_weekly_metric_date', 'fact_raw_data_analytics_weekly', ['metric_date'])
    op.create_index('ix_raw_data_analytics_weekly_file_id', 'fact_raw_data_analytics_weekly', ['file_id'])
    op.create_index('ix_raw_data_analytics_weekly_data_domain', 'fact_raw_data_analytics_weekly', ['data_domain'])
    
    # Analytics Monthly
    op.create_table(
        'fact_raw_data_analytics_monthly',
        sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('platform_code', sa.String(length=32), nullable=False),
        sa.Column('shop_id', sa.String(length=256), nullable=True),
        sa.Column('data_domain', sa.String(length=64), nullable=False, server_default='analytics'),
        sa.Column('granularity', sa.String(length=32), nullable=False, server_default='monthly'),
        sa.Column('metric_date', sa.Date(), nullable=False),
        sa.Column('file_id', sa.Integer(), nullable=True),
        sa.Column('raw_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('header_columns', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('data_hash', sa.String(length=64), nullable=False),
        sa.Column('ingest_timestamp', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('currency_code', sa.String(length=3), nullable=True, comment='货币代码（ISO 3位代码，如BRL/COP/SGD）'),
        sa.ForeignKeyConstraint(['file_id'], ['catalog_files.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('data_domain', 'granularity', 'data_hash', name='uq_raw_data_analytics_monthly_hash')
    )
    op.create_index('ix_raw_data_analytics_monthly_hash', 'fact_raw_data_analytics_monthly', ['data_hash'])
    op.create_index('ix_raw_data_analytics_monthly_domain_gran_date', 'fact_raw_data_analytics_monthly', ['data_domain', 'granularity', 'metric_date'])
    op.create_index('ix_raw_data_analytics_monthly_gin', 'fact_raw_data_analytics_monthly', ['raw_data'], postgresql_using='gin')
    op.create_index('ix_raw_data_analytics_monthly_currency', 'fact_raw_data_analytics_monthly', ['currency_code'])
    op.create_index('ix_raw_data_analytics_monthly_platform_code', 'fact_raw_data_analytics_monthly', ['platform_code'])
    op.create_index('ix_raw_data_analytics_monthly_shop_id', 'fact_raw_data_analytics_monthly', ['shop_id'])
    op.create_index('ix_raw_data_analytics_monthly_metric_date', 'fact_raw_data_analytics_monthly', ['metric_date'])
    op.create_index('ix_raw_data_analytics_monthly_file_id', 'fact_raw_data_analytics_monthly', ['file_id'])
    op.create_index('ix_raw_data_analytics_monthly_data_domain', 'fact_raw_data_analytics_monthly', ['data_domain'])
    
    # ==================== Services数据域按sub_domain分表（ai_assistant子类型）====================
    
    # Services AI Assistant Daily
    op.create_table(
        'fact_raw_data_services_ai_assistant_daily',
        sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('platform_code', sa.String(length=32), nullable=False),
        sa.Column('shop_id', sa.String(length=256), nullable=True),
        sa.Column('data_domain', sa.String(length=64), nullable=False, server_default='services'),
        sa.Column('sub_domain', sa.String(length=64), nullable=False, server_default='ai_assistant'),
        sa.Column('granularity', sa.String(length=32), nullable=False, server_default='daily'),
        sa.Column('metric_date', sa.Date(), nullable=False),
        sa.Column('file_id', sa.Integer(), nullable=True),
        sa.Column('raw_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('header_columns', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('data_hash', sa.String(length=64), nullable=False),
        sa.Column('ingest_timestamp', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('currency_code', sa.String(length=3), nullable=True, comment='货币代码（ISO 3位代码，如BRL/COP/SGD）'),
        sa.ForeignKeyConstraint(['file_id'], ['catalog_files.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('data_domain', 'sub_domain', 'granularity', 'data_hash', name='uq_raw_data_services_ai_assistant_daily_hash')
    )
    op.create_index('ix_raw_data_services_ai_assistant_daily_hash', 'fact_raw_data_services_ai_assistant_daily', ['data_hash'])
    op.create_index('ix_raw_data_services_ai_assistant_daily_domain_sub_gran_date', 'fact_raw_data_services_ai_assistant_daily', ['data_domain', 'sub_domain', 'granularity', 'metric_date'])
    op.create_index('ix_raw_data_services_ai_assistant_daily_gin', 'fact_raw_data_services_ai_assistant_daily', ['raw_data'], postgresql_using='gin')
    op.create_index('ix_raw_data_services_ai_assistant_daily_currency', 'fact_raw_data_services_ai_assistant_daily', ['currency_code'])
    op.create_index('ix_raw_data_services_ai_assistant_daily_platform_code', 'fact_raw_data_services_ai_assistant_daily', ['platform_code'])
    op.create_index('ix_raw_data_services_ai_assistant_daily_shop_id', 'fact_raw_data_services_ai_assistant_daily', ['shop_id'])
    op.create_index('ix_raw_data_services_ai_assistant_daily_metric_date', 'fact_raw_data_services_ai_assistant_daily', ['metric_date'])
    op.create_index('ix_raw_data_services_ai_assistant_daily_file_id', 'fact_raw_data_services_ai_assistant_daily', ['file_id'])
    op.create_index('ix_raw_data_services_ai_assistant_daily_data_domain', 'fact_raw_data_services_ai_assistant_daily', ['data_domain'])
    op.create_index('ix_raw_data_services_ai_assistant_daily_sub_domain', 'fact_raw_data_services_ai_assistant_daily', ['sub_domain'])
    
    # Services AI Assistant Weekly
    op.create_table(
        'fact_raw_data_services_ai_assistant_weekly',
        sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('platform_code', sa.String(length=32), nullable=False),
        sa.Column('shop_id', sa.String(length=256), nullable=True),
        sa.Column('data_domain', sa.String(length=64), nullable=False, server_default='services'),
        sa.Column('sub_domain', sa.String(length=64), nullable=False, server_default='ai_assistant'),
        sa.Column('granularity', sa.String(length=32), nullable=False, server_default='weekly'),
        sa.Column('metric_date', sa.Date(), nullable=False),
        sa.Column('file_id', sa.Integer(), nullable=True),
        sa.Column('raw_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('header_columns', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('data_hash', sa.String(length=64), nullable=False),
        sa.Column('ingest_timestamp', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('currency_code', sa.String(length=3), nullable=True, comment='货币代码（ISO 3位代码，如BRL/COP/SGD）'),
        sa.ForeignKeyConstraint(['file_id'], ['catalog_files.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('data_domain', 'sub_domain', 'granularity', 'data_hash', name='uq_raw_data_services_ai_assistant_weekly_hash')
    )
    op.create_index('ix_raw_data_services_ai_assistant_weekly_hash', 'fact_raw_data_services_ai_assistant_weekly', ['data_hash'])
    op.create_index('ix_raw_data_services_ai_assistant_weekly_domain_sub_gran_date', 'fact_raw_data_services_ai_assistant_weekly', ['data_domain', 'sub_domain', 'granularity', 'metric_date'])
    op.create_index('ix_raw_data_services_ai_assistant_weekly_gin', 'fact_raw_data_services_ai_assistant_weekly', ['raw_data'], postgresql_using='gin')
    op.create_index('ix_raw_data_services_ai_assistant_weekly_currency', 'fact_raw_data_services_ai_assistant_weekly', ['currency_code'])
    op.create_index('ix_raw_data_services_ai_assistant_weekly_platform_code', 'fact_raw_data_services_ai_assistant_weekly', ['platform_code'])
    op.create_index('ix_raw_data_services_ai_assistant_weekly_shop_id', 'fact_raw_data_services_ai_assistant_weekly', ['shop_id'])
    op.create_index('ix_raw_data_services_ai_assistant_weekly_metric_date', 'fact_raw_data_services_ai_assistant_weekly', ['metric_date'])
    op.create_index('ix_raw_data_services_ai_assistant_weekly_file_id', 'fact_raw_data_services_ai_assistant_weekly', ['file_id'])
    op.create_index('ix_raw_data_services_ai_assistant_weekly_data_domain', 'fact_raw_data_services_ai_assistant_weekly', ['data_domain'])
    op.create_index('ix_raw_data_services_ai_assistant_weekly_sub_domain', 'fact_raw_data_services_ai_assistant_weekly', ['sub_domain'])
    
    # Services AI Assistant Monthly
    op.create_table(
        'fact_raw_data_services_ai_assistant_monthly',
        sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('platform_code', sa.String(length=32), nullable=False),
        sa.Column('shop_id', sa.String(length=256), nullable=True),
        sa.Column('data_domain', sa.String(length=64), nullable=False, server_default='services'),
        sa.Column('sub_domain', sa.String(length=64), nullable=False, server_default='ai_assistant'),
        sa.Column('granularity', sa.String(length=32), nullable=False, server_default='monthly'),
        sa.Column('metric_date', sa.Date(), nullable=False),
        sa.Column('file_id', sa.Integer(), nullable=True),
        sa.Column('raw_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('header_columns', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('data_hash', sa.String(length=64), nullable=False),
        sa.Column('ingest_timestamp', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('currency_code', sa.String(length=3), nullable=True, comment='货币代码（ISO 3位代码，如BRL/COP/SGD）'),
        sa.ForeignKeyConstraint(['file_id'], ['catalog_files.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('data_domain', 'sub_domain', 'granularity', 'data_hash', name='uq_raw_data_services_ai_assistant_monthly_hash')
    )
    op.create_index('ix_raw_data_services_ai_assistant_monthly_hash', 'fact_raw_data_services_ai_assistant_monthly', ['data_hash'])
    op.create_index('ix_raw_data_services_ai_assistant_monthly_domain_sub_gran_date', 'fact_raw_data_services_ai_assistant_monthly', ['data_domain', 'sub_domain', 'granularity', 'metric_date'])
    op.create_index('ix_raw_data_services_ai_assistant_monthly_gin', 'fact_raw_data_services_ai_assistant_monthly', ['raw_data'], postgresql_using='gin')
    op.create_index('ix_raw_data_services_ai_assistant_monthly_currency', 'fact_raw_data_services_ai_assistant_monthly', ['currency_code'])
    op.create_index('ix_raw_data_services_ai_assistant_monthly_platform_code', 'fact_raw_data_services_ai_assistant_monthly', ['platform_code'])
    op.create_index('ix_raw_data_services_ai_assistant_monthly_shop_id', 'fact_raw_data_services_ai_assistant_monthly', ['shop_id'])
    op.create_index('ix_raw_data_services_ai_assistant_monthly_metric_date', 'fact_raw_data_services_ai_assistant_monthly', ['metric_date'])
    op.create_index('ix_raw_data_services_ai_assistant_monthly_file_id', 'fact_raw_data_services_ai_assistant_monthly', ['file_id'])
    op.create_index('ix_raw_data_services_ai_assistant_monthly_data_domain', 'fact_raw_data_services_ai_assistant_monthly', ['data_domain'])
    op.create_index('ix_raw_data_services_ai_assistant_monthly_sub_domain', 'fact_raw_data_services_ai_assistant_monthly', ['sub_domain'])
    
    # ==================== Services数据域按sub_domain分表（agent子类型）====================
    
    # Services Agent Weekly
    op.create_table(
        'fact_raw_data_services_agent_weekly',
        sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('platform_code', sa.String(length=32), nullable=False),
        sa.Column('shop_id', sa.String(length=256), nullable=True),
        sa.Column('data_domain', sa.String(length=64), nullable=False, server_default='services'),
        sa.Column('sub_domain', sa.String(length=64), nullable=False, server_default='agent'),
        sa.Column('granularity', sa.String(length=32), nullable=False, server_default='weekly'),
        sa.Column('metric_date', sa.Date(), nullable=False),
        sa.Column('file_id', sa.Integer(), nullable=True),
        sa.Column('raw_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('header_columns', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('data_hash', sa.String(length=64), nullable=False),
        sa.Column('ingest_timestamp', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('currency_code', sa.String(length=3), nullable=True, comment='货币代码（ISO 3位代码，如BRL/COP/SGD）'),
        sa.ForeignKeyConstraint(['file_id'], ['catalog_files.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('data_domain', 'sub_domain', 'granularity', 'data_hash', name='uq_raw_data_services_agent_weekly_hash')
    )
    op.create_index('ix_raw_data_services_agent_weekly_hash', 'fact_raw_data_services_agent_weekly', ['data_hash'])
    op.create_index('ix_raw_data_services_agent_weekly_domain_sub_gran_date', 'fact_raw_data_services_agent_weekly', ['data_domain', 'sub_domain', 'granularity', 'metric_date'])
    op.create_index('ix_raw_data_services_agent_weekly_gin', 'fact_raw_data_services_agent_weekly', ['raw_data'], postgresql_using='gin')
    op.create_index('ix_raw_data_services_agent_weekly_currency', 'fact_raw_data_services_agent_weekly', ['currency_code'])
    op.create_index('ix_raw_data_services_agent_weekly_platform_code', 'fact_raw_data_services_agent_weekly', ['platform_code'])
    op.create_index('ix_raw_data_services_agent_weekly_shop_id', 'fact_raw_data_services_agent_weekly', ['shop_id'])
    op.create_index('ix_raw_data_services_agent_weekly_metric_date', 'fact_raw_data_services_agent_weekly', ['metric_date'])
    op.create_index('ix_raw_data_services_agent_weekly_file_id', 'fact_raw_data_services_agent_weekly', ['file_id'])
    op.create_index('ix_raw_data_services_agent_weekly_data_domain', 'fact_raw_data_services_agent_weekly', ['data_domain'])
    op.create_index('ix_raw_data_services_agent_weekly_sub_domain', 'fact_raw_data_services_agent_weekly', ['sub_domain'])
    
    # Services Agent Monthly
    op.create_table(
        'fact_raw_data_services_agent_monthly',
        sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('platform_code', sa.String(length=32), nullable=False),
        sa.Column('shop_id', sa.String(length=256), nullable=True),
        sa.Column('data_domain', sa.String(length=64), nullable=False, server_default='services'),
        sa.Column('sub_domain', sa.String(length=64), nullable=False, server_default='agent'),
        sa.Column('granularity', sa.String(length=32), nullable=False, server_default='monthly'),
        sa.Column('metric_date', sa.Date(), nullable=False),
        sa.Column('file_id', sa.Integer(), nullable=True),
        sa.Column('raw_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('header_columns', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('data_hash', sa.String(length=64), nullable=False),
        sa.Column('ingest_timestamp', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('currency_code', sa.String(length=3), nullable=True, comment='货币代码（ISO 3位代码，如BRL/COP/SGD）'),
        sa.ForeignKeyConstraint(['file_id'], ['catalog_files.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('data_domain', 'sub_domain', 'granularity', 'data_hash', name='uq_raw_data_services_agent_monthly_hash')
    )
    op.create_index('ix_raw_data_services_agent_monthly_hash', 'fact_raw_data_services_agent_monthly', ['data_hash'])
    op.create_index('ix_raw_data_services_agent_monthly_domain_sub_gran_date', 'fact_raw_data_services_agent_monthly', ['data_domain', 'sub_domain', 'granularity', 'metric_date'])
    op.create_index('ix_raw_data_services_agent_monthly_gin', 'fact_raw_data_services_agent_monthly', ['raw_data'], postgresql_using='gin')
    op.create_index('ix_raw_data_services_agent_monthly_currency', 'fact_raw_data_services_agent_monthly', ['currency_code'])
    op.create_index('ix_raw_data_services_agent_monthly_platform_code', 'fact_raw_data_services_agent_monthly', ['platform_code'])
    op.create_index('ix_raw_data_services_agent_monthly_shop_id', 'fact_raw_data_services_agent_monthly', ['shop_id'])
    op.create_index('ix_raw_data_services_agent_monthly_metric_date', 'fact_raw_data_services_agent_monthly', ['metric_date'])
    op.create_index('ix_raw_data_services_agent_monthly_file_id', 'fact_raw_data_services_agent_monthly', ['file_id'])
    op.create_index('ix_raw_data_services_agent_monthly_data_domain', 'fact_raw_data_services_agent_monthly', ['data_domain'])
    op.create_index('ix_raw_data_services_agent_monthly_sub_domain', 'fact_raw_data_services_agent_monthly', ['sub_domain'])


def downgrade() -> None:
    # 删除索引
    op.drop_index('ix_raw_data_services_agent_monthly_sub_domain', table_name='fact_raw_data_services_agent_monthly')
    op.drop_index('ix_raw_data_services_agent_monthly_data_domain', table_name='fact_raw_data_services_agent_monthly')
    op.drop_index('ix_raw_data_services_agent_monthly_file_id', table_name='fact_raw_data_services_agent_monthly')
    op.drop_index('ix_raw_data_services_agent_monthly_metric_date', table_name='fact_raw_data_services_agent_monthly')
    op.drop_index('ix_raw_data_services_agent_monthly_shop_id', table_name='fact_raw_data_services_agent_monthly')
    op.drop_index('ix_raw_data_services_agent_monthly_platform_code', table_name='fact_raw_data_services_agent_monthly')
    op.drop_index('ix_raw_data_services_agent_monthly_currency', table_name='fact_raw_data_services_agent_monthly')
    op.drop_index('ix_raw_data_services_agent_monthly_gin', table_name='fact_raw_data_services_agent_monthly')
    op.drop_index('ix_raw_data_services_agent_monthly_domain_sub_gran_date', table_name='fact_raw_data_services_agent_monthly')
    op.drop_index('ix_raw_data_services_agent_monthly_hash', table_name='fact_raw_data_services_agent_monthly')
    
    op.drop_index('ix_raw_data_services_agent_weekly_sub_domain', table_name='fact_raw_data_services_agent_weekly')
    op.drop_index('ix_raw_data_services_agent_weekly_data_domain', table_name='fact_raw_data_services_agent_weekly')
    op.drop_index('ix_raw_data_services_agent_weekly_file_id', table_name='fact_raw_data_services_agent_weekly')
    op.drop_index('ix_raw_data_services_agent_weekly_metric_date', table_name='fact_raw_data_services_agent_weekly')
    op.drop_index('ix_raw_data_services_agent_weekly_shop_id', table_name='fact_raw_data_services_agent_weekly')
    op.drop_index('ix_raw_data_services_agent_weekly_platform_code', table_name='fact_raw_data_services_agent_weekly')
    op.drop_index('ix_raw_data_services_agent_weekly_currency', table_name='fact_raw_data_services_agent_weekly')
    op.drop_index('ix_raw_data_services_agent_weekly_gin', table_name='fact_raw_data_services_agent_weekly')
    op.drop_index('ix_raw_data_services_agent_weekly_domain_sub_gran_date', table_name='fact_raw_data_services_agent_weekly')
    op.drop_index('ix_raw_data_services_agent_weekly_hash', table_name='fact_raw_data_services_agent_weekly')
    
    op.drop_index('ix_raw_data_services_ai_assistant_monthly_sub_domain', table_name='fact_raw_data_services_ai_assistant_monthly')
    op.drop_index('ix_raw_data_services_ai_assistant_monthly_data_domain', table_name='fact_raw_data_services_ai_assistant_monthly')
    op.drop_index('ix_raw_data_services_ai_assistant_monthly_file_id', table_name='fact_raw_data_services_ai_assistant_monthly')
    op.drop_index('ix_raw_data_services_ai_assistant_monthly_metric_date', table_name='fact_raw_data_services_ai_assistant_monthly')
    op.drop_index('ix_raw_data_services_ai_assistant_monthly_shop_id', table_name='fact_raw_data_services_ai_assistant_monthly')
    op.drop_index('ix_raw_data_services_ai_assistant_monthly_platform_code', table_name='fact_raw_data_services_ai_assistant_monthly')
    op.drop_index('ix_raw_data_services_ai_assistant_monthly_currency', table_name='fact_raw_data_services_ai_assistant_monthly')
    op.drop_index('ix_raw_data_services_ai_assistant_monthly_gin', table_name='fact_raw_data_services_ai_assistant_monthly')
    op.drop_index('ix_raw_data_services_ai_assistant_monthly_domain_sub_gran_date', table_name='fact_raw_data_services_ai_assistant_monthly')
    op.drop_index('ix_raw_data_services_ai_assistant_monthly_hash', table_name='fact_raw_data_services_ai_assistant_monthly')
    
    op.drop_index('ix_raw_data_services_ai_assistant_weekly_sub_domain', table_name='fact_raw_data_services_ai_assistant_weekly')
    op.drop_index('ix_raw_data_services_ai_assistant_weekly_data_domain', table_name='fact_raw_data_services_ai_assistant_weekly')
    op.drop_index('ix_raw_data_services_ai_assistant_weekly_file_id', table_name='fact_raw_data_services_ai_assistant_weekly')
    op.drop_index('ix_raw_data_services_ai_assistant_weekly_metric_date', table_name='fact_raw_data_services_ai_assistant_weekly')
    op.drop_index('ix_raw_data_services_ai_assistant_weekly_shop_id', table_name='fact_raw_data_services_ai_assistant_weekly')
    op.drop_index('ix_raw_data_services_ai_assistant_weekly_platform_code', table_name='fact_raw_data_services_ai_assistant_weekly')
    op.drop_index('ix_raw_data_services_ai_assistant_weekly_currency', table_name='fact_raw_data_services_ai_assistant_weekly')
    op.drop_index('ix_raw_data_services_ai_assistant_weekly_gin', table_name='fact_raw_data_services_ai_assistant_weekly')
    op.drop_index('ix_raw_data_services_ai_assistant_weekly_domain_sub_gran_date', table_name='fact_raw_data_services_ai_assistant_weekly')
    op.drop_index('ix_raw_data_services_ai_assistant_weekly_hash', table_name='fact_raw_data_services_ai_assistant_weekly')
    
    op.drop_index('ix_raw_data_services_ai_assistant_daily_sub_domain', table_name='fact_raw_data_services_ai_assistant_daily')
    op.drop_index('ix_raw_data_services_ai_assistant_daily_data_domain', table_name='fact_raw_data_services_ai_assistant_daily')
    op.drop_index('ix_raw_data_services_ai_assistant_daily_file_id', table_name='fact_raw_data_services_ai_assistant_daily')
    op.drop_index('ix_raw_data_services_ai_assistant_daily_metric_date', table_name='fact_raw_data_services_ai_assistant_daily')
    op.drop_index('ix_raw_data_services_ai_assistant_daily_shop_id', table_name='fact_raw_data_services_ai_assistant_daily')
    op.drop_index('ix_raw_data_services_ai_assistant_daily_platform_code', table_name='fact_raw_data_services_ai_assistant_daily')
    op.drop_index('ix_raw_data_services_ai_assistant_daily_currency', table_name='fact_raw_data_services_ai_assistant_daily')
    op.drop_index('ix_raw_data_services_ai_assistant_daily_gin', table_name='fact_raw_data_services_ai_assistant_daily')
    op.drop_index('ix_raw_data_services_ai_assistant_daily_domain_sub_gran_date', table_name='fact_raw_data_services_ai_assistant_daily')
    op.drop_index('ix_raw_data_services_ai_assistant_daily_hash', table_name='fact_raw_data_services_ai_assistant_daily')
    
    op.drop_index('ix_raw_data_analytics_monthly_data_domain', table_name='fact_raw_data_analytics_monthly')
    op.drop_index('ix_raw_data_analytics_monthly_file_id', table_name='fact_raw_data_analytics_monthly')
    op.drop_index('ix_raw_data_analytics_monthly_metric_date', table_name='fact_raw_data_analytics_monthly')
    op.drop_index('ix_raw_data_analytics_monthly_shop_id', table_name='fact_raw_data_analytics_monthly')
    op.drop_index('ix_raw_data_analytics_monthly_platform_code', table_name='fact_raw_data_analytics_monthly')
    op.drop_index('ix_raw_data_analytics_monthly_currency', table_name='fact_raw_data_analytics_monthly')
    op.drop_index('ix_raw_data_analytics_monthly_gin', table_name='fact_raw_data_analytics_monthly')
    op.drop_index('ix_raw_data_analytics_monthly_domain_gran_date', table_name='fact_raw_data_analytics_monthly')
    op.drop_index('ix_raw_data_analytics_monthly_hash', table_name='fact_raw_data_analytics_monthly')
    
    op.drop_index('ix_raw_data_analytics_weekly_data_domain', table_name='fact_raw_data_analytics_weekly')
    op.drop_index('ix_raw_data_analytics_weekly_file_id', table_name='fact_raw_data_analytics_weekly')
    op.drop_index('ix_raw_data_analytics_weekly_metric_date', table_name='fact_raw_data_analytics_weekly')
    op.drop_index('ix_raw_data_analytics_weekly_shop_id', table_name='fact_raw_data_analytics_weekly')
    op.drop_index('ix_raw_data_analytics_weekly_platform_code', table_name='fact_raw_data_analytics_weekly')
    op.drop_index('ix_raw_data_analytics_weekly_currency', table_name='fact_raw_data_analytics_weekly')
    op.drop_index('ix_raw_data_analytics_weekly_gin', table_name='fact_raw_data_analytics_weekly')
    op.drop_index('ix_raw_data_analytics_weekly_domain_gran_date', table_name='fact_raw_data_analytics_weekly')
    op.drop_index('ix_raw_data_analytics_weekly_hash', table_name='fact_raw_data_analytics_weekly')
    
    op.drop_index('ix_raw_data_analytics_daily_data_domain', table_name='fact_raw_data_analytics_daily')
    op.drop_index('ix_raw_data_analytics_daily_file_id', table_name='fact_raw_data_analytics_daily')
    op.drop_index('ix_raw_data_analytics_daily_metric_date', table_name='fact_raw_data_analytics_daily')
    op.drop_index('ix_raw_data_analytics_daily_shop_id', table_name='fact_raw_data_analytics_daily')
    op.drop_index('ix_raw_data_analytics_daily_platform_code', table_name='fact_raw_data_analytics_daily')
    op.drop_index('ix_raw_data_analytics_daily_currency', table_name='fact_raw_data_analytics_daily')
    op.drop_index('ix_raw_data_analytics_daily_gin', table_name='fact_raw_data_analytics_daily')
    op.drop_index('ix_raw_data_analytics_daily_domain_gran_date', table_name='fact_raw_data_analytics_daily')
    op.drop_index('ix_raw_data_analytics_daily_hash', table_name='fact_raw_data_analytics_daily')
    
    # 删除表
    op.drop_table('fact_raw_data_services_agent_monthly')
    op.drop_table('fact_raw_data_services_agent_weekly')
    op.drop_table('fact_raw_data_services_ai_assistant_monthly')
    op.drop_table('fact_raw_data_services_ai_assistant_weekly')
    op.drop_table('fact_raw_data_services_ai_assistant_daily')
    op.drop_table('fact_raw_data_analytics_monthly')
    op.drop_table('fact_raw_data_analytics_weekly')
    op.drop_table('fact_raw_data_analytics_daily')

