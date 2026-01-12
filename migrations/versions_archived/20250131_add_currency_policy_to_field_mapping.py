"""添加货币策略字段到字段映射辞典表

Revision ID: 20250131_add_currency_policy
Revises: 20251115_c_class_mv
Create Date: 2025-01-31

C类数据核心字段优化计划（Phase 3）：
添加currency_policy和source_priority字段到field_mapping_dictionary表
- currency_policy: 货币策略（CNY/无货币/多币种，String类型，默认NULL，可空）
- source_priority: 数据源优先级（JSON数组，JSON类型，默认NULL，可空）

向后兼容性保证：
- 新增字段必须为可空（NULL），确保现有数据不受影响
- 迁移脚本设置默认值为NULL，避免现有数据报错
- 现有代码不受影响，新字段仅用于新功能
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20250131_add_currency_policy'
down_revision = '20251115_c_class_mv'
branch_labels = None
depends_on = None


def upgrade():
    """添加货币策略字段到field_mapping_dictionary表"""
    
    # 添加currency_policy字段（货币策略）
    op.add_column(
        'field_mapping_dictionary',
        sa.Column(
            'currency_policy',
            sa.String(32),
            nullable=True,
            comment='货币策略（CNY/无货币/多币种）'
        )
    )
    
    # 添加source_priority字段（数据源优先级）
    op.add_column(
        'field_mapping_dictionary',
        sa.Column(
            'source_priority',
            postgresql.JSON(astext_type=sa.Text()),
            nullable=True,
            comment='数据源优先级（JSON数组，如["miaoshou", "shopee"]）'
        )
    )
    
    # 创建索引（可选，用于查询优化）
    op.create_index(
        'ix_dictionary_currency_policy',
        'field_mapping_dictionary',
        ['currency_policy'],
        unique=False
    )
    
    # 添加注释
    op.execute(sa.text("""
        COMMENT ON COLUMN field_mapping_dictionary.currency_policy IS 
        '货币策略（CNY/无货币/多币种）- C类数据核心字段优化计划（Phase 3）';
    """))
    
    op.execute(sa.text("""
        COMMENT ON COLUMN field_mapping_dictionary.source_priority IS 
        '数据源优先级（JSON数组，如["miaoshou", "shopee"]）- C类数据核心字段优化计划（Phase 3）';
    """))


def downgrade():
    """删除货币策略字段"""
    
    # 删除索引
    op.drop_index('ix_dictionary_currency_policy', table_name='field_mapping_dictionary')
    
    # 删除字段
    op.drop_column('field_mapping_dictionary', 'source_priority')
    op.drop_column('field_mapping_dictionary', 'currency_policy')

