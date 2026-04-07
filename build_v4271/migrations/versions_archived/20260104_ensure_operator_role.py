"""确保operator角色存在

Revision ID: 20260104_operator_role
Revises: 20260104_user_status_trigger
Create Date: 2026-01-04

确保operator角色存在，用于新用户审批时的默认角色分配
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260104_operator_role'
down_revision = '20260104_user_status_trigger'
branch_labels = None
depends_on = None


def upgrade():
    """插入operator角色（如果不存在）"""
    # 检查并插入operator角色
    op.execute("""
        INSERT INTO dim_roles (role_code, role_name, description, is_active, permissions, data_scope, is_system)
        SELECT 
            'operator',
            '运营人员',
            '默认运营角色，用于新用户审批',
            true,
            '[]',
            'all',
            false
        WHERE NOT EXISTS (
            SELECT 1 FROM dim_roles WHERE role_code = 'operator'
        );
    """)


def downgrade():
    """移除operator角色（可选，通常不执行）"""
    # 注意：通常不删除角色，因为可能已有用户使用
    # 如果需要删除，取消注释以下代码
    # op.execute("DELETE FROM dim_roles WHERE role_code = 'operator' AND is_system = false;")
    pass

