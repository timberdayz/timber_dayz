"""添加用户状态同步触发器

Revision ID: 20260104_user_status_trigger
Revises: 20260104_user_approval_logs
Create Date: 2026-01-04

创建数据库触发器，确保status和is_active字段自动同步
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = '20260104_user_status_trigger'
down_revision = '20260104_user_approval_logs'
branch_labels = None
depends_on = None


def upgrade():
    """创建状态同步触发器"""
    # 创建触发器函数
    op.execute("""
        CREATE OR REPLACE FUNCTION sync_user_status()
        RETURNS TRIGGER AS $$
        BEGIN
            IF NEW.status = 'active' THEN
                NEW.is_active = true;
            ELSE
                NEW.is_active = false;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    # 创建触发器
    op.execute("""
        CREATE TRIGGER trigger_sync_user_status
        BEFORE INSERT OR UPDATE ON dim_users
        FOR EACH ROW
        EXECUTE FUNCTION sync_user_status();
    """)


def downgrade():
    """删除状态同步触发器"""
    op.execute("DROP TRIGGER IF EXISTS trigger_sync_user_status ON dim_users;")
    op.execute("DROP FUNCTION IF EXISTS sync_user_status();")

