"""v4_6_0_dss_architecture_tables

Revision ID: 20251126_132151
Revises: 20251121_132800
Create Date: 2025-11-26 13:21:51.000000

DSS架构重构 - 创建新表结构：
- B类数据分表（按data_domain+granularity，最多16张表）
- 统一对齐表（entity_aliases）
- A类数据表（7张，使用中文字段名）
- C类数据表（4张，使用中文字段名）
- StagingRawData表
- 修改FieldMappingTemplate表（添加header_columns字段）
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = '20251126_132151'
down_revision = '20251121_132800'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==================== B类数据分表（按data_domain+granularity） ====================
    
    # Orders数据域 - 日度/周度/月度
    op.create_table(
        'fact_raw_data_orders_daily',
        sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('platform_code', sa.String(length=32), nullable=False),
        sa.Column('shop_id', sa.String(length=256), nullable=True),
        sa.Column('data_domain', sa.String(length=64), nullable=False, server_default='orders'),
        sa.Column('granularity', sa.String(length=32), nullable=False, server_default='daily'),
        sa.Column('metric_date', sa.Date(), nullable=False),
        sa.Column('file_id', sa.Integer(), nullable=True),
        sa.Column('raw_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('header_columns', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('data_hash', sa.String(length=64), nullable=False),
        sa.Column('ingest_timestamp', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['file_id'], ['catalog_files.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('data_domain', 'granularity', 'data_hash', name='uq_raw_data_orders_daily_hash')
    )
    op.create_index('ix_raw_data_orders_daily_hash', 'fact_raw_data_orders_daily', ['data_hash'])
    op.create_index('ix_raw_data_orders_daily_domain_gran_date', 'fact_raw_data_orders_daily', ['data_domain', 'granularity', 'metric_date'])
    op.create_index('ix_raw_data_orders_daily_gin', 'fact_raw_data_orders_daily', ['raw_data'], postgresql_using='gin')
    
    op.create_table(
        'fact_raw_data_orders_weekly',
        sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('platform_code', sa.String(length=32), nullable=False),
        sa.Column('shop_id', sa.String(length=256), nullable=True),
        sa.Column('data_domain', sa.String(length=64), nullable=False, server_default='orders'),
        sa.Column('granularity', sa.String(length=32), nullable=False, server_default='weekly'),
        sa.Column('metric_date', sa.Date(), nullable=False),
        sa.Column('file_id', sa.Integer(), nullable=True),
        sa.Column('raw_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('header_columns', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('data_hash', sa.String(length=64), nullable=False),
        sa.Column('ingest_timestamp', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['file_id'], ['catalog_files.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('data_domain', 'granularity', 'data_hash', name='uq_raw_data_orders_weekly_hash')
    )
    op.create_index('ix_raw_data_orders_weekly_hash', 'fact_raw_data_orders_weekly', ['data_hash'])
    op.create_index('ix_raw_data_orders_weekly_domain_gran_date', 'fact_raw_data_orders_weekly', ['data_domain', 'granularity', 'metric_date'])
    op.create_index('ix_raw_data_orders_weekly_gin', 'fact_raw_data_orders_weekly', ['raw_data'], postgresql_using='gin')
    
    op.create_table(
        'fact_raw_data_orders_monthly',
        sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('platform_code', sa.String(length=32), nullable=False),
        sa.Column('shop_id', sa.String(length=256), nullable=True),
        sa.Column('data_domain', sa.String(length=64), nullable=False, server_default='orders'),
        sa.Column('granularity', sa.String(length=32), nullable=False, server_default='monthly'),
        sa.Column('metric_date', sa.Date(), nullable=False),
        sa.Column('file_id', sa.Integer(), nullable=True),
        sa.Column('raw_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('header_columns', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('data_hash', sa.String(length=64), nullable=False),
        sa.Column('ingest_timestamp', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['file_id'], ['catalog_files.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('data_domain', 'granularity', 'data_hash', name='uq_raw_data_orders_monthly_hash')
    )
    op.create_index('ix_raw_data_orders_monthly_hash', 'fact_raw_data_orders_monthly', ['data_hash'])
    op.create_index('ix_raw_data_orders_monthly_domain_gran_date', 'fact_raw_data_orders_monthly', ['data_domain', 'granularity', 'metric_date'])
    op.create_index('ix_raw_data_orders_monthly_gin', 'fact_raw_data_orders_monthly', ['raw_data'], postgresql_using='gin')
    
    # Products数据域 - 日度/周度/月度
    op.create_table(
        'fact_raw_data_products_daily',
        sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('platform_code', sa.String(length=32), nullable=False),
        sa.Column('shop_id', sa.String(length=256), nullable=True),
        sa.Column('data_domain', sa.String(length=64), nullable=False, server_default='products'),
        sa.Column('granularity', sa.String(length=32), nullable=False, server_default='daily'),
        sa.Column('metric_date', sa.Date(), nullable=False),
        sa.Column('file_id', sa.Integer(), nullable=True),
        sa.Column('raw_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('header_columns', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('data_hash', sa.String(length=64), nullable=False),
        sa.Column('ingest_timestamp', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['file_id'], ['catalog_files.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('data_domain', 'granularity', 'data_hash', name='uq_raw_data_products_daily_hash')
    )
    op.create_index('ix_raw_data_products_daily_hash', 'fact_raw_data_products_daily', ['data_hash'])
    op.create_index('ix_raw_data_products_daily_domain_gran_date', 'fact_raw_data_products_daily', ['data_domain', 'granularity', 'metric_date'])
    op.create_index('ix_raw_data_products_daily_gin', 'fact_raw_data_products_daily', ['raw_data'], postgresql_using='gin')
    
    op.create_table(
        'fact_raw_data_products_weekly',
        sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('platform_code', sa.String(length=32), nullable=False),
        sa.Column('shop_id', sa.String(length=256), nullable=True),
        sa.Column('data_domain', sa.String(length=64), nullable=False, server_default='products'),
        sa.Column('granularity', sa.String(length=32), nullable=False, server_default='weekly'),
        sa.Column('metric_date', sa.Date(), nullable=False),
        sa.Column('file_id', sa.Integer(), nullable=True),
        sa.Column('raw_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('header_columns', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('data_hash', sa.String(length=64), nullable=False),
        sa.Column('ingest_timestamp', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['file_id'], ['catalog_files.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('data_domain', 'granularity', 'data_hash', name='uq_raw_data_products_weekly_hash')
    )
    op.create_index('ix_raw_data_products_weekly_hash', 'fact_raw_data_products_weekly', ['data_hash'])
    op.create_index('ix_raw_data_products_weekly_domain_gran_date', 'fact_raw_data_products_weekly', ['data_domain', 'granularity', 'metric_date'])
    op.create_index('ix_raw_data_products_weekly_gin', 'fact_raw_data_products_weekly', ['raw_data'], postgresql_using='gin')
    
    op.create_table(
        'fact_raw_data_products_monthly',
        sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('platform_code', sa.String(length=32), nullable=False),
        sa.Column('shop_id', sa.String(length=256), nullable=True),
        sa.Column('data_domain', sa.String(length=64), nullable=False, server_default='products'),
        sa.Column('granularity', sa.String(length=32), nullable=False, server_default='monthly'),
        sa.Column('metric_date', sa.Date(), nullable=False),
        sa.Column('file_id', sa.Integer(), nullable=True),
        sa.Column('raw_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('header_columns', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('data_hash', sa.String(length=64), nullable=False),
        sa.Column('ingest_timestamp', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['file_id'], ['catalog_files.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('data_domain', 'granularity', 'data_hash', name='uq_raw_data_products_monthly_hash')
    )
    op.create_index('ix_raw_data_products_monthly_hash', 'fact_raw_data_products_monthly', ['data_hash'])
    op.create_index('ix_raw_data_products_monthly_domain_gran_date', 'fact_raw_data_products_monthly', ['data_domain', 'granularity', 'metric_date'])
    op.create_index('ix_raw_data_products_monthly_gin', 'fact_raw_data_products_monthly', ['raw_data'], postgresql_using='gin')
    
    # Traffic数据域 - 日度/周度/月度
    op.create_table(
        'fact_raw_data_traffic_daily',
        sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('platform_code', sa.String(length=32), nullable=False),
        sa.Column('shop_id', sa.String(length=256), nullable=True),
        sa.Column('data_domain', sa.String(length=64), nullable=False, server_default='traffic'),
        sa.Column('granularity', sa.String(length=32), nullable=False, server_default='daily'),
        sa.Column('metric_date', sa.Date(), nullable=False),
        sa.Column('file_id', sa.Integer(), nullable=True),
        sa.Column('raw_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('header_columns', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('data_hash', sa.String(length=64), nullable=False),
        sa.Column('ingest_timestamp', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['file_id'], ['catalog_files.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('data_domain', 'granularity', 'data_hash', name='uq_raw_data_traffic_daily_hash')
    )
    op.create_index('ix_raw_data_traffic_daily_hash', 'fact_raw_data_traffic_daily', ['data_hash'])
    op.create_index('ix_raw_data_traffic_daily_domain_gran_date', 'fact_raw_data_traffic_daily', ['data_domain', 'granularity', 'metric_date'])
    op.create_index('ix_raw_data_traffic_daily_gin', 'fact_raw_data_traffic_daily', ['raw_data'], postgresql_using='gin')
    
    op.create_table(
        'fact_raw_data_traffic_weekly',
        sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('platform_code', sa.String(length=32), nullable=False),
        sa.Column('shop_id', sa.String(length=256), nullable=True),
        sa.Column('data_domain', sa.String(length=64), nullable=False, server_default='traffic'),
        sa.Column('granularity', sa.String(length=32), nullable=False, server_default='weekly'),
        sa.Column('metric_date', sa.Date(), nullable=False),
        sa.Column('file_id', sa.Integer(), nullable=True),
        sa.Column('raw_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('header_columns', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('data_hash', sa.String(length=64), nullable=False),
        sa.Column('ingest_timestamp', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['file_id'], ['catalog_files.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('data_domain', 'granularity', 'data_hash', name='uq_raw_data_traffic_weekly_hash')
    )
    op.create_index('ix_raw_data_traffic_weekly_hash', 'fact_raw_data_traffic_weekly', ['data_hash'])
    op.create_index('ix_raw_data_traffic_weekly_domain_gran_date', 'fact_raw_data_traffic_weekly', ['data_domain', 'granularity', 'metric_date'])
    op.create_index('ix_raw_data_traffic_weekly_gin', 'fact_raw_data_traffic_weekly', ['raw_data'], postgresql_using='gin')
    
    op.create_table(
        'fact_raw_data_traffic_monthly',
        sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('platform_code', sa.String(length=32), nullable=False),
        sa.Column('shop_id', sa.String(length=256), nullable=True),
        sa.Column('data_domain', sa.String(length=64), nullable=False, server_default='traffic'),
        sa.Column('granularity', sa.String(length=32), nullable=False, server_default='monthly'),
        sa.Column('metric_date', sa.Date(), nullable=False),
        sa.Column('file_id', sa.Integer(), nullable=True),
        sa.Column('raw_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('header_columns', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('data_hash', sa.String(length=64), nullable=False),
        sa.Column('ingest_timestamp', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['file_id'], ['catalog_files.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('data_domain', 'granularity', 'data_hash', name='uq_raw_data_traffic_monthly_hash')
    )
    op.create_index('ix_raw_data_traffic_monthly_hash', 'fact_raw_data_traffic_monthly', ['data_hash'])
    op.create_index('ix_raw_data_traffic_monthly_domain_gran_date', 'fact_raw_data_traffic_monthly', ['data_domain', 'granularity', 'metric_date'])
    op.create_index('ix_raw_data_traffic_monthly_gin', 'fact_raw_data_traffic_monthly', ['raw_data'], postgresql_using='gin')
    
    # Services数据域 - 日度/周度/月度
    op.create_table(
        'fact_raw_data_services_daily',
        sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('platform_code', sa.String(length=32), nullable=False),
        sa.Column('shop_id', sa.String(length=256), nullable=True),
        sa.Column('data_domain', sa.String(length=64), nullable=False, server_default='services'),
        sa.Column('granularity', sa.String(length=32), nullable=False, server_default='daily'),
        sa.Column('metric_date', sa.Date(), nullable=False),
        sa.Column('file_id', sa.Integer(), nullable=True),
        sa.Column('raw_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('header_columns', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('data_hash', sa.String(length=64), nullable=False),
        sa.Column('ingest_timestamp', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['file_id'], ['catalog_files.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('data_domain', 'granularity', 'data_hash', name='uq_raw_data_services_daily_hash')
    )
    op.create_index('ix_raw_data_services_daily_hash', 'fact_raw_data_services_daily', ['data_hash'])
    op.create_index('ix_raw_data_services_daily_domain_gran_date', 'fact_raw_data_services_daily', ['data_domain', 'granularity', 'metric_date'])
    op.create_index('ix_raw_data_services_daily_gin', 'fact_raw_data_services_daily', ['raw_data'], postgresql_using='gin')
    
    op.create_table(
        'fact_raw_data_services_weekly',
        sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('platform_code', sa.String(length=32), nullable=False),
        sa.Column('shop_id', sa.String(length=256), nullable=True),
        sa.Column('data_domain', sa.String(length=64), nullable=False, server_default='services'),
        sa.Column('granularity', sa.String(length=32), nullable=False, server_default='weekly'),
        sa.Column('metric_date', sa.Date(), nullable=False),
        sa.Column('file_id', sa.Integer(), nullable=True),
        sa.Column('raw_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('header_columns', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('data_hash', sa.String(length=64), nullable=False),
        sa.Column('ingest_timestamp', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['file_id'], ['catalog_files.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('data_domain', 'granularity', 'data_hash', name='uq_raw_data_services_weekly_hash')
    )
    op.create_index('ix_raw_data_services_weekly_hash', 'fact_raw_data_services_weekly', ['data_hash'])
    op.create_index('ix_raw_data_services_weekly_domain_gran_date', 'fact_raw_data_services_weekly', ['data_domain', 'granularity', 'metric_date'])
    op.create_index('ix_raw_data_services_weekly_gin', 'fact_raw_data_services_weekly', ['raw_data'], postgresql_using='gin')
    
    op.create_table(
        'fact_raw_data_services_monthly',
        sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('platform_code', sa.String(length=32), nullable=False),
        sa.Column('shop_id', sa.String(length=256), nullable=True),
        sa.Column('data_domain', sa.String(length=64), nullable=False, server_default='services'),
        sa.Column('granularity', sa.String(length=32), nullable=False, server_default='monthly'),
        sa.Column('metric_date', sa.Date(), nullable=False),
        sa.Column('file_id', sa.Integer(), nullable=True),
        sa.Column('raw_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('header_columns', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('data_hash', sa.String(length=64), nullable=False),
        sa.Column('ingest_timestamp', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['file_id'], ['catalog_files.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('data_domain', 'granularity', 'data_hash', name='uq_raw_data_services_monthly_hash')
    )
    op.create_index('ix_raw_data_services_monthly_hash', 'fact_raw_data_services_monthly', ['data_hash'])
    op.create_index('ix_raw_data_services_monthly_domain_gran_date', 'fact_raw_data_services_monthly', ['data_domain', 'granularity', 'metric_date'])
    op.create_index('ix_raw_data_services_monthly_gin', 'fact_raw_data_services_monthly', ['raw_data'], postgresql_using='gin')
    
    # Inventory数据域 - 快照粒度（现有）
    op.create_table(
        'fact_raw_data_inventory_snapshot',
        sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('platform_code', sa.String(length=32), nullable=False),
        sa.Column('shop_id', sa.String(length=256), nullable=True),
        sa.Column('data_domain', sa.String(length=64), nullable=False, server_default='inventory'),
        sa.Column('granularity', sa.String(length=32), nullable=False, server_default='snapshot'),
        sa.Column('metric_date', sa.Date(), nullable=False),
        sa.Column('file_id', sa.Integer(), nullable=True),
        sa.Column('raw_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('header_columns', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('data_hash', sa.String(length=64), nullable=False),
        sa.Column('ingest_timestamp', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['file_id'], ['catalog_files.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('data_domain', 'granularity', 'data_hash', name='uq_raw_data_inventory_snapshot_hash')
    )
    op.create_index('ix_raw_data_inventory_snapshot_hash', 'fact_raw_data_inventory_snapshot', ['data_hash'])
    op.create_index('ix_raw_data_inventory_snapshot_domain_gran_date', 'fact_raw_data_inventory_snapshot', ['data_domain', 'granularity', 'metric_date'])
    op.create_index('ix_raw_data_inventory_snapshot_gin', 'fact_raw_data_inventory_snapshot', ['raw_data'], postgresql_using='gin')
    
    # ==================== 统一对齐表 ====================
    op.create_table(
        'entity_aliases',
        sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('source_platform', sa.String(length=32), nullable=False),
        sa.Column('source_type', sa.String(length=32), nullable=False),
        sa.Column('source_name', sa.String(length=256), nullable=False),
        sa.Column('source_account', sa.String(length=128), nullable=True),
        sa.Column('source_site', sa.String(length=64), nullable=True),
        sa.Column('data_domain', sa.String(length=64), nullable=True),
        sa.Column('target_type', sa.String(length=32), nullable=False),
        sa.Column('target_id', sa.String(length=256), nullable=False),
        sa.Column('target_name', sa.String(length=256), nullable=True),
        sa.Column('target_platform_code', sa.String(length=32), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True, server_default='1.0'),
        sa.Column('active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(length=64), nullable=True, server_default='system'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_by', sa.String(length=64), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_platform', 'source_type', 'source_name', 'source_account', 'source_site', name='uq_entity_alias_source')
    )
    op.create_index('ix_entity_aliases_source', 'entity_aliases', ['source_platform', 'source_type', 'source_name'])
    op.create_index('ix_entity_aliases_target', 'entity_aliases', ['target_type', 'target_id', 'active'])
    
    # ==================== Staging表 ====================
    op.create_table(
        'staging_raw_data',
        sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('file_id', sa.Integer(), nullable=True),
        sa.Column('row_number', sa.Integer(), nullable=False),
        sa.Column('platform_code', sa.String(length=32), nullable=True),
        sa.Column('shop_id', sa.String(length=256), nullable=True),
        sa.Column('data_domain', sa.String(length=64), nullable=True),
        sa.Column('granularity', sa.String(length=32), nullable=True),
        sa.Column('metric_date', sa.Date(), nullable=True),
        sa.Column('raw_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('header_columns', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['file_id'], ['catalog_files.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_staging_raw_data_file', 'staging_raw_data', ['file_id', 'status'])
    op.create_index('ix_staging_raw_data_domain_gran', 'staging_raw_data', ['data_domain', 'granularity'])
    
    # ==================== A类数据表（使用中文字段名） ====================
    # 注意：中文字段名需要在SQL中直接使用双引号，这里先创建表结构，字段名在后续SQL中重命名
    
    # SalesTargets表（销售目标）
    op.execute(text("""
        CREATE TABLE sales_targets_a (
            id BIGSERIAL PRIMARY KEY,
            "店铺ID" VARCHAR(256) NOT NULL,
            "年月" VARCHAR(7) NOT NULL,
            "目标销售额" NUMERIC(15, 2) NOT NULL DEFAULT 0.0,
            "目标订单数" INTEGER NOT NULL DEFAULT 0,
            "创建时间" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "更新时间" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE ("店铺ID", "年月")
        );
        CREATE INDEX ix_sales_targets_shop ON sales_targets_a ("店铺ID");
        CREATE INDEX ix_sales_targets_month ON sales_targets_a ("年月");
    """))
    
    # SalesCampaigns表（销售战役）
    op.execute(text("""
        CREATE TABLE sales_campaigns_a (
            id BIGSERIAL PRIMARY KEY,
            "战役名称" VARCHAR(200) NOT NULL,
            "战役类型" VARCHAR(32) NOT NULL,
            "开始日期" DATE NOT NULL,
            "结束日期" DATE NOT NULL,
            "目标销售额" NUMERIC(15, 2) NOT NULL DEFAULT 0.0,
            "目标订单数" INTEGER NOT NULL DEFAULT 0,
            "状态" VARCHAR(32) NOT NULL DEFAULT 'pending',
            "描述" TEXT,
            "创建人" VARCHAR(64),
            "创建时间" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "更新时间" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK ("结束日期" >= "开始日期")
        );
        CREATE INDEX ix_sales_campaigns_a_type ON sales_campaigns_a ("战役类型");
        CREATE INDEX ix_sales_campaigns_a_status ON sales_campaigns_a ("状态");
    """))
    
    # OperatingCosts表（运营成本）
    op.execute(text("""
        CREATE TABLE operating_costs (
            id BIGSERIAL PRIMARY KEY,
            "店铺ID" VARCHAR(256) NOT NULL,
            "年月" VARCHAR(7) NOT NULL,
            "租金" NUMERIC(15, 2) NOT NULL DEFAULT 0.0,
            "工资" NUMERIC(15, 2) NOT NULL DEFAULT 0.0,
            "水电费" NUMERIC(15, 2) NOT NULL DEFAULT 0.0,
            "其他成本" NUMERIC(15, 2) NOT NULL DEFAULT 0.0,
            "创建时间" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "更新时间" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE ("店铺ID", "年月")
        );
        CREATE INDEX ix_operating_costs_shop ON operating_costs ("店铺ID");
        CREATE INDEX ix_operating_costs_month ON operating_costs ("年月");
    """))
    
    # Employees表（员工档案）
    op.execute(text("""
        CREATE TABLE employees (
            id BIGSERIAL PRIMARY KEY,
            "员工编号" VARCHAR(64) NOT NULL UNIQUE,
            "姓名" VARCHAR(128) NOT NULL,
            "部门" VARCHAR(128),
            "职位" VARCHAR(128),
            "入职日期" DATE,
            "状态" VARCHAR(32) NOT NULL DEFAULT 'active',
            "创建时间" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "更新时间" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX ix_employees_code ON employees ("员工编号");
        CREATE INDEX ix_employees_department ON employees ("部门");
    """))
    
    # EmployeeTargets表（员工目标）
    op.execute(text("""
        CREATE TABLE employee_targets (
            id BIGSERIAL PRIMARY KEY,
            "员工编号" VARCHAR(64) NOT NULL,
            "年月" VARCHAR(7) NOT NULL,
            "目标类型" VARCHAR(32) NOT NULL,
            "目标值" NUMERIC(15, 2) NOT NULL,
            "创建时间" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "更新时间" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE ("员工编号", "年月", "目标类型")
        );
        CREATE INDEX ix_employee_targets_employee ON employee_targets ("员工编号");
        CREATE INDEX ix_employee_targets_month ON employee_targets ("年月");
    """))
    
    # AttendanceRecords表（考勤记录）
    op.execute(text("""
        CREATE TABLE attendance_records (
            id BIGSERIAL PRIMARY KEY,
            "员工编号" VARCHAR(64) NOT NULL,
            "考勤日期" DATE NOT NULL,
            "上班时间" TIMESTAMP,
            "下班时间" TIMESTAMP,
            "工作时长" FLOAT,
            "状态" VARCHAR(32) NOT NULL DEFAULT 'normal',
            "创建时间" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "更新时间" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE ("员工编号", "考勤日期")
        );
        CREATE INDEX ix_attendance_records_employee ON attendance_records ("员工编号");
        CREATE INDEX ix_attendance_records_date ON attendance_records ("考勤日期");
    """))
    
    # PerformanceConfig表（绩效权重配置）
    op.execute(text("""
        CREATE TABLE performance_config_a (
            id BIGSERIAL PRIMARY KEY,
            "配置名称" VARCHAR(128) NOT NULL UNIQUE,
            "销售额权重" FLOAT NOT NULL DEFAULT 0.0,
            "订单数权重" FLOAT NOT NULL DEFAULT 0.0,
            "质量权重" FLOAT NOT NULL DEFAULT 0.0,
            "是否启用" BOOLEAN NOT NULL DEFAULT true,
            "创建时间" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "更新时间" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX ix_performance_config_a_active ON performance_config_a ("是否启用");
    """))
    
    # ==================== C类数据表（使用中文字段名，Metabase定时计算更新） ====================
    
    # EmployeePerformance表（员工绩效）
    op.execute(text("""
        CREATE TABLE employee_performance (
            id BIGSERIAL PRIMARY KEY,
            "员工编号" VARCHAR(64) NOT NULL,
            "年月" VARCHAR(7) NOT NULL,
            "实际销售额" NUMERIC(15, 2) NOT NULL DEFAULT 0.0,
            "达成率" FLOAT NOT NULL DEFAULT 0.0,
            "绩效得分" FLOAT NOT NULL DEFAULT 0.0,
            "计算时间" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE ("员工编号", "年月")
        );
        CREATE INDEX ix_employee_performance_employee ON employee_performance ("员工编号");
        CREATE INDEX ix_employee_performance_month ON employee_performance ("年月");
    """))
    
    # EmployeeCommissions表（员工提成）
    op.execute(text("""
        CREATE TABLE employee_commissions (
            id BIGSERIAL PRIMARY KEY,
            "员工编号" VARCHAR(64) NOT NULL,
            "年月" VARCHAR(7) NOT NULL,
            "销售额" NUMERIC(15, 2) NOT NULL DEFAULT 0.0,
            "提成金额" NUMERIC(15, 2) NOT NULL DEFAULT 0.0,
            "提成比例" FLOAT NOT NULL DEFAULT 0.0,
            "计算时间" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE ("员工编号", "年月")
        );
        CREATE INDEX ix_employee_commissions_employee ON employee_commissions ("员工编号");
        CREATE INDEX ix_employee_commissions_month ON employee_commissions ("年月");
    """))
    
    # ShopCommissions表（店铺提成）
    op.execute(text("""
        CREATE TABLE shop_commissions (
            id BIGSERIAL PRIMARY KEY,
            "店铺ID" VARCHAR(256) NOT NULL,
            "年月" VARCHAR(7) NOT NULL,
            "销售额" NUMERIC(15, 2) NOT NULL DEFAULT 0.0,
            "提成金额" NUMERIC(15, 2) NOT NULL DEFAULT 0.0,
            "提成比例" FLOAT NOT NULL DEFAULT 0.0,
            "计算时间" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE ("店铺ID", "年月")
        );
        CREATE INDEX ix_shop_commissions_shop ON shop_commissions ("店铺ID");
        CREATE INDEX ix_shop_commissions_month ON shop_commissions ("年月");
    """))
    
    # PerformanceScores表（店铺绩效）
    op.execute(text("""
        CREATE TABLE performance_scores_c (
            id BIGSERIAL PRIMARY KEY,
            "店铺ID" VARCHAR(256) NOT NULL,
            "考核周期" VARCHAR(32) NOT NULL,
            "总分" FLOAT NOT NULL DEFAULT 0.0,
            "销售得分" FLOAT NOT NULL DEFAULT 0.0,
            "质量得分" FLOAT NOT NULL DEFAULT 0.0,
            "计算时间" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE ("店铺ID", "考核周期")
        );
        CREATE INDEX ix_performance_scores_c_shop ON performance_scores_c ("店铺ID");
        CREATE INDEX ix_performance_scores_c_period ON performance_scores_c ("考核周期");
    """))
    
    # ==================== 修改FieldMappingTemplate表 ====================
    # 检查表是否存在，如果存在则添加列
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if 'field_mapping_templates' in inspector.get_table_names():
        op.add_column('field_mapping_templates', 
            sa.Column('header_columns', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='原始表头字段列表（JSONB数组）')
        )


def downgrade() -> None:
    # 删除A类数据表
    op.execute(text('DROP TABLE IF EXISTS performance_scores_c CASCADE'))
    op.execute(text('DROP TABLE IF EXISTS shop_commissions CASCADE'))
    op.execute(text('DROP TABLE IF EXISTS employee_commissions CASCADE'))
    op.execute(text('DROP TABLE IF EXISTS employee_performance CASCADE'))
    op.execute(text('DROP TABLE IF EXISTS performance_config_a CASCADE'))
    op.execute(text('DROP TABLE IF EXISTS attendance_records CASCADE'))
    op.execute(text('DROP TABLE IF EXISTS employee_targets CASCADE'))
    op.execute(text('DROP TABLE IF EXISTS employees CASCADE'))
    op.execute(text('DROP TABLE IF EXISTS operating_costs CASCADE'))
    op.execute(text('DROP TABLE IF EXISTS sales_campaigns_a CASCADE'))
    op.execute(text('DROP TABLE IF EXISTS sales_targets_a CASCADE'))
    
    # 删除Staging表
    op.drop_table('staging_raw_data')
    
    # 删除统一对齐表
    op.drop_table('entity_aliases')
    
    # 删除B类数据表
    op.drop_table('fact_raw_data_inventory_snapshot')
    op.drop_table('fact_raw_data_services_monthly')
    op.drop_table('fact_raw_data_services_weekly')
    op.drop_table('fact_raw_data_services_daily')
    op.drop_table('fact_raw_data_traffic_monthly')
    op.drop_table('fact_raw_data_traffic_weekly')
    op.drop_table('fact_raw_data_traffic_daily')
    op.drop_table('fact_raw_data_products_monthly')
    op.drop_table('fact_raw_data_products_weekly')
    op.drop_table('fact_raw_data_products_daily')
    op.drop_table('fact_raw_data_orders_monthly')
    op.drop_table('fact_raw_data_orders_weekly')
    op.drop_table('fact_raw_data_orders_daily')
    
    # 删除FieldMappingTemplate表的header_columns字段
    op.drop_column('field_mapping_templates', 'header_columns')

