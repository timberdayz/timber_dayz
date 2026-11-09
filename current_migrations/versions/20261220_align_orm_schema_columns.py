"""对齐 ORM 与数据库之间的列结构漂移（9 张表）。

背景
----
ORM(``modules/core/db/schema.py``)与真实库之间存在**列结构漂移**：
ORM 声明的列在库里不存在（有的表库里还留着中文列名），
代码一用到就抛 ``UndefinedColumnError``，现场表现为

    /api/hr/attendance                500
    /api/inventory/ledger             500
    /api/inventory/opening-balances   500
    /api/management/data-records       500

这类漂移的根本问题是「同一张表的结构有两份真相」，
ORM 一份、数据库一份，谁都不校验对方，于是漂移可以一直存在。

处理原则（SSOT）
----------------
1. **ORM 列名是 SSOT**（AGENTS.md 规定）⇒ 库里缺的列补到库里；
   库里是中文列名的，改成 ORM 的英文字段名。
2. **例外**：当代码**正在使用**库里独有、而 ORM 缺失的列时
   （``DataRecord.quality_score`` 等），以库为准补齐 ORM ——
   否则改库只会把「代码用不到」的问题换个方向再犯一次。

涉及的两张表走例外（改 ORM 而不是改库）：

* ``core.data_records`` —— 代码在用 ``quality_score``，
  且 ``docker/postgres/init-tables.py`` 也是按库里那套结构写的。
* ``core.accounts`` —— ORM 的 ``account_name/account_id`` 与库里的
  ``username/password/login_url`` **同名不同义**；
  ``docker/postgres/init-tables.py`` 同样按库里那套写的。

幂等
----
所有改名/加列都先判断列是否存在，因此本迁移可重复执行。
"""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261220_align_orm_schema_columns"
down_revision = "current_schema_20261219_annotate_target_profit_columns"
branch_labels = None
depends_on = None


#: 表 -> [(库里旧列名, ORM 列名)]
#: 库里是中文列名，ORM 是英文字段名 —— 改成 ORM 的写法。
COLUMN_RENAMES = {
    "a_class.attendance_records": [
        ("员工编号", "employee_code"),
        ("考勤日期", "attendance_date"),
        ("上班时间", "clock_in_time"),
        ("下班时间", "clock_out_time"),
        ("工作时长", "work_hours"),
        ("状态", "status"),
        ("创建时间", "created_at"),
        ("更新时间", "updated_at"),
    ],
    "a_class.sales_campaigns_a": [
        ("战役名称", "campaign_name"),
        ("战役类型", "campaign_type"),
        ("开始日期", "start_date"),
        ("结束日期", "end_date"),
        ("目标销售额", "target_amount"),
        ("目标订单数", "target_quantity"),
        ("状态", "status"),
        ("描述", "description"),
        ("创建人", "created_by"),
        ("创建时间", "created_at"),
        ("更新时间", "updated_at"),
    ],
}

#: 表 -> [(列名, DDL 片段)]
#: ORM 有、库里没有的列 —— 补到库里。
ADD_COLUMNS = {
    "finance.inventory_ledger": [
        ("received_date", "DATE"),
        ("opening_age_days", "INTEGER"),
    ],
    "finance.opening_balances": [
        ("received_date", "DATE"),
        ("opening_age_days", "INTEGER"),
    ],
    "core.field_mapping_dictionary": [
        ("is_pattern_based", "BOOLEAN NOT NULL DEFAULT FALSE"),
        ("field_pattern", "TEXT"),
        ("dimension_config", "JSON"),
        ("target_table", "VARCHAR(64)"),
        ("target_columns", "JSON"),
        ("is_mv_display", "BOOLEAN NOT NULL DEFAULT FALSE"),
        ("currency_policy", "VARCHAR(32)"),
        ("source_priority", "JSON"),
    ],
    "core.mapping_sessions": [
        ("session_id", "VARCHAR(100) NOT NULL DEFAULT ''"),
        ("domain", "VARCHAR(50)"),
    ],
    "core.data_files": [
        ("data_type", "VARCHAR(50) NOT NULL DEFAULT ''"),
        ("status", "VARCHAR(50) NOT NULL DEFAULT 'registered'"),
        (
            "discovery_time",
            "TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP",
        ),
    ],
}


def _table_exists(table: str) -> bool:
    row = (
        op.get_bind()
        .execute(sa.text("SELECT to_regclass(:name)"), {"name": table})
        .scalar_one_or_none()
    )
    return row is not None


def _column_exists(table: str, column: str) -> bool:
    row = (
        op.get_bind()
        .execute(
            sa.text(
                """
                SELECT 1
                  FROM information_schema.columns
                 WHERE table_schema = :schema
                   AND table_name = :table
                   AND column_name = :column
                """
            ),
            {
                "schema": table.split(".", 1)[0],
                "table": table.split(".", 1)[1],
                "column": column,
            },
        )
        .fetchone()
    )
    return row is not None


def _split(table: str) -> tuple[str, str]:
    schema, name = table.split(".", 1)
    return schema, name


def _apply_renames() -> None:
    for table, pairs in COLUMN_RENAMES.items():
        if not _table_exists(table):
            print(f"[WARN] 表不存在，跳过改名：{table}")
            continue
        schema, name = _split(table)
        for old, new in pairs:
            if _column_exists(table, new):
                # 目标列已存在（生产库可能已英文化）—— 不动，避免覆盖数据
                if _column_exists(table, old):
                    print(f"[WARN] 目标列已存在，保留旧列：{table}.{old} -> {new}")
                continue
            if not _column_exists(table, old):
                print(f"[WARN] 源列不存在，跳过：{table}.{old}")
                continue
            # schema 与表名要**分开**加引号
            op.execute(
                f'ALTER TABLE "{schema}"."{name}" RENAME COLUMN "{old}" TO "{new}"'
            )
            print(f"[OK] 改名 {table}.{old} -> {new}")


def _apply_add_columns() -> None:
    for table, columns in ADD_COLUMNS.items():
        if not _table_exists(table):
            print(f"[WARN] 表不存在，跳过加列：{table}")
            continue
        schema, name = _split(table)
        for column, ddl in columns:
            if _column_exists(table, column):
                continue
            op.execute(
                f'ALTER TABLE "{schema}"."{name}" ADD COLUMN "{column}" {ddl}'
            )
            print(f"[OK] 加列 {table}.{column} {ddl}")


def upgrade() -> None:
    _apply_renames()
    _apply_add_columns()


def downgrade() -> None:
    """回滚：加的列删掉，改名的列改回中文名。

    只在确实执行过 upgrade 且列状态与本次一致时才回滚，
    避免误删运行期新增的数据。
    """
    for table, pairs in COLUMN_RENAMES.items():
        if not _table_exists(table):
            continue
        schema, name = _split(table)
        for old, new in pairs:
            if _column_exists(table, old) or not _column_exists(table, new):
                continue
            op.execute(
                f'ALTER TABLE "{schema}"."{name}" RENAME COLUMN "{new}" TO "{old}"'
            )

    for table, columns in ADD_COLUMNS.items():
        if not _table_exists(table):
            continue
        schema, name = _split(table)
        for column, _ddl in columns:
            if not _column_exists(table, column):
                continue
            op.execute(f'ALTER TABLE "{schema}"."{name}" DROP COLUMN "{column}"')
