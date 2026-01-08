"""add_security_config_table

Revision ID: v4_20_0_security_config
Revises: v4_20_0_system_logs
Create Date: 2026-01-08

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'v4_20_0_security_config'
down_revision = 'v4_20_0_system_logs'
branch_labels = None
depends_on = None


def upgrade():
    # 创建安全配置表
    op.create_table(
        'security_config',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('config_key', sa.String(length=64), nullable=False),
        sa.Column('config_value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['updated_by'], ['dim_users.user_id'], name='fk_security_config_updated_by'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('config_key', name='uq_security_config_key')
    )
    
    # 创建索引
    op.create_index('ix_security_config_key', 'security_config', ['config_key'])


def downgrade():
    # 删除索引
    op.drop_index('ix_security_config_key', table_name='security_config')
    
    # 删除表
    op.drop_table('security_config')
