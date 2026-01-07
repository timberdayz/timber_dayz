"""Catalog Phase1: Add B-Tree & GIN indexes and CHECK constraints

Revision ID: 20251027_0007
Revises: 20250126_0006
Create Date: 2025-10-27 20:00:00

第一阶段PostgreSQL索引与约束优化：
1. 添加 catalog_files(file_name) B-Tree 索引（毫秒级查询）
2. 添加 catalog_files(file_metadata) GIN(JSONB) 索引（如列为 JSONB）
3. 添加 catalog_files(validation_errors) GIN(JSONB) 索引
4. 添加 CHECK (date_from <= date_to) 约束
5. 添加 CHECK (status IN (...)) 约束
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '20251027_0007'
down_revision: Union[str, None] = '20250126_0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """第一阶段索引与约束优化"""
    
    # 1. B-Tree 索引：file_name（精确查询）
    op.create_index(
        'ix_catalog_files_file_name',
        'catalog_files',
        ['file_name'],
        unique=False
    )
    
    # 2. GIN 索引：file_metadata（JSONB 列，支持 JSON 查询）
    # 注意：仅当列类型为 JSONB 时创建 GIN 索引
    try:
        conn = op.get_bind()
        # 检查列类型
        result = conn.execute(sa.text("""
            SELECT data_type 
            FROM information_schema.columns 
            WHERE table_name = 'catalog_files' 
            AND column_name = 'file_metadata'
        """))
        row = result.fetchone()
        
        if row and row[0] in ('jsonb', 'json'):
            op.execute("""
                CREATE INDEX IF NOT EXISTS ix_catalog_files_file_metadata_gin 
                ON catalog_files USING gin (file_metadata)
            """)
    except Exception as e:
        print(f"跳过 file_metadata GIN 索引（可能不是 JSONB 列）: {e}")
    
    # 3. GIN 索引：validation_errors（JSONB 列）
    try:
        conn = op.get_bind()
        result = conn.execute(sa.text("""
            SELECT data_type 
            FROM information_schema.columns 
            WHERE table_name = 'catalog_files' 
            AND column_name = 'validation_errors'
        """))
        row = result.fetchone()
        
        if row and row[0] in ('jsonb', 'json'):
            op.execute("""
                CREATE INDEX IF NOT EXISTS ix_catalog_files_validation_errors_gin 
                ON catalog_files USING gin (validation_errors)
            """)
    except Exception as e:
        print(f"跳过 validation_errors GIN 索引（可能不是 JSONB 列）: {e}")
    
    # 4. CHECK 约束：date_from <= date_to
    op.create_check_constraint(
        'ck_catalog_files_date_range',
        'catalog_files',
        'date_from IS NULL OR date_to IS NULL OR date_from <= date_to'
    )
    
    # 5. CHECK 约束：status 枚举值
    op.create_check_constraint(
        'ck_catalog_files_status',
        'catalog_files',
        "status IN ('pending', 'validated', 'ingested', 'partial_success', 'failed', 'quarantined')"
    )
    
    print("✓ 第一阶段索引与约束优化完成")


def downgrade() -> None:
    """回滚索引与约束"""
    
    # 删除 CHECK 约束
    op.drop_constraint('ck_catalog_files_status', 'catalog_files', type_='check')
    op.drop_constraint('ck_catalog_files_date_range', 'catalog_files', type_='check')
    
    # 删除 GIN 索引
    try:
        op.execute("DROP INDEX IF EXISTS ix_catalog_files_validation_errors_gin")
        op.execute("DROP INDEX IF EXISTS ix_catalog_files_file_metadata_gin")
    except Exception:
        pass
    
    # 删除 B-Tree 索引
    op.drop_index('ix_catalog_files_file_name', table_name='catalog_files')
    
    print("✓ 索引与约束已回滚")

