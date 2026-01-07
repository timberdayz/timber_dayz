"""
添加field_usage_tracking表

Revision ID: add_field_usage_tracking
Revises: 最新版本
Create Date: 2025-11-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'add_field_usage_tracking'
down_revision = None  # 将被Alembic自动设置
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'field_usage_tracking',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('table_name', sa.String(length=64), nullable=False, comment='数据库表名'),
        sa.Column('field_name', sa.String(length=128), nullable=False, comment='数据库字段名'),
        sa.Column('api_endpoint', sa.String(length=256), nullable=True, comment='API端点'),
        sa.Column('api_param', sa.String(length=64), nullable=True, comment='API参数名'),
        sa.Column('api_file', sa.String(length=256), nullable=True, comment='API路由文件路径'),
        sa.Column('frontend_component', sa.String(length=256), nullable=True, comment='前端组件'),
        sa.Column('frontend_param', sa.String(length=128), nullable=True, comment='前端参数'),
        sa.Column('frontend_file', sa.String(length=256), nullable=True, comment='前端组件文件路径'),
        sa.Column('usage_type', sa.String(length=32), nullable=False, comment='使用类型'),
        sa.Column('source_type', sa.String(length=32), nullable=False, server_default='scanned', comment='来源类型'),
        sa.Column('code_snippet', sa.Text(), nullable=True, comment='代码片段'),
        sa.Column('line_number', sa.Integer(), nullable=True, comment='行号'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('created_by', sa.String(length=64), nullable=False, server_default='scanner'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('table_name', 'field_name', 'api_endpoint', 'frontend_component', name='uq_field_usage')
    )
    
    op.create_index('idx_usage_field', 'field_usage_tracking', ['table_name', 'field_name'])
    op.create_index('idx_usage_api', 'field_usage_tracking', ['api_endpoint'])
    op.create_index('idx_usage_frontend', 'field_usage_tracking', ['frontend_component'])
    op.create_index('idx_usage_type', 'field_usage_tracking', ['usage_type'])


def downgrade():
    op.drop_index('idx_usage_type', table_name='field_usage_tracking')
    op.drop_index('idx_usage_frontend', table_name='field_usage_tracking')
    op.drop_index('idx_usage_api', table_name='field_usage_tracking')
    op.drop_index('idx_usage_field', table_name='field_usage_tracking')
    op.drop_table('field_usage_tracking')

