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
    
    # 2. GIN 索引：file_metadata（仅当列类型为 JSONB 时创建）
    # [FIX] PostgreSQL GIN 索引只能用于 jsonb 类型，不能用于 json 类型
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
        
        # [FIX] 只对 jsonb 类型创建 GIN 索引，json 类型不支持 GIN
        if row and row[0] == 'jsonb':
            op.execute("""
                CREATE INDEX IF NOT EXISTS ix_catalog_files_file_metadata_gin 
                ON catalog_files USING gin (file_metadata)
            """)
            print("[OK] file_metadata GIN 索引创建成功")
        elif row and row[0] == 'json':
            print("[SKIP] file_metadata 列为 json 类型，不支持 GIN 索引（需要 jsonb 类型）")
        else:
            print(f"[SKIP] file_metadata 列类型为 {row[0] if row else 'unknown'}，跳过 GIN 索引")
    except Exception as e:
        # [FIX] 如果事务被中止，需要回滚
        try:
            conn = op.get_bind()
            conn.rollback()
        except:
            pass
        print(f"[SKIP] 跳过 file_metadata GIN 索引: {e}")
    
    # 3. GIN 索引：validation_errors（仅当列类型为 JSONB 时创建）
    # [FIX] PostgreSQL GIN 索引只能用于 jsonb 类型，不能用于 json 类型
    try:
        # [FIX] 重新获取连接，确保事务正常
        conn = op.get_bind()
        result = conn.execute(sa.text("""
            SELECT data_type 
            FROM information_schema.columns 
            WHERE table_name = 'catalog_files' 
            AND column_name = 'validation_errors'
        """))
        row = result.fetchone()
        
        # [FIX] 只对 jsonb 类型创建 GIN 索引，json 类型不支持 GIN
        if row and row[0] == 'jsonb':
            op.execute("""
                CREATE INDEX IF NOT EXISTS ix_catalog_files_validation_errors_gin 
                ON catalog_files USING gin (validation_errors)
            """)
            print("[OK] validation_errors GIN 索引创建成功")
        elif row and row[0] == 'json':
            print("[SKIP] validation_errors 列为 json 类型，不支持 GIN 索引（需要 jsonb 类型）")
        else:
            print(f"[SKIP] validation_errors 列类型为 {row[0] if row else 'unknown'}，跳过 GIN 索引")
    except Exception as e:
        # [FIX] 如果事务被中止，需要回滚
        try:
            conn = op.get_bind()
            conn.rollback()
        except:
            pass
        print(f"[SKIP] 跳过 validation_errors GIN 索引: {e}")
    
    # 4. CHECK 约束：date_from <= date_to
    # [FIX] 确保事务正常，如果之前有错误，需要重新开始
    try:
        conn = op.get_bind()
        # 测试连接是否正常
        conn.execute(sa.text("SELECT 1"))
    except Exception:
        # 如果连接异常，尝试回滚
        try:
            conn = op.get_bind()
            conn.rollback()
        except:
            pass
    
    try:
        op.create_check_constraint(
            'ck_catalog_files_date_range',
            'catalog_files',
            'date_from IS NULL OR date_to IS NULL OR date_from <= date_to'
        )
        print("[OK] CHECK 约束 ck_catalog_files_date_range 创建成功")
    except Exception as e:
        # [FIX] 如果约束已存在，跳过
        error_msg = str(e).lower()
        if 'already exists' in error_msg or 'duplicate' in error_msg:
            print("[SKIP] CHECK 约束 ck_catalog_files_date_range 已存在")
        else:
            # 其他错误需要回滚并重新抛出
            try:
                conn = op.get_bind()
                conn.rollback()
            except:
                pass
            raise
    
    # 5. CHECK 约束：status 枚举值
    try:
        op.create_check_constraint(
            'ck_catalog_files_status',
            'catalog_files',
            "status IN ('pending', 'validated', 'ingested', 'partial_success', 'failed', 'quarantined')"
        )
        print("[OK] CHECK 约束 ck_catalog_files_status 创建成功")
    except Exception as e:
        # [FIX] 如果约束已存在，跳过
        error_msg = str(e).lower()
        if 'already exists' in error_msg or 'duplicate' in error_msg:
            print("[SKIP] CHECK 约束 ck_catalog_files_status 已存在")
        else:
            # 其他错误需要回滚并重新抛出
            try:
                conn = op.get_bind()
                conn.rollback()
            except:
                pass
            raise
    
    print("[OK] 第一阶段索引与约束优化完成")


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

