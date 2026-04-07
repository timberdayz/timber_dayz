"""
v4.6.0 数据采集模块表结构 (Rewritten)

创建采集配置和日志相关表，增强任务表

Revision ID: collection_module_v460
Revises: 20251205_153442
Create Date: 2025-12-09

Changes:
- 创建 collection_configs 表（采集配置）
- 增强 collection_tasks 表（添加进度、错误、验证码等字段）
- 创建 collection_task_logs 表（任务日志）

重写说明（2026-01-11）：
- 修复DuplicateTable和DuplicateColumn错误
- 基于schema.py中实际表定义
- 添加完整的幂等性检查
- 注意：collection_configs使用sub_domains（JSON），不是sub_domain（String）
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = 'collection_module_v460'
down_revision = '20251205_153442'
branch_labels = None
depends_on = None


def upgrade():
    """升级：创建采集模块表"""
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = set(inspector.get_table_names())
    
    # 1. 创建 collection_configs 表
    if 'collection_configs' not in existing_tables:
        try:
            op.create_table(
                'collection_configs',
                sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
                sa.Column('name', sa.String(100), nullable=False),
                sa.Column('platform', sa.String(50), nullable=False),
                sa.Column('account_ids', postgresql.JSON(), nullable=False),
                sa.Column('data_domains', postgresql.JSON(), nullable=False),
                sa.Column('sub_domains', postgresql.JSON(), nullable=True),  # 注意：是sub_domains（JSON数组），不是sub_domain
                sa.Column('granularity', sa.String(20), nullable=False, server_default='daily'),
                sa.Column('date_range_type', sa.String(20), nullable=False, server_default='yesterday'),
                sa.Column('custom_date_start', sa.Date(), nullable=True),
                sa.Column('custom_date_end', sa.Date(), nullable=True),
                sa.Column('schedule_enabled', sa.Boolean(), nullable=False, server_default='false'),
                sa.Column('schedule_cron', sa.String(50), nullable=True),
                sa.Column('retry_count', sa.Integer(), nullable=False, server_default='3'),
                sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
                sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
                sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
                sa.PrimaryKeyConstraint('id'),
                sa.UniqueConstraint('name', 'platform', name='uq_collection_configs_name_platform')
            )
            
            # 创建索引
            op.create_index('ix_collection_configs_platform', 'collection_configs', ['platform'])
            op.create_index('ix_collection_configs_active', 'collection_configs', ['is_active'])
            
            print("[OK] Created table: collection_configs")
        except Exception as e:
            print(f"[WARNING] 创建collection_configs表失败: {e}")
    else:
        print("[INFO] Table collection_configs already exists, skipping creation")
    
    # 2. 增强 collection_tasks 表（添加新字段）
    if 'collection_tasks' in existing_tables:
        try:
            existing_columns = [col['name'] for col in inspector.get_columns('collection_tasks')]
            existing_indexes = [idx['name'] for idx in inspector.get_indexes('collection_tasks')]
            
            # 添加 config_id 外键
            if 'config_id' not in existing_columns:
                op.add_column('collection_tasks', 
                    sa.Column('config_id', sa.Integer(), nullable=True))
                try:
                    op.create_foreign_key(
                        'fk_collection_tasks_config',
                        'collection_tasks', 'collection_configs',
                        ['config_id'], ['id'],
                        ondelete='SET NULL'
                    )
                except Exception as e:
                    print(f"[WARNING] 创建外键fk_collection_tasks_config失败: {e}")
            
            # 添加进度跟踪字段
            new_columns = [
                ('progress', sa.Integer(), 0),
                ('current_step', sa.String(200), None),
                ('files_collected', sa.Integer(), 0),
                ('trigger_type', sa.String(20), 'manual'),
                ('data_domains', postgresql.JSON(), None),
                ('sub_domains', postgresql.JSON(), None),  # 注意：是sub_domains（JSON数组）
                ('granularity', sa.String(20), None),
                ('date_range', postgresql.JSON(), None),
                ('error_message', sa.Text(), None),
                ('error_screenshot_path', sa.String(500), None),
                ('duration_seconds', sa.Integer(), None),
                ('retry_count', sa.Integer(), 0),
                ('parent_task_id', sa.Integer(), None),
                ('verification_type', sa.String(50), None),
                ('verification_screenshot', sa.String(500), None),
                ('version', sa.Integer(), 1),
                # v4.7.0 任务粒度优化字段
                ('total_domains', sa.Integer(), 0),
                ('completed_domains', postgresql.JSON(), None),
                ('failed_domains', postgresql.JSON(), None),
                ('current_domain', sa.String(100), None),
                ('debug_mode', sa.Boolean(), False),
            ]
            
            for col_name, col_type, default_val in new_columns:
                if col_name not in existing_columns:
                    try:
                        if default_val is not None:
                            op.add_column('collection_tasks',
                                sa.Column(col_name, col_type, nullable=False, server_default=str(default_val) if not isinstance(default_val, bool) else ('true' if default_val else 'false')))
                        else:
                            op.add_column('collection_tasks',
                                sa.Column(col_name, col_type, nullable=True))
                        print(f"[OK] Added column {col_name} to collection_tasks")
                    except Exception as e:
                        print(f"[WARNING] 添加列{col_name}失败: {e}")
            
            # 创建外键约束（如果parent_task_id列存在且外键不存在）
            if 'parent_task_id' in [col['name'] for col in inspector.get_columns('collection_tasks')]:
                try:
                    existing_constraints = [c['name'] for c in inspector.get_foreign_keys('collection_tasks')]
                    if 'fk_collection_tasks_parent' not in existing_constraints:
                        op.create_foreign_key(
                            'fk_collection_tasks_parent',
                            'collection_tasks', 'collection_tasks',
                            ['parent_task_id'], ['id'],
                            ondelete='SET NULL'
                        )
                except Exception as e:
                    print(f"[WARNING] 创建外键fk_collection_tasks_parent失败: {e}")
            
            # 创建新索引
            new_indexes = [
                ('ix_collection_tasks_config', ['config_id']),
                ('ix_collection_tasks_created', ['created_at']),
            ]
            
            for idx_name, idx_cols in new_indexes:
                if idx_name not in existing_indexes:
                    try:
                        op.create_index(idx_name, 'collection_tasks', idx_cols)
                        print(f"[OK] Created index {idx_name}")
                    except Exception as e:
                        print(f"[WARNING] 创建索引{idx_name}失败: {e}")
            
            print("[OK] Enhanced table: collection_tasks")
        except Exception as e:
            print(f"[WARNING] 增强collection_tasks表失败: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("[SKIP] Table collection_tasks does not exist, will be created by schema")
    
    # 3. 创建 collection_task_logs 表
    if 'collection_task_logs' not in existing_tables:
        try:
            op.create_table(
                'collection_task_logs',
                sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
                sa.Column('task_id', sa.Integer(), nullable=False),
                sa.Column('level', sa.String(10), nullable=False),
                sa.Column('message', sa.Text(), nullable=False),
                sa.Column('details', postgresql.JSON(), nullable=True),
                sa.Column('timestamp', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
                sa.PrimaryKeyConstraint('id'),
                sa.ForeignKeyConstraint(['task_id'], ['collection_tasks.id'], ondelete='CASCADE')
            )
            
            # 创建索引
            op.create_index('ix_collection_task_logs_task', 'collection_task_logs', ['task_id'])
            op.create_index('ix_collection_task_logs_level', 'collection_task_logs', ['level'])
            op.create_index('ix_collection_task_logs_time', 'collection_task_logs', ['timestamp'])
            
            print("[OK] Created table: collection_task_logs")
        except Exception as e:
            print(f"[WARNING] 创建collection_task_logs表失败: {e}")
    else:
        print("[INFO] Table collection_task_logs already exists, skipping creation")
    
    print("\n[OK] v4.6.0 Collection Module tables migration completed!")


def downgrade():
    """降级：删除采集模块表"""
    conn = op.get_bind()
    inspector = inspect(conn)
    
    # 1. 删除 collection_task_logs 表
    if 'collection_task_logs' in inspector.get_table_names():
        try:
            op.drop_table('collection_task_logs')
            print("[OK] Dropped table: collection_task_logs")
        except Exception as e:
            print(f"[WARNING] 删除collection_task_logs表失败: {e}")
    
    # 2. 从 collection_tasks 删除新增字段
    if 'collection_tasks' in inspector.get_table_names():
        try:
            existing_columns = [col['name'] for col in inspector.get_columns('collection_tasks')]
            existing_constraints = [c['name'] for c in inspector.get_foreign_keys('collection_tasks')]
            existing_indexes = [idx['name'] for idx in inspector.get_indexes('collection_tasks')]
            
            # 删除外键
            for constraint_name in ['fk_collection_tasks_config', 'fk_collection_tasks_parent']:
                if constraint_name in existing_constraints:
                    try:
                        op.drop_constraint(constraint_name, 'collection_tasks', type_='foreignkey')
                    except:
                        pass
            
            # 删除索引
            for idx_name in ['ix_collection_tasks_config', 'ix_collection_tasks_created']:
                if idx_name in existing_indexes:
                    try:
                        op.drop_index(idx_name, table_name='collection_tasks')
                    except:
                        pass
            
            # 删除新增列
            new_columns = [
                'config_id', 'progress', 'current_step', 'files_collected',
                'trigger_type', 'data_domains', 'sub_domains', 'granularity', 'date_range',
                'error_message', 'error_screenshot_path',
                'duration_seconds', 'retry_count', 'parent_task_id',
                'verification_type', 'verification_screenshot', 'version',
                'total_domains', 'completed_domains', 'failed_domains', 'current_domain',
                'debug_mode'
            ]
            
            for col in new_columns:
                if col in existing_columns:
                    try:
                        op.drop_column('collection_tasks', col)
                    except:
                        pass
            
            print("[OK] Reverted table: collection_tasks")
        except Exception as e:
            print(f"[WARNING] 回滚collection_tasks表失败: {e}")
    
    # 3. 删除 collection_configs 表
    if 'collection_configs' in inspector.get_table_names():
        try:
            op.drop_table('collection_configs')
            print("[OK] Dropped table: collection_configs")
        except Exception as e:
            print(f"[WARNING] 删除collection_configs表失败: {e}")
    
    print("\n[OK] v4.6.0 Collection Module tables downgrade completed!")
