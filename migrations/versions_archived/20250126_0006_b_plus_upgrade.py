"""B+ upgrade: add source_platform, sub_domain, quality_score

Revision ID: 20250126_0006
Revises: 20251023_0005
Create Date: 2025-01-26 19:30:00

方案B+架构升级：
1. 添加source_platform字段（数据来源平台，用于字段映射模板匹配）
2. 添加sub_domain字段（子数据域，如services的agent/ai_assistant）
3. 添加storage_layer字段（存储层：raw/staging/curated/quarantine）
4. 添加quality_score字段（数据质量评分0-100）
5. 添加validation_errors字段（验证错误列表）
6. 添加meta_file_path字段（伴生元数据文件路径）
7. 创建新索引（支持跨年/跨月查询）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '20250126_0006'
down_revision: Union[str, None] = '20251023_0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """升级到方案B+架构"""
    
    # 添加方案B+核心字段
    op.add_column('catalog_files',
        sa.Column('source_platform', sa.String(32), nullable=True,
                 comment='数据来源平台（用于字段映射模板匹配）'))
    
    op.add_column('catalog_files',
        sa.Column('sub_domain', sa.String(64), nullable=True,
                 comment='子数据域（如services的agent/ai_assistant）'))
    
    # 添加方案B+数据治理字段
    op.add_column('catalog_files',
        sa.Column('storage_layer', sa.String(32), nullable=True,
                 server_default='raw',
                 comment='存储层：raw/staging/curated/quarantine'))
    
    op.add_column('catalog_files',
        sa.Column('quality_score', sa.Float, nullable=True,
                 comment='数据质量评分（0-100）'))
    
    op.add_column('catalog_files',
        sa.Column('validation_errors', sa.JSON, nullable=True,
                 comment='验证错误列表'))
    
    op.add_column('catalog_files',
        sa.Column('meta_file_path', sa.String(1024), nullable=True,
                 comment='伴生元数据文件路径（.meta.json）'))
    
    # 创建新索引（方案B+关键索引）
    op.create_index('ix_catalog_source_domain', 'catalog_files',
                   ['source_platform', 'data_domain'],
                   unique=False)
    
    op.create_index('ix_catalog_sub_domain', 'catalog_files',
                   ['sub_domain'],
                   unique=False)
    
    op.create_index('ix_catalog_storage_layer', 'catalog_files',
                   ['storage_layer'],
                   unique=False)
    
    op.create_index('ix_catalog_quality_score', 'catalog_files',
                   ['quality_score'],
                   unique=False)
    
    # 数据迁移：将platform_code同步到source_platform
    op.execute("""
        UPDATE catalog_files 
        SET source_platform = platform_code 
        WHERE source_platform IS NULL
    """)


def downgrade() -> None:
    """回滚到旧架构"""
    
    # 删除索引
    op.drop_index('ix_catalog_quality_score', table_name='catalog_files')
    op.drop_index('ix_catalog_storage_layer', table_name='catalog_files')
    op.drop_index('ix_catalog_sub_domain', table_name='catalog_files')
    op.drop_index('ix_catalog_source_domain', table_name='catalog_files')
    
    # 删除字段
    op.drop_column('catalog_files', 'meta_file_path')
    op.drop_column('catalog_files', 'validation_errors')
    op.drop_column('catalog_files', 'quality_score')
    op.drop_column('catalog_files', 'storage_layer')
    op.drop_column('catalog_files', 'sub_domain')
    op.drop_column('catalog_files', 'source_platform')

