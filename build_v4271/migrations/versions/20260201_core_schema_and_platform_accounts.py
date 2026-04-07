"""Create core schema and move platform_accounts / performance_scores_c to correct schema

Revision ID: 20260201_core_platform
Revises: 20260131_ym
Create Date: 2026-02-01

Description:
- schema.py 定义 platform_accounts 在 core schema、performance_scores_c 在 c_class schema，
  但快照迁移在 public 下创建，且 20260127 只迁移了 performance_scores_c 到 c_class，未处理 platform_accounts。
- 本迁移：创建 core schema；将 public.platform_accounts 移至 core；将 public.performance_scores_c 移至 c_class（若仍在 public）。
"""

from alembic import op
from sqlalchemy import text


revision = '20260201_core_platform'
down_revision = '20260131_ym'
branch_labels = None
depends_on = None


def safe_print(msg):
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        try:
            print(msg.encode('gbk', errors='ignore').decode('gbk'), flush=True)
        except Exception:
            print(msg.encode('ascii', errors='ignore').decode('ascii'), flush=True)


def table_exists(conn, table_name: str, schema: str = 'public') -> bool:
    r = conn.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = :schema AND table_name = :t
        )
    """), {"schema": schema, "t": table_name})
    return r.scalar() or False


def upgrade():
    conn = op.get_bind()

    # 1. 创建 core schema（schema.py 中 platform_accounts 在 core）
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS core"))
    safe_print("[OK] core schema ensured")

    # 2. public.platform_accounts -> core.platform_accounts
    if table_exists(conn, 'platform_accounts', 'public') and not table_exists(conn, 'platform_accounts', 'core'):
        conn.execute(text('ALTER TABLE public.platform_accounts SET SCHEMA core'))
        safe_print("[OK] public.platform_accounts moved to core.platform_accounts")
    elif table_exists(conn, 'platform_accounts', 'core'):
        safe_print("[SKIP] core.platform_accounts already exists")
    else:
        safe_print("[SKIP] public.platform_accounts not found (will be created by ORM/snapshot if needed)")

    # 3. public.performance_scores_c -> c_class.performance_scores_c（若 20260127 未执行或表仍在 public）
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS c_class"))
    if table_exists(conn, 'performance_scores_c', 'public') and not table_exists(conn, 'performance_scores_c', 'c_class'):
        conn.execute(text('ALTER TABLE public.performance_scores_c SET SCHEMA c_class'))
        safe_print("[OK] public.performance_scores_c moved to c_class.performance_scores_c")
    elif table_exists(conn, 'performance_scores_c', 'c_class'):
        safe_print("[SKIP] c_class.performance_scores_c already exists")
    else:
        safe_print("[SKIP] public.performance_scores_c not found (will be created by ORM/snapshot if needed)")


def downgrade():
    conn = op.get_bind()
    # 回滚：移回 public（仅当表存在时）
    if table_exists(conn, 'platform_accounts', 'core'):
        conn.execute(text('ALTER TABLE core.platform_accounts SET SCHEMA public'))
        safe_print("[OK] core.platform_accounts moved back to public")
    if table_exists(conn, 'performance_scores_c', 'c_class'):
        conn.execute(text('ALTER TABLE c_class.performance_scores_c SET SCHEMA public'))
        safe_print("[OK] c_class.performance_scores_c moved back to public")
    # 不 DROP SCHEMA core，可能还有其他对象
    safe_print("[INFO] core schema left in place (manual DROP if needed)")
