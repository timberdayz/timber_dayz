"""
v4.6.0 数据采集模块表结构

创建采集配置和日志相关表，增强任务表

Revision ID: collection_module_v460
Revises: 20251205_153442_v4_16_0_add_analytics_and_sub_domain_tables
Create Date: 2025-12-09

Changes:
- 创建 collection_configs 表（采集配置）
- 增强 collection_tasks 表（添加进度、错误、验证码等字段）
- 创建 collection_task_logs 表（任务日志）
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'collection_module_v460'
down_revision = '20251205_153442'  # 前一个迁移：v4_16_0_add_analytics_and_sub_domain_tables
branch_labels = None
depends_on = None


def upgrade():
    """升级：创建采集模块表"""
    
    # 1. 创建 collection_configs 表
    op.create_table(
        'collection_configs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('platform', sa.String(50), nullable=False),
        sa.Column('account_ids', postgresql.JSON(), nullable=False),
        sa.Column('data_domains', postgresql.JSON(), nullable=False),
        sa.Column('sub_domain', sa.String(50), nullable=True),
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
        sa.Column('created_by', sa.String(100), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', 'platform', name='uq_collection_configs_name_platform')
    )
    
    # 创建索引
    op.create_index('ix_collection_configs_platform', 'collection_configs', ['platform'])
    op.create_index('ix_collection_configs_active', 'collection_configs', ['is_active'])
    
    print("[OK] Created table: collection_configs")
    
    # 2. 增强 collection_tasks 表（添加新字段）
    # 检查表是否存在
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    if 'collection_tasks' in inspector.get_table_names():
        existing_columns = [col['name'] for col in inspector.get_columns('collection_tasks')]
        
        # 添加 config_id 外键
        if 'config_id' not in existing_columns:
            op.add_column('collection_tasks', 
                sa.Column('config_id', sa.Integer(), nullable=True))
            op.create_foreign_key(
                'fk_collection_tasks_config',
                'collection_tasks', 'collection_configs',
                ['config_id'], ['id'],
                ondelete='SET NULL'
            )
        
        # 添加进度跟踪字段
        if 'progress' not in existing_columns:
            op.add_column('collection_tasks',
                sa.Column('progress', sa.Integer(), nullable=False, server_default='0'))
        
        if 'current_step' not in existing_columns:
            op.add_column('collection_tasks',
                sa.Column('current_step', sa.String(200), nullable=True))
        
        if 'files_collected' not in existing_columns:
            op.add_column('collection_tasks',
                sa.Column('files_collected', sa.Integer(), nullable=False, server_default='0'))
        
        # 添加任务配置字段
        if 'trigger_type' not in existing_columns:
            op.add_column('collection_tasks',
                sa.Column('trigger_type', sa.String(20), nullable=False, server_default='manual'))
        
        if 'data_domains' not in existing_columns:
            op.add_column('collection_tasks',
                sa.Column('data_domains', postgresql.JSON(), nullable=True))
        
        if 'sub_domain' not in existing_columns:
            op.add_column('collection_tasks',
                sa.Column('sub_domain', sa.String(50), nullable=True))
        
        if 'granularity' not in existing_columns:
            op.add_column('collection_tasks',
                sa.Column('granularity', sa.String(20), nullable=True))
        
        if 'date_range' not in existing_columns:
            op.add_column('collection_tasks',
                sa.Column('date_range', postgresql.JSON(), nullable=True))
        
        # 添加错误信息字段
        if 'error_message' not in existing_columns:
            op.add_column('collection_tasks',
                sa.Column('error_message', sa.Text(), nullable=True))
        
        if 'error_screenshot_path' not in existing_columns:
            op.add_column('collection_tasks',
                sa.Column('error_screenshot_path', sa.String(500), nullable=True))
        
        # 添加执行统计字段
        if 'duration_seconds' not in existing_columns:
            op.add_column('collection_tasks',
                sa.Column('duration_seconds', sa.Integer(), nullable=True))
        
        if 'retry_count' not in existing_columns:
            op.add_column('collection_tasks',
                sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'))
        
        if 'parent_task_id' not in existing_columns:
            op.add_column('collection_tasks',
                sa.Column('parent_task_id', sa.Integer(), nullable=True))
            op.create_foreign_key(
                'fk_collection_tasks_parent',
                'collection_tasks', 'collection_tasks',
                ['parent_task_id'], ['id'],
                ondelete='SET NULL'
            )
        
        # 添加验证码字段
        if 'verification_type' not in existing_columns:
            op.add_column('collection_tasks',
                sa.Column('verification_type', sa.String(50), nullable=True))
        
        if 'verification_screenshot' not in existing_columns:
            op.add_column('collection_tasks',
                sa.Column('verification_screenshot', sa.String(500), nullable=True))
        
        # 添加乐观锁版本号
        if 'version' not in existing_columns:
            op.add_column('collection_tasks',
                sa.Column('version', sa.Integer(), nullable=False, server_default='1'))
        
        # 创建新索引
        try:
            op.create_index('ix_collection_tasks_config', 'collection_tasks', ['config_id'])
        except:
            pass
        
        try:
            op.create_index('ix_collection_tasks_created', 'collection_tasks', ['created_at'])
        except:
            pass
        
        print("[OK] Enhanced table: collection_tasks")
    else:
        print("[SKIP] Table collection_tasks does not exist, will be created by schema")
    
    # 3. 创建 collection_task_logs 表
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
    
    print("\n[OK] v4.6.0 Collection Module tables migration completed!")


def downgrade():
    """降级：删除采集模块表"""
    
    # 1. 删除 collection_task_logs 表
    op.drop_table('collection_task_logs')
    print("[OK] Dropped table: collection_task_logs")
    
    # 2. 从 collection_tasks 删除新增字段
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    if 'collection_tasks' in inspector.get_table_names():
        existing_columns = [col['name'] for col in inspector.get_columns('collection_tasks')]
        
        # 删除外键
        try:
            op.drop_constraint('fk_collection_tasks_config', 'collection_tasks', type_='foreignkey')
        except:
            pass
        
        try:
            op.drop_constraint('fk_collection_tasks_parent', 'collection_tasks', type_='foreignkey')
        except:
            pass
        
        # 删除索引
        try:
            op.drop_index('ix_collection_tasks_config', 'collection_tasks')
        except:
            pass
        
        try:
            op.drop_index('ix_collection_tasks_created', 'collection_tasks')
        except:
            pass
        
        # 删除新增列
        new_columns = [
            'config_id', 'progress', 'current_step', 'files_collected',
            'trigger_type', 'data_domains', 'sub_domain', 'granularity', 'date_range',
            'error_message', 'error_screenshot_path',
            'duration_seconds', 'retry_count', 'parent_task_id',
            'verification_type', 'verification_screenshot', 'version'
        ]
        
        for col in new_columns:
            if col in existing_columns:
                op.drop_column('collection_tasks', col)
        
        print("[OK] Reverted table: collection_tasks")
    
    # 3. 删除 collection_configs 表
    op.drop_table('collection_configs')
    print("[OK] Dropped table: collection_configs")
    
    print("\n[OK] v4.6.0 Collection Module tables downgrade completed!")

