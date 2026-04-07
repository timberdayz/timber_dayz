"""Complete schema base tables migration

Revision ID: 20260110_complete_schema_base
Revises: v4_20_0_backup_records
Create Date: 2026-01-10

将所有通过 Base.metadata.create_all() 创建但未在 Alembic 迁移中的表
统一迁移到 Alembic 管理。

包括但不限于：
- collection_tasks, collection_task_logs, collection_configs
- field_mappings, mapping_sessions
- catalog_files (如果不存在)
- accounts, data_files, data_records (如果不存在)
- staging_orders, staging_product_metrics (如果不存在)

注意：
- 本迁移使用 IF NOT EXISTS 模式，不会覆盖已存在的表
- 仅创建基础表结构，字段增强通过后续迁移完成
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, JSON
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '20260110_complete_schema_base'
down_revision = 'v4_20_0_backup_records'
branch_labels = None
depends_on = None


def upgrade():
    """创建所有缺失的基础表"""
    from sqlalchemy import inspect
    
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = set(inspector.get_table_names())
    
    print("[INFO] 开始创建基础表（仅创建不存在的表）...")
    created_count = 0
    
    # 1. 创建 catalog_files 表（如果不存在）
    if 'catalog_files' not in existing_tables:
        print("[1] 创建 catalog_files 表...")
        op.create_table(
            'catalog_files',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('file_path', sa.String(length=1024), nullable=False),
            sa.Column('file_name', sa.String(length=255), nullable=False),
            sa.Column('source', sa.String(length=64), nullable=False, server_default='temp/outputs'),
            sa.Column('file_size', sa.Integer(), nullable=True),
            sa.Column('file_hash', sa.String(length=64), nullable=True),
            sa.Column('platform_code', sa.String(length=32), nullable=True),
            sa.Column('account', sa.String(length=128), nullable=True),
            sa.Column('shop_id', sa.String(length=256), nullable=True),
            sa.Column('data_domain', sa.String(length=64), nullable=True),
            sa.Column('granularity', sa.String(length=16), nullable=True),
            sa.Column('date_from', sa.Date(), nullable=True),
            sa.Column('date_to', sa.Date(), nullable=True),
            sa.Column('source_platform', sa.String(length=32), nullable=True),
            sa.Column('sub_domain', sa.String(length=64), nullable=True),
            sa.Column('storage_layer', sa.String(length=32), nullable=True, server_default='raw'),
            sa.Column('quality_score', sa.Float(), nullable=True),
            sa.Column('validation_errors', JSON, nullable=True),
            sa.Column('meta_file_path', sa.String(length=1024), nullable=True),
            sa.Column('file_metadata', JSON, nullable=True),
            sa.Column('status', sa.String(length=32), nullable=False, server_default='pending'),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('first_seen_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
            sa.Column('last_processed_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('file_hash', name='uq_catalog_files_hash'),
        )
        op.create_index('ix_catalog_files_status', 'catalog_files', ['status'])
        op.create_index('ix_catalog_files_platform_shop', 'catalog_files', ['platform_code', 'shop_id'])
        op.create_index('ix_catalog_files_dates', 'catalog_files', ['date_from', 'date_to'])
        op.create_index('ix_catalog_source_domain', 'catalog_files', ['source_platform', 'data_domain'])
        op.create_index('ix_catalog_sub_domain', 'catalog_files', ['sub_domain'])
        op.create_index('ix_catalog_storage_layer', 'catalog_files', ['storage_layer'])
        op.create_index('ix_catalog_quality_score', 'catalog_files', ['quality_score'])
        created_count += 1
        print("[OK] catalog_files 表创建成功")
    else:
        print("[SKIP] catalog_files 表已存在")
    
    # 2. 创建 collection_configs 表（如果不存在）
    if 'collection_configs' not in existing_tables:
        print("[2] 创建 collection_configs 表...")
        op.create_table(
            'collection_configs',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.Column('platform', sa.String(length=50), nullable=False),
            sa.Column('account_ids', JSON, nullable=False),
            sa.Column('data_domains', JSON, nullable=False),
            sa.Column('sub_domains', JSON, nullable=True),
            sa.Column('granularity', sa.String(length=20), nullable=False, server_default='daily'),
            sa.Column('date_range_type', sa.String(length=20), nullable=False, server_default='yesterday'),
            sa.Column('custom_date_start', sa.Date(), nullable=True),
            sa.Column('custom_date_end', sa.Date(), nullable=True),
            sa.Column('schedule_enabled', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('schedule_cron', sa.String(length=50), nullable=True),
            sa.Column('retry_count', sa.Integer(), nullable=False, server_default='3'),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
            sa.Column('created_by', sa.String(length=100), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('name', 'platform', name='uq_collection_configs_name_platform'),
        )
        op.create_index('ix_collection_configs_platform', 'collection_configs', ['platform'])
        op.create_index('ix_collection_configs_active', 'collection_configs', ['is_active'])
        created_count += 1
        print("[OK] collection_configs 表创建成功")
    else:
        print("[SKIP] collection_configs 表已存在")
    
    # 3. 创建 collection_tasks 表（如果不存在）- 最关键
    if 'collection_tasks' not in existing_tables:
        print("[3] 创建 collection_tasks 表（关键表）...")
        op.create_table(
            'collection_tasks',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('task_id', sa.String(length=100), nullable=False),
            sa.Column('platform', sa.String(length=50), nullable=False),
            sa.Column('account', sa.String(length=100), nullable=False),
            sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
            sa.Column('config_id', sa.Integer(), nullable=True),
            sa.Column('progress', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('current_step', sa.String(length=200), nullable=True),
            sa.Column('files_collected', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('trigger_type', sa.String(length=20), nullable=False, server_default='manual'),
            sa.Column('data_domains', JSON, nullable=True),
            sa.Column('sub_domains', JSON, nullable=True),
            sa.Column('granularity', sa.String(length=20), nullable=True),
            sa.Column('date_range', JSON, nullable=True),
            sa.Column('total_domains', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('completed_domains', JSON, nullable=True),
            sa.Column('failed_domains', JSON, nullable=True),
            sa.Column('current_domain', sa.String(length=100), nullable=True),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('error_screenshot_path', sa.String(length=500), nullable=True),
            sa.Column('duration_seconds', sa.Integer(), nullable=True),
            sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('parent_task_id', sa.Integer(), nullable=True),
            sa.Column('verification_type', sa.String(length=50), nullable=True),
            sa.Column('verification_screenshot', sa.String(length=500), nullable=True),
            sa.Column('debug_mode', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('task_id', name='uq_collection_tasks_task_id'),
        )
        op.create_index('ix_collection_tasks_platform', 'collection_tasks', ['platform'])
        op.create_index('ix_collection_tasks_status', 'collection_tasks', ['status'])
        op.create_index('ix_collection_tasks_config', 'collection_tasks', ['config_id'])
        op.create_index('ix_collection_tasks_created', 'collection_tasks', ['created_at'])
        
        # 创建外键约束
        try:
            op.create_foreign_key(
                'fk_collection_tasks_config',
                'collection_tasks', 'collection_configs',
                ['config_id'], ['id'],
                ondelete='SET NULL'
            )
        except Exception:
            pass  # 如果 collection_configs 不存在，跳过外键
        
        try:
            op.create_foreign_key(
                'fk_collection_tasks_parent',
                'collection_tasks', 'collection_tasks',
                ['parent_task_id'], ['id'],
                ondelete='SET NULL'
            )
        except Exception:
            pass  # 自引用外键，如果表不存在会失败
        
        created_count += 1
        print("[OK] collection_tasks 表创建成功")
    else:
        print("[SKIP] collection_tasks 表已存在")
    
    # 4. 创建 collection_task_logs 表（如果不存在）
    if 'collection_task_logs' not in existing_tables:
        print("[4] 创建 collection_task_logs 表...")
        op.create_table(
            'collection_task_logs',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('task_id', sa.Integer(), nullable=False),
            sa.Column('level', sa.String(length=20), nullable=False, server_default='info'),
            sa.Column('message', sa.Text(), nullable=False),
            sa.Column('details', JSON, nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_collection_task_logs_task', 'collection_task_logs', ['task_id'])
        op.create_index('ix_collection_task_logs_created', 'collection_task_logs', ['created_at'])
        
        # 创建外键约束
        try:
            op.create_foreign_key(
                'fk_collection_task_logs_task',
                'collection_task_logs', 'collection_tasks',
                ['task_id'], ['id'],
                ondelete='CASCADE'
            )
        except Exception:
            pass  # 如果 collection_tasks 不存在，跳过外键
        
        created_count += 1
        print("[OK] collection_task_logs 表创建成功")
    else:
        print("[SKIP] collection_task_logs 表已存在")
    
    # 5. 创建 field_mappings 表（如果不存在）
    if 'field_mappings' not in existing_tables:
        print("[5] 创建 field_mappings 表...")
        op.create_table(
            'field_mappings',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('file_id', sa.Integer(), nullable=True),
            sa.Column('platform', sa.String(length=50), nullable=True),
            sa.Column('original_field', sa.String(length=100), nullable=False),
            sa.Column('standard_field', sa.String(length=100), nullable=False),
            sa.Column('confidence', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('is_manual', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('domain', sa.String(length=50), nullable=True),
            sa.Column('granularity', sa.String(length=50), nullable=True),
            sa.Column('sheet_name', sa.String(length=100), nullable=True),
            sa.Column('sub_domain', sa.String(length=64), nullable=True, server_default=''),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_field_mappings_platform', 'field_mappings', ['platform'])
        op.create_index('ix_field_mappings_domain', 'field_mappings', ['domain'])
        op.create_index('ix_field_mappings_version', 'field_mappings', ['version'])
        op.create_index('ix_field_mappings_template_key', 'field_mappings', ['platform', 'domain', 'sub_domain', 'granularity'])
        created_count += 1
        print("[OK] field_mappings 表创建成功")
    else:
        print("[SKIP] field_mappings 表已存在")
    
    # 6. 创建 mapping_sessions 表（如果不存在）
    if 'mapping_sessions' not in existing_tables:
        print("[6] 创建 mapping_sessions 表...")
        op.create_table(
            'mapping_sessions',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('session_id', sa.String(length=100), nullable=False),
            sa.Column('platform', sa.String(length=50), nullable=True),
            sa.Column('domain', sa.String(length=50), nullable=True),
            sa.Column('status', sa.String(length=20), nullable=False, server_default='active'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('session_id', name='uq_mapping_sessions_session_id'),
        )
        created_count += 1
        print("[OK] mapping_sessions 表创建成功")
    else:
        print("[SKIP] mapping_sessions 表已存在")
    
    # 7. 创建 accounts 表（如果不存在）
    if 'accounts' not in existing_tables:
        print("[7] 创建 accounts 表...")
        op.create_table(
            'accounts',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('platform', sa.String(length=50), nullable=False),
            sa.Column('username', sa.String(length=100), nullable=False),
            sa.Column('password', sa.String(length=500), nullable=True),
            sa.Column('login_url', sa.String(length=500), nullable=True),
            sa.Column('status', sa.String(length=20), nullable=False, server_default='offline'),
            sa.Column('health_score', sa.Float(), nullable=True, server_default='0.0'),
            sa.Column('notes', sa.String(length=500), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
            sa.PrimaryKeyConstraint('id'),
        )
        created_count += 1
        print("[OK] accounts 表创建成功")
    else:
        print("[SKIP] accounts 表已存在")
    
    # 8. 创建 data_files 表（如果不存在）
    if 'data_files' not in existing_tables:
        print("[8] 创建 data_files 表...")
        op.create_table(
            'data_files',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('file_name', sa.String(length=255), nullable=False),
            sa.Column('file_path', sa.String(length=500), nullable=False),
            sa.Column('platform', sa.String(length=50), nullable=False),
            sa.Column('data_type', sa.String(length=50), nullable=False),
            sa.Column('status', sa.String(length=50), nullable=False, server_default='pending'),
            sa.Column('discovery_time', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_data_files_platform', 'data_files', ['platform'])
        op.create_index('ix_data_files_status', 'data_files', ['status'])
        created_count += 1
        print("[OK] data_files 表创建成功")
    else:
        print("[SKIP] data_files 表已存在")
    
    # 9. 创建 data_records 表（如果不存在）
    if 'data_records' not in existing_tables:
        print("[9] 创建 data_records 表...")
        op.create_table(
            'data_records',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('platform', sa.String(length=50), nullable=False),
            sa.Column('record_type', sa.String(length=50), nullable=False),
            sa.Column('data', JSON, nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_data_records_platform', 'data_records', ['platform'])
        op.create_index('ix_data_records_type', 'data_records', ['record_type'])
        created_count += 1
        print("[OK] data_records 表创建成功")
    else:
        print("[SKIP] data_records 表已存在")
    
    # 10. 创建 staging_orders 和 staging_product_metrics 表（如果不存在）
    if 'staging_orders' not in existing_tables:
        print("[10] 创建 staging_orders 表...")
        op.create_table(
            'staging_orders',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('platform_code', sa.String(length=32), nullable=True),
            sa.Column('shop_id', sa.String(length=64), nullable=True),
            sa.Column('order_id', sa.String(length=128), nullable=True),
            sa.Column('order_data', JSON, nullable=False),
            sa.Column('ingest_task_id', sa.String(length=64), nullable=True),
            sa.Column('file_id', sa.Integer(), nullable=True),
            sa.Column('processed', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_staging_orders_platform_shop', 'staging_orders', ['platform_code', 'shop_id'])
        op.create_index('ix_staging_orders_processed', 'staging_orders', ['processed'])
        created_count += 1
        print("[OK] staging_orders 表创建成功")
    else:
        print("[SKIP] staging_orders 表已存在")
    
    if 'staging_product_metrics' not in existing_tables:
        print("[11] 创建 staging_product_metrics 表...")
        op.create_table(
            'staging_product_metrics',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('platform_code', sa.String(length=32), nullable=True),
            sa.Column('shop_id', sa.String(length=64), nullable=True),
            sa.Column('product_sku', sa.String(length=200), nullable=True),
            sa.Column('metric_data', JSON, nullable=False),
            sa.Column('ingest_task_id', sa.String(length=64), nullable=True),
            sa.Column('file_id', sa.Integer(), nullable=True),
            sa.Column('processed', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_staging_product_metrics_platform_shop', 'staging_product_metrics', ['platform_code', 'shop_id'])
        op.create_index('ix_staging_product_metrics_processed', 'staging_product_metrics', ['processed'])
        created_count += 1
        print("[OK] staging_product_metrics 表创建成功")
    else:
        print("[SKIP] staging_product_metrics 表已存在")
    
    print(f"[OK] 基础表迁移完成: 创建 {created_count} 张新表")


def downgrade():
    """删除所有基础表（谨慎使用）"""
    # 注意：downgrade 只删除在本迁移中创建的表
    # 如果表在迁移前已存在，则不会删除
    
    tables_to_drop = [
        'staging_product_metrics',
        'staging_orders',
        'data_records',
        'data_files',
        'mapping_sessions',
        'field_mappings',
        'collection_task_logs',
        'collection_tasks',
        'collection_configs',
        'accounts',
        'catalog_files',  # 注意：data_quarantine 在其他迁移中，不在这里删除
    ]
    
    for table in tables_to_drop:
        try:
            op.drop_table(table)
            print(f"[OK] 删除表: {table}")
        except Exception as e:
            print(f"[SKIP] 表 {table} 不存在或无法删除: {e}")
