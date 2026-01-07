"""add template parsing config (header_row, sub_domain, etc.) - v4.5.1

Revision ID: 20250131_0013
Revises: 20250129_v4_4_0_finance_domain
Create Date: 2025-01-31 16:30:00

新增字段到field_mapping_templates表：
- header_row: 表头行索引（解决问题1）
- sub_domain: 子数据类型识别（解决问题2）
- sheet_name: Excel工作表名称
- encoding: 文件编码

符合企业级ERP标准：
- 向后兼容（DEFAULT值）
- 数据验证（CHECK约束）
- 审计追溯（完整记录）
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20250131_0013'
down_revision = 'v4_4_0_finance'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """升级数据库schema"""
    
    # 1. 添加新字段到field_mapping_templates表
    op.add_column('field_mapping_templates', 
                  sa.Column('sub_domain', sa.String(64), nullable=True, 
                           comment='子数据类型（如ai_assistant/agent）'))
    
    op.add_column('field_mapping_templates', 
                  sa.Column('header_row', sa.Integer(), nullable=False, 
                           server_default='0',
                           comment='表头行索引（0-based，默认0）'))
    
    op.add_column('field_mapping_templates', 
                  sa.Column('sheet_name', sa.String(128), nullable=True,
                           comment='Excel工作表名称'))
    
    op.add_column('field_mapping_templates', 
                  sa.Column('encoding', sa.String(32), nullable=False,
                           server_default='utf-8',
                           comment='文件编码（默认utf-8）'))
    
    # 2. 创建新的复合索引（包含sub_domain）
    op.create_index('ix_template_dimension_v2', 
                    'field_mapping_templates', 
                    ['platform', 'data_domain', 'sub_domain', 'granularity', 'account'])
    
    # 3. 添加CHECK约束（header_row范围验证）
    op.create_check_constraint(
        'ck_template_header_row_range',
        'field_mapping_templates',
        'header_row >= 0 AND header_row <= 100'
    )
    
    # 4. 添加注释（PostgreSQL）
    op.execute("""
        COMMENT ON COLUMN field_mapping_templates.sub_domain IS '子数据类型（如ai_assistant/agent）';
        COMMENT ON COLUMN field_mapping_templates.header_row IS '表头行索引（0-based，默认0）';
        COMMENT ON COLUMN field_mapping_templates.sheet_name IS 'Excel工作表名称';
        COMMENT ON COLUMN field_mapping_templates.encoding IS '文件编码（默认utf-8）';
    """)
    
    print("[OK] v4.5.1: field_mapping_templates表增强完成")


def downgrade() -> None:
    """回滚数据库schema（企业级标准 - 可回滚）"""
    
    # 1. 删除CHECK约束
    op.drop_constraint('ck_template_header_row_range', 'field_mapping_templates', type_='check')
    
    # 2. 删除索引
    op.drop_index('ix_template_dimension_v2', table_name='field_mapping_templates')
    
    # 3. 删除新增字段
    op.drop_column('field_mapping_templates', 'encoding')
    op.drop_column('field_mapping_templates', 'sheet_name')
    op.drop_column('field_mapping_templates', 'header_row')
    op.drop_column('field_mapping_templates', 'sub_domain')
    
    print("[OK] v4.5.1: 回滚完成")

