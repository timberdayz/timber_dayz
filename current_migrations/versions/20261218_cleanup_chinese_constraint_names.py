"""清理中文命名的约束（与英文唯一约束重复的那一个直接删掉，其余改名）。

背景
----
``a_class.operating_costs`` 上有**两个**完全相同的唯一约束：

    operating_costs_店铺ID_年月_key   UNIQUE (shop_id, year_month)   ← 中文名，历史遗留
    uq_operating_costs_shop_month    UNIQUE (shop_id, year_month)   ← 英文名，当前 SSOT

当初列名从中文改成英文时新建了英文约束，**旧的中文约束没删**，
于是同一张表上挂了两份一模一样的唯一键：

* 建表语句报错信息指向中文名，看不出真正生效的是哪一条；
* 任何「按约束名做幂等写入」的工具都会以为两个名字是两个对象；
* 中文名在英文工具链（pg_dump、schema diff、BI 工具）里处处需要转义。

处理方式
--------
* ``operating_costs_店铺ID_年月_key`` —— **直接删除**。
  它与 ``uq_operating_costs_shop_month`` 列集合、唯一性完全一致，
  删掉不丢任何约束语义（数据本来就被同列唯一约束挡着）。
* ``employees_员工编号_key`` —— **改名**为 ``uq_employees_employee_code``。
  它是 ``a_class.employees.employee_code`` 的唯一约束，列名本来就是英文，
  只是约束名留了中文，改名即可。

刻意不在本迁移里动的
--------------------
``a_class.attendance_records`` 的 ``attendance_records_员工编号_考勤日期_key``：
这张表**整张表的中文列都还没改名**（``员工编号`` / ``考勤日期`` / ``上班时间`` …），
ORM 里却是英文列 —— 是另一件事（考勤模块的表结构与 ORM 没对齐），
光改约束名会掩盖真正的问题。留到考勤模块单独立项处理，
本迁移只打印提示，不擅自改它的列。

安全性
------
* 删的是**重复**约束，不是唯一约束 ⇒ 不会放宽任何写入约束；
* 改名不改变列集合与唯一性 ⇒ 索引行为不变；
* 所有操作都是幂等的（``IF EXISTS`` + 先查后改）。
"""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261218_cleanup_chinese_constraint_names"
down_revision = "current_schema_20261217_rename_labor_cost_allocation_version"
branch_labels = None
depends_on = None


#: 表 → 约束名 → (新名字, 是否是重复约束)
CONSTRAINT_RENAMES = {
    "a_class.employees": ("employees_员工编号_key", "uq_employees_employee_code"),
}

#: 重复约束 → 直接删除
DROP_CONSTRAINTS = (
    ("a_class.operating_costs", "operating_costs_店铺ID_年月_key"),
)


def _constraint_exists(table: str, name: str) -> bool:
    """``table`` 形如 ``a_class.employees``（带 schema 前缀）。"""
    row = (
        op.get_bind()
        .execute(
            sa.text(
                """
                SELECT 1
                  FROM pg_constraint con
                  JOIN pg_class c ON c.oid = con.conrelid
                  JOIN pg_namespace n ON n.oid = c.relnamespace
                 WHERE n.nspname || '.' || c.relname = :table
                   AND con.conname = :name
                """
            ),
            {"table": table, "name": name},
        )
        .fetchone()
    )
    return row is not None


def _index_exists(name: str) -> bool:
    row = (
        op.get_bind()
        .execute(
            sa.text("SELECT 1 FROM pg_indexes WHERE indexname = :name"),
            {"name": name},
        )
        .fetchone()
    )
    return row is not None


def _remaining_chinese_constraints() -> list[str]:
    rows = (
        op.get_bind()
        .execute(
            sa.text(
                """
                SELECT n.nspname || '.' || c.relname || '.' || con.conname
                  FROM pg_constraint con
                  JOIN pg_class c ON c.oid = con.conrelid
                  JOIN pg_namespace n ON n.oid = c.relnamespace
                 WHERE con.conname ~ '[^\\x00-\\x7F]'
                 ORDER BY 1
                """
            )
        )
        .fetchall()
    )
    return [row[0] for row in rows]


def upgrade() -> None:
    for table, name in DROP_CONSTRAINTS:
        if not _constraint_exists(table, name):
            continue
        op.execute(f'ALTER TABLE {table} DROP CONSTRAINT "{name}"')
        print(f"[INFO] 删除重复约束：{table}.{name}")

    for table, (old_name, new_name) in CONSTRAINT_RENAMES.items():
        if not _constraint_exists(table, old_name):
            continue
        op.execute(
            f'ALTER TABLE {table} RENAME CONSTRAINT "{old_name}" TO "{new_name}"'
        )
        print(f"[INFO] 约束改名：{table}.{old_name} → {new_name}")
        # 唯一约束背后的索引名可能仍是旧名，一并改掉，免得索引名继续带中文
        if _index_exists(old_name):
            op.execute(f'ALTER INDEX "{old_name}" RENAME TO "{new_name}"')
            print(f"[INFO] 索引改名：{old_name} → {new_name}")

    remaining = _remaining_chinese_constraints()
    if remaining:
        print(
            "[WARN] 仍有中文命名的约束（属考勤模块表结构未对齐，单独立项处理）："
            + ", ".join(remaining)
        )


def downgrade() -> None:
    for table, (old_name, new_name) in CONSTRAINT_RENAMES.items():
        if not _constraint_exists(table, new_name):
            continue
        op.execute(
            f'ALTER TABLE {table} RENAME CONSTRAINT "{new_name}" TO "{old_name}"'
        )
        if _index_exists(new_name):
            op.execute(f'ALTER INDEX "{new_name}" RENAME TO "{old_name}"')

    for table, name in DROP_CONSTRAINTS:
        if _constraint_exists(table, name):
            continue
        op.execute(
            f'ALTER TABLE {table} ADD CONSTRAINT "{name}" UNIQUE (shop_id, year_month)'
        )
