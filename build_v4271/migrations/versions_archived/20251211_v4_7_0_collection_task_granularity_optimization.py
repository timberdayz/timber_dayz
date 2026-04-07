"""
v4.7.0 数据采集模块任务粒度优化

更新采集配置和任务表，支持子域数组和任务粒度优化

Revision ID: collection_task_granularity_v470
Revises: collection_module_v460
Create Date: 2025-12-11

Changes:
- CollectionConfig: sub_domain (String) → sub_domains (JSON)
- CollectionTask: sub_domain (String) → sub_domains (JSON)  
- CollectionTask: 新增 total_domains, completed_domains, failed_domains, current_domain
- CollectionTask: 新增 debug_mode（调试模式）
- CollectionTask: 状态新增 partial_success（部分成功）
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'collection_task_granularity_v470'
down_revision = 'collection_module_v460'
branch_labels = None
depends_on = None


def upgrade():
    """升级：v4.7.0 任务粒度优化"""
    
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    print("\n[START] v4.7.0 Collection Module Task Granularity Optimization")
    
    # 1. 增强 collection_configs 表
    if 'collection_configs' in inspector.get_table_names():
        existing_columns = [col['name'] for col in inspector.get_columns('collection_configs')]
        
        # sub_domain (String) → sub_domains (JSON)
        if 'sub_domain' in existing_columns:
            # 数据迁移：String → JSON 数组
            print("[INFO] Migrating sub_domain to sub_domains (collection_configs)...")
            
            # 创建新列
            op.add_column('collection_configs',
                sa.Column('sub_domains', postgresql.JSON(), nullable=True))
            
            # 迁移数据：将字符串转为单元素数组
            op.execute("""
                UPDATE collection_configs
                SET sub_domains = 
                    CASE 
                        WHEN sub_domain IS NULL THEN NULL
                        ELSE jsonb_build_array(sub_domain)
                    END
            """)
            
            # 删除旧列
            op.drop_column('collection_configs', 'sub_domain')
            
            print("[OK] Migrated sub_domain → sub_domains (collection_configs)")
        elif 'sub_domains' not in existing_columns:
            # 如果两列都不存在，创建新列
            op.add_column('collection_configs',
                sa.Column('sub_domains', postgresql.JSON(), nullable=True))
            print("[OK] Created sub_domains column (collection_configs)")
    
    # 2. 增强 collection_tasks 表
    if 'collection_tasks' in inspector.get_table_names():
        existing_columns = [col['name'] for col in inspector.get_columns('collection_tasks')]
        
        # sub_domain (String) → sub_domains (JSON)
        if 'sub_domain' in existing_columns:
            print("[INFO] Migrating sub_domain to sub_domains (collection_tasks)...")
            
            # 创建新列
            op.add_column('collection_tasks',
                sa.Column('sub_domains', postgresql.JSON(), nullable=True))
            
            # 迁移数据
            op.execute("""
                UPDATE collection_tasks
                SET sub_domains = 
                    CASE 
                        WHEN sub_domain IS NULL THEN NULL
                        ELSE jsonb_build_array(sub_domain)
                    END
            """)
            
            # 删除旧列
            op.drop_column('collection_tasks', 'sub_domain')
            
            print("[OK] Migrated sub_domain → sub_domains (collection_tasks)")
        elif 'sub_domains' not in existing_columns:
            op.add_column('collection_tasks',
                sa.Column('sub_domains', postgresql.JSON(), nullable=True))
            print("[OK] Created sub_domains column (collection_tasks)")
        
        # 新增任务粒度优化字段
        if 'total_domains' not in existing_columns:
            op.add_column('collection_tasks',
                sa.Column('total_domains', sa.Integer(), nullable=False, server_default='0'))
            print("[OK] Added total_domains column")
        
        if 'completed_domains' not in existing_columns:
            op.add_column('collection_tasks',
                sa.Column('completed_domains', postgresql.JSON(), nullable=True))
            print("[OK] Added completed_domains column")
        
        if 'failed_domains' not in existing_columns:
            op.add_column('collection_tasks',
                sa.Column('failed_domains', postgresql.JSON(), nullable=True))
            print("[OK] Added failed_domains column")
        
        if 'current_domain' not in existing_columns:
            op.add_column('collection_tasks',
                sa.Column('current_domain', sa.String(100), nullable=True))
            print("[OK] Added current_domain column")
        
        # 新增调试模式字段
        if 'debug_mode' not in existing_columns:
            op.add_column('collection_tasks',
                sa.Column('debug_mode', sa.Boolean(), nullable=False, server_default='false'))
            print("[OK] Added debug_mode column")
    
    print("\n[OK] v4.7.0 Collection Module Task Granularity Optimization completed!")
    print("[INFO] New features:")
    print("  - Sub-domain arrays (supports multiple services)")
    print("  - Task granularity: one account, all domains (browser reuse)")
    print("  - Partial success mechanism (single domain failure doesn't affect others)")
    print("  - Debug mode support (temporary headful mode in production)")


def downgrade():
    """降级：回退 v4.7.0 变更"""
    
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    print("\n[START] Downgrade v4.7.0 Collection Module Task Granularity Optimization")
    
    # 1. 回退 collection_configs 表
    if 'collection_configs' in inspector.get_table_names():
        existing_columns = [col['name'] for col in inspector.get_columns('collection_configs')]
        
        if 'sub_domains' in existing_columns:
            # 创建旧列
            op.add_column('collection_configs',
                sa.Column('sub_domain', sa.String(50), nullable=True))
            
            # 迁移数据：取数组第一个元素
            op.execute("""
                UPDATE collection_configs
                SET sub_domain = 
                    CASE 
                        WHEN sub_domains IS NULL THEN NULL
                        WHEN jsonb_array_length(sub_domains::jsonb) > 0 THEN sub_domains::jsonb->>0
                        ELSE NULL
                    END
            """)
            
            # 删除新列
            op.drop_column('collection_configs', 'sub_domains')
            
            print("[OK] Reverted sub_domains → sub_domain (collection_configs)")
    
    # 2. 回退 collection_tasks 表
    if 'collection_tasks' in inspector.get_table_names():
        existing_columns = [col['name'] for col in inspector.get_columns('collection_tasks')]
        
        # 删除调试模式字段
        if 'debug_mode' in existing_columns:
            op.drop_column('collection_tasks', 'debug_mode')
            print("[OK] Dropped debug_mode column")
        
        # 删除任务粒度优化字段
        granularity_columns = ['total_domains', 'completed_domains', 'failed_domains', 'current_domain']
        for col in granularity_columns:
            if col in existing_columns:
                op.drop_column('collection_tasks', col)
                print(f"[OK] Dropped {col} column")
        
        # sub_domains → sub_domain
        if 'sub_domains' in existing_columns:
            # 创建旧列
            op.add_column('collection_tasks',
                sa.Column('sub_domain', sa.String(50), nullable=True))
            
            # 迁移数据
            op.execute("""
                UPDATE collection_tasks
                SET sub_domain = 
                    CASE 
                        WHEN sub_domains IS NULL THEN NULL
                        WHEN jsonb_array_length(sub_domains::jsonb) > 0 THEN sub_domains::jsonb->>0
                        ELSE NULL
                    END
            """)
            
            # 删除新列
            op.drop_column('collection_tasks', 'sub_domains')
            
            print("[OK] Reverted sub_domains → sub_domain (collection_tasks)")
    
    print("\n[OK] v4.7.0 Collection Module Task Granularity Optimization downgrade completed!")

