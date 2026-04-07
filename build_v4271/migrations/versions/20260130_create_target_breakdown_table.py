"""创建 target_breakdown 表

Revision ID: 20260130_target_breakdown
Revises: 20260130_v4_21_0_hr_module_tables
Create Date: 2026-01-30

说明:
- 创建目标分解表 target_breakdown
- 用于存储目标的店铺拆分和时间拆分配置
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import func


# revision identifiers, used by Alembic.
revision = '20260130_target_breakdown'
down_revision = '20260130_hr_module'  # 指向最新的迁移
branch_labels = None
depends_on = None


def safe_print(msg: str):
    """安全打印（避免 Windows 终端 Unicode 错误）"""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("utf-8", errors="replace").decode("utf-8"))


def table_exists(conn, table_name: str, schema: str = "public") -> bool:
    """检查表是否存在"""
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = :schema AND table_name = :table
        )
    """), {"schema": schema, "table": table_name})
    return result.scalar()


def upgrade():
    """创建 target_breakdown 表（a_class schema，与 ORM 及后续迁移一致）"""
    conn = op.get_bind()

    # 确保 a_class schema 存在（自包含，不依赖迁移顺序）
    conn.execute(sa.text("CREATE SCHEMA IF NOT EXISTS a_class"))

    # 检查表是否已存在（a_class）
    if table_exists(conn, "target_breakdown", "a_class"):
        safe_print("[INFO] a_class.target_breakdown 表已存在，跳过创建")
        return

    safe_print("[INFO] 创建 a_class.target_breakdown 表...")

    # 创建表于 a_class（此时 sales_targets 仍在 public，由 20260131 迁至 a_class）
    op.create_table(
        'target_breakdown',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('target_id', sa.Integer(), nullable=False),
        sa.Column('breakdown_type', sa.String(length=32), nullable=False, comment="分解类型:shop/time"),
        sa.Column('platform_code', sa.String(length=32), nullable=True),
        sa.Column('shop_id', sa.String(length=64), nullable=True),
        sa.Column('period_start', sa.Date(), nullable=True, comment="周期开始"),
        sa.Column('period_end', sa.Date(), nullable=True, comment="周期结束"),
        sa.Column('period_label', sa.String(length=64), nullable=True, comment="周期标签"),
        sa.Column('target_amount', sa.Float(), nullable=False, default=0.0, comment="目标销售额(CNY)"),
        sa.Column('target_quantity', sa.Integer(), nullable=False, default=0, comment="目标订单数"),
        sa.Column('achieved_amount', sa.Float(), nullable=False, default=0.0, comment="实际销售额(CNY)"),
        sa.Column('achieved_quantity', sa.Integer(), nullable=False, default=0, comment="实际订单数"),
        sa.Column('achievement_rate', sa.Float(), nullable=False, default=0.0, comment="达成率"),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['target_id'], ['public.sales_targets.id'], ondelete='CASCADE'),
        sa.CheckConstraint("breakdown_type IN ('shop', 'time')", name='chk_breakdown_type'),
        schema='a_class',
    )

    # 创建索引（a_class）
    op.create_index('ix_target_breakdown_target', 'target_breakdown', ['target_id'], schema='a_class')
    op.create_index('ix_target_breakdown_type', 'target_breakdown', ['breakdown_type'], schema='a_class')
    op.create_index('ix_target_breakdown_shop', 'target_breakdown', ['platform_code', 'shop_id'], schema='a_class')

    safe_print("[OK] a_class.target_breakdown 表创建成功")


def downgrade():
    """删除 a_class.target_breakdown 表"""
    conn = op.get_bind()

    if not table_exists(conn, "target_breakdown", "a_class"):
        safe_print("[INFO] a_class.target_breakdown 表不存在，跳过删除")
        return

    # 删除索引（a_class）
    op.drop_index('ix_target_breakdown_shop', table_name='target_breakdown', schema='a_class')
    op.drop_index('ix_target_breakdown_type', table_name='target_breakdown', schema='a_class')
    op.drop_index('ix_target_breakdown_target', table_name='target_breakdown', schema='a_class')

    # 删除表
    op.drop_table('target_breakdown', schema='a_class')
    safe_print("[OK] a_class.target_breakdown 表已删除")
