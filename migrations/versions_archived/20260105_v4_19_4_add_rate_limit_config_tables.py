"""v4.19.4: 添加限流配置表

Revision ID: v4_19_4_rate_limit_config
Revises: 20260105_create_user_sessions_table
Create Date: 2026-01-05

用途：
- 创建限流配置维度表（DimRateLimitConfig）
- 创建限流配置审计日志表（FactRateLimitConfigAudit）
- 支持基于角色的限流配置动态管理（Phase 3）
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from datetime import datetime

# revision identifiers, used by Alembic.
revision = 'v4_19_4_rate_limit_config'
down_revision = '20260105_user_sessions'
branch_labels = None
depends_on = None


def upgrade():
    """创建限流配置表和审计表"""
    
    # 创建限流配置维度表
    op.create_table(
        'dim_rate_limit_config',
        sa.Column('config_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('role_code', sa.String(length=50), nullable=False),
        sa.Column('endpoint_type', sa.String(length=50), nullable=False),
        sa.Column('limit_value', sa.String(length=50), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('updated_by', sa.String(length=100), nullable=True),
        sa.PrimaryKeyConstraint('config_id'),
        sa.UniqueConstraint('role_code', 'endpoint_type', name='uq_rate_limit_config_role_endpoint')
    )
    
    # 创建索引
    op.create_index('ix_rate_limit_config_active', 'dim_rate_limit_config', ['is_active', 'role_code'])
    op.create_index('ix_rate_limit_config_role', 'dim_rate_limit_config', ['role_code', 'endpoint_type'])
    op.create_index('ix_dim_rate_limit_config_role_code', 'dim_rate_limit_config', ['role_code'], unique=False)
    op.create_index('ix_dim_rate_limit_config_endpoint_type', 'dim_rate_limit_config', ['endpoint_type'], unique=False)
    
    # 创建限流配置审计日志表
    op.create_table(
        'fact_rate_limit_config_audit',
        sa.Column('audit_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('config_id', sa.Integer(), nullable=True),
        sa.Column('role_code', sa.String(length=50), nullable=False),
        sa.Column('endpoint_type', sa.String(length=50), nullable=False),
        sa.Column('action_type', sa.String(length=50), nullable=False),
        sa.Column('old_limit_value', sa.String(length=50), nullable=True),
        sa.Column('new_limit_value', sa.String(length=50), nullable=True),
        sa.Column('old_is_active', sa.Boolean(), nullable=True),
        sa.Column('new_is_active', sa.Boolean(), nullable=True),
        sa.Column('operator_id', sa.BigInteger(), nullable=True),
        sa.Column('operator_username', sa.String(length=100), nullable=False),
        sa.Column('ip_address', sa.String(length=50), nullable=True),
        sa.Column('user_agent', sa.String(length=500), nullable=True),
        sa.Column('is_success', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('audit_id'),
        sa.ForeignKeyConstraint(['config_id'], ['dim_rate_limit_config.config_id'], name='fk_rate_limit_audit_config'),
        sa.ForeignKeyConstraint(['operator_id'], ['dim_users.user_id'], name='fk_rate_limit_audit_operator')
    )
    
    # 创建审计表索引
    op.create_index('idx_rate_limit_audit_config', 'fact_rate_limit_config_audit', ['config_id', 'created_at'])
    op.create_index('idx_rate_limit_audit_role', 'fact_rate_limit_config_audit', ['role_code', 'endpoint_type', 'created_at'])
    op.create_index('idx_rate_limit_audit_operator', 'fact_rate_limit_config_audit', ['operator_id', 'created_at'])
    op.create_index('idx_rate_limit_audit_action', 'fact_rate_limit_config_audit', ['action_type', 'created_at'])
    op.create_index('ix_fact_rate_limit_config_audit_audit_id', 'fact_rate_limit_config_audit', ['audit_id'], unique=False)
    op.create_index('ix_fact_rate_limit_config_audit_role_code', 'fact_rate_limit_config_audit', ['role_code'], unique=False)
    op.create_index('ix_fact_rate_limit_config_audit_endpoint_type', 'fact_rate_limit_config_audit', ['endpoint_type'], unique=False)
    op.create_index('ix_fact_rate_limit_config_audit_created_at', 'fact_rate_limit_config_audit', ['created_at'], unique=False)


def downgrade():
    """删除限流配置表和审计表"""
    
    # 删除审计表（先删除，因为有外键依赖）
    op.drop_index('ix_fact_rate_limit_config_audit_created_at', table_name='fact_rate_limit_config_audit')
    op.drop_index('ix_fact_rate_limit_config_audit_endpoint_type', table_name='fact_rate_limit_config_audit')
    op.drop_index('ix_fact_rate_limit_config_audit_role_code', table_name='fact_rate_limit_config_audit')
    op.drop_index('ix_fact_rate_limit_config_audit_audit_id', table_name='fact_rate_limit_config_audit')
    op.drop_index('idx_rate_limit_audit_action', table_name='fact_rate_limit_config_audit')
    op.drop_index('idx_rate_limit_audit_operator', table_name='fact_rate_limit_config_audit')
    op.drop_index('idx_rate_limit_audit_role', table_name='fact_rate_limit_config_audit')
    op.drop_index('idx_rate_limit_audit_config', table_name='fact_rate_limit_config_audit')
    op.drop_table('fact_rate_limit_config_audit')
    
    # 删除配置表
    op.drop_index('ix_dim_rate_limit_config_endpoint_type', table_name='dim_rate_limit_config')
    op.drop_index('ix_dim_rate_limit_config_role_code', table_name='dim_rate_limit_config')
    op.drop_index('ix_rate_limit_config_role', table_name='dim_rate_limit_config')
    op.drop_index('ix_rate_limit_config_active', table_name='dim_rate_limit_config')
    op.drop_table('dim_rate_limit_config')

