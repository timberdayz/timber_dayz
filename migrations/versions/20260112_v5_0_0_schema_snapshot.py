"""Schema Snapshot Migration (v5.0.0)

Revision ID: v5_0_0_schema_snapshot
Revises: None
Create Date: 2026-01-12 15:27:06

完整的数据库结构快照迁移。
包含所有在 schema.py 中定义的表。

注意：
- 此迁移是幂等的，可以重复执行
- 如果表已存在，将跳过创建
- 可作为新环境的起点，不依赖旧迁移历史
- 表按依赖顺序创建（被引用的表优先创建）
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision = 'v5_0_0_schema_snapshot'
down_revision = None
branch_labels = None
depends_on = None


def safe_print(text):
    """安全打印（处理Windows GBK编码）"""
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        try:
            safe_text = text.encode('gbk', errors='ignore').decode('gbk')
            print(safe_text, flush=True)
        except:
            safe_text = text.encode('ascii', errors='ignore').decode('ascii')
            print(safe_text, flush=True)



def upgrade():
    """创建完整数据库结构（幂等）"""
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = set(inspector.get_table_names())

    # ==================== 1. account_aliases ====================
    safe_print("[1/106] Creating account_aliases table...")

    if 'account_aliases' not in existing_tables:
        op.create_table(
            'account_aliases',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('platform', sa.String(length=32), nullable=False),
            sa.Column('data_domain', sa.String(length=64), nullable=False),
            sa.Column('account', sa.String(length=128)),
            sa.Column('site', sa.String(length=64)),
            sa.Column('store_label_raw', sa.String(length=256), nullable=False),
            sa.Column('target_type', sa.String(length=32), nullable=False),
            sa.Column('target_id', sa.String(length=128), nullable=False),
            sa.Column('confidence', sa.Numeric()),
            sa.Column('active', sa.Boolean()),
            sa.Column('notes', sa.String()),
            sa.Column('created_by', sa.String(length=64)),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_by', sa.String(length=64)),
            sa.Column('updated_at', sa.DateTime()),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_account_alias_platform_domain', 'account_aliases', ['platform', 'data_domain'])
        op.create_index('ix_account_alias_target', 'account_aliases', ['target_id', 'active'])
        op.create_index('uq_account_alias_source', 'account_aliases', ['platform', 'data_domain', 'account', 'site', 'store_label_raw'])
        safe_print("[OK] account_aliases table created")
    else:
        safe_print("[SKIP] account_aliases table already exists")

    # ==================== 2. accounts ====================
    safe_print("[2/106] Creating accounts table...")

    if 'accounts' not in existing_tables:
        op.create_table(
            'accounts',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('platform', sa.String(length=50), nullable=False),
            sa.Column('account_name', sa.String(length=100), nullable=False),
            sa.Column('account_id', sa.String(length=100), nullable=False),
            sa.Column('status', sa.String(length=20), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('account_id', name='uq_accounts_account_id')
        )
        op.create_index('ix_accounts_platform', 'accounts', ['platform'])
        op.create_index('ix_accounts_status', 'accounts', ['status'])
        safe_print("[OK] accounts table created")
    else:
        safe_print("[SKIP] accounts table already exists")

    # ==================== 3. allocation_rules ====================
    safe_print("[3/106] Creating allocation_rules table...")

    if 'allocation_rules' not in existing_tables:
        op.create_table(
            'allocation_rules',
            sa.Column('rule_id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('rule_name', sa.String(length=256), nullable=False),
            sa.Column('scope', sa.String(length=64), nullable=False),
            sa.Column('driver', sa.String(length=64), nullable=False),
            sa.Column('weights', sa.JSON),
            sa.Column('effective_from', sa.Date(), nullable=False),
            sa.Column('effective_to', sa.Date()),
            sa.Column('active', sa.Boolean()),
            sa.Column('created_by', sa.String(length=64)),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('rule_id')
        )
        op.create_index('ix_allocation_rules_scope', 'allocation_rules', ['scope', 'active'])
        safe_print("[OK] allocation_rules table created")
    else:
        safe_print("[SKIP] allocation_rules table already exists")

    # ==================== 4. approval_logs ====================
    safe_print("[4/106] Creating approval_logs table...")

    if 'approval_logs' not in existing_tables:
        op.create_table(
            'approval_logs',
            sa.Column('log_id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('entity_type', sa.String(length=64), nullable=False),
            sa.Column('entity_id', sa.String(length=128), nullable=False),
            sa.Column('approver', sa.String(length=64), nullable=False),
            sa.Column('status', sa.String(length=32), nullable=False),
            sa.Column('comment', sa.String()),
            sa.Column('approved_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('log_id')
        )
        op.create_index('ix_approval_logs_entity', 'approval_logs', ['entity_type', 'entity_id'])
        op.create_index('ix_approval_logs_approver', 'approval_logs', ['approver', 'status'])
        safe_print("[OK] approval_logs table created")
    else:
        safe_print("[SKIP] approval_logs table already exists")

    # ==================== 5. attendance_records ====================
    safe_print("[5/106] Creating attendance_records table...")

    if 'attendance_records' not in existing_tables:
        op.create_table(
            'attendance_records',
            sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
            sa.Column('employee_code', sa.String(length=64), nullable=False),
            sa.Column('attendance_date', sa.Date(), nullable=False),
            sa.Column('clock_in_time', sa.DateTime()),
            sa.Column('clock_out_time', sa.DateTime()),
            sa.Column('work_hours', sa.Numeric()),
            sa.Column('status', sa.String(length=32), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('employee_code', 'attendance_date', name='uq_attendance_records')
        )
        op.create_index('ix_attendance_records_date', 'attendance_records', ['attendance_date'])
        op.create_index('ix_attendance_records_employee', 'attendance_records', ['employee_code'])
        safe_print("[OK] attendance_records table created")
    else:
        safe_print("[SKIP] attendance_records table already exists")

    # ==================== 6. catalog_files ====================
    safe_print("[6/106] Creating catalog_files table...")

    if 'catalog_files' not in existing_tables:
        op.create_table(
            'catalog_files',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('file_path', sa.String(length=1024), nullable=False),
            sa.Column('file_name', sa.String(length=255), nullable=False),
            sa.Column('source', sa.String(length=64), nullable=False),
            sa.Column('file_size', sa.Integer()),
            sa.Column('file_hash', sa.String(length=64)),
            sa.Column('platform_code', sa.String(length=32)),
            sa.Column('account', sa.String(length=128)),
            sa.Column('shop_id', sa.String(length=256)),
            sa.Column('data_domain', sa.String(length=64)),
            sa.Column('granularity', sa.String(length=16)),
            sa.Column('date_from', sa.Date()),
            sa.Column('date_to', sa.Date()),
            sa.Column('source_platform', sa.String(length=32)),
            sa.Column('sub_domain', sa.String(length=64)),
            sa.Column('storage_layer', sa.String(length=32)),
            sa.Column('quality_score', sa.Numeric()),
            sa.Column('validation_errors', sa.JSON),
            sa.Column('meta_file_path', sa.String(length=1024)),
            sa.Column('file_metadata', sa.JSON),
            sa.Column('status', sa.String(length=32), nullable=False),
            sa.Column('error_message', sa.String()),
            sa.Column('first_seen_at', sa.DateTime(), nullable=False),
            sa.Column('last_processed_at', sa.DateTime()),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('file_hash', name='uq_catalog_files_hash')
        )
        op.create_index('ix_catalog_quality_score', 'catalog_files', ['quality_score'])
        op.create_index('ix_catalog_source_domain', 'catalog_files', ['source_platform', 'data_domain'])
        op.create_index('ix_catalog_files_status', 'catalog_files', ['status'])
        op.create_index('ix_catalog_sub_domain', 'catalog_files', ['sub_domain'])
        op.create_index('ix_catalog_files_platform_shop', 'catalog_files', ['platform_code', 'shop_id'])
        op.create_index('ix_catalog_storage_layer', 'catalog_files', ['storage_layer'])
        op.create_index('ix_catalog_files_dates', 'catalog_files', ['date_from', 'date_to'])
        safe_print("[OK] catalog_files table created")
    else:
        safe_print("[SKIP] catalog_files table already exists")

    # ==================== 7. collection_configs ====================
    safe_print("[7/106] Creating collection_configs table...")

    if 'collection_configs' not in existing_tables:
        op.create_table(
            'collection_configs',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.Column('platform', sa.String(length=50), nullable=False),
            sa.Column('account_ids', sa.JSON, nullable=False),
            sa.Column('data_domains', sa.JSON, nullable=False),
            sa.Column('sub_domains', sa.JSON),
            sa.Column('granularity', sa.String(length=20), nullable=False),
            sa.Column('date_range_type', sa.String(length=20), nullable=False),
            sa.Column('custom_date_start', sa.Date()),
            sa.Column('custom_date_end', sa.Date()),
            sa.Column('schedule_enabled', sa.Boolean(), nullable=False),
            sa.Column('schedule_cron', sa.String(length=50)),
            sa.Column('retry_count', sa.Integer(), nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.Column('created_by', sa.String(length=100)),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('name', 'platform', name='uq_collection_configs_name_platform')
        )
        op.create_index('ix_collection_configs_platform', 'collection_configs', ['platform'])
        op.create_index('ix_collection_configs_active', 'collection_configs', ['is_active'])
        safe_print("[OK] collection_configs table created")
    else:
        safe_print("[SKIP] collection_configs table already exists")

    # ==================== 8. collection_sync_points ====================
    safe_print("[8/106] Creating collection_sync_points table...")

    if 'collection_sync_points' not in existing_tables:
        op.create_table(
            'collection_sync_points',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('platform', sa.String(length=50), nullable=False),
            sa.Column('account_id', sa.String(length=100), nullable=False),
            sa.Column('data_domain', sa.String(length=50), nullable=False),
            sa.Column('last_sync_at', sa.DateTime(), nullable=False),
            sa.Column('last_sync_value', sa.String(length=200)),
            sa.Column('total_synced_count', sa.Integer()),
            sa.Column('last_batch_count', sa.Integer()),
            sa.Column('sync_mode', sa.String(length=20)),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('platform', 'account_id', 'data_domain', name='uq_sync_point')
        )
        op.create_index('ix_sync_points_last_sync', 'collection_sync_points', ['last_sync_at'])
        op.create_index('ix_sync_points_platform_account', 'collection_sync_points', ['platform', 'account_id'])
        safe_print("[OK] collection_sync_points table created")
    else:
        safe_print("[SKIP] collection_sync_points table already exists")

    # ==================== 9. collection_tasks ====================
    safe_print("[9/106] Creating collection_tasks table...")

    if 'collection_tasks' not in existing_tables:
        op.create_table(
            'collection_tasks',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('task_id', sa.String(length=100), nullable=False),
            sa.Column('platform', sa.String(length=50), nullable=False),
            sa.Column('account', sa.String(length=100), nullable=False),
            sa.Column('status', sa.String(length=20), nullable=False),
            sa.Column('config_id', sa.Integer()),
            sa.Column('progress', sa.Integer(), nullable=False),
            sa.Column('current_step', sa.String(length=200)),
            sa.Column('files_collected', sa.Integer(), nullable=False),
            sa.Column('trigger_type', sa.String(length=20), nullable=False),
            sa.Column('data_domains', sa.JSON),
            sa.Column('sub_domains', sa.JSON),
            sa.Column('granularity', sa.String(length=20)),
            sa.Column('date_range', sa.JSON),
            sa.Column('total_domains', sa.Integer(), nullable=False),
            sa.Column('completed_domains', sa.JSON),
            sa.Column('failed_domains', sa.JSON),
            sa.Column('current_domain', sa.String(length=100)),
            sa.Column('error_message', sa.String()),
            sa.Column('error_screenshot_path', sa.String(length=500)),
            sa.Column('duration_seconds', sa.Integer()),
            sa.Column('retry_count', sa.Integer(), nullable=False),
            sa.Column('parent_task_id', sa.Integer()),
            sa.Column('verification_type', sa.String(length=50)),
            sa.Column('verification_screenshot', sa.String(length=500)),
            sa.Column('debug_mode', sa.Boolean(), nullable=False),
            sa.Column('version', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('task_id', name='uq_collection_tasks_task_id'),
            sa.ForeignKeyConstraint(['config_id'], ['collection_configs.id'], ),
            sa.ForeignKeyConstraint(['parent_task_id'], ['collection_tasks.id'], )
        )
        op.create_index('ix_collection_tasks_created', 'collection_tasks', ['created_at'])
        op.create_index('ix_collection_tasks_platform', 'collection_tasks', ['platform'])
        op.create_index('ix_collection_tasks_status', 'collection_tasks', ['status'])
        op.create_index('ix_collection_tasks_config', 'collection_tasks', ['config_id'])
        safe_print("[OK] collection_tasks table created")
    else:
        safe_print("[SKIP] collection_tasks table already exists")

    # ==================== 10. collection_task_logs ====================
    safe_print("[10/106] Creating collection_task_logs table...")

    if 'collection_task_logs' not in existing_tables:
        op.create_table(
            'collection_task_logs',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('task_id', sa.Integer(), nullable=False),
            sa.Column('level', sa.String(length=10), nullable=False),
            sa.Column('message', sa.String(), nullable=False),
            sa.Column('details', sa.JSON),
            sa.Column('timestamp', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['task_id'], ['collection_tasks.id'], )
        )
        op.create_index('ix_collection_task_logs_time', 'collection_task_logs', ['timestamp'])
        op.create_index('ix_collection_task_logs_task', 'collection_task_logs', ['task_id'])
        op.create_index('ix_collection_task_logs_level', 'collection_task_logs', ['level'])
        safe_print("[OK] collection_task_logs table created")
    else:
        safe_print("[SKIP] collection_task_logs table already exists")

    # ==================== 11. component_versions ====================
    safe_print("[11/106] Creating component_versions table...")

    if 'component_versions' not in existing_tables:
        op.create_table(
            'component_versions',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('component_name', sa.String(length=100), nullable=False),
            sa.Column('version', sa.String(length=20), nullable=False),
            sa.Column('file_path', sa.String(length=200), nullable=False),
            sa.Column('is_stable', sa.Boolean()),
            sa.Column('is_active', sa.Boolean()),
            sa.Column('is_testing', sa.Boolean()),
            sa.Column('usage_count', sa.Integer()),
            sa.Column('success_count', sa.Integer()),
            sa.Column('failure_count', sa.Integer()),
            sa.Column('success_rate', sa.Numeric()),
            sa.Column('test_ratio', sa.Numeric()),
            sa.Column('test_start_at', sa.DateTime()),
            sa.Column('test_end_at', sa.DateTime()),
            sa.Column('description', sa.String()),
            sa.Column('created_by', sa.String(length=100)),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('component_name', 'version', name='uq_component_version')
        )
        op.create_index('ix_component_versions_name', 'component_versions', ['component_name'])
        op.create_index('ix_component_versions_stable', 'component_versions', ['is_stable'])
        op.create_index('ix_component_versions_success_rate', 'component_versions', ['success_rate'])
        safe_print("[OK] component_versions table created")
    else:
        safe_print("[SKIP] component_versions table already exists")

    # ==================== 12. component_test_history ====================
    safe_print("[12/106] Creating component_test_history table...")

    if 'component_test_history' not in existing_tables:
        op.create_table(
            'component_test_history',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('test_id', sa.String(length=36), nullable=False),
            sa.Column('component_name', sa.String(length=100), nullable=False),
            sa.Column('component_version', sa.String(length=20)),
            sa.Column('version_id', sa.Integer()),
            sa.Column('platform', sa.String(length=50), nullable=False),
            sa.Column('account_id', sa.String(length=100), nullable=False),
            sa.Column('headless', sa.Boolean()),
            sa.Column('status', sa.String(length=20), nullable=False),
            sa.Column('duration_ms', sa.Integer(), nullable=False),
            sa.Column('steps_total', sa.Integer(), nullable=False),
            sa.Column('steps_passed', sa.Integer(), nullable=False),
            sa.Column('steps_failed', sa.Integer(), nullable=False),
            sa.Column('success_rate', sa.Numeric(), nullable=False),
            sa.Column('step_results', sa.dialects.postgresql.JSONB, nullable=False),
            sa.Column('error_message', sa.String()),
            sa.Column('browser_info', sa.dialects.postgresql.JSONB),
            sa.Column('tested_by', sa.String(length=100)),
            sa.Column('tested_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('test_id'),
            sa.ForeignKeyConstraint(['version_id'], ['component_versions.id'], )
        )
        op.create_index('ix_test_history_version', 'component_test_history', ['version_id'])
        op.create_index('ix_test_history_component', 'component_test_history', ['component_name'])
        op.create_index('ix_test_history_status', 'component_test_history', ['status'])
        op.create_index('ix_test_history_tested_at', 'component_test_history', ['tested_at'])
        safe_print("[OK] component_test_history table created")
    else:
        safe_print("[SKIP] component_test_history table already exists")

    # ==================== 13. data_files ====================
    safe_print("[13/106] Creating data_files table...")

    if 'data_files' not in existing_tables:
        op.create_table(
            'data_files',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('file_name', sa.String(length=255), nullable=False),
            sa.Column('file_path', sa.String(length=500), nullable=False),
            sa.Column('platform', sa.String(length=50), nullable=False),
            sa.Column('data_type', sa.String(length=50), nullable=False),
            sa.Column('status', sa.String(length=50), nullable=False),
            sa.Column('discovery_time', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_data_files_platform', 'data_files', ['platform'])
        op.create_index('ix_data_files_status', 'data_files', ['status'])
        safe_print("[OK] data_files table created")
    else:
        safe_print("[SKIP] data_files table already exists")

    # ==================== 14. data_quarantine ====================
    safe_print("[14/106] Creating data_quarantine table...")

    if 'data_quarantine' not in existing_tables:
        op.create_table(
            'data_quarantine',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('source_file', sa.String(length=500), nullable=False),
            sa.Column('catalog_file_id', sa.Integer()),
            sa.Column('row_number', sa.Integer()),
            sa.Column('row_data', sa.String(), nullable=False),
            sa.Column('error_type', sa.String(length=100), nullable=False),
            sa.Column('error_msg', sa.String()),
            sa.Column('platform_code', sa.String(length=32)),
            sa.Column('shop_id', sa.String(length=64)),
            sa.Column('data_domain', sa.String(length=64)),
            sa.Column('is_resolved', sa.Boolean()),
            sa.Column('resolved_at', sa.DateTime()),
            sa.Column('resolution_note', sa.String()),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['catalog_file_id'], ['catalog_files.id'], )
        )
        op.create_index('ix_quarantine_platform_shop', 'data_quarantine', ['platform_code', 'shop_id'])
        op.create_index('ix_quarantine_source_file', 'data_quarantine', ['source_file'])
        op.create_index('ix_quarantine_created', 'data_quarantine', ['created_at'])
        op.create_index('ix_quarantine_error_type', 'data_quarantine', ['error_type'])
        op.create_index('ix_quarantine_resolved', 'data_quarantine', ['is_resolved'])
        safe_print("[OK] data_quarantine table created")
    else:
        safe_print("[SKIP] data_quarantine table already exists")

    # ==================== 15. data_records ====================
    safe_print("[15/106] Creating data_records table...")

    if 'data_records' not in existing_tables:
        op.create_table(
            'data_records',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('platform', sa.String(length=50), nullable=False),
            sa.Column('record_type', sa.String(length=50), nullable=False),
            sa.Column('data', sa.JSON),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_data_records_platform', 'data_records', ['platform'])
        op.create_index('ix_data_records_type', 'data_records', ['record_type'])
        safe_print("[OK] data_records table created")
    else:
        safe_print("[SKIP] data_records table already exists")

    # ==================== 16. dim_currencies ====================
    safe_print("[16/106] Creating dim_currencies table...")

    if 'dim_currencies' not in existing_tables:
        op.create_table(
            'dim_currencies',
            sa.Column('currency_code', sa.String(length=8), nullable=False),
            sa.Column('currency_name', sa.String(length=64), nullable=False),
            sa.Column('symbol', sa.String(length=8)),
            sa.Column('is_base', sa.Boolean()),
            sa.Column('active', sa.Boolean()),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('currency_code')
        )
        safe_print("[OK] dim_currencies table created")
    else:
        safe_print("[SKIP] dim_currencies table already exists")

    # ==================== 17. dim_currency_rates ====================
    safe_print("[17/106] Creating dim_currency_rates table...")

    if 'dim_currency_rates' not in existing_tables:
        op.create_table(
            'dim_currency_rates',
            sa.Column('rate_date', sa.Date(), nullable=False),
            sa.Column('base_currency', sa.String(length=8), nullable=False),
            sa.Column('quote_currency', sa.String(length=8), nullable=False),
            sa.Column('rate', sa.Numeric(), nullable=False),
            sa.Column('source', sa.String(length=64)),
            sa.Column('fetched_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('rate_date', 'base_currency', 'quote_currency')
        )
        op.create_index('ix_currency_base_quote', 'dim_currency_rates', ['base_currency', 'quote_currency'])
        safe_print("[OK] dim_currency_rates table created")
    else:
        safe_print("[SKIP] dim_currency_rates table already exists")

    # ==================== 18. dim_exchange_rates ====================
    safe_print("[18/106] Creating dim_exchange_rates table...")

    if 'dim_exchange_rates' not in existing_tables:
        op.create_table(
            'dim_exchange_rates',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('from_currency', sa.String(length=3), nullable=False),
            sa.Column('to_currency', sa.String(length=3), nullable=False),
            sa.Column('rate_date', sa.Date(), nullable=False),
            sa.Column('rate', sa.Numeric(), nullable=False),
            sa.Column('source', sa.String(length=50)),
            sa.Column('priority', sa.Integer()),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('from_currency', 'to_currency', 'rate_date', name='uq_exchange_rate')
        )
        op.create_index('ix_exchange_rate_lookup', 'dim_exchange_rates', ['from_currency', 'to_currency', 'rate_date'])
        op.create_index('ix_dim_exchange_rates_to_currency', 'dim_exchange_rates', ['to_currency'])
        op.create_index('ix_dim_exchange_rates_rate_date', 'dim_exchange_rates', ['rate_date'])
        op.create_index('ix_exchange_rate_date', 'dim_exchange_rates', ['rate_date'])
        op.create_index('ix_dim_exchange_rates_from_currency', 'dim_exchange_rates', ['from_currency'])
        safe_print("[OK] dim_exchange_rates table created")
    else:
        safe_print("[SKIP] dim_exchange_rates table already exists")

    # ==================== 19. dim_fiscal_calendar ====================
    safe_print("[19/106] Creating dim_fiscal_calendar table...")

    if 'dim_fiscal_calendar' not in existing_tables:
        op.create_table(
            'dim_fiscal_calendar',
            sa.Column('period_id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('period_year', sa.Integer(), nullable=False),
            sa.Column('period_month', sa.Integer(), nullable=False),
            sa.Column('period_code', sa.String(length=16), nullable=False),
            sa.Column('start_date', sa.Date(), nullable=False),
            sa.Column('end_date', sa.Date(), nullable=False),
            sa.Column('status', sa.String(length=32), nullable=False),
            sa.Column('closed_by', sa.String(length=64)),
            sa.Column('closed_at', sa.DateTime()),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('period_id'),
            sa.UniqueConstraint('period_code'),
            sa.UniqueConstraint('period_year', 'period_month', name='uq_fiscal_period')
        )
        op.create_index('ix_fiscal_calendar_status', 'dim_fiscal_calendar', ['status'])
        op.create_index('ix_fiscal_calendar_year_month', 'dim_fiscal_calendar', ['period_year', 'period_month'])
        safe_print("[OK] dim_fiscal_calendar table created")
    else:
        safe_print("[SKIP] dim_fiscal_calendar table already exists")

    # ==================== 20. dim_metric_formulas ====================
    safe_print("[20/106] Creating dim_metric_formulas table...")

    if 'dim_metric_formulas' not in existing_tables:
        op.create_table(
            'dim_metric_formulas',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('metric_code', sa.String(length=128), nullable=False),
            sa.Column('cn_name', sa.String(length=128), nullable=False),
            sa.Column('en_name', sa.String(length=128)),
            sa.Column('description', sa.String()),
            sa.Column('data_domain', sa.String(length=64), nullable=False),
            sa.Column('metric_type', sa.String(length=32), nullable=False),
            sa.Column('sql_expr', sa.String(), nullable=False),
            sa.Column('depends_on', sa.JSON),
            sa.Column('aggregator', sa.String(length=32)),
            sa.Column('unit', sa.String(length=32)),
            sa.Column('display_format', sa.String(length=64)),
            sa.Column('active', sa.Boolean()),
            sa.Column('version', sa.Integer(), nullable=False),
            sa.Column('created_by', sa.String(length=64)),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime()),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_metric_formula_domain', 'dim_metric_formulas', ['data_domain', 'active'])
        op.create_index('ix_dim_metric_formulas_data_domain', 'dim_metric_formulas', ['data_domain'])
        op.create_index('ix_dim_metric_formulas_metric_code', 'dim_metric_formulas', ['metric_code'])
        safe_print("[OK] dim_metric_formulas table created")
    else:
        safe_print("[SKIP] dim_metric_formulas table already exists")

    # ==================== 21. dim_platforms ====================
    safe_print("[21/106] Creating dim_platforms table...")

    if 'dim_platforms' not in existing_tables:
        op.create_table(
            'dim_platforms',
            sa.Column('platform_code', sa.String(length=32), nullable=False),
            sa.Column('name', sa.String(length=64), nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('platform_code'),
            sa.UniqueConstraint('name', name='uq_dim_platforms_name')
        )
        safe_print("[OK] dim_platforms table created")
    else:
        safe_print("[SKIP] dim_platforms table already exists")

    # ==================== 22. dim_product_master ====================
    safe_print("[22/106] Creating dim_product_master table...")

    if 'dim_product_master' not in existing_tables:
        op.create_table(
            'dim_product_master',
            sa.Column('product_id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('company_sku', sa.String(length=128), nullable=False),
            sa.Column('product_title', sa.String(length=512)),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('product_id'),
            sa.UniqueConstraint('company_sku')
        )
        safe_print("[OK] dim_product_master table created")
    else:
        safe_print("[SKIP] dim_product_master table already exists")

    # ==================== 23. dim_products ====================
    safe_print("[23/106] Creating dim_products table...")

    if 'dim_products' not in existing_tables:
        op.create_table(
            'dim_products',
            sa.Column('platform_code', sa.String(length=32), nullable=False),
            sa.Column('shop_id', sa.String(length=64), nullable=False),
            sa.Column('platform_sku', sa.String(length=128), nullable=False),
            sa.Column('product_title', sa.String(length=512)),
            sa.Column('category', sa.String(length=128)),
            sa.Column('status', sa.String(length=32)),
            sa.Column('image_url', sa.String(length=1024)),
            sa.Column('image_path', sa.String(length=512)),
            sa.Column('image_last_fetched_at', sa.DateTime()),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('platform_code', 'shop_id', 'platform_sku')
        )
        op.create_index('ix_dim_products_platform_shop', 'dim_products', ['platform_code', 'shop_id'])
        safe_print("[OK] dim_products table created")
    else:
        safe_print("[SKIP] dim_products table already exists")

    # ==================== 24. bridge_product_keys ====================
    safe_print("[24/106] Creating bridge_product_keys table...")

    if 'bridge_product_keys' not in existing_tables:
        op.create_table(
            'bridge_product_keys',
            sa.Column('product_id', sa.Integer(), nullable=False),
            sa.Column('platform_code', sa.String(length=32), nullable=False),
            sa.Column('shop_id', sa.String(length=64), nullable=False),
            sa.Column('platform_sku', sa.String(length=128), nullable=False),
            sa.PrimaryKeyConstraint('product_id', 'platform_code', 'shop_id', 'platform_sku'),
            sa.UniqueConstraint('platform_code', 'shop_id', 'platform_sku', name='uq_bridge_platform_sku'),
            sa.ForeignKeyConstraint(['product_id'], ['dim_product_master.product_id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(
                ['platform_code', 'shop_id', 'platform_sku'],
                ['dim_products.platform_code', 'dim_products.shop_id', 'dim_products.platform_sku'],
                ondelete='CASCADE'
            )
        )
        op.create_index('ix_bridge_product_id', 'bridge_product_keys', ['product_id'])
        safe_print("[OK] bridge_product_keys table created")
    else:
        safe_print("[SKIP] bridge_product_keys table already exists")

    # ==================== 25. dim_rate_limit_config ====================
    safe_print("[25/106] Creating dim_rate_limit_config table...")

    if 'dim_rate_limit_config' not in existing_tables:
        op.create_table(
            'dim_rate_limit_config',
            sa.Column('config_id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('role_code', sa.String(length=50), nullable=False),
            sa.Column('endpoint_type', sa.String(length=50), nullable=False),
            sa.Column('limit_value', sa.String(length=50), nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=False),
            sa.Column('description', sa.String()),
            sa.Column('created_by', sa.String(length=100)),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.Column('updated_by', sa.String(length=100)),
            sa.PrimaryKeyConstraint('config_id'),
            sa.UniqueConstraint('role_code', 'endpoint_type', name='uq_rate_limit_config_role_endpoint')
        )
        op.create_index('ix_dim_rate_limit_config_is_active', 'dim_rate_limit_config', ['is_active'])
        op.create_index('ix_dim_rate_limit_config_role_code', 'dim_rate_limit_config', ['role_code'])
        op.create_index('ix_rate_limit_config_active', 'dim_rate_limit_config', ['is_active', 'role_code'])
        op.create_index('ix_dim_rate_limit_config_endpoint_type', 'dim_rate_limit_config', ['endpoint_type'])
        op.create_index('ix_rate_limit_config_role', 'dim_rate_limit_config', ['role_code', 'endpoint_type'])
        safe_print("[OK] dim_rate_limit_config table created")
    else:
        safe_print("[SKIP] dim_rate_limit_config table already exists")

    # ==================== 26. dim_roles ====================
    safe_print("[26/106] Creating dim_roles table...")

    if 'dim_roles' not in existing_tables:
        op.create_table(
            'dim_roles',
            sa.Column('role_id', sa.BigInteger(), nullable=False, autoincrement=True),
            sa.Column('role_name', sa.String(length=100), nullable=False),
            sa.Column('role_code', sa.String(length=50), nullable=False),
            sa.Column('description', sa.String()),
            sa.Column('permissions', sa.String(), nullable=False),
            sa.Column('data_scope', sa.String(length=50)),
            sa.Column('is_active', sa.Boolean(), nullable=False),
            sa.Column('is_system', sa.Boolean()),
            sa.Column('created_at', sa.DateTime(), server_default=func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=func.now()),
            sa.PrimaryKeyConstraint('role_id'),
            sa.UniqueConstraint('role_code')
        )
        op.create_index('ix_dim_roles_role_name', 'dim_roles', ['role_name'])
        op.create_index('idx_roles_active', 'dim_roles', ['is_active'])
        op.create_index('ix_dim_roles_role_id', 'dim_roles', ['role_id'])
        safe_print("[OK] dim_roles table created")
    else:
        safe_print("[SKIP] dim_roles table already exists")

    # ==================== 27. dim_shops ====================
    safe_print("[27/106] Creating dim_shops table...")

    if 'dim_shops' not in existing_tables:
        op.create_table(
            'dim_shops',
            sa.Column('platform_code', sa.String(length=32), nullable=False),
            sa.Column('shop_id', sa.String(length=256), nullable=False),
            sa.Column('shop_slug', sa.String(length=128)),
            sa.Column('shop_name', sa.String(length=256)),
            sa.Column('region', sa.String(length=16)),
            sa.Column('currency', sa.String(length=8)),
            sa.Column('timezone', sa.String(length=64)),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('platform_code', 'shop_id'),
            sa.ForeignKeyConstraint(['platform_code'], ['dim_platforms.platform_code'], )
        )
        op.create_index('ix_dim_shops_platform_slug', 'dim_shops', ['platform_code', 'shop_slug'])
        op.create_index('ix_dim_shops_platform_shop', 'dim_shops', ['platform_code', 'shop_id'])
        safe_print("[OK] dim_shops table created")
    else:
        safe_print("[SKIP] dim_shops table already exists")

    # ==================== 28. clearance_rankings ====================
    safe_print("[28/106] Creating clearance_rankings table...")

    if 'clearance_rankings' not in existing_tables:
        op.create_table(
            'clearance_rankings',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('platform_code', sa.String(length=32), nullable=False),
            sa.Column('shop_id', sa.String(length=64), nullable=False),
            sa.Column('metric_date', sa.Date(), nullable=False),
            sa.Column('granularity', sa.String(length=16), nullable=False),
            sa.Column('clearance_amount', sa.Numeric(), nullable=False),
            sa.Column('clearance_quantity', sa.Integer(), nullable=False),
            sa.Column('incentive_amount', sa.Numeric(), nullable=False),
            sa.Column('total_incentive', sa.Numeric(), nullable=False),
            sa.Column('rank', sa.Integer()),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('platform_code', 'shop_id', 'metric_date', 'granularity', name='uq_clearance_ranking'),
            sa.ForeignKeyConstraint(['shop_id'], ['dim_shops.shop_id'], ),
            sa.ForeignKeyConstraint(['platform_code'], ['dim_shops.platform_code'], )
        )
        op.create_index('ix_clearance_ranking_date', 'clearance_rankings', ['metric_date', 'granularity'])
        op.create_index('ix_clearance_ranking_rank', 'clearance_rankings', ['rank'])
        op.create_index('ix_clearance_ranking_amount', 'clearance_rankings', ['clearance_amount'])
        safe_print("[OK] clearance_rankings table created")
    else:
        safe_print("[SKIP] clearance_rankings table already exists")

    # ==================== 29. dim_users ====================
    safe_print("[29/106] Creating dim_users table...")

    if 'dim_users' not in existing_tables:
        op.create_table(
            'dim_users',
            sa.Column('user_id', sa.BigInteger(), nullable=False, autoincrement=True),
            sa.Column('username', sa.String(length=100), nullable=False),
            sa.Column('email', sa.String(length=255), nullable=False),
            sa.Column('full_name', sa.String(length=200)),
            sa.Column('password_hash', sa.String(length=255), nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=False),
            sa.Column('is_superuser', sa.Boolean(), nullable=False),
            sa.Column('status', sa.String(length=20), nullable=False),
            sa.Column('approved_at', sa.DateTime()),
            sa.Column('approved_by', sa.BigInteger()),
            sa.Column('rejection_reason', sa.String()),
            sa.Column('allowed_platforms', sa.String()),
            sa.Column('allowed_shops', sa.String()),
            sa.Column('phone', sa.String(length=50)),
            sa.Column('department', sa.String(length=100)),
            sa.Column('position', sa.String(length=100)),
            sa.Column('last_login', sa.DateTime()),
            sa.Column('login_count', sa.Integer()),
            sa.Column('failed_login_attempts', sa.Integer()),
            sa.Column('locked_until', sa.DateTime()),
            sa.Column('created_at', sa.DateTime(), server_default=func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=func.now()),
            sa.PrimaryKeyConstraint('user_id'),
            sa.ForeignKeyConstraint(['approved_by'], ['dim_users.user_id'], )
        )
        op.create_index('idx_users_active', 'dim_users', ['is_active'])
        op.create_index('ix_dim_users_status', 'dim_users', ['status'])
        op.create_index('ix_dim_users_username', 'dim_users', ['username'])
        op.create_index('idx_users_email_active', 'dim_users', ['email', 'is_active'])
        op.create_index('ix_dim_users_user_id', 'dim_users', ['user_id'])
        op.create_index('ix_dim_users_email', 'dim_users', ['email'])
        safe_print("[OK] dim_users table created")
    else:
        safe_print("[SKIP] dim_users table already exists")

    # ==================== 30. backup_records ====================
    safe_print("[30/106] Creating backup_records table...")

    if 'backup_records' not in existing_tables:
        op.create_table(
            'backup_records',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('backup_type', sa.String(length=32), nullable=False),
            sa.Column('backup_path', sa.String(length=512), nullable=False),
            sa.Column('backup_size', sa.BigInteger(), nullable=False),
            sa.Column('checksum', sa.String(length=64)),
            sa.Column('status', sa.String(length=32), nullable=False),
            sa.Column('description', sa.String()),
            sa.Column('created_by', sa.Integer()),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('completed_at', sa.DateTime()),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['created_by'], ['dim_users.user_id'], )
        )
        op.create_index('ix_backup_records_status', 'backup_records', ['status'])
        op.create_index('ix_backup_records_created_at', 'backup_records', ['created_at'])
        safe_print("[OK] backup_records table created")
    else:
        safe_print("[SKIP] backup_records table already exists")

    # ==================== 31. dim_vendors ====================
    safe_print("[31/106] Creating dim_vendors table...")

    if 'dim_vendors' not in existing_tables:
        op.create_table(
            'dim_vendors',
            sa.Column('vendor_code', sa.String(length=64), nullable=False),
            sa.Column('vendor_name', sa.String(length=256), nullable=False),
            sa.Column('country', sa.String(length=64)),
            sa.Column('tax_id', sa.String(length=128)),
            sa.Column('payment_terms', sa.String(length=64)),
            sa.Column('credit_limit', sa.Numeric()),
            sa.Column('status', sa.String(length=32), nullable=False),
            sa.Column('contact_person', sa.String(length=128)),
            sa.Column('contact_phone', sa.String(length=64)),
            sa.Column('contact_email', sa.String(length=128)),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime()),
            sa.PrimaryKeyConstraint('vendor_code')
        )
        op.create_index('ix_vendors_status', 'dim_vendors', ['status'])
        safe_print("[OK] dim_vendors table created")
    else:
        safe_print("[SKIP] dim_vendors table already exists")

    # ==================== 32. employee_commissions ====================
    safe_print("[32/106] Creating employee_commissions table...")

    if 'employee_commissions' not in existing_tables:
        op.create_table(
            'employee_commissions',
            sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
            sa.Column('employee_code', sa.String(length=64), nullable=False),
            sa.Column('year_month', sa.String(length=7), nullable=False),
            sa.Column('sales_amount', sa.Numeric(precision=15, scale=2), nullable=False),
            sa.Column('commission_amount', sa.Numeric(precision=15, scale=2), nullable=False),
            sa.Column('commission_rate', sa.Numeric(), nullable=False),
            sa.Column('calculated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('employee_code', 'year_month', name='uq_employee_commissions')
        )
        op.create_index('ix_employee_commissions_employee', 'employee_commissions', ['employee_code'])
        op.create_index('ix_employee_commissions_month', 'employee_commissions', ['year_month'])
        safe_print("[OK] employee_commissions table created")
    else:
        safe_print("[SKIP] employee_commissions table already exists")

    # ==================== 33. employee_performance ====================
    safe_print("[33/106] Creating employee_performance table...")

    if 'employee_performance' not in existing_tables:
        op.create_table(
            'employee_performance',
            sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
            sa.Column('employee_code', sa.String(length=64), nullable=False),
            sa.Column('year_month', sa.String(length=7), nullable=False),
            sa.Column('actual_sales', sa.Numeric(precision=15, scale=2), nullable=False),
            sa.Column('achievement_rate', sa.Numeric(), nullable=False),
            sa.Column('performance_score', sa.Numeric(), nullable=False),
            sa.Column('calculated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('employee_code', 'year_month', name='uq_employee_performance')
        )
        op.create_index('ix_employee_performance_employee', 'employee_performance', ['employee_code'])
        op.create_index('ix_employee_performance_month', 'employee_performance', ['year_month'])
        safe_print("[OK] employee_performance table created")
    else:
        safe_print("[SKIP] employee_performance table already exists")

    # ==================== 34. employee_targets ====================
    safe_print("[34/106] Creating employee_targets table...")

    if 'employee_targets' not in existing_tables:
        op.create_table(
            'employee_targets',
            sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
            sa.Column('employee_code', sa.String(length=64), nullable=False),
            sa.Column('year_month', sa.String(length=7), nullable=False),
            sa.Column('target_type', sa.String(length=32), nullable=False),
            sa.Column('target_value', sa.Numeric(precision=15, scale=2), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('employee_code', 'year_month', 'target_type', name='uq_employee_targets')
        )
        op.create_index('ix_employee_targets_employee', 'employee_targets', ['employee_code'])
        op.create_index('ix_employee_targets_month', 'employee_targets', ['year_month'])
        safe_print("[OK] employee_targets table created")
    else:
        safe_print("[SKIP] employee_targets table already exists")

    # ==================== 35. employees ====================
    safe_print("[35/106] Creating employees table...")

    if 'employees' not in existing_tables:
        op.create_table(
            'employees',
            sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
            sa.Column('employee_code', sa.String(length=64), nullable=False),
            sa.Column('name', sa.String(length=128), nullable=False),
            sa.Column('department', sa.String(length=128)),
            sa.Column('position', sa.String(length=128)),
            sa.Column('hire_date', sa.Date()),
            sa.Column('status', sa.String(length=32), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('employee_code')
        )
        op.create_index('ix_employees_code', 'employees', ['employee_code'])
        op.create_index('ix_employees_department', 'employees', ['department'])
        safe_print("[OK] employees table created")
    else:
        safe_print("[SKIP] employees table already exists")

    # ==================== 36. entity_aliases ====================
    safe_print("[36/106] Creating entity_aliases table...")

    if 'entity_aliases' not in existing_tables:
        op.create_table(
            'entity_aliases',
            sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
            sa.Column('source_platform', sa.String(length=32), nullable=False),
            sa.Column('source_type', sa.String(length=32), nullable=False),
            sa.Column('source_name', sa.String(length=256), nullable=False),
            sa.Column('source_account', sa.String(length=128)),
            sa.Column('source_site', sa.String(length=64)),
            sa.Column('data_domain', sa.String(length=64)),
            sa.Column('target_type', sa.String(length=32), nullable=False),
            sa.Column('target_id', sa.String(length=256), nullable=False),
            sa.Column('target_name', sa.String(length=256)),
            sa.Column('target_platform_code', sa.String(length=32)),
            sa.Column('confidence', sa.Numeric()),
            sa.Column('active', sa.Boolean(), nullable=False),
            sa.Column('notes', sa.String()),
            sa.Column('created_by', sa.String(length=64)),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_by', sa.String(length=64)),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('source_platform', 'source_type', 'source_name', 'source_account', 'source_site', name='uq_entity_alias_source')
        )
        op.create_index('ix_entity_aliases_source_name', 'entity_aliases', ['source_name'])
        op.create_index('ix_entity_aliases_source_platform', 'entity_aliases', ['source_platform'])
        op.create_index('ix_entity_aliases_target_id', 'entity_aliases', ['target_id'])
        op.create_index('ix_entity_aliases_source', 'entity_aliases', ['source_platform', 'source_type', 'source_name'])
        op.create_index('ix_entity_aliases_source_type', 'entity_aliases', ['source_type'])
        op.create_index('ix_entity_aliases_target', 'entity_aliases', ['target_type', 'target_id', 'active'])
        op.create_index('ix_entity_aliases_target_type', 'entity_aliases', ['target_type'])
        op.create_index('ix_entity_aliases_active', 'entity_aliases', ['active'])
        safe_print("[OK] entity_aliases table created")
    else:
        safe_print("[SKIP] entity_aliases table already exists")

    # ==================== 37. fact_analytics ====================
    safe_print("[37/106] Creating fact_analytics table...")

    if 'fact_analytics' not in existing_tables:
        op.create_table(
            'fact_analytics',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('platform_code', sa.String(length=50), nullable=False),
            sa.Column('shop_id', sa.String(length=100)),
            sa.Column('account', sa.String(length=100)),
            sa.Column('analytics_date', sa.Date(), nullable=False),
            sa.Column('granularity', sa.String(length=20), nullable=False),
            sa.Column('metric_type', sa.String(length=50), nullable=False),
            sa.Column('metric_value', sa.Numeric(precision=15, scale=2), nullable=False),
            sa.Column('data_domain', sa.String(length=50), nullable=False),
            sa.Column('attributes', sa.dialects.postgresql.JSONB),
            sa.Column('file_id', sa.Integer()),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=func.now()),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('platform_code', 'shop_id', 'analytics_date', 'granularity', 'metric_type', 'data_domain', name='uq_fact_analytics_business'),
            sa.ForeignKeyConstraint(['file_id'], ['catalog_files.id'], )
        )
        op.create_index('ix_fact_analytics_file_id', 'fact_analytics', ['file_id'])
        op.create_index('ix_fact_analytics_shop_id', 'fact_analytics', ['shop_id'])
        op.create_index('ix_fact_analytics_analytics_date', 'fact_analytics', ['analytics_date'])
        op.create_index('ix_fact_analytics_platform_code', 'fact_analytics', ['platform_code'])
        safe_print("[OK] fact_analytics table created")
    else:
        safe_print("[SKIP] fact_analytics table already exists")

    # ==================== 38. fact_audit_logs ====================
    safe_print("[38/106] Creating fact_audit_logs table...")

    if 'fact_audit_logs' not in existing_tables:
        op.create_table(
            'fact_audit_logs',
            sa.Column('log_id', sa.BigInteger(), nullable=False, autoincrement=True),
            sa.Column('user_id', sa.BigInteger(), nullable=False),
            sa.Column('username', sa.String(length=100), nullable=False),
            sa.Column('action_type', sa.String(length=50), nullable=False),
            sa.Column('resource_type', sa.String(length=100), nullable=False),
            sa.Column('resource_id', sa.String(length=150)),
            sa.Column('action_description', sa.String()),
            sa.Column('changes_json', sa.String()),
            sa.Column('ip_address', sa.String(length=50)),
            sa.Column('user_agent', sa.String(length=500)),
            sa.Column('is_success', sa.Boolean()),
            sa.Column('error_message', sa.String()),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=func.now()),
            sa.PrimaryKeyConstraint('log_id'),
            sa.ForeignKeyConstraint(['user_id'], ['dim_users.user_id'], )
        )
        op.create_index('ix_fact_audit_logs_created_at', 'fact_audit_logs', ['created_at'])
        op.create_index('ix_fact_audit_logs_log_id', 'fact_audit_logs', ['log_id'])
        op.create_index('idx_audit_action_time', 'fact_audit_logs', ['action_type', 'created_at'])
        op.create_index('ix_fact_audit_logs_action_type', 'fact_audit_logs', ['action_type'])
        op.create_index('idx_audit_resource', 'fact_audit_logs', ['resource_type', 'resource_id'])
        op.create_index('idx_audit_recent', 'fact_audit_logs', ['created_at'])
        op.create_index('idx_audit_user_time', 'fact_audit_logs', ['user_id', 'created_at'])
        safe_print("[OK] fact_audit_logs table created")
    else:
        safe_print("[SKIP] fact_audit_logs table already exists")

    # ==================== 39. fact_expenses_month ====================
    safe_print("[39/106] Creating fact_expenses_month table...")

    if 'fact_expenses_month' not in existing_tables:
        op.create_table(
            'fact_expenses_month',
            sa.Column('expense_id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('period_month', sa.String(length=16), nullable=False),
            sa.Column('cost_center', sa.String(length=64)),
            sa.Column('expense_type', sa.String(length=128), nullable=False),
            sa.Column('vendor', sa.String(length=256)),
            sa.Column('currency', sa.String(length=8), nullable=False),
            sa.Column('currency_amt', sa.Numeric()),
            sa.Column('base_amt', sa.Numeric()),
            sa.Column('tax_amt', sa.Numeric()),
            sa.Column('platform_code', sa.String(length=32)),
            sa.Column('shop_id', sa.String(length=64)),
            sa.Column('source_file_id', sa.Integer()),
            sa.Column('memo', sa.String()),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('expense_id'),
            sa.ForeignKeyConstraint(['source_file_id'], ['catalog_files.id'], ),
            sa.ForeignKeyConstraint(['period_month'], ['dim_fiscal_calendar.period_code'], )
        )
        op.create_index('ix_expenses_month_period', 'fact_expenses_month', ['period_month'])
        op.create_index('ix_expenses_month_type', 'fact_expenses_month', ['expense_type'])
        op.create_index('ix_expenses_month_shop', 'fact_expenses_month', ['platform_code', 'shop_id'])
        safe_print("[OK] fact_expenses_month table created")
    else:
        safe_print("[SKIP] fact_expenses_month table already exists")

    # ==================== 40. fact_expenses_allocated_day_shop_sku ====================
    safe_print("[40/106] Creating fact_expenses_allocated_day_shop_sku table...")

    if 'fact_expenses_allocated_day_shop_sku' not in existing_tables:
        op.create_table(
            'fact_expenses_allocated_day_shop_sku',
            sa.Column('allocation_id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('expense_id', sa.Integer(), nullable=False),
            sa.Column('allocation_date', sa.Date(), nullable=False),
            sa.Column('platform_code', sa.String(length=32), nullable=False),
            sa.Column('shop_id', sa.String(length=64), nullable=False),
            sa.Column('platform_sku', sa.String(length=128)),
            sa.Column('allocated_amt', sa.Numeric()),
            sa.Column('allocation_driver', sa.String(length=64)),
            sa.Column('allocation_weight', sa.Numeric()),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('allocation_id'),
            sa.ForeignKeyConstraint(['expense_id'], ['fact_expenses_month.expense_id'], )
        )
        op.create_index('ix_expenses_allocated_date', 'fact_expenses_allocated_day_shop_sku', ['allocation_date'])
        op.create_index('ix_expenses_allocated_shop', 'fact_expenses_allocated_day_shop_sku', ['platform_code', 'shop_id', 'allocation_date'])
        op.create_index('ix_expenses_allocated_sku', 'fact_expenses_allocated_day_shop_sku', ['platform_code', 'shop_id', 'platform_sku', 'allocation_date'])
        safe_print("[OK] fact_expenses_allocated_day_shop_sku table created")
    else:
        safe_print("[SKIP] fact_expenses_allocated_day_shop_sku table already exists")

    # ==================== 41. fact_order_amounts ====================
    safe_print("[41/106] Creating fact_order_amounts table...")

    if 'fact_order_amounts' not in existing_tables:
        op.create_table(
            'fact_order_amounts',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('order_id', sa.String(length=128), nullable=False),
            sa.Column('metric_type', sa.String(length=32), nullable=False),
            sa.Column('metric_subtype', sa.String(length=32), nullable=False),
            sa.Column('currency', sa.String(length=3), nullable=False),
            sa.Column('amount_original', sa.Numeric(), nullable=False),
            sa.Column('amount_cny', sa.Numeric()),
            sa.Column('exchange_rate', sa.Numeric()),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_fact_order_amounts_metric_type', 'fact_order_amounts', ['metric_type'])
        op.create_index('ix_order_amounts_composite', 'fact_order_amounts', ['order_id', 'metric_type', 'metric_subtype', 'currency'])
        op.create_index('ix_order_amounts_order', 'fact_order_amounts', ['order_id'])
        op.create_index('ix_fact_order_amounts_currency', 'fact_order_amounts', ['currency'])
        op.create_index('ix_order_amounts_metric', 'fact_order_amounts', ['metric_type', 'metric_subtype'])
        op.create_index('ix_fact_order_amounts_metric_subtype', 'fact_order_amounts', ['metric_subtype'])
        op.create_index('ix_fact_order_amounts_order_id', 'fact_order_amounts', ['order_id'])
        op.create_index('ix_order_amounts_currency', 'fact_order_amounts', ['currency', 'created_at'])
        safe_print("[OK] fact_order_amounts table created")
    else:
        safe_print("[SKIP] fact_order_amounts table already exists")

    # ==================== 42. fact_order_items ====================
    safe_print("[42/106] Creating fact_order_items table...")

    if 'fact_order_items' not in existing_tables:
        op.create_table(
            'fact_order_items',
            sa.Column('platform_code', sa.String(length=32), nullable=False),
            sa.Column('shop_id', sa.String(length=64), nullable=False),
            sa.Column('order_id', sa.String(length=128), nullable=False),
            sa.Column('platform_sku', sa.String(length=128), nullable=False),
            sa.Column('product_id', sa.Integer()),
            sa.Column('product_title', sa.String(length=512)),
            sa.Column('quantity', sa.Integer(), nullable=False),
            sa.Column('currency', sa.String(length=8)),
            sa.Column('unit_price', sa.Numeric(), nullable=False),
            sa.Column('unit_price_rmb', sa.Numeric(), nullable=False),
            sa.Column('line_amount', sa.Numeric()),
            sa.Column('line_amount_rmb', sa.Numeric()),
            sa.Column('attributes', sa.JSON),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('platform_code', 'shop_id', 'order_id', 'platform_sku'),
            sa.ForeignKeyConstraint(['product_id'], ['dim_product_master.product_id'], )
        )
        op.create_index('ix_fact_items_plat_shop_sku', 'fact_order_items', ['platform_code', 'shop_id', 'platform_sku'])
        op.create_index('ix_fact_items_plat_shop_order', 'fact_order_items', ['platform_code', 'shop_id', 'order_id'])
        op.create_index('ix_fact_items_product_id', 'fact_order_items', ['product_id'])
        safe_print("[OK] fact_order_items table created")
    else:
        safe_print("[SKIP] fact_order_items table already exists")

    # ==================== 43. fact_orders ====================
    safe_print("[43/106] Creating fact_orders table...")

    if 'fact_orders' not in existing_tables:
        op.create_table(
            'fact_orders',
            sa.Column('platform_code', sa.String(length=32), nullable=False),
            sa.Column('shop_id', sa.String(length=64), nullable=False),
            sa.Column('order_id', sa.String(length=128), nullable=False),
            sa.Column('order_time_utc', sa.DateTime()),
            sa.Column('order_date_local', sa.Date()),
            sa.Column('currency', sa.String(length=8)),
            sa.Column('subtotal', sa.Numeric(), nullable=False),
            sa.Column('subtotal_rmb', sa.Numeric(), nullable=False),
            sa.Column('shipping_fee', sa.Numeric()),
            sa.Column('shipping_fee_rmb', sa.Numeric()),
            sa.Column('tax_amount', sa.Numeric()),
            sa.Column('tax_amount_rmb', sa.Numeric()),
            sa.Column('discount_amount', sa.Numeric()),
            sa.Column('discount_amount_rmb', sa.Numeric()),
            sa.Column('total_amount', sa.Numeric(), nullable=False),
            sa.Column('total_amount_rmb', sa.Numeric(), nullable=False),
            sa.Column('payment_method', sa.String(length=64)),
            sa.Column('payment_status', sa.String(length=32)),
            sa.Column('order_status', sa.String(length=32)),
            sa.Column('shipping_status', sa.String(length=32)),
            sa.Column('delivery_status', sa.String(length=32)),
            sa.Column('is_cancelled', sa.Boolean()),
            sa.Column('is_refunded', sa.Boolean()),
            sa.Column('refund_amount', sa.Numeric()),
            sa.Column('refund_amount_rmb', sa.Numeric()),
            sa.Column('buyer_id', sa.String(length=128)),
            sa.Column('buyer_name', sa.String(length=256)),
            sa.Column('file_id', sa.Integer()),
            sa.Column('attributes', sa.JSON),
            sa.Column('store_label_raw', sa.String(length=256)),
            sa.Column('site', sa.String(length=64)),
            sa.Column('account', sa.String(length=128)),
            sa.Column('aligned_account_id', sa.String(length=128)),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('platform_code', 'shop_id', 'order_id')
        )
        op.create_index('ix_fact_orders_file_id', 'fact_orders', ['file_id'])
        op.create_index('ix_fact_orders_status', 'fact_orders', ['platform_code', 'shop_id', 'order_status'])
        op.create_index('ix_fact_orders_plat_shop_date', 'fact_orders', ['platform_code', 'shop_id', 'order_date_local'])
        safe_print("[OK] fact_orders table created")
    else:
        safe_print("[SKIP] fact_orders table already exists")

    # ==================== 44. fact_product_metrics ====================
    safe_print("[44/106] Creating fact_product_metrics table...")

    if 'fact_product_metrics' not in existing_tables:
        op.create_table(
            'fact_product_metrics',
            sa.Column('platform_code', sa.String(length=32), nullable=False),
            sa.Column('shop_id', sa.String(length=64), nullable=False),
            sa.Column('platform_sku', sa.String(length=128), nullable=False),
            sa.Column('metric_date', sa.Date(), nullable=False),
            sa.Column('metric_type', sa.String(length=64), nullable=False),
            sa.Column('granularity', sa.String(length=16), nullable=False, server_default=sa.text('daily')),
            sa.Column('sku_scope', sa.String(length=8), nullable=False, server_default=sa.text('product')),
            sa.Column('data_domain', sa.String(length=50)),
            sa.Column('parent_platform_sku', sa.String(length=128)),
            sa.Column('source_catalog_id', sa.Integer()),
            sa.Column('product_name', sa.String(length=500)),
            sa.Column('category', sa.String(length=200)),
            sa.Column('brand', sa.String(length=100)),
            sa.Column('specification', sa.String(length=500)),
            sa.Column('currency', sa.String(length=8)),
            sa.Column('price', sa.Numeric(), nullable=False, server_default=sa.text('0.0')),
            sa.Column('price_rmb', sa.Numeric(), nullable=False, server_default=sa.text('0.0')),
            sa.Column('stock', sa.Integer(), nullable=False, server_default=sa.text('0')),
            sa.Column('total_stock', sa.Integer()),
            sa.Column('available_stock', sa.Integer()),
            sa.Column('reserved_stock', sa.Integer()),
            sa.Column('in_transit_stock', sa.Integer()),
            sa.Column('warehouse', sa.String(length=100)),
            sa.Column('image_url', sa.String(length=500)),
            sa.Column('sales_volume', sa.Integer(), nullable=False, server_default=sa.text('0')),
            sa.Column('sales_amount', sa.Numeric(), nullable=False, server_default=sa.text('0.0')),
            sa.Column('sales_amount_rmb', sa.Numeric(), nullable=False, server_default=sa.text('0.0')),
            sa.Column('sales_volume_7d', sa.Integer()),
            sa.Column('sales_volume_30d', sa.Integer()),
            sa.Column('sales_volume_60d', sa.Integer()),
            sa.Column('sales_volume_90d', sa.Integer()),
            sa.Column('page_views', sa.Integer(), nullable=False, server_default=sa.text('0')),
            sa.Column('unique_visitors', sa.Integer(), nullable=False, server_default=sa.text('0')),
            sa.Column('click_through_rate', sa.Numeric()),
            sa.Column('order_count', sa.Integer(), server_default=sa.text('0')),
            sa.Column('conversion_rate', sa.Numeric()),
            sa.Column('add_to_cart_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
            sa.Column('rating', sa.Numeric()),
            sa.Column('review_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
            sa.Column('period_start', sa.Date()),
            sa.Column('metric_date_utc', sa.Date()),
            sa.Column('metric_value', sa.Numeric(), nullable=False, server_default=sa.text('0')),
            sa.Column('metric_value_rmb', sa.Numeric(), nullable=False, server_default=sa.text('0')),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=func.now()),
            sa.PrimaryKeyConstraint('platform_code', 'shop_id', 'platform_sku', 'metric_date', 'metric_type'),
            sa.UniqueConstraint('platform_code', 'shop_id', 'platform_sku', 'metric_date', 'granularity', 'sku_scope', name='ix_product_unique_with_scope'),
            sa.ForeignKeyConstraint(['source_catalog_id'], ['catalog_files.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(
                ['platform_code', 'shop_id', 'platform_sku'],
                ['dim_products.platform_code', 'dim_products.shop_id', 'dim_products.platform_sku']
            )
        )
        op.create_index('ix_metrics_plat_shop_date_gran', 'fact_product_metrics', ['platform_code', 'shop_id', 'metric_date', 'granularity'])
        op.create_index('ix_fact_product_metrics_metric_date', 'fact_product_metrics', ['metric_date'])
        op.create_index('ix_product_parent_date', 'fact_product_metrics', ['platform_code', 'shop_id', 'parent_platform_sku', 'metric_date'])
        op.create_index('ix_fact_product_metrics_source_catalog_id', 'fact_product_metrics', ['source_catalog_id'])
        op.create_index('ix_fact_product_metrics_sku_scope', 'fact_product_metrics', ['sku_scope'])
        op.create_index('ix_metrics_plat_shop_type', 'fact_product_metrics', ['platform_code', 'shop_id', 'metric_type'])
        op.create_index('ix_fact_product_metrics_shop_id', 'fact_product_metrics', ['shop_id'])
        op.create_index('ix_fact_product_metrics_platform_sku', 'fact_product_metrics', ['platform_sku'])
        op.create_index('ix_fact_product_metrics_parent_platform_sku', 'fact_product_metrics', ['parent_platform_sku'])
        op.create_index('ix_fact_product_metrics_granularity', 'fact_product_metrics', ['granularity'])
        op.create_index('ix_fact_product_metrics_platform_code', 'fact_product_metrics', ['platform_code'])
        op.create_index('ix_fact_product_metrics_data_domain', 'fact_product_metrics', ['data_domain'])
        safe_print("[OK] fact_product_metrics table created")
    else:
        safe_print("[SKIP] fact_product_metrics table already exists")

    # ==================== 45. fact_rate_limit_config_audit ====================
    safe_print("[45/106] Creating fact_rate_limit_config_audit table...")

    if 'fact_rate_limit_config_audit' not in existing_tables:
        op.create_table(
            'fact_rate_limit_config_audit',
            sa.Column('audit_id', sa.BigInteger(), nullable=False, autoincrement=True),
            sa.Column('config_id', sa.Integer()),
            sa.Column('role_code', sa.String(length=50), nullable=False),
            sa.Column('endpoint_type', sa.String(length=50), nullable=False),
            sa.Column('action_type', sa.String(length=50), nullable=False),
            sa.Column('old_limit_value', sa.String(length=50)),
            sa.Column('new_limit_value', sa.String(length=50)),
            sa.Column('old_is_active', sa.Boolean()),
            sa.Column('new_is_active', sa.Boolean()),
            sa.Column('operator_id', sa.BigInteger()),
            sa.Column('operator_username', sa.String(length=100), nullable=False),
            sa.Column('ip_address', sa.String(length=50)),
            sa.Column('user_agent', sa.String(length=500)),
            sa.Column('is_success', sa.Boolean(), nullable=False),
            sa.Column('error_message', sa.String()),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=func.now()),
            sa.PrimaryKeyConstraint('audit_id'),
            sa.ForeignKeyConstraint(['operator_id'], ['dim_users.user_id'], ),
            sa.ForeignKeyConstraint(['config_id'], ['dim_rate_limit_config.config_id'], )
        )
        op.create_index('ix_fact_rate_limit_config_audit_endpoint_type', 'fact_rate_limit_config_audit', ['endpoint_type'])
        op.create_index('ix_fact_rate_limit_config_audit_role_code', 'fact_rate_limit_config_audit', ['role_code'])
        op.create_index('idx_rate_limit_audit_action', 'fact_rate_limit_config_audit', ['action_type', 'created_at'])
        op.create_index('idx_rate_limit_audit_config', 'fact_rate_limit_config_audit', ['config_id', 'created_at'])
        op.create_index('idx_rate_limit_audit_role', 'fact_rate_limit_config_audit', ['role_code', 'endpoint_type', 'created_at'])
        op.create_index('ix_fact_rate_limit_config_audit_created_at', 'fact_rate_limit_config_audit', ['created_at'])
        op.create_index('ix_fact_rate_limit_config_audit_action_type', 'fact_rate_limit_config_audit', ['action_type'])
        op.create_index('ix_fact_rate_limit_config_audit_audit_id', 'fact_rate_limit_config_audit', ['audit_id'])
        op.create_index('idx_rate_limit_audit_operator', 'fact_rate_limit_config_audit', ['operator_id', 'created_at'])
        safe_print("[OK] fact_rate_limit_config_audit table created")
    else:
        safe_print("[SKIP] fact_rate_limit_config_audit table already exists")

    # ==================== 46. fact_service ====================
    safe_print("[46/106] Creating fact_service table...")

    if 'fact_service' not in existing_tables:
        op.create_table(
            'fact_service',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('platform_code', sa.String(length=50), nullable=False),
            sa.Column('shop_id', sa.String(length=100)),
            sa.Column('account', sa.String(length=100)),
            sa.Column('service_date', sa.Date(), nullable=False),
            sa.Column('granularity', sa.String(length=20), nullable=False),
            sa.Column('metric_type', sa.String(length=50), nullable=False),
            sa.Column('metric_value', sa.Numeric(precision=15, scale=2), nullable=False),
            sa.Column('data_domain', sa.String(length=50), nullable=False),
            sa.Column('attributes', sa.dialects.postgresql.JSONB),
            sa.Column('file_id', sa.Integer()),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=func.now()),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('platform_code', 'shop_id', 'service_date', 'granularity', 'metric_type', 'data_domain', name='uq_fact_service_business'),
            sa.ForeignKeyConstraint(['file_id'], ['catalog_files.id'], )
        )
        op.create_index('ix_fact_service_platform_code', 'fact_service', ['platform_code'])
        op.create_index('ix_fact_service_file_id', 'fact_service', ['file_id'])
        op.create_index('ix_fact_service_shop_id', 'fact_service', ['shop_id'])
        op.create_index('ix_fact_service_service_date', 'fact_service', ['service_date'])
        safe_print("[OK] fact_service table created")
    else:
        safe_print("[SKIP] fact_service table already exists")

    # ==================== 47. fact_traffic ====================
    safe_print("[47/106] Creating fact_traffic table...")

    if 'fact_traffic' not in existing_tables:
        op.create_table(
            'fact_traffic',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('platform_code', sa.String(length=50), nullable=False),
            sa.Column('shop_id', sa.String(length=100)),
            sa.Column('account', sa.String(length=100)),
            sa.Column('traffic_date', sa.Date(), nullable=False),
            sa.Column('granularity', sa.String(length=20), nullable=False),
            sa.Column('metric_type', sa.String(length=50), nullable=False),
            sa.Column('metric_value', sa.Numeric(precision=15, scale=2), nullable=False),
            sa.Column('data_domain', sa.String(length=50), nullable=False),
            sa.Column('attributes', sa.dialects.postgresql.JSONB),
            sa.Column('file_id', sa.Integer()),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=func.now()),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('platform_code', 'shop_id', 'traffic_date', 'granularity', 'metric_type', 'data_domain', name='uq_fact_traffic_business'),
            sa.ForeignKeyConstraint(['file_id'], ['catalog_files.id'], )
        )
        op.create_index('ix_fact_traffic_traffic_date', 'fact_traffic', ['traffic_date'])
        op.create_index('ix_fact_traffic_platform_code', 'fact_traffic', ['platform_code'])
        op.create_index('ix_fact_traffic_file_id', 'fact_traffic', ['file_id'])
        op.create_index('ix_fact_traffic_shop_id', 'fact_traffic', ['shop_id'])
        safe_print("[OK] fact_traffic table created")
    else:
        safe_print("[SKIP] fact_traffic table already exists")

    # ==================== 48. field_mapping_audit ====================
    safe_print("[48/106] Creating field_mapping_audit table...")

    if 'field_mapping_audit' not in existing_tables:
        op.create_table(
            'field_mapping_audit',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('action', sa.String(length=64), nullable=False),
            sa.Column('entity_type', sa.String(length=64), nullable=False),
            sa.Column('entity_id', sa.Integer()),
            sa.Column('before_data', sa.JSON),
            sa.Column('after_data', sa.JSON),
            sa.Column('success', sa.Boolean()),
            sa.Column('error_message', sa.String()),
            sa.Column('operator', sa.String(length=64), nullable=False),
            sa.Column('operated_at', sa.DateTime(), nullable=False),
            sa.Column('ip_address', sa.String(length=64)),
            sa.Column('user_agent', sa.String(length=256)),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_audit_entity', 'field_mapping_audit', ['entity_type', 'entity_id'])
        op.create_index('ix_audit_operator', 'field_mapping_audit', ['operator', 'operated_at'])
        op.create_index('ix_field_mapping_audit_operated_at', 'field_mapping_audit', ['operated_at'])
        safe_print("[OK] field_mapping_audit table created")
    else:
        safe_print("[SKIP] field_mapping_audit table already exists")

    # ==================== 49. field_mapping_dictionary ====================
    safe_print("[49/106] Creating field_mapping_dictionary table...")

    if 'field_mapping_dictionary' not in existing_tables:
        op.create_table(
            'field_mapping_dictionary',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('field_code', sa.String(length=128), nullable=False),
            sa.Column('cn_name', sa.String(length=128), nullable=False),
            sa.Column('en_name', sa.String(length=128)),
            sa.Column('description', sa.String()),
            sa.Column('data_domain', sa.String(length=64), nullable=False),
            sa.Column('field_group', sa.String(length=64)),
            sa.Column('is_required', sa.Boolean()),
            sa.Column('data_type', sa.String(length=32)),
            sa.Column('value_range', sa.String(length=256)),
            sa.Column('synonyms', sa.JSON),
            sa.Column('platform_synonyms', sa.JSON),
            sa.Column('example_values', sa.JSON),
            sa.Column('display_order', sa.Integer()),
            sa.Column('match_weight', sa.Numeric()),
            sa.Column('active', sa.Boolean()),
            sa.Column('version', sa.Integer(), nullable=False),
            sa.Column('status', sa.String(length=32), nullable=False),
            sa.Column('created_by', sa.String(length=64)),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_by', sa.String(length=64)),
            sa.Column('updated_at', sa.DateTime()),
            sa.Column('notes', sa.String()),
            sa.Column('is_pattern_based', sa.Boolean(), nullable=False),
            sa.Column('field_pattern', sa.String()),
            sa.Column('dimension_config', sa.JSON),
            sa.Column('target_table', sa.String(length=64)),
            sa.Column('target_columns', sa.JSON),
            sa.Column('is_mv_display', sa.Boolean(), nullable=False),
            sa.Column('currency_policy', sa.String(length=32)),
            sa.Column('source_priority', sa.JSON),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('cn_name', name='uq_dictionary_cn_name')
        )
        op.create_index('ix_dictionary_status', 'field_mapping_dictionary', ['status', 'data_domain'])
        op.create_index('ix_field_mapping_dictionary_field_code', 'field_mapping_dictionary', ['field_code'])
        op.create_index('ix_dictionary_mv_display', 'field_mapping_dictionary', ['is_mv_display', 'data_domain'])
        op.create_index('ix_dictionary_domain_group', 'field_mapping_dictionary', ['data_domain', 'field_group'])
        op.create_index('ix_field_mapping_dictionary_data_domain', 'field_mapping_dictionary', ['data_domain'])
        op.create_index('ix_dictionary_currency_policy', 'field_mapping_dictionary', ['currency_policy'])
        op.create_index('ix_dictionary_required', 'field_mapping_dictionary', ['is_required', 'data_domain'])
        safe_print("[OK] field_mapping_dictionary table created")
    else:
        safe_print("[SKIP] field_mapping_dictionary table already exists")

    # ==================== 50. field_mapping_template_items ====================
    safe_print("[50/106] Creating field_mapping_template_items table...")

    if 'field_mapping_template_items' not in existing_tables:
        op.create_table(
            'field_mapping_template_items',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('template_id', sa.Integer(), nullable=False),
            sa.Column('original_column', sa.String(length=256), nullable=False),
            sa.Column('standard_field', sa.String(length=128), nullable=False),
            sa.Column('confidence', sa.Numeric()),
            sa.Column('match_method', sa.String(length=64)),
            sa.Column('match_reason', sa.String()),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('template_id', 'original_column', name='uq_template_original_column')
        )
        op.create_index('ix_template_item_template', 'field_mapping_template_items', ['template_id'])
        op.create_index('ix_field_mapping_template_items_template_id', 'field_mapping_template_items', ['template_id'])
        safe_print("[OK] field_mapping_template_items table created")
    else:
        safe_print("[SKIP] field_mapping_template_items table already exists")

    # ==================== 51. field_mapping_templates ====================
    safe_print("[51/106] Creating field_mapping_templates table...")

    if 'field_mapping_templates' not in existing_tables:
        op.create_table(
            'field_mapping_templates',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('platform', sa.String(length=32), nullable=False),
            sa.Column('data_domain', sa.String(length=64), nullable=False),
            sa.Column('granularity', sa.String(length=32)),
            sa.Column('account', sa.String(length=128)),
            sa.Column('sub_domain', sa.String(length=64)),
            sa.Column('header_row', sa.Integer(), nullable=False),
            sa.Column('sheet_name', sa.String(length=128)),
            sa.Column('encoding', sa.String(length=32), nullable=False),
            sa.Column('header_columns', sa.dialects.postgresql.JSONB),
            sa.Column('deduplication_fields', sa.dialects.postgresql.JSONB),
            sa.Column('template_name', sa.String(length=256)),
            sa.Column('version', sa.Integer(), nullable=False),
            sa.Column('status', sa.String(length=32)),
            sa.Column('field_count', sa.Integer()),
            sa.Column('usage_count', sa.Integer()),
            sa.Column('success_rate', sa.Numeric()),
            sa.Column('created_by', sa.String(length=64)),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_by', sa.String(length=64)),
            sa.Column('updated_at', sa.DateTime()),
            sa.Column('notes', sa.String()),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_template_status', 'field_mapping_templates', ['status', 'platform'])
        op.create_index('ix_field_mapping_templates_platform', 'field_mapping_templates', ['platform'])
        op.create_index('ix_template_dimension_v2', 'field_mapping_templates', ['platform', 'data_domain', 'sub_domain', 'granularity', 'account'])
        op.create_index('ix_field_mapping_templates_data_domain', 'field_mapping_templates', ['data_domain'])
        safe_print("[OK] field_mapping_templates table created")
    else:
        safe_print("[SKIP] field_mapping_templates table already exists")

    # ==================== 52. field_mappings ====================
    safe_print("[52/106] Creating field_mappings table...")

    if 'field_mappings' not in existing_tables:
        op.create_table(
            'field_mappings',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('file_id', sa.Integer()),
            sa.Column('platform', sa.String(length=50)),
            sa.Column('original_field', sa.String(length=100), nullable=False),
            sa.Column('standard_field', sa.String(length=100), nullable=False),
            sa.Column('confidence', sa.Numeric(), nullable=False),
            sa.Column('is_manual', sa.Boolean(), nullable=False),
            sa.Column('version', sa.Integer(), nullable=False),
            sa.Column('domain', sa.String(length=50)),
            sa.Column('granularity', sa.String(length=50)),
            sa.Column('sheet_name', sa.String(length=100)),
            sa.Column('sub_domain', sa.String(length=64)),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['file_id'], ['data_files.id'], )
        )
        op.create_index('ix_field_mappings_template_key', 'field_mappings', ['platform', 'domain', 'sub_domain', 'granularity'])
        op.create_index('ix_field_mappings_platform', 'field_mappings', ['platform'])
        op.create_index('ix_field_mappings_domain', 'field_mappings', ['domain'])
        op.create_index('ix_field_mappings_version', 'field_mappings', ['version'])
        safe_print("[OK] field_mappings table created")
    else:
        safe_print("[SKIP] field_mappings table already exists")

    # ==================== 53. field_usage_tracking ====================
    safe_print("[53/106] Creating field_usage_tracking table...")

    if 'field_usage_tracking' not in existing_tables:
        op.create_table(
            'field_usage_tracking',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('table_name', sa.String(length=64)),
            sa.Column('field_name', sa.String(length=128)),
            sa.Column('api_endpoint', sa.String(length=256)),
            sa.Column('api_param', sa.String(length=64)),
            sa.Column('api_file', sa.String(length=256)),
            sa.Column('frontend_component', sa.String(length=256)),
            sa.Column('frontend_param', sa.String(length=128)),
            sa.Column('frontend_file', sa.String(length=256)),
            sa.Column('usage_type', sa.String(length=32), nullable=False),
            sa.Column('source_type', sa.String(length=32), nullable=False),
            sa.Column('code_snippet', sa.String()),
            sa.Column('line_number', sa.Integer()),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime()),
            sa.Column('created_by', sa.String(length=64), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('table_name', 'field_name', 'api_endpoint', 'frontend_component', name='uq_field_usage')
        )
        op.create_index('idx_usage_field', 'field_usage_tracking', ['table_name', 'field_name'])
        op.create_index('idx_usage_api', 'field_usage_tracking', ['api_endpoint'])
        op.create_index('ix_field_usage_tracking_table_name', 'field_usage_tracking', ['table_name'])
        op.create_index('idx_usage_frontend', 'field_usage_tracking', ['frontend_component'])
        op.create_index('ix_field_usage_tracking_field_name', 'field_usage_tracking', ['field_name'])
        op.create_index('idx_usage_type', 'field_usage_tracking', ['usage_type'])
        safe_print("[OK] field_usage_tracking table created")
    else:
        safe_print("[SKIP] field_usage_tracking table already exists")

    # ==================== 54. fx_rates ====================
    safe_print("[54/106] Creating fx_rates table...")

    if 'fx_rates' not in existing_tables:
        op.create_table(
            'fx_rates',
            sa.Column('rate_date', sa.Date(), nullable=False),
            sa.Column('from_currency', sa.String(length=8), nullable=False),
            sa.Column('to_currency', sa.String(length=8), nullable=False),
            sa.Column('rate', sa.Numeric(), nullable=False),
            sa.Column('source', sa.String(length=64)),
            sa.Column('version', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('rate_date', 'from_currency', 'to_currency')
        )
        op.create_index('ix_fx_rates_date_from', 'fx_rates', ['rate_date', 'from_currency'])
        safe_print("[OK] fx_rates table created")
    else:
        safe_print("[SKIP] fx_rates table already exists")

    # ==================== 55. gl_accounts ====================
    safe_print("[55/106] Creating gl_accounts table...")

    if 'gl_accounts' not in existing_tables:
        op.create_table(
            'gl_accounts',
            sa.Column('account_code', sa.String(length=64), nullable=False),
            sa.Column('account_name', sa.String(length=256), nullable=False),
            sa.Column('account_type', sa.String(length=64), nullable=False),
            sa.Column('parent_account', sa.String(length=64)),
            sa.Column('is_debit_normal', sa.Boolean()),
            sa.Column('active', sa.Boolean()),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('account_code')
        )
        op.create_index('ix_gl_accounts_type', 'gl_accounts', ['account_type', 'active'])
        safe_print("[OK] gl_accounts table created")
    else:
        safe_print("[SKIP] gl_accounts table already exists")

    # ==================== 56. inventory_ledger ====================
    safe_print("[56/106] Creating inventory_ledger table...")

    if 'inventory_ledger' not in existing_tables:
        op.create_table(
            'inventory_ledger',
            sa.Column('ledger_id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('platform_code', sa.String(length=32), nullable=False),
            sa.Column('shop_id', sa.String(length=64), nullable=False),
            sa.Column('platform_sku', sa.String(length=128), nullable=False),
            sa.Column('transaction_date', sa.Date(), nullable=False),
            sa.Column('movement_type', sa.String(length=32), nullable=False),
            sa.Column('qty_in', sa.Integer()),
            sa.Column('qty_out', sa.Integer()),
            sa.Column('unit_cost_wac', sa.Numeric(), nullable=False),
            sa.Column('ext_value', sa.Numeric()),
            sa.Column('base_ext_value', sa.Numeric()),
            sa.Column('qty_before', sa.Integer()),
            sa.Column('avg_cost_before', sa.Numeric()),
            sa.Column('qty_after', sa.Integer()),
            sa.Column('avg_cost_after', sa.Numeric()),
            sa.Column('link_grn_id', sa.String(length=64)),
            sa.Column('link_order_id', sa.String(length=128)),
            sa.Column('original_sale_line_id', sa.Integer()),
            sa.Column('return_reason', sa.String(length=256)),
            sa.Column('created_by', sa.String(length=64)),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('ledger_id')
        )
        op.create_index('ix_inventory_ledger_sku_date', 'inventory_ledger', ['platform_code', 'shop_id', 'platform_sku', 'transaction_date'])
        op.create_index('ix_inventory_ledger_type', 'inventory_ledger', ['movement_type', 'transaction_date'])
        op.create_index('ix_inventory_ledger_grn', 'inventory_ledger', ['link_grn_id'])
        op.create_index('ix_inventory_ledger_order', 'inventory_ledger', ['link_order_id'])
        safe_print("[OK] inventory_ledger table created")
    else:
        safe_print("[SKIP] inventory_ledger table already exists")

    # ==================== 57. invoice_headers ====================
    safe_print("[57/106] Creating invoice_headers table...")

    if 'invoice_headers' not in existing_tables:
        op.create_table(
            'invoice_headers',
            sa.Column('invoice_id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('vendor_code', sa.String(length=64), nullable=False),
            sa.Column('invoice_no', sa.String(length=128), nullable=False),
            sa.Column('invoice_date', sa.Date(), nullable=False),
            sa.Column('due_date', sa.Date()),
            sa.Column('currency', sa.String(length=8), nullable=False),
            sa.Column('total_amt', sa.Numeric()),
            sa.Column('tax_amt', sa.Numeric()),
            sa.Column('base_total_amt', sa.Numeric()),
            sa.Column('status', sa.String(length=32), nullable=False),
            sa.Column('source_file_id', sa.Integer()),
            sa.Column('ocr_result', sa.JSON),
            sa.Column('ocr_confidence', sa.Numeric()),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime()),
            sa.PrimaryKeyConstraint('invoice_id'),
            sa.UniqueConstraint('invoice_no'),
            sa.ForeignKeyConstraint(['vendor_code'], ['dim_vendors.vendor_code'], ),
            sa.ForeignKeyConstraint(['source_file_id'], ['catalog_files.id'], )
        )
        op.create_index('ix_invoice_headers_vendor_date', 'invoice_headers', ['vendor_code', 'invoice_date'])
        op.create_index('ix_invoice_headers_status', 'invoice_headers', ['status'])
        safe_print("[OK] invoice_headers table created")
    else:
        safe_print("[SKIP] invoice_headers table already exists")

    # ==================== 58. invoice_attachments ====================
    safe_print("[58/106] Creating invoice_attachments table...")

    if 'invoice_attachments' not in existing_tables:
        op.create_table(
            'invoice_attachments',
            sa.Column('attachment_id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('invoice_id', sa.Integer(), nullable=False),
            sa.Column('file_path', sa.String(length=1024), nullable=False),
            sa.Column('file_type', sa.String(length=32)),
            sa.Column('file_size', sa.Integer()),
            sa.Column('ocr_text', sa.String()),
            sa.Column('ocr_fields', sa.JSON),
            sa.Column('uploaded_by', sa.String(length=64)),
            sa.Column('uploaded_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('attachment_id'),
            sa.ForeignKeyConstraint(['invoice_id'], ['invoice_headers.invoice_id'], )
        )
        op.create_index('ix_invoice_attachments_invoice', 'invoice_attachments', ['invoice_id'])
        safe_print("[OK] invoice_attachments table created")
    else:
        safe_print("[SKIP] invoice_attachments table already exists")

    # ==================== 59. journal_entries ====================
    safe_print("[59/106] Creating journal_entries table...")

    if 'journal_entries' not in existing_tables:
        op.create_table(
            'journal_entries',
            sa.Column('entry_id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('entry_no', sa.String(length=64), nullable=False),
            sa.Column('entry_date', sa.Date(), nullable=False),
            sa.Column('period_month', sa.String(length=16), nullable=False),
            sa.Column('entry_type', sa.String(length=64), nullable=False),
            sa.Column('description', sa.String()),
            sa.Column('status', sa.String(length=32), nullable=False),
            sa.Column('created_by', sa.String(length=64)),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('posted_at', sa.DateTime()),
            sa.PrimaryKeyConstraint('entry_id'),
            sa.UniqueConstraint('entry_no'),
            sa.ForeignKeyConstraint(['period_month'], ['dim_fiscal_calendar.period_code'], )
        )
        op.create_index('ix_journal_entries_status', 'journal_entries', ['status'])
        op.create_index('ix_journal_entries_date', 'journal_entries', ['entry_date'])
        op.create_index('ix_journal_entries_period', 'journal_entries', ['period_month'])
        safe_print("[OK] journal_entries table created")
    else:
        safe_print("[SKIP] journal_entries table already exists")

    # ==================== 60. journal_entry_lines ====================
    safe_print("[60/106] Creating journal_entry_lines table...")

    if 'journal_entry_lines' not in existing_tables:
        op.create_table(
            'journal_entry_lines',
            sa.Column('line_id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('entry_id', sa.Integer(), nullable=False),
            sa.Column('line_number', sa.Integer(), nullable=False),
            sa.Column('account_code', sa.String(length=64), nullable=False),
            sa.Column('debit_amt', sa.Numeric()),
            sa.Column('credit_amt', sa.Numeric()),
            sa.Column('currency', sa.String(length=8)),
            sa.Column('currency_amt', sa.Numeric()),
            sa.Column('base_amt', sa.Numeric()),
            sa.Column('link_order_id', sa.String(length=128)),
            sa.Column('link_expense_id', sa.Integer()),
            sa.Column('link_invoice_id', sa.Integer()),
            sa.Column('description', sa.String()),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('line_id'),
            sa.UniqueConstraint('entry_id', 'line_number', name='uq_journal_line'),
            sa.ForeignKeyConstraint(['entry_id'], ['journal_entries.entry_id'], ),
            sa.ForeignKeyConstraint(['account_code'], ['gl_accounts.account_code'], )
        )
        op.create_index('ix_journal_lines_entry', 'journal_entry_lines', ['entry_id'])
        op.create_index('ix_journal_lines_account', 'journal_entry_lines', ['account_code'])
        safe_print("[OK] journal_entry_lines table created")
    else:
        safe_print("[SKIP] journal_entry_lines table already exists")

    # ==================== 61. logistics_allocation_rules ====================
    safe_print("[61/106] Creating logistics_allocation_rules table...")

    if 'logistics_allocation_rules' not in existing_tables:
        op.create_table(
            'logistics_allocation_rules',
            sa.Column('rule_id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('rule_name', sa.String(length=256), nullable=False),
            sa.Column('scope', sa.String(length=64), nullable=False),
            sa.Column('driver', sa.String(length=64), nullable=False),
            sa.Column('effective_from', sa.Date(), nullable=False),
            sa.Column('effective_to', sa.Date()),
            sa.Column('active', sa.Boolean()),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('rule_id')
        )
        op.create_index('ix_logistics_alloc_rules_scope', 'logistics_allocation_rules', ['scope', 'active'])
        safe_print("[OK] logistics_allocation_rules table created")
    else:
        safe_print("[SKIP] logistics_allocation_rules table already exists")

    # ==================== 62. mapping_sessions ====================
    safe_print("[62/106] Creating mapping_sessions table...")

    if 'mapping_sessions' not in existing_tables:
        op.create_table(
            'mapping_sessions',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('session_id', sa.String(length=100), nullable=False),
            sa.Column('platform', sa.String(length=50)),
            sa.Column('domain', sa.String(length=50)),
            sa.Column('status', sa.String(length=20), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('session_id', name='uq_mapping_sessions_session_id')
        )
        safe_print("[OK] mapping_sessions table created")
    else:
        safe_print("[SKIP] mapping_sessions table already exists")

    # ==================== 63. mv_refresh_log ====================
    safe_print("[63/106] Creating mv_refresh_log table...")

    if 'mv_refresh_log' not in existing_tables:
        op.create_table(
            'mv_refresh_log',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('view_name', sa.String(length=128), nullable=False),
            sa.Column('refresh_started_at', sa.DateTime(), nullable=False),
            sa.Column('refresh_completed_at', sa.DateTime()),
            sa.Column('duration_seconds', sa.Numeric()),
            sa.Column('row_count', sa.Integer()),
            sa.Column('status', sa.String(length=20), nullable=False),
            sa.Column('error_message', sa.String()),
            sa.Column('triggered_by', sa.String(length=64), nullable=False),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_mv_refresh_log_view', 'mv_refresh_log', ['view_name', 'refresh_started_at'])
        op.create_index('ix_mv_refresh_log_status', 'mv_refresh_log', ['status', 'refresh_started_at'])
        op.create_index('ix_mv_refresh_log_view_name', 'mv_refresh_log', ['view_name'])
        safe_print("[OK] mv_refresh_log table created")
    else:
        safe_print("[SKIP] mv_refresh_log table already exists")

    # ==================== 64. notification_templates ====================
    safe_print("[64/106] Creating notification_templates table...")

    if 'notification_templates' not in existing_tables:
        op.create_table(
            'notification_templates',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('template_name', sa.String(length=128), nullable=False),
            sa.Column('template_type', sa.String(length=64), nullable=False),
            sa.Column('subject', sa.String(length=256)),
            sa.Column('content', sa.String(), nullable=False),
            sa.Column('variables', sa.dialects.postgresql.JSONB),
            sa.Column('is_active', sa.Boolean(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.Column('created_by', sa.Integer()),
            sa.Column('updated_by', sa.Integer()),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('template_name'),
            sa.ForeignKeyConstraint(['created_by'], ['dim_users.user_id'], ),
            sa.ForeignKeyConstraint(['updated_by'], ['dim_users.user_id'], )
        )
        op.create_index('ix_notification_templates_template_type', 'notification_templates', ['template_type'])
        op.create_index('ix_notification_templates_template_name', 'notification_templates', ['template_name'])
        safe_print("[OK] notification_templates table created")
    else:
        safe_print("[SKIP] notification_templates table already exists")

    # ==================== 65. alert_rules ====================
    safe_print("[65/106] Creating alert_rules table...")

    if 'alert_rules' not in existing_tables:
        op.create_table(
            'alert_rules',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('rule_name', sa.String(length=128), nullable=False),
            sa.Column('rule_type', sa.String(length=64), nullable=False),
            sa.Column('condition', sa.dialects.postgresql.JSONB, nullable=False),
            sa.Column('template_id', sa.Integer()),
            sa.Column('recipients', sa.dialects.postgresql.JSONB),
            sa.Column('enabled', sa.Boolean(), nullable=False),
            sa.Column('priority', sa.String(length=16), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.Column('created_by', sa.Integer()),
            sa.Column('updated_by', sa.Integer()),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('rule_name'),
            sa.ForeignKeyConstraint(['updated_by'], ['dim_users.user_id'], ),
            sa.ForeignKeyConstraint(['created_by'], ['dim_users.user_id'], ),
            sa.ForeignKeyConstraint(['template_id'], ['notification_templates.id'], )
        )
        op.create_index('ix_alert_rules_rule_name', 'alert_rules', ['rule_name'])
        op.create_index('ix_alert_rules_rule_type', 'alert_rules', ['rule_type'])
        op.create_index('ix_alert_rules_enabled', 'alert_rules', ['enabled'])
        safe_print("[OK] alert_rules table created")
    else:
        safe_print("[SKIP] alert_rules table already exists")

    # ==================== 66. notifications ====================
    safe_print("[66/106] Creating notifications table...")

    if 'notifications' not in existing_tables:
        op.create_table(
            'notifications',
            sa.Column('notification_id', sa.BigInteger(), nullable=False, autoincrement=True),
            sa.Column('recipient_id', sa.BigInteger(), nullable=False),
            sa.Column('notification_type', sa.String(length=50), nullable=False),
            sa.Column('title', sa.String(length=200), nullable=False),
            sa.Column('content', sa.String(), nullable=False),
            sa.Column('extra_data', sa.JSON),
            sa.Column('related_user_id', sa.BigInteger()),
            sa.Column('priority', sa.String(length=10), nullable=False),
            sa.Column('is_read', sa.Boolean(), nullable=False),
            sa.Column('read_at', sa.DateTime()),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=func.now()),
            sa.PrimaryKeyConstraint('notification_id'),
            sa.ForeignKeyConstraint(['recipient_id'], ['dim_users.user_id'], ),
            sa.ForeignKeyConstraint(['related_user_id'], ['dim_users.user_id'], )
        )
        op.create_index('ix_notifications_priority', 'notifications', ['priority'])
        op.create_index('ix_notifications_created_at', 'notifications', ['created_at'])
        op.create_index('idx_notification_user_unread', 'notifications', ['recipient_id', 'is_read'])
        op.create_index('ix_notifications_recipient_id', 'notifications', ['recipient_id'])
        op.create_index('ix_notifications_is_read', 'notifications', ['is_read'])
        op.create_index('idx_notification_type_created', 'notifications', ['notification_type', 'created_at'])
        op.create_index('ix_notifications_notification_type', 'notifications', ['notification_type'])
        safe_print("[OK] notifications table created")
    else:
        safe_print("[SKIP] notifications table already exists")

    # ==================== 67. opening_balances ====================
    safe_print("[67/106] Creating opening_balances table...")

    if 'opening_balances' not in existing_tables:
        op.create_table(
            'opening_balances',
            sa.Column('balance_id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('period', sa.String(length=16), nullable=False),
            sa.Column('platform_code', sa.String(length=32), nullable=False),
            sa.Column('shop_id', sa.String(length=64), nullable=False),
            sa.Column('platform_sku', sa.String(length=128), nullable=False),
            sa.Column('opening_qty', sa.Integer()),
            sa.Column('opening_cost', sa.Numeric()),
            sa.Column('opening_value', sa.Numeric()),
            sa.Column('source', sa.String(length=64)),
            sa.Column('migration_batch_id', sa.String(length=64)),
            sa.Column('created_by', sa.String(length=64)),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('balance_id'),
            sa.UniqueConstraint('period', 'platform_code', 'shop_id', 'platform_sku', name='uq_opening_balance')
        )
        op.create_index('ix_opening_balances_sku', 'opening_balances', ['platform_code', 'shop_id', 'platform_sku'])
        op.create_index('ix_opening_balances_period', 'opening_balances', ['period'])
        safe_print("[OK] opening_balances table created")
    else:
        safe_print("[SKIP] opening_balances table already exists")

    # ==================== 68. operating_costs ====================
    safe_print("[68/106] Creating operating_costs table...")

    if 'operating_costs' not in existing_tables:
        op.create_table(
            'operating_costs',
            sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
            sa.Column('shop_id', sa.String(length=256), nullable=False),
            sa.Column('year_month', sa.String(length=7), nullable=False),
            sa.Column('rent', sa.Numeric(precision=15, scale=2), nullable=False),
            sa.Column('salary', sa.Numeric(precision=15, scale=2), nullable=False),
            sa.Column('utilities', sa.Numeric(precision=15, scale=2), nullable=False),
            sa.Column('other_costs', sa.Numeric(precision=15, scale=2), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('shop_id', 'year_month', name='uq_operating_costs_shop_month')
        )
        op.create_index('ix_operating_costs_shop', 'operating_costs', ['shop_id'])
        op.create_index('ix_operating_costs_month', 'operating_costs', ['year_month'])
        safe_print("[OK] operating_costs table created")
    else:
        safe_print("[SKIP] operating_costs table already exists")

    # ==================== 69. performance_config ====================
    safe_print("[69/106] Creating performance_config table...")

    if 'performance_config' not in existing_tables:
        op.create_table(
            'performance_config',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('config_name', sa.String(length=64), nullable=False),
            sa.Column('sales_weight', sa.Integer(), nullable=False),
            sa.Column('profit_weight', sa.Integer(), nullable=False),
            sa.Column('key_product_weight', sa.Integer(), nullable=False),
            sa.Column('operation_weight', sa.Integer(), nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=False),
            sa.Column('effective_from', sa.Date(), nullable=False),
            sa.Column('effective_to', sa.Date()),
            sa.Column('created_by', sa.String(length=64)),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_performance_config_active', 'performance_config', ['is_active', 'effective_from'])
        safe_print("[OK] performance_config table created")
    else:
        safe_print("[SKIP] performance_config table already exists")

    # ==================== 70. performance_config_a ====================
    safe_print("[70/106] Creating performance_config_a table...")

    if 'performance_config_a' not in existing_tables:
        op.create_table(
            'performance_config_a',
            sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
            sa.Column('config_name', sa.String(length=128), nullable=False),
            sa.Column('sales_weight', sa.Numeric(), nullable=False),
            sa.Column('quantity_weight', sa.Numeric(), nullable=False),
            sa.Column('quality_weight', sa.Numeric(), nullable=False),
            sa.Column('active', sa.Boolean(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('config_name', name='uq_performance_config_name')
        )
        op.create_index('ix_performance_config_active', 'performance_config_a', ['active'])
        safe_print("[OK] performance_config_a table created")
    else:
        safe_print("[SKIP] performance_config_a table already exists")

    # ==================== 71. performance_scores ====================
    safe_print("[71/106] Creating performance_scores table...")

    if 'performance_scores' not in existing_tables:
        op.create_table(
            'performance_scores',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('platform_code', sa.String(length=32), nullable=False),
            sa.Column('shop_id', sa.String(length=64), nullable=False),
            sa.Column('period', sa.String(length=16), nullable=False),
            sa.Column('total_score', sa.Numeric(), nullable=False),
            sa.Column('sales_score', sa.Numeric(), nullable=False),
            sa.Column('profit_score', sa.Numeric(), nullable=False),
            sa.Column('key_product_score', sa.Numeric(), nullable=False),
            sa.Column('operation_score', sa.Numeric(), nullable=False),
            sa.Column('score_details', sa.JSON),
            sa.Column('rank', sa.Integer()),
            sa.Column('performance_coefficient', sa.Numeric(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('platform_code', 'shop_id', 'period', name='uq_performance_shop_period'),
            sa.ForeignKeyConstraint(['platform_code'], ['dim_shops.platform_code'], ),
            sa.ForeignKeyConstraint(['shop_id'], ['dim_shops.shop_id'], )
        )
        op.create_index('ix_performance_period', 'performance_scores', ['period'])
        op.create_index('ix_performance_shop', 'performance_scores', ['platform_code', 'shop_id'])
        op.create_index('ix_performance_score', 'performance_scores', ['total_score'])
        op.create_index('ix_performance_rank', 'performance_scores', ['rank'])
        safe_print("[OK] performance_scores table created")
    else:
        safe_print("[SKIP] performance_scores table already exists")

    # ==================== 72. performance_scores_c ====================
    safe_print("[72/106] Creating performance_scores_c table...")

    if 'performance_scores_c' not in existing_tables:
        op.create_table(
            'performance_scores_c',
            sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
            sa.Column('shop_id', sa.String(length=256), nullable=False),
            sa.Column('period', sa.String(length=32), nullable=False),
            sa.Column('total_score', sa.Numeric(), nullable=False),
            sa.Column('sales_score', sa.Numeric(), nullable=False),
            sa.Column('quality_score', sa.Numeric(), nullable=False),
            sa.Column('calculated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('shop_id', 'period', name='uq_performance_scores')
        )
        op.create_index('ix_performance_scores_period', 'performance_scores_c', ['period'])
        op.create_index('ix_performance_scores_shop', 'performance_scores_c', ['shop_id'])
        safe_print("[OK] performance_scores_c table created")
    else:
        safe_print("[SKIP] performance_scores_c table already exists")

    # ==================== 73. platform_accounts ====================
    safe_print("[73/106] Creating platform_accounts table...")

    if 'platform_accounts' not in existing_tables:
        op.create_table(
            'platform_accounts',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('account_id', sa.String(length=100), nullable=False),
            sa.Column('parent_account', sa.String(length=100)),
            sa.Column('platform', sa.String(length=50), nullable=False),
            sa.Column('account_alias', sa.String(length=200)),
            sa.Column('store_name', sa.String(length=200), nullable=False),
            sa.Column('shop_type', sa.String(length=50)),
            sa.Column('shop_region', sa.String(length=50)),
            sa.Column('shop_id', sa.String(length=256)),
            sa.Column('username', sa.String(length=200), nullable=False),
            sa.Column('password_encrypted', sa.String(), nullable=False),
            sa.Column('login_url', sa.String()),
            sa.Column('email', sa.String(length=200)),
            sa.Column('phone', sa.String(length=50)),
            sa.Column('region', sa.String(length=50)),
            sa.Column('currency', sa.String(length=10)),
            sa.Column('capabilities', sa.dialects.postgresql.JSONB, nullable=False),
            sa.Column('enabled', sa.Boolean(), nullable=False),
            sa.Column('proxy_required', sa.Boolean()),
            sa.Column('notes', sa.String()),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.Column('created_by', sa.String(length=100)),
            sa.Column('updated_by', sa.String(length=100)),
            sa.Column('extra_config', sa.dialects.postgresql.JSONB),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('account_id')
        )
        op.create_index('ix_platform_accounts_shop_id', 'platform_accounts', ['shop_id'])
        op.create_index('ix_platform_accounts_parent', 'platform_accounts', ['parent_account'])
        op.create_index('ix_platform_accounts_enabled', 'platform_accounts', ['enabled'])
        op.create_index('ix_platform_accounts_shop_type', 'platform_accounts', ['shop_type'])
        op.create_index('ix_platform_accounts_platform', 'platform_accounts', ['platform'])
        safe_print("[OK] platform_accounts table created")
    else:
        safe_print("[SKIP] platform_accounts table already exists")

    # ==================== 74. po_headers ====================
    safe_print("[74/106] Creating po_headers table...")

    if 'po_headers' not in existing_tables:
        op.create_table(
            'po_headers',
            sa.Column('po_id', sa.String(length=64), nullable=False),
            sa.Column('vendor_code', sa.String(length=64), nullable=False),
            sa.Column('po_date', sa.Date(), nullable=False),
            sa.Column('expected_date', sa.Date()),
            sa.Column('currency', sa.String(length=8), nullable=False),
            sa.Column('total_amt', sa.Numeric()),
            sa.Column('base_amt', sa.Numeric()),
            sa.Column('status', sa.String(length=32), nullable=False),
            sa.Column('approval_threshold', sa.Numeric()),
            sa.Column('approved_by', sa.String(length=64)),
            sa.Column('approved_at', sa.DateTime()),
            sa.Column('created_by', sa.String(length=64)),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime()),
            sa.PrimaryKeyConstraint('po_id'),
            sa.ForeignKeyConstraint(['vendor_code'], ['dim_vendors.vendor_code'], )
        )
        op.create_index('ix_po_headers_vendor_date', 'po_headers', ['vendor_code', 'po_date'])
        op.create_index('ix_po_headers_status', 'po_headers', ['status'])
        safe_print("[OK] po_headers table created")
    else:
        safe_print("[SKIP] po_headers table already exists")

    # ==================== 75. grn_headers ====================
    safe_print("[75/106] Creating grn_headers table...")

    if 'grn_headers' not in existing_tables:
        op.create_table(
            'grn_headers',
            sa.Column('grn_id', sa.String(length=64), nullable=False),
            sa.Column('po_id', sa.String(length=64), nullable=False),
            sa.Column('receipt_date', sa.Date(), nullable=False),
            sa.Column('warehouse', sa.String(length=64)),
            sa.Column('status', sa.String(length=32), nullable=False),
            sa.Column('created_by', sa.String(length=64)),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('grn_id'),
            sa.ForeignKeyConstraint(['po_id'], ['po_headers.po_id'], )
        )
        op.create_index('ix_grn_headers_po_id', 'grn_headers', ['po_id'])
        op.create_index('ix_grn_headers_date', 'grn_headers', ['receipt_date'])
        safe_print("[OK] grn_headers table created")
    else:
        safe_print("[SKIP] grn_headers table already exists")

    # ==================== 76. logistics_costs ====================
    safe_print("[76/106] Creating logistics_costs table...")

    if 'logistics_costs' not in existing_tables:
        op.create_table(
            'logistics_costs',
            sa.Column('logistics_id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('grn_id', sa.String(length=64)),
            sa.Column('order_id', sa.String(length=128)),
            sa.Column('logistics_provider', sa.String(length=128)),
            sa.Column('tracking_no', sa.String(length=128)),
            sa.Column('cost_type', sa.String(length=64), nullable=False),
            sa.Column('currency', sa.String(length=8), nullable=False),
            sa.Column('currency_amt', sa.Numeric()),
            sa.Column('base_amt', sa.Numeric()),
            sa.Column('weight_kg', sa.Numeric()),
            sa.Column('volume_m3', sa.Numeric()),
            sa.Column('invoice_id', sa.Integer()),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('logistics_id'),
            sa.ForeignKeyConstraint(['invoice_id'], ['invoice_headers.invoice_id'], ),
            sa.ForeignKeyConstraint(['grn_id'], ['grn_headers.grn_id'], )
        )
        op.create_index('ix_logistics_costs_invoice', 'logistics_costs', ['invoice_id'])
        op.create_index('ix_logistics_costs_grn', 'logistics_costs', ['grn_id'])
        op.create_index('ix_logistics_costs_order', 'logistics_costs', ['order_id'])
        safe_print("[OK] logistics_costs table created")
    else:
        safe_print("[SKIP] logistics_costs table already exists")

    # ==================== 77. po_lines ====================
    safe_print("[77/106] Creating po_lines table...")

    if 'po_lines' not in existing_tables:
        op.create_table(
            'po_lines',
            sa.Column('po_line_id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('po_id', sa.String(length=64), nullable=False),
            sa.Column('line_number', sa.Integer(), nullable=False),
            sa.Column('platform_sku', sa.String(length=128), nullable=False),
            sa.Column('product_title', sa.String(length=512)),
            sa.Column('qty_ordered', sa.Integer()),
            sa.Column('qty_received', sa.Integer()),
            sa.Column('unit_price', sa.Numeric(), nullable=False),
            sa.Column('currency', sa.String(length=8), nullable=False),
            sa.Column('line_amt', sa.Numeric()),
            sa.Column('base_amt', sa.Numeric()),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('po_line_id'),
            sa.UniqueConstraint('po_id', 'line_number', name='uq_po_line'),
            sa.ForeignKeyConstraint(['po_id'], ['po_headers.po_id'], )
        )
        op.create_index('ix_po_lines_sku', 'po_lines', ['platform_sku'])
        op.create_index('ix_po_lines_po_id', 'po_lines', ['po_id'])
        safe_print("[OK] po_lines table created")
    else:
        safe_print("[SKIP] po_lines table already exists")

    # ==================== 78. grn_lines ====================
    safe_print("[78/106] Creating grn_lines table...")

    if 'grn_lines' not in existing_tables:
        op.create_table(
            'grn_lines',
            sa.Column('grn_line_id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('grn_id', sa.String(length=64), nullable=False),
            sa.Column('po_line_id', sa.Integer(), nullable=False),
            sa.Column('platform_sku', sa.String(length=128), nullable=False),
            sa.Column('qty_received', sa.Integer()),
            sa.Column('unit_cost', sa.Numeric(), nullable=False),
            sa.Column('currency', sa.String(length=8), nullable=False),
            sa.Column('ext_value', sa.Numeric()),
            sa.Column('base_ext_value', sa.Numeric()),
            sa.Column('weight_kg', sa.Numeric()),
            sa.Column('volume_m3', sa.Numeric()),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('grn_line_id'),
            sa.ForeignKeyConstraint(['grn_id'], ['grn_headers.grn_id'], ),
            sa.ForeignKeyConstraint(['po_line_id'], ['po_lines.po_line_id'], )
        )
        op.create_index('ix_grn_lines_sku', 'grn_lines', ['platform_sku'])
        op.create_index('ix_grn_lines_grn_id', 'grn_lines', ['grn_id'])
        op.create_index('ix_grn_lines_po_line', 'grn_lines', ['po_line_id'])
        safe_print("[OK] grn_lines table created")
    else:
        safe_print("[SKIP] grn_lines table already exists")

    # ==================== 79. invoice_lines ====================
    safe_print("[79/106] Creating invoice_lines table...")

    if 'invoice_lines' not in existing_tables:
        op.create_table(
            'invoice_lines',
            sa.Column('invoice_line_id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('invoice_id', sa.Integer(), nullable=False),
            sa.Column('po_line_id', sa.Integer()),
            sa.Column('grn_line_id', sa.Integer()),
            sa.Column('platform_sku', sa.String(length=128), nullable=False),
            sa.Column('qty', sa.Integer()),
            sa.Column('unit_price', sa.Numeric(), nullable=False),
            sa.Column('line_amt', sa.Numeric()),
            sa.Column('tax_amt', sa.Numeric()),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('invoice_line_id'),
            sa.ForeignKeyConstraint(['grn_line_id'], ['grn_lines.grn_line_id'], ),
            sa.ForeignKeyConstraint(['invoice_id'], ['invoice_headers.invoice_id'], ),
            sa.ForeignKeyConstraint(['po_line_id'], ['po_lines.po_line_id'], )
        )
        op.create_index('ix_invoice_lines_invoice', 'invoice_lines', ['invoice_id'])
        op.create_index('ix_invoice_lines_po_line', 'invoice_lines', ['po_line_id'])
        op.create_index('ix_invoice_lines_grn_line', 'invoice_lines', ['grn_line_id'])
        safe_print("[OK] invoice_lines table created")
    else:
        safe_print("[SKIP] invoice_lines table already exists")

    # ==================== 80. product_images ====================
    safe_print("[80/106] Creating product_images table...")

    if 'product_images' not in existing_tables:
        op.create_table(
            'product_images',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('platform_code', sa.String(length=32), nullable=False),
            sa.Column('shop_id', sa.String(length=64), nullable=False),
            sa.Column('platform_sku', sa.String(length=128), nullable=False),
            sa.Column('image_url', sa.String(length=1024), nullable=False),
            sa.Column('thumbnail_url', sa.String(length=1024), nullable=False),
            sa.Column('image_type', sa.String(length=20), nullable=False),
            sa.Column('image_order', sa.Integer(), nullable=False),
            sa.Column('file_size', sa.Integer()),
            sa.Column('width', sa.Integer()),
            sa.Column('height', sa.Integer()),
            sa.Column('format', sa.String(length=10)),
            sa.Column('quality_score', sa.Numeric()),
            sa.Column('is_main_image', sa.Boolean(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('idx_product_images_product', 'product_images', ['platform_code', 'shop_id', 'platform_sku'])
        op.create_index('idx_product_images_order', 'product_images', ['platform_sku', 'image_order'])
        op.create_index('idx_product_images_sku', 'product_images', ['platform_sku'])
        safe_print("[OK] product_images table created")
    else:
        safe_print("[SKIP] product_images table already exists")

    # ==================== 81. return_orders ====================
    safe_print("[81/106] Creating return_orders table...")

    if 'return_orders' not in existing_tables:
        op.create_table(
            'return_orders',
            sa.Column('return_id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('original_order_id', sa.String(length=128), nullable=False),
            sa.Column('return_type', sa.String(length=32), nullable=False),
            sa.Column('platform_code', sa.String(length=32), nullable=False),
            sa.Column('shop_id', sa.String(length=64), nullable=False),
            sa.Column('platform_sku', sa.String(length=128), nullable=False),
            sa.Column('qty', sa.Integer()),
            sa.Column('refund_amt', sa.Numeric()),
            sa.Column('restocking_fee', sa.Numeric()),
            sa.Column('reason', sa.String()),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('return_id')
        )
        op.create_index('ix_return_orders_original', 'return_orders', ['original_order_id'])
        op.create_index('ix_return_orders_shop', 'return_orders', ['platform_code', 'shop_id'])
        safe_print("[OK] return_orders table created")
    else:
        safe_print("[SKIP] return_orders table already exists")

    # ==================== 82. sales_campaigns ====================
    safe_print("[82/106] Creating sales_campaigns table...")

    if 'sales_campaigns' not in existing_tables:
        op.create_table(
            'sales_campaigns',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('campaign_name', sa.String(length=200), nullable=False),
            sa.Column('campaign_type', sa.String(length=32), nullable=False),
            sa.Column('start_date', sa.Date(), nullable=False),
            sa.Column('end_date', sa.Date(), nullable=False),
            sa.Column('target_amount', sa.Numeric(), nullable=False),
            sa.Column('target_quantity', sa.Integer(), nullable=False),
            sa.Column('actual_amount', sa.Numeric(), nullable=False),
            sa.Column('actual_quantity', sa.Integer(), nullable=False),
            sa.Column('achievement_rate', sa.Numeric(), nullable=False),
            sa.Column('status', sa.String(length=32), nullable=False),
            sa.Column('description', sa.String()),
            sa.Column('created_by', sa.String(length=64)),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_sales_campaigns_type', 'sales_campaigns', ['campaign_type'])
        op.create_index('ix_sales_campaigns_dates', 'sales_campaigns', ['start_date', 'end_date'])
        op.create_index('ix_sales_campaigns_status', 'sales_campaigns', ['status'])
        safe_print("[OK] sales_campaigns table created")
    else:
        safe_print("[SKIP] sales_campaigns table already exists")

    # ==================== 83. sales_campaign_shops ====================
    safe_print("[83/106] Creating sales_campaign_shops table...")

    if 'sales_campaign_shops' not in existing_tables:
        op.create_table(
            'sales_campaign_shops',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('campaign_id', sa.Integer(), nullable=False),
            sa.Column('platform_code', sa.String(length=32)),
            sa.Column('shop_id', sa.String(length=64)),
            sa.Column('target_amount', sa.Numeric(), nullable=False),
            sa.Column('target_quantity', sa.Integer(), nullable=False),
            sa.Column('actual_amount', sa.Numeric(), nullable=False),
            sa.Column('actual_quantity', sa.Integer(), nullable=False),
            sa.Column('achievement_rate', sa.Numeric(), nullable=False),
            sa.Column('rank', sa.Integer()),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('campaign_id', 'platform_code', 'shop_id', name='uq_campaign_shop'),
            sa.ForeignKeyConstraint(['shop_id'], ['dim_shops.shop_id'], ),
            sa.ForeignKeyConstraint(['campaign_id'], ['sales_campaigns.id'], ),
            sa.ForeignKeyConstraint(['platform_code'], ['dim_shops.platform_code'], )
        )
        op.create_index('ix_campaign_shops_campaign', 'sales_campaign_shops', ['campaign_id'])
        op.create_index('ix_campaign_shops_shop', 'sales_campaign_shops', ['platform_code', 'shop_id'])
        safe_print("[OK] sales_campaign_shops table created")
    else:
        safe_print("[SKIP] sales_campaign_shops table already exists")

    # ==================== 84. sales_campaigns_a ====================
    safe_print("[84/106] Creating sales_campaigns_a table...")

    if 'sales_campaigns_a' not in existing_tables:
        op.create_table(
            'sales_campaigns_a',
            sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
            sa.Column('campaign_name', sa.String(length=200), nullable=False),
            sa.Column('campaign_type', sa.String(length=32), nullable=False),
            sa.Column('start_date', sa.Date(), nullable=False),
            sa.Column('end_date', sa.Date(), nullable=False),
            sa.Column('target_amount', sa.Numeric(precision=15, scale=2), nullable=False),
            sa.Column('target_quantity', sa.Integer(), nullable=False),
            sa.Column('status', sa.String(length=32), nullable=False),
            sa.Column('description', sa.String()),
            sa.Column('created_by', sa.String(length=64)),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_sales_campaigns_status', 'sales_campaigns_a', ['status'])
        op.create_index('ix_sales_campaigns_type', 'sales_campaigns_a', ['campaign_type'])
        safe_print("[OK] sales_campaigns_a table created")
    else:
        safe_print("[SKIP] sales_campaigns_a table already exists")

    # ==================== 85. sales_targets ====================
    safe_print("[85/106] Creating sales_targets table...")

    if 'sales_targets' not in existing_tables:
        op.create_table(
            'sales_targets',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('target_name', sa.String(length=200), nullable=False),
            sa.Column('target_type', sa.String(length=32), nullable=False),
            sa.Column('period_start', sa.Date(), nullable=False),
            sa.Column('period_end', sa.Date(), nullable=False),
            sa.Column('target_amount', sa.Numeric(), nullable=False),
            sa.Column('target_quantity', sa.Integer(), nullable=False),
            sa.Column('achieved_amount', sa.Numeric(), nullable=False),
            sa.Column('achieved_quantity', sa.Integer(), nullable=False),
            sa.Column('achievement_rate', sa.Numeric(), nullable=False),
            sa.Column('status', sa.String(length=32), nullable=False),
            sa.Column('description', sa.String()),
            sa.Column('created_by', sa.String(length=64)),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_sales_targets_period', 'sales_targets', ['period_start', 'period_end'])
        op.create_index('ix_sales_targets_status', 'sales_targets', ['status'])
        op.create_index('ix_sales_targets_type', 'sales_targets', ['target_type'])
        safe_print("[OK] sales_targets table created")
    else:
        safe_print("[SKIP] sales_targets table already exists")

    # ==================== 86. sales_targets_a ====================
    safe_print("[86/106] Creating sales_targets_a table...")

    if 'sales_targets_a' not in existing_tables:
        op.create_table(
            'sales_targets_a',
            sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
            sa.Column('shop_id', sa.String(length=256), nullable=False),
            sa.Column('year_month', sa.String(length=7), nullable=False),
            sa.Column('target_sales_amount', sa.Numeric(precision=15, scale=2), nullable=False),
            sa.Column('target_quantity', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('shop_id', 'year_month', name='uq_sales_targets_shop_month')
        )
        op.create_index('ix_sales_targets_month', 'sales_targets_a', ['year_month'])
        op.create_index('ix_sales_targets_shop', 'sales_targets_a', ['shop_id'])
        safe_print("[OK] sales_targets_a table created")
    else:
        safe_print("[SKIP] sales_targets_a table already exists")

    # ==================== 87. security_config ====================
    safe_print("[87/106] Creating security_config table...")

    if 'security_config' not in existing_tables:
        op.create_table(
            'security_config',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('config_key', sa.String(length=64), nullable=False),
            sa.Column('config_value', sa.dialects.postgresql.JSONB, nullable=False),
            sa.Column('description', sa.String()),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.Column('updated_by', sa.Integer()),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('config_key', name='uq_security_config_key'),
            sa.UniqueConstraint('config_key'),
            sa.ForeignKeyConstraint(['updated_by'], ['dim_users.user_id'], )
        )
        op.create_index('ix_security_config_key', 'security_config', ['config_key'])
        safe_print("[OK] security_config table created")
    else:
        safe_print("[SKIP] security_config table already exists")

    # ==================== 88. shop_alerts ====================
    safe_print("[88/106] Creating shop_alerts table...")

    if 'shop_alerts' not in existing_tables:
        op.create_table(
            'shop_alerts',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('platform_code', sa.String(length=32), nullable=False),
            sa.Column('shop_id', sa.String(length=64), nullable=False),
            sa.Column('alert_type', sa.String(length=64), nullable=False),
            sa.Column('alert_level', sa.String(length=16), nullable=False),
            sa.Column('title', sa.String(length=200), nullable=False),
            sa.Column('message', sa.String(), nullable=False),
            sa.Column('metric_value', sa.Numeric()),
            sa.Column('threshold', sa.Numeric()),
            sa.Column('metric_unit', sa.String(length=32)),
            sa.Column('is_resolved', sa.Boolean(), nullable=False),
            sa.Column('resolved_at', sa.DateTime()),
            sa.Column('resolved_by', sa.String(length=64)),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['shop_id'], ['dim_shops.shop_id'], ),
            sa.ForeignKeyConstraint(['platform_code'], ['dim_shops.platform_code'], )
        )
        op.create_index('ix_shop_alerts_level', 'shop_alerts', ['alert_level'])
        op.create_index('ix_shop_alerts_shop', 'shop_alerts', ['platform_code', 'shop_id'])
        op.create_index('ix_shop_alerts_resolved', 'shop_alerts', ['is_resolved'])
        op.create_index('ix_shop_alerts_created', 'shop_alerts', ['created_at'])
        safe_print("[OK] shop_alerts table created")
    else:
        safe_print("[SKIP] shop_alerts table already exists")

    # ==================== 89. shop_commissions ====================
    safe_print("[89/106] Creating shop_commissions table...")

    if 'shop_commissions' not in existing_tables:
        op.create_table(
            'shop_commissions',
            sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
            sa.Column('shop_id', sa.String(length=256), nullable=False),
            sa.Column('year_month', sa.String(length=7), nullable=False),
            sa.Column('sales_amount', sa.Numeric(precision=15, scale=2), nullable=False),
            sa.Column('commission_amount', sa.Numeric(precision=15, scale=2), nullable=False),
            sa.Column('commission_rate', sa.Numeric(), nullable=False),
            sa.Column('calculated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('shop_id', 'year_month', name='uq_shop_commissions')
        )
        op.create_index('ix_shop_commissions_shop', 'shop_commissions', ['shop_id'])
        op.create_index('ix_shop_commissions_month', 'shop_commissions', ['year_month'])
        safe_print("[OK] shop_commissions table created")
    else:
        safe_print("[SKIP] shop_commissions table already exists")

    # ==================== 90. shop_health_scores ====================
    safe_print("[90/106] Creating shop_health_scores table...")

    if 'shop_health_scores' not in existing_tables:
        op.create_table(
            'shop_health_scores',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('platform_code', sa.String(length=32), nullable=False),
            sa.Column('shop_id', sa.String(length=64), nullable=False),
            sa.Column('metric_date', sa.Date(), nullable=False),
            sa.Column('granularity', sa.String(length=16), nullable=False),
            sa.Column('health_score', sa.Numeric(), nullable=False),
            sa.Column('gmv_score', sa.Numeric(), nullable=False),
            sa.Column('conversion_score', sa.Numeric(), nullable=False),
            sa.Column('inventory_score', sa.Numeric(), nullable=False),
            sa.Column('service_score', sa.Numeric(), nullable=False),
            sa.Column('gmv', sa.Numeric(), nullable=False),
            sa.Column('conversion_rate', sa.Numeric(), nullable=False),
            sa.Column('inventory_turnover', sa.Numeric(), nullable=False),
            sa.Column('customer_satisfaction', sa.Numeric(), nullable=False),
            sa.Column('risk_level', sa.String(length=16), nullable=False),
            sa.Column('risk_factors', sa.JSON),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('platform_code', 'shop_id', 'metric_date', 'granularity', name='uq_shop_health'),
            sa.ForeignKeyConstraint(['platform_code'], ['dim_shops.platform_code'], ),
            sa.ForeignKeyConstraint(['shop_id'], ['dim_shops.shop_id'], )
        )
        op.create_index('ix_shop_health_date', 'shop_health_scores', ['metric_date'])
        op.create_index('ix_shop_health_shop', 'shop_health_scores', ['platform_code', 'shop_id'])
        op.create_index('ix_shop_health_score', 'shop_health_scores', ['health_score'])
        op.create_index('ix_shop_health_risk', 'shop_health_scores', ['risk_level'])
        safe_print("[OK] shop_health_scores table created")
    else:
        safe_print("[SKIP] shop_health_scores table already exists")

    # ==================== 91. smtp_config ====================
    safe_print("[91/106] Creating smtp_config table...")

    if 'smtp_config' not in existing_tables:
        op.create_table(
            'smtp_config',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('smtp_server', sa.String(length=256), nullable=False),
            sa.Column('smtp_port', sa.Integer(), nullable=False),
            sa.Column('use_tls', sa.Boolean(), nullable=False),
            sa.Column('username', sa.String(length=256), nullable=False),
            sa.Column('password_encrypted', sa.String(), nullable=False),
            sa.Column('from_email', sa.String(length=256), nullable=False),
            sa.Column('from_name', sa.String(length=128)),
            sa.Column('is_active', sa.Boolean(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.Column('updated_by', sa.Integer()),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['updated_by'], ['dim_users.user_id'], )
        )
        safe_print("[OK] smtp_config table created")
    else:
        safe_print("[SKIP] smtp_config table already exists")

    # ==================== 92. staging_inventory ====================
    safe_print("[92/106] Creating staging_inventory table...")

    if 'staging_inventory' not in existing_tables:
        op.create_table(
            'staging_inventory',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('platform_code', sa.String(length=32)),
            sa.Column('shop_id', sa.String(length=64)),
            sa.Column('platform_sku', sa.String(length=128)),
            sa.Column('warehouse_id', sa.String(length=64)),
            sa.Column('inventory_data', sa.JSON, nullable=False),
            sa.Column('ingest_task_id', sa.String(length=64)),
            sa.Column('file_id', sa.Integer()),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['file_id'], ['catalog_files.id'], )
        )
        op.create_index('ix_staging_inventory_file_id', 'staging_inventory', ['file_id'])
        op.create_index('ix_staging_inventory_task', 'staging_inventory', ['ingest_task_id'])
        op.create_index('ix_staging_inventory_ingest_task_id', 'staging_inventory', ['ingest_task_id'])
        op.create_index('ix_staging_inventory_file', 'staging_inventory', ['file_id'])
        op.create_index('ix_staging_inventory_sku', 'staging_inventory', ['platform_code', 'shop_id', 'platform_sku'])
        op.create_index('ix_staging_inventory_platform', 'staging_inventory', ['platform_code'])
        safe_print("[OK] staging_inventory table created")
    else:
        safe_print("[SKIP] staging_inventory table already exists")

    # ==================== 93. staging_orders ====================
    safe_print("[93/106] Creating staging_orders table...")

    if 'staging_orders' not in existing_tables:
        op.create_table(
            'staging_orders',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('platform_code', sa.String(length=32)),
            sa.Column('shop_id', sa.String(length=64)),
            sa.Column('order_id', sa.String(length=128)),
            sa.Column('order_data', sa.JSON, nullable=False),
            sa.Column('ingest_task_id', sa.String(length=64)),
            sa.Column('file_id', sa.Integer()),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['file_id'], ['catalog_files.id'], )
        )
        op.create_index('ix_staging_orders_task', 'staging_orders', ['ingest_task_id'])
        op.create_index('ix_staging_orders_file_id', 'staging_orders', ['file_id'])
        op.create_index('ix_staging_orders_file', 'staging_orders', ['file_id'])
        op.create_index('ix_staging_orders_ingest_task_id', 'staging_orders', ['ingest_task_id'])
        op.create_index('ix_staging_orders_platform', 'staging_orders', ['platform_code'])
        safe_print("[OK] staging_orders table created")
    else:
        safe_print("[SKIP] staging_orders table already exists")

    # ==================== 94. staging_product_metrics ====================
    safe_print("[94/106] Creating staging_product_metrics table...")

    if 'staging_product_metrics' not in existing_tables:
        op.create_table(
            'staging_product_metrics',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('platform_code', sa.String(length=32)),
            sa.Column('shop_id', sa.String(length=64)),
            sa.Column('platform_sku', sa.String(length=64)),
            sa.Column('metric_data', sa.JSON, nullable=False),
            sa.Column('ingest_task_id', sa.String(length=64)),
            sa.Column('file_id', sa.Integer()),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['file_id'], ['catalog_files.id'], )
        )
        op.create_index('ix_staging_metrics_task', 'staging_product_metrics', ['ingest_task_id'])
        op.create_index('ix_staging_product_metrics_file_id', 'staging_product_metrics', ['file_id'])
        op.create_index('ix_staging_product_metrics_ingest_task_id', 'staging_product_metrics', ['ingest_task_id'])
        op.create_index('ix_staging_metrics_file', 'staging_product_metrics', ['file_id'])
        op.create_index('ix_staging_metrics_platform', 'staging_product_metrics', ['platform_code'])
        safe_print("[OK] staging_product_metrics table created")
    else:
        safe_print("[SKIP] staging_product_metrics table already exists")

    # ==================== 95. staging_raw_data ====================
    safe_print("[95/106] Creating staging_raw_data table...")

    if 'staging_raw_data' not in existing_tables:
        op.create_table(
            'staging_raw_data',
            sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
            sa.Column('file_id', sa.Integer()),
            sa.Column('row_number', sa.Integer(), nullable=False),
            sa.Column('platform_code', sa.String(length=32)),
            sa.Column('shop_id', sa.String(length=256)),
            sa.Column('data_domain', sa.String(length=64)),
            sa.Column('granularity', sa.String(length=32)),
            sa.Column('metric_date', sa.Date()),
            sa.Column('raw_data', sa.dialects.postgresql.JSONB, nullable=False),
            sa.Column('header_columns', sa.dialects.postgresql.JSONB),
            sa.Column('status', sa.String(length=32), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['file_id'], ['catalog_files.id'], )
        )
        op.create_index('ix_staging_raw_data_domain_gran', 'staging_raw_data', ['data_domain', 'granularity'])
        op.create_index('ix_staging_raw_data_data_domain', 'staging_raw_data', ['data_domain'])
        op.create_index('ix_staging_raw_data_file_id', 'staging_raw_data', ['file_id'])
        op.create_index('ix_staging_raw_data_file', 'staging_raw_data', ['file_id', 'status'])
        op.create_index('ix_staging_raw_data_shop_id', 'staging_raw_data', ['shop_id'])
        op.create_index('ix_staging_raw_data_platform_code', 'staging_raw_data', ['platform_code'])
        op.create_index('ix_staging_raw_data_status', 'staging_raw_data', ['status'])
        safe_print("[OK] staging_raw_data table created")
    else:
        safe_print("[SKIP] staging_raw_data table already exists")

    # ==================== 96. sync_progress_tasks ====================
    safe_print("[96/106] Creating sync_progress_tasks table...")

    if 'sync_progress_tasks' not in existing_tables:
        op.create_table(
            'sync_progress_tasks',
            sa.Column('task_id', sa.String(length=100), nullable=False),
            sa.Column('task_type', sa.String(length=50), nullable=False),
            sa.Column('total_files', sa.Integer(), nullable=False),
            sa.Column('processed_files', sa.Integer(), nullable=False),
            sa.Column('current_file', sa.String(length=500)),
            sa.Column('status', sa.String(length=20), nullable=False),
            sa.Column('total_rows', sa.Integer(), nullable=False),
            sa.Column('processed_rows', sa.Integer(), nullable=False),
            sa.Column('valid_rows', sa.Integer(), nullable=False),
            sa.Column('error_rows', sa.Integer(), nullable=False),
            sa.Column('quarantined_rows', sa.Integer(), nullable=False),
            sa.Column('file_progress', sa.Numeric(), nullable=False),
            sa.Column('row_progress', sa.Numeric(), nullable=False),
            sa.Column('start_time', sa.DateTime(), nullable=False),
            sa.Column('end_time', sa.DateTime()),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.Column('errors', sa.JSON),
            sa.Column('warnings', sa.JSON),
            sa.Column('task_details', sa.JSON),
            sa.PrimaryKeyConstraint('task_id')
        )
        op.create_index('ix_sync_progress_status', 'sync_progress_tasks', ['status', 'start_time'])
        op.create_index('ix_sync_progress_tasks_start_time', 'sync_progress_tasks', ['start_time'])
        op.create_index('ix_sync_progress_tasks_task_id', 'sync_progress_tasks', ['task_id'])
        op.create_index('ix_sync_progress_tasks_status', 'sync_progress_tasks', ['status'])
        op.create_index('ix_sync_progress_updated', 'sync_progress_tasks', ['updated_at'])
        safe_print("[OK] sync_progress_tasks table created")
    else:
        safe_print("[SKIP] sync_progress_tasks table already exists")

    # ==================== 97. system_config ====================
    safe_print("[97/106] Creating system_config table...")

    if 'system_config' not in existing_tables:
        op.create_table(
            'system_config',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('config_key', sa.String(length=64), nullable=False),
            sa.Column('config_value', sa.String(length=512), nullable=False),
            sa.Column('description', sa.String()),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.Column('updated_by', sa.Integer()),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('config_key', name='uq_system_config_key'),
            sa.UniqueConstraint('config_key'),
            sa.ForeignKeyConstraint(['updated_by'], ['dim_users.user_id'], )
        )
        op.create_index('ix_system_config_key', 'system_config', ['config_key'])
        safe_print("[OK] system_config table created")
    else:
        safe_print("[SKIP] system_config table already exists")

    # ==================== 98. system_logs ====================
    safe_print("[98/106] Creating system_logs table...")

    if 'system_logs' not in existing_tables:
        op.create_table(
            'system_logs',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('level', sa.String(length=10), nullable=False),
            sa.Column('module', sa.String(length=64), nullable=False),
            sa.Column('message', sa.String(), nullable=False),
            sa.Column('user_id', sa.Integer()),
            sa.Column('ip_address', sa.String(length=45)),
            sa.Column('user_agent', sa.String(length=512)),
            sa.Column('details', sa.dialects.postgresql.JSONB),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['user_id'], ['dim_users.user_id'], )
        )
        op.create_index('ix_system_logs_level', 'system_logs', ['level'])
        op.create_index('ix_system_logs_module', 'system_logs', ['module'])
        op.create_index('ix_system_logs_created_at', 'system_logs', ['created_at'])
        safe_print("[OK] system_logs table created")
    else:
        safe_print("[SKIP] system_logs table already exists")

    # ==================== 99. target_breakdown ====================
    safe_print("[99/106] Creating target_breakdown table...")

    if 'target_breakdown' not in existing_tables:
        op.create_table(
            'target_breakdown',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('target_id', sa.Integer(), nullable=False),
            sa.Column('breakdown_type', sa.String(length=32), nullable=False),
            sa.Column('platform_code', sa.String(length=32)),
            sa.Column('shop_id', sa.String(length=64)),
            sa.Column('period_start', sa.Date()),
            sa.Column('period_end', sa.Date()),
            sa.Column('period_label', sa.String(length=64)),
            sa.Column('target_amount', sa.Numeric(), nullable=False),
            sa.Column('target_quantity', sa.Integer(), nullable=False),
            sa.Column('achieved_amount', sa.Numeric(), nullable=False),
            sa.Column('achieved_quantity', sa.Integer(), nullable=False),
            sa.Column('achievement_rate', sa.Numeric(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['shop_id'], ['dim_shops.shop_id'], ),
            sa.ForeignKeyConstraint(['target_id'], ['sales_targets.id'], ),
            sa.ForeignKeyConstraint(['platform_code'], ['dim_shops.platform_code'], )
        )
        op.create_index('ix_target_breakdown_shop', 'target_breakdown', ['platform_code', 'shop_id'])
        op.create_index('ix_target_breakdown_target', 'target_breakdown', ['target_id'])
        op.create_index('ix_target_breakdown_period', 'target_breakdown', ['period_start', 'period_end'])
        safe_print("[OK] target_breakdown table created")
    else:
        safe_print("[SKIP] target_breakdown table already exists")

    # ==================== 100. tax_reports ====================
    safe_print("[100/106] Creating tax_reports table...")

    if 'tax_reports' not in existing_tables:
        op.create_table(
            'tax_reports',
            sa.Column('report_id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('period_month', sa.String(length=16), nullable=False),
            sa.Column('report_type', sa.String(length=64), nullable=False),
            sa.Column('status', sa.String(length=32), nullable=False),
            sa.Column('export_file_path', sa.String(length=1024)),
            sa.Column('generated_by', sa.String(length=64)),
            sa.Column('generated_at', sa.DateTime(), nullable=False),
            sa.Column('submitted_at', sa.DateTime()),
            sa.PrimaryKeyConstraint('report_id'),
            sa.ForeignKeyConstraint(['period_month'], ['dim_fiscal_calendar.period_code'], )
        )
        op.create_index('ix_tax_reports_period', 'tax_reports', ['period_month'])
        op.create_index('ix_tax_reports_status', 'tax_reports', ['status'])
        safe_print("[OK] tax_reports table created")
    else:
        safe_print("[SKIP] tax_reports table already exists")

    # ==================== 101. tax_vouchers ====================
    safe_print("[101/106] Creating tax_vouchers table...")

    if 'tax_vouchers' not in existing_tables:
        op.create_table(
            'tax_vouchers',
            sa.Column('voucher_id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('period_month', sa.String(length=16), nullable=False),
            sa.Column('voucher_type', sa.String(length=32), nullable=False),
            sa.Column('invoice_id', sa.Integer()),
            sa.Column('tax_amt', sa.Numeric()),
            sa.Column('deductible_amt', sa.Numeric()),
            sa.Column('status', sa.String(length=32), nullable=False),
            sa.Column('filing_status', sa.String(length=64)),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('voucher_id'),
            sa.ForeignKeyConstraint(['invoice_id'], ['invoice_headers.invoice_id'], ),
            sa.ForeignKeyConstraint(['period_month'], ['dim_fiscal_calendar.period_code'], )
        )
        op.create_index('ix_tax_vouchers_period', 'tax_vouchers', ['period_month'])
        op.create_index('ix_tax_vouchers_type', 'tax_vouchers', ['voucher_type', 'status'])
        safe_print("[OK] tax_vouchers table created")
    else:
        safe_print("[SKIP] tax_vouchers table already exists")

    # ==================== 102. three_way_match_log ====================
    safe_print("[102/106] Creating three_way_match_log table...")

    if 'three_way_match_log' not in existing_tables:
        op.create_table(
            'three_way_match_log',
            sa.Column('match_id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('po_line_id', sa.Integer(), nullable=False),
            sa.Column('grn_line_id', sa.Integer()),
            sa.Column('invoice_line_id', sa.Integer()),
            sa.Column('match_status', sa.String(length=32), nullable=False),
            sa.Column('variance_qty', sa.Integer()),
            sa.Column('variance_amt', sa.Numeric()),
            sa.Column('variance_reason', sa.String()),
            sa.Column('approved_by', sa.String(length=64)),
            sa.Column('approved_at', sa.DateTime()),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('match_id'),
            sa.ForeignKeyConstraint(['invoice_line_id'], ['invoice_lines.invoice_line_id'], ),
            sa.ForeignKeyConstraint(['po_line_id'], ['po_lines.po_line_id'], ),
            sa.ForeignKeyConstraint(['grn_line_id'], ['grn_lines.grn_line_id'], )
        )
        op.create_index('ix_three_way_match_po', 'three_way_match_log', ['po_line_id'])
        op.create_index('ix_three_way_match_status', 'three_way_match_log', ['match_status'])
        safe_print("[OK] three_way_match_log table created")
    else:
        safe_print("[SKIP] three_way_match_log table already exists")

    # ==================== 103. user_approval_logs ====================
    safe_print("[103/106] Creating user_approval_logs table...")

    if 'user_approval_logs' not in existing_tables:
        op.create_table(
            'user_approval_logs',
            sa.Column('log_id', sa.BigInteger(), nullable=False, autoincrement=True),
            sa.Column('user_id', sa.BigInteger(), nullable=False),
            sa.Column('action', sa.String(length=20), nullable=False),
            sa.Column('approved_by', sa.BigInteger(), nullable=False),
            sa.Column('reason', sa.String()),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=func.now()),
            sa.PrimaryKeyConstraint('log_id'),
            sa.ForeignKeyConstraint(['approved_by'], ['dim_users.user_id'], ),
            sa.ForeignKeyConstraint(['user_id'], ['dim_users.user_id'], )
        )
        op.create_index('ix_user_approval_logs_log_id', 'user_approval_logs', ['log_id'])
        op.create_index('ix_user_approval_logs_created_at', 'user_approval_logs', ['created_at'])
        op.create_index('ix_user_approval_logs_action', 'user_approval_logs', ['action'])
        op.create_index('idx_approval_user_time', 'user_approval_logs', ['user_id', 'created_at'])
        op.create_index('ix_user_approval_logs_user_id', 'user_approval_logs', ['user_id'])
        op.create_index('idx_approval_action_time', 'user_approval_logs', ['action', 'created_at'])
        safe_print("[OK] user_approval_logs table created")
    else:
        safe_print("[SKIP] user_approval_logs table already exists")

    # ==================== 104. user_notification_preferences ====================
    safe_print("[104/106] Creating user_notification_preferences table...")

    if 'user_notification_preferences' not in existing_tables:
        op.create_table(
            'user_notification_preferences',
            sa.Column('preference_id', sa.BigInteger(), nullable=False, autoincrement=True),
            sa.Column('user_id', sa.BigInteger(), nullable=False),
            sa.Column('notification_type', sa.String(length=50), nullable=False),
            sa.Column('enabled', sa.Boolean(), nullable=False),
            sa.Column('desktop_enabled', sa.Boolean(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=func.now()),
            sa.PrimaryKeyConstraint('preference_id'),
            sa.UniqueConstraint('user_id', 'notification_type', name='uq_user_notification_preference'),
            sa.ForeignKeyConstraint(['user_id'], ['dim_users.user_id'], )
        )
        op.create_index('idx_user_notification_user', 'user_notification_preferences', ['user_id'])
        op.create_index('ix_user_notification_preferences_user_id', 'user_notification_preferences', ['user_id'])
        safe_print("[OK] user_notification_preferences table created")
    else:
        safe_print("[SKIP] user_notification_preferences table already exists")

    # ==================== 105. user_roles ====================
    safe_print("[105/106] Creating user_roles table...")

    if 'user_roles' not in existing_tables:
        op.create_table(
            'user_roles',
            sa.Column('user_id', sa.BigInteger(), nullable=False),
            sa.Column('role_id', sa.BigInteger(), nullable=False),
            sa.Column('assigned_at', sa.DateTime(), server_default=func.now()),
            sa.Column('assigned_by', sa.String(length=100)),
            sa.PrimaryKeyConstraint('user_id', 'role_id'),
            sa.ForeignKeyConstraint(['user_id'], ['dim_users.user_id'], ),
            sa.ForeignKeyConstraint(['role_id'], ['dim_roles.role_id'], )
        )
        safe_print("[OK] user_roles table created")
    else:
        safe_print("[SKIP] user_roles table already exists")

    # ==================== 106. user_sessions ====================
    safe_print("[106/106] Creating user_sessions table...")

    if 'user_sessions' not in existing_tables:
        op.create_table(
            'user_sessions',
            sa.Column('session_id', sa.String(length=64), nullable=False),
            sa.Column('user_id', sa.BigInteger(), nullable=False),
            sa.Column('device_info', sa.String(length=255)),
            sa.Column('ip_address', sa.String(length=45)),
            sa.Column('location', sa.String(length=100)),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=func.now()),
            sa.Column('expires_at', sa.DateTime(), nullable=False),
            sa.Column('last_active_at', sa.DateTime(), nullable=False, server_default=func.now()),
            sa.Column('is_active', sa.Boolean(), nullable=False),
            sa.Column('revoked_at', sa.DateTime()),
            sa.Column('revoked_reason', sa.String(length=100)),
            sa.PrimaryKeyConstraint('session_id'),
            sa.ForeignKeyConstraint(['user_id'], ['dim_users.user_id'], )
        )
        op.create_index('idx_session_user_active', 'user_sessions', ['user_id', 'is_active'])
        op.create_index('ix_user_sessions_session_id', 'user_sessions', ['session_id'])
        op.create_index('idx_session_expires', 'user_sessions', ['expires_at'])
        op.create_index('ix_user_sessions_user_id', 'user_sessions', ['user_id'])
        safe_print("[OK] user_sessions table created")
    else:
        safe_print("[SKIP] user_sessions table already exists")



def downgrade():
    """回滚：删除所有表（谨慎使用）"""
    # 注意：downgrade 会删除所有表，生产环境请谨慎使用
    # 按相反顺序删除表（处理外键依赖）
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = set(inspector.get_table_names())

    if 'user_sessions' in existing_tables:
        op.drop_table('user_sessions')
        safe_print("[OK] user_sessions table dropped")

    if 'user_roles' in existing_tables:
        op.drop_table('user_roles')
        safe_print("[OK] user_roles table dropped")

    if 'user_notification_preferences' in existing_tables:
        op.drop_table('user_notification_preferences')
        safe_print("[OK] user_notification_preferences table dropped")

    if 'user_approval_logs' in existing_tables:
        op.drop_table('user_approval_logs')
        safe_print("[OK] user_approval_logs table dropped")

    if 'three_way_match_log' in existing_tables:
        op.drop_table('three_way_match_log')
        safe_print("[OK] three_way_match_log table dropped")

    if 'tax_vouchers' in existing_tables:
        op.drop_table('tax_vouchers')
        safe_print("[OK] tax_vouchers table dropped")

    if 'tax_reports' in existing_tables:
        op.drop_table('tax_reports')
        safe_print("[OK] tax_reports table dropped")

    if 'target_breakdown' in existing_tables:
        op.drop_table('target_breakdown')
        safe_print("[OK] target_breakdown table dropped")

    if 'system_logs' in existing_tables:
        op.drop_table('system_logs')
        safe_print("[OK] system_logs table dropped")

    if 'system_config' in existing_tables:
        op.drop_table('system_config')
        safe_print("[OK] system_config table dropped")

    if 'sync_progress_tasks' in existing_tables:
        op.drop_table('sync_progress_tasks')
        safe_print("[OK] sync_progress_tasks table dropped")

    if 'staging_raw_data' in existing_tables:
        op.drop_table('staging_raw_data')
        safe_print("[OK] staging_raw_data table dropped")

    if 'staging_product_metrics' in existing_tables:
        op.drop_table('staging_product_metrics')
        safe_print("[OK] staging_product_metrics table dropped")

    if 'staging_orders' in existing_tables:
        op.drop_table('staging_orders')
        safe_print("[OK] staging_orders table dropped")

    if 'staging_inventory' in existing_tables:
        op.drop_table('staging_inventory')
        safe_print("[OK] staging_inventory table dropped")

    if 'smtp_config' in existing_tables:
        op.drop_table('smtp_config')
        safe_print("[OK] smtp_config table dropped")

    if 'shop_health_scores' in existing_tables:
        op.drop_table('shop_health_scores')
        safe_print("[OK] shop_health_scores table dropped")

    if 'shop_commissions' in existing_tables:
        op.drop_table('shop_commissions')
        safe_print("[OK] shop_commissions table dropped")

    if 'shop_alerts' in existing_tables:
        op.drop_table('shop_alerts')
        safe_print("[OK] shop_alerts table dropped")

    if 'security_config' in existing_tables:
        op.drop_table('security_config')
        safe_print("[OK] security_config table dropped")

    if 'sales_targets_a' in existing_tables:
        op.drop_table('sales_targets_a')
        safe_print("[OK] sales_targets_a table dropped")

    if 'sales_targets' in existing_tables:
        op.drop_table('sales_targets')
        safe_print("[OK] sales_targets table dropped")

    if 'sales_campaigns_a' in existing_tables:
        op.drop_table('sales_campaigns_a')
        safe_print("[OK] sales_campaigns_a table dropped")

    if 'sales_campaign_shops' in existing_tables:
        op.drop_table('sales_campaign_shops')
        safe_print("[OK] sales_campaign_shops table dropped")

    if 'sales_campaigns' in existing_tables:
        op.drop_table('sales_campaigns')
        safe_print("[OK] sales_campaigns table dropped")

    if 'return_orders' in existing_tables:
        op.drop_table('return_orders')
        safe_print("[OK] return_orders table dropped")

    if 'product_images' in existing_tables:
        op.drop_table('product_images')
        safe_print("[OK] product_images table dropped")

    if 'invoice_lines' in existing_tables:
        op.drop_table('invoice_lines')
        safe_print("[OK] invoice_lines table dropped")

    if 'grn_lines' in existing_tables:
        op.drop_table('grn_lines')
        safe_print("[OK] grn_lines table dropped")

    if 'po_lines' in existing_tables:
        op.drop_table('po_lines')
        safe_print("[OK] po_lines table dropped")

    if 'logistics_costs' in existing_tables:
        op.drop_table('logistics_costs')
        safe_print("[OK] logistics_costs table dropped")

    if 'grn_headers' in existing_tables:
        op.drop_table('grn_headers')
        safe_print("[OK] grn_headers table dropped")

    if 'po_headers' in existing_tables:
        op.drop_table('po_headers')
        safe_print("[OK] po_headers table dropped")

    if 'platform_accounts' in existing_tables:
        op.drop_table('platform_accounts')
        safe_print("[OK] platform_accounts table dropped")

    if 'performance_scores_c' in existing_tables:
        op.drop_table('performance_scores_c')
        safe_print("[OK] performance_scores_c table dropped")

    if 'performance_scores' in existing_tables:
        op.drop_table('performance_scores')
        safe_print("[OK] performance_scores table dropped")

    if 'performance_config_a' in existing_tables:
        op.drop_table('performance_config_a')
        safe_print("[OK] performance_config_a table dropped")

    if 'performance_config' in existing_tables:
        op.drop_table('performance_config')
        safe_print("[OK] performance_config table dropped")

    if 'operating_costs' in existing_tables:
        op.drop_table('operating_costs')
        safe_print("[OK] operating_costs table dropped")

    if 'opening_balances' in existing_tables:
        op.drop_table('opening_balances')
        safe_print("[OK] opening_balances table dropped")

    if 'notifications' in existing_tables:
        op.drop_table('notifications')
        safe_print("[OK] notifications table dropped")

    if 'alert_rules' in existing_tables:
        op.drop_table('alert_rules')
        safe_print("[OK] alert_rules table dropped")

    if 'notification_templates' in existing_tables:
        op.drop_table('notification_templates')
        safe_print("[OK] notification_templates table dropped")

    if 'mv_refresh_log' in existing_tables:
        op.drop_table('mv_refresh_log')
        safe_print("[OK] mv_refresh_log table dropped")

    if 'mapping_sessions' in existing_tables:
        op.drop_table('mapping_sessions')
        safe_print("[OK] mapping_sessions table dropped")

    if 'logistics_allocation_rules' in existing_tables:
        op.drop_table('logistics_allocation_rules')
        safe_print("[OK] logistics_allocation_rules table dropped")

    if 'journal_entry_lines' in existing_tables:
        op.drop_table('journal_entry_lines')
        safe_print("[OK] journal_entry_lines table dropped")

    if 'journal_entries' in existing_tables:
        op.drop_table('journal_entries')
        safe_print("[OK] journal_entries table dropped")

    if 'invoice_attachments' in existing_tables:
        op.drop_table('invoice_attachments')
        safe_print("[OK] invoice_attachments table dropped")

    if 'invoice_headers' in existing_tables:
        op.drop_table('invoice_headers')
        safe_print("[OK] invoice_headers table dropped")

    if 'inventory_ledger' in existing_tables:
        op.drop_table('inventory_ledger')
        safe_print("[OK] inventory_ledger table dropped")

    if 'gl_accounts' in existing_tables:
        op.drop_table('gl_accounts')
        safe_print("[OK] gl_accounts table dropped")

    if 'fx_rates' in existing_tables:
        op.drop_table('fx_rates')
        safe_print("[OK] fx_rates table dropped")

    if 'field_usage_tracking' in existing_tables:
        op.drop_table('field_usage_tracking')
        safe_print("[OK] field_usage_tracking table dropped")

    if 'field_mappings' in existing_tables:
        op.drop_table('field_mappings')
        safe_print("[OK] field_mappings table dropped")

    if 'field_mapping_templates' in existing_tables:
        op.drop_table('field_mapping_templates')
        safe_print("[OK] field_mapping_templates table dropped")

    if 'field_mapping_template_items' in existing_tables:
        op.drop_table('field_mapping_template_items')
        safe_print("[OK] field_mapping_template_items table dropped")

    if 'field_mapping_dictionary' in existing_tables:
        op.drop_table('field_mapping_dictionary')
        safe_print("[OK] field_mapping_dictionary table dropped")

    if 'field_mapping_audit' in existing_tables:
        op.drop_table('field_mapping_audit')
        safe_print("[OK] field_mapping_audit table dropped")

    if 'fact_traffic' in existing_tables:
        op.drop_table('fact_traffic')
        safe_print("[OK] fact_traffic table dropped")

    if 'fact_service' in existing_tables:
        op.drop_table('fact_service')
        safe_print("[OK] fact_service table dropped")

    if 'fact_rate_limit_config_audit' in existing_tables:
        op.drop_table('fact_rate_limit_config_audit')
        safe_print("[OK] fact_rate_limit_config_audit table dropped")

    if 'fact_product_metrics' in existing_tables:
        op.drop_table('fact_product_metrics')
        safe_print("[OK] fact_product_metrics table dropped")

    if 'fact_orders' in existing_tables:
        op.drop_table('fact_orders')
        safe_print("[OK] fact_orders table dropped")

    if 'fact_order_items' in existing_tables:
        op.drop_table('fact_order_items')
        safe_print("[OK] fact_order_items table dropped")

    if 'fact_order_amounts' in existing_tables:
        op.drop_table('fact_order_amounts')
        safe_print("[OK] fact_order_amounts table dropped")

    if 'fact_expenses_allocated_day_shop_sku' in existing_tables:
        op.drop_table('fact_expenses_allocated_day_shop_sku')
        safe_print("[OK] fact_expenses_allocated_day_shop_sku table dropped")

    if 'fact_expenses_month' in existing_tables:
        op.drop_table('fact_expenses_month')
        safe_print("[OK] fact_expenses_month table dropped")

    if 'fact_audit_logs' in existing_tables:
        op.drop_table('fact_audit_logs')
        safe_print("[OK] fact_audit_logs table dropped")

    if 'fact_analytics' in existing_tables:
        op.drop_table('fact_analytics')
        safe_print("[OK] fact_analytics table dropped")

    if 'entity_aliases' in existing_tables:
        op.drop_table('entity_aliases')
        safe_print("[OK] entity_aliases table dropped")

    if 'employees' in existing_tables:
        op.drop_table('employees')
        safe_print("[OK] employees table dropped")

    if 'employee_targets' in existing_tables:
        op.drop_table('employee_targets')
        safe_print("[OK] employee_targets table dropped")

    if 'employee_performance' in existing_tables:
        op.drop_table('employee_performance')
        safe_print("[OK] employee_performance table dropped")

    if 'employee_commissions' in existing_tables:
        op.drop_table('employee_commissions')
        safe_print("[OK] employee_commissions table dropped")

    if 'dim_vendors' in existing_tables:
        op.drop_table('dim_vendors')
        safe_print("[OK] dim_vendors table dropped")

    if 'backup_records' in existing_tables:
        op.drop_table('backup_records')
        safe_print("[OK] backup_records table dropped")

    if 'dim_users' in existing_tables:
        op.drop_table('dim_users')
        safe_print("[OK] dim_users table dropped")

    if 'clearance_rankings' in existing_tables:
        op.drop_table('clearance_rankings')
        safe_print("[OK] clearance_rankings table dropped")

    if 'dim_shops' in existing_tables:
        op.drop_table('dim_shops')
        safe_print("[OK] dim_shops table dropped")

    if 'dim_roles' in existing_tables:
        op.drop_table('dim_roles')
        safe_print("[OK] dim_roles table dropped")

    if 'dim_rate_limit_config' in existing_tables:
        op.drop_table('dim_rate_limit_config')
        safe_print("[OK] dim_rate_limit_config table dropped")

    if 'bridge_product_keys' in existing_tables:
        op.drop_table('bridge_product_keys')
        safe_print("[OK] bridge_product_keys table dropped")

    if 'dim_products' in existing_tables:
        op.drop_table('dim_products')
        safe_print("[OK] dim_products table dropped")

    if 'dim_product_master' in existing_tables:
        op.drop_table('dim_product_master')
        safe_print("[OK] dim_product_master table dropped")

    if 'dim_platforms' in existing_tables:
        op.drop_table('dim_platforms')
        safe_print("[OK] dim_platforms table dropped")

    if 'dim_metric_formulas' in existing_tables:
        op.drop_table('dim_metric_formulas')
        safe_print("[OK] dim_metric_formulas table dropped")

    if 'dim_fiscal_calendar' in existing_tables:
        op.drop_table('dim_fiscal_calendar')
        safe_print("[OK] dim_fiscal_calendar table dropped")

    if 'dim_exchange_rates' in existing_tables:
        op.drop_table('dim_exchange_rates')
        safe_print("[OK] dim_exchange_rates table dropped")

    if 'dim_currency_rates' in existing_tables:
        op.drop_table('dim_currency_rates')
        safe_print("[OK] dim_currency_rates table dropped")

    if 'dim_currencies' in existing_tables:
        op.drop_table('dim_currencies')
        safe_print("[OK] dim_currencies table dropped")

    if 'data_records' in existing_tables:
        op.drop_table('data_records')
        safe_print("[OK] data_records table dropped")

    if 'data_quarantine' in existing_tables:
        op.drop_table('data_quarantine')
        safe_print("[OK] data_quarantine table dropped")

    if 'data_files' in existing_tables:
        op.drop_table('data_files')
        safe_print("[OK] data_files table dropped")

    if 'component_test_history' in existing_tables:
        op.drop_table('component_test_history')
        safe_print("[OK] component_test_history table dropped")

    if 'component_versions' in existing_tables:
        op.drop_table('component_versions')
        safe_print("[OK] component_versions table dropped")

    if 'collection_task_logs' in existing_tables:
        op.drop_table('collection_task_logs')
        safe_print("[OK] collection_task_logs table dropped")

    if 'collection_tasks' in existing_tables:
        op.drop_table('collection_tasks')
        safe_print("[OK] collection_tasks table dropped")

    if 'collection_sync_points' in existing_tables:
        op.drop_table('collection_sync_points')
        safe_print("[OK] collection_sync_points table dropped")

    if 'collection_configs' in existing_tables:
        op.drop_table('collection_configs')
        safe_print("[OK] collection_configs table dropped")

    if 'catalog_files' in existing_tables:
        op.drop_table('catalog_files')
        safe_print("[OK] catalog_files table dropped")

    if 'attendance_records' in existing_tables:
        op.drop_table('attendance_records')
        safe_print("[OK] attendance_records table dropped")

    if 'approval_logs' in existing_tables:
        op.drop_table('approval_logs')
        safe_print("[OK] approval_logs table dropped")

    if 'allocation_rules' in existing_tables:
        op.drop_table('allocation_rules')
        safe_print("[OK] allocation_rules table dropped")

    if 'accounts' in existing_tables:
        op.drop_table('accounts')
        safe_print("[OK] accounts table dropped")

    if 'account_aliases' in existing_tables:
        op.drop_table('account_aliases')
        safe_print("[OK] account_aliases table dropped")
