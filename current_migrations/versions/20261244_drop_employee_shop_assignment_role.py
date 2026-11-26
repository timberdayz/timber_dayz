"""退休「员工店铺归属」的角色字段（supervisor/operator）。

背景
----
系统里有两个都叫「角色」的东西，本迁移**只**动第 2 个：

* ✅ **访问权限角色**（admin/manager/operator/finance，存在 ``core.dim_users.roles``、
  ``backend/dependencies/auth.py`` 的 ``require_admin`` / ``get_current_user``、
  路由 ``meta.roles``）—— **一行不动**；
* ❌ **归属角色**（``a_class.employee_shop_assignments.role``）—— 本批次彻底删除。

业务已确认（2026-11-26）：

* 归属配置只回答「**谁在这家店分多少提成**」：一行 = 人 × 平台 × 店 × 月 × 提成比；
* 现实是一店可以同时有主管、两个总经理、操作员一起吃提成
  ⇒ **不存在「一店一主管」约束**，本迁移**不新增任何角色唯一性校验**；
* 店铺当月在职人员提成比例合计 ≤ 100% 的口径**不变**（本来就按店铺聚合）；
* 提成金额口径「可分配利润 × 归属提成比（零系数）」**不变** ⇒ 钱一分不变。

本迁移做两件事
--------------
1. 删掉 ``a_class.employee_shop_assignments.role``（归属表上的「角色」列）；
2. 删掉 ``a_class.personal_performance_assignment_snapshots.role_snapshot``
   （绩效工作台留痕快照里的归属角色留痕）。

⚠️ 为什么连快照列一起删
----------------------
``role_snapshot`` 是归属角色的**第三处下游**（唯一读者是「我的收入审计」接口，
而它只是把角色原样回显，前端根本不展示）。
归属角色退休后它永远只可能是 NULL ⇒ 留着是一列没有读者的死结构。
该列**可空**（``nullable=True``，见 ``modules/core/db/schema_parts/business.py``）
⇒ 直接删列即可，不需要先洗数据。

影响面
------
* **读**：``/api/hr/employee-shop-assignments`` 的响应不再有 ``role``；
* **写**：请求体里仍带 ``role``（旧页面）会被**忽略**而不是报错；
* **金额**：提成计算链路（``commission_caliber`` /
  ``hr_income_calculation_service``）从不按角色分流 ⇒ 金额口径与结果**完全不变**；
* **任务**：「每月成本录入任务」依赖 ``role == "supervisor"`` 判定店主，
  已随本批次整条下线（代码改动先于本迁移上线）。

可逆性
------
**可逆**：downgrade 会把两列**按原样加回来**（都是可空列），
schema 与迁移链都能回滚。
⚠️ 但**历史值找不回来**：被删两列里的旧数据（``supervisor`` / ``operator`` 文字）
无法恢复 —— 归属角色已退休，恢复它没有业务意义。
数据可恢复性由发版流程自带的迁移前备份（``perform_pre_migration_backup``）兜底。
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261244_drop_employee_shop_assignment_role"
down_revision = "current_schema_20261243_drop_legacy_profit_basis"
branch_labels = None
depends_on = None


ACLASS_SCHEMA = "a_class"

#: 归属表：删掉「角色」列。
ASSIGNMENT_TABLE = "employee_shop_assignments"
ASSIGNMENT_ROLE_COLUMN = "role"

#: 绩效工作台的归属快照表：删掉「角色」留痕列。
SNAPSHOT_TABLE = "personal_performance_assignment_snapshots"
SNAPSHOT_ROLE_COLUMN = "role_snapshot"

#: downgrade 时加回两列用的类型 —— 与被删前**完全一致**（都是可空 varchar(32)）。
COLUMN_DEFINITION = "character varying(32)"


def _has_table(schema: str, table: str) -> bool:
    """表是否已存在（幂等的前提：缺表要安全跳过）。"""
    inspector = sa.inspect(op.get_bind())
    return inspector.has_table(table, schema=schema)


def _has_column(schema: str, table: str, column: str) -> bool:
    """列是否已存在（缺列要安全跳过）。"""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table, schema=schema):
        return False
    return any(
        col["name"] == column for col in inspector.get_columns(table, schema=schema)
    )


def _is_nullable(schema: str, table: str, column: str) -> bool:
    """列是否可空（默认按可空处理：拿不到就当可空，不做多余的数据清洗）。"""
    inspector = sa.inspect(op.get_bind())
    for col in inspector.get_columns(table, schema=schema):
        if col["name"] == column:
            return bool(col.get("nullable", True))
    return True


def upgrade() -> None:
    """删掉归属表与归属快照表上的「角色」列。"""
    bind = op.get_bind()

    if _has_table(ACLASS_SCHEMA, ASSIGNMENT_TABLE) and _has_column(
        ACLASS_SCHEMA, ASSIGNMENT_TABLE, ASSIGNMENT_ROLE_COLUMN
    ):
        bind.execute(
            sa.text(
                f"ALTER TABLE {ACLASS_SCHEMA}.{ASSIGNMENT_TABLE} "
                f"DROP COLUMN IF EXISTS {ASSIGNMENT_ROLE_COLUMN}"
            )
        )
        print("[20261244] 已删除归属表的角色列 employee_shop_assignments.role")

    if _has_table(ACLASS_SCHEMA, SNAPSHOT_TABLE) and _has_column(
        ACLASS_SCHEMA, SNAPSHOT_TABLE, SNAPSHOT_ROLE_COLUMN
    ):
        if not _is_nullable(ACLASS_SCHEMA, SNAPSHOT_TABLE, SNAPSHOT_ROLE_COLUMN):
            # 理论上不会走到（当前是可空列）⇒ 万一不可空，先置 NULL 再删，
            # 不留「有行但列没了」的坏数据。
            bind.execute(
                sa.text(
                    f"UPDATE {ACLASS_SCHEMA}.{SNAPSHOT_TABLE} "
                    f"SET {SNAPSHOT_ROLE_COLUMN} = NULL "
                    f"WHERE {SNAPSHOT_ROLE_COLUMN} IS NOT NULL"
                )
            )
        bind.execute(
            sa.text(
                f"ALTER TABLE {ACLASS_SCHEMA}.{SNAPSHOT_TABLE} "
                f"DROP COLUMN IF EXISTS {SNAPSHOT_ROLE_COLUMN}"
            )
        )
        print("[20261244] 已删除绩效快照的角色留痕列 role_snapshot")


def downgrade() -> None:
    """把两列按原样加回来（可空）—— schema 可回滚，历史角色文字找不回来。"""
    bind = op.get_bind()

    if _has_table(ACLASS_SCHEMA, ASSIGNMENT_TABLE) and not _has_column(
        ACLASS_SCHEMA, ASSIGNMENT_TABLE, ASSIGNMENT_ROLE_COLUMN
    ):
        bind.execute(
            sa.text(
                f"ALTER TABLE {ACLASS_SCHEMA}.{ASSIGNMENT_TABLE} "
                f"ADD COLUMN IF NOT EXISTS {ASSIGNMENT_ROLE_COLUMN} {COLUMN_DEFINITION}"
            )
        )
        print("[20261244] 已加回归属表的角色列 employee_shop_assignments.role")

    if _has_table(ACLASS_SCHEMA, SNAPSHOT_TABLE) and not _has_column(
        ACLASS_SCHEMA, SNAPSHOT_TABLE, SNAPSHOT_ROLE_COLUMN
    ):
        bind.execute(
            sa.text(
                f"ALTER TABLE {ACLASS_SCHEMA}.{SNAPSHOT_TABLE} "
                f"ADD COLUMN IF NOT EXISTS {SNAPSHOT_ROLE_COLUMN} {COLUMN_DEFINITION}"
            )
        )
        print("[20261244] 已加回绩效快照的角色留痕列 role_snapshot")
