"""SSOT 收敛（第一阶段）：删除影子表、清理冗余中文列、统一员工目标列名。

背景
----
本轮「月度结算单」改造在梳理数据源时，发现同一份业务事实在库里有多套存储：

1. **影子表**（运行时零引用，0 行，却仍在 schema 里占位）
   - ``a_class.performance_config_a``：中文字段的绩效权重配置副本。
     运行时全部走 ``a_class.performance_config``（英文列），这张表无人读写。
   - ``c_class.performance_scores_c``：中文字段的店铺绩效副本。
     真 SSOT 是 ``c_class.performance_scores``，历史迁移已把两者合并。
   - ``c_class.shop_commissions``：中文字段的店铺提成副本。
     真 SSOT 是 ``c_class.employee_commissions`` / ``c_class.employee_shop_assignments``。
     这张表的 ORM 声明的是英文字段，与库里实际的中文字段**对不上**，
     唯一读者 ``GET /api/hr/commissions/shop`` 在当前库上本来就会抛 UndefinedColumn。

2. **同表两套列**（``a_class.employees``）
   - ``"入职日期"`` 全为 NULL，``"状态"`` 与英文 ``status`` 逐行一致，
     而运行时（含 ORM、前端）一律使用英文列。两个中文列是纯冗余。

3. **中文列名**（``a_class.employee_targets``）
   - 运行时通过 ORM 的 ``Column("中文名", ...)`` 访问，四列全是中文，
     与本仓库其余 ``a_class`` 表的英文列风格不一致。
   - 这张表**有活跃 CRUD 接口**（``backend/domains/business/routers/hr_salary.py``）
     和前端入口，因此本次是**改列名保功能**，不是删表。

安全策略
--------
- 三张影子表全部 fail-closed：非空则中止迁移，不擅自丢数据。
- 删除 ``a_class.employees`` 中文列前，逐行比对中英文列值；只要有差异就中止，
  避免删掉「只存在于中文列」的数据。
- 列重命名与约束/索引重建在同一次迁移内完成，保证中途不会出现「孤儿约束」。
"""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261212_cleanup_shadow_tables_and_legacy_columns"
down_revision = "current_schema_20261211_semantic_analytics_tiktok_visitor"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------- 影子表
SHADOW_TABLES = (
    ("a_class", "performance_config_a"),
    ("c_class", "performance_scores_c"),
    ("c_class", "shop_commissions"),
)

# ---------------------------------------------------------------- 员工冗余中文列
EMPLOYEE_LEGACY_COLUMNS = ("入职日期", "状态")

# ---------------------------------------------------------------- 员工目标列重命名
EMPLOYEE_TARGET_RENAMES = (
    ("员工编号", "employee_code"),
    ("年月", "year_month"),
    ("目标类型", "target_type"),
    ("目标值", "target_value"),
    ("创建时间", "created_at"),
    ("更新时间", "updated_at"),
)

SHADOW_TABLE_DDL = {
    ("a_class", "performance_config_a"): """
        CREATE TABLE a_class.performance_config_a (
            id bigint NOT NULL,
            "配置名称" character varying(128) NOT NULL,
            "销售额权重" double precision DEFAULT 0.0 NOT NULL,
            "订单数权重" double precision DEFAULT 0.0 NOT NULL,
            "质量权重" double precision DEFAULT 0.0 NOT NULL,
            "是否启用" boolean DEFAULT true NOT NULL,
            "创建时间" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
            "更新时间" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
        )
    """,
    ("c_class", "performance_scores_c"): """
        CREATE TABLE c_class.performance_scores_c (
            id bigint NOT NULL,
            "店铺ID" character varying(256) NOT NULL,
            "考核周期" character varying(32) NOT NULL,
            "总分" double precision DEFAULT 0.0 NOT NULL,
            "销售得分" double precision DEFAULT 0.0 NOT NULL,
            "质量得分" double precision DEFAULT 0.0 NOT NULL,
            "计算时间" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
        )
    """,
    ("c_class", "shop_commissions"): """
        CREATE TABLE c_class.shop_commissions (
            id bigint NOT NULL,
            "店铺ID" character varying(256) NOT NULL,
            "年月" character varying(7) NOT NULL,
            "销售额" numeric(15,2) DEFAULT 0.0 NOT NULL,
            "提成金额" numeric(15,2) DEFAULT 0.0 NOT NULL,
            "提成比例" double precision DEFAULT 0.0 NOT NULL,
            "计算时间" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
        )
    """,
}


def _inspector():
    return sa.inspect(op.get_bind())


def _table_exists(schema: str, table: str) -> bool:
    return _inspector().has_table(table, schema=schema)


def _column_exists(schema: str, table: str, column: str) -> bool:
    inspector = _inspector()
    if not inspector.has_table(table, schema=schema):
        return False
    return any(
        col["name"] == column for col in inspector.get_columns(table, schema=schema)
    )


def _scalar(sql: str):
    return op.get_bind().execute(sa.text(sql)).scalar_one()


def _rename_column(schema: str, table: str, old: str, new: str) -> None:
    op.execute(
        'ALTER TABLE "{schema}"."{table}" RENAME COLUMN "{old}" TO "{new}"'.format(
            schema=schema, table=table, old=old, new=new
        )
    )


def _drop_shadow_tables() -> None:
    for schema, table in SHADOW_TABLES:
        if not _table_exists(schema, table):
            continue
        row_count = _scalar(
            'SELECT COUNT(*) FROM "{schema}"."{table}"'.format(
                schema=schema, table=table
            )
        )
        if row_count:
            raise RuntimeError(
                "{schema}.{table} 非空({rows} 行), 拒绝删除; "
                "请先人工确认这些数据是否需要迁移, 再重跑迁移。".format(
                    schema=schema, table=table, rows=row_count
                )
            )
        op.execute(
            'DROP TABLE IF EXISTS "{schema}"."{table}"'.format(
                schema=schema, table=table
            )
        )


def _drop_employee_legacy_columns() -> None:
    if not _table_exists("a_class", "employees"):
        return
    # 只在中文列与英文列逐行一致时才允许删除（fail-closed）。
    if _column_exists("a_class", "employees", "入职日期"):
        diff = _scalar(
            """
            SELECT COUNT(*) FROM a_class.employees
            WHERE COALESCE("入职日期", DATE '1900-01-01')
                  IS DISTINCT FROM COALESCE(hire_date, DATE '1900-01-01')
            """
        )
        if diff:
            raise RuntimeError(
                "a_class.employees.入职日期 与 hire_date 存在 {rows} 行差异, "
                "拒绝删除; 请先人工确认数据来源。".format(rows=diff)
            )
        op.execute('ALTER TABLE a_class.employees DROP COLUMN IF EXISTS "入职日期"')
    if _column_exists("a_class", "employees", "状态"):
        diff = _scalar(
            """
            SELECT COUNT(*) FROM a_class.employees
            WHERE COALESCE("状态", '') IS DISTINCT FROM COALESCE(status, '')
            """
        )
        if diff:
            raise RuntimeError(
                "a_class.employees.状态 与 status 存在 {rows} 行差异, "
                "拒绝删除; 请先人工确认数据来源。".format(rows=diff)
            )
        op.execute('ALTER TABLE a_class.employees DROP COLUMN IF EXISTS "状态"')


def _rename_employee_target_columns() -> None:
    if not _table_exists("a_class", "employee_targets"):
        return
    # 约束名带中文，先摘掉再改名，最后用英文名重建。
    op.execute(
        'ALTER TABLE a_class.employee_targets '
        'DROP CONSTRAINT IF EXISTS "employee_targets_员工编号_年月_目标类型_key"'
    )
    for old, new in EMPLOYEE_TARGET_RENAMES:
        if _column_exists("a_class", "employee_targets", old):
            _rename_column("a_class", "employee_targets", old, new)
    op.execute(
        "ALTER TABLE a_class.employee_targets "
        "ADD CONSTRAINT uq_employee_targets_a UNIQUE "
        "(employee_code, year_month, target_type)"
    )
    op.execute("DROP INDEX IF EXISTS a_class.ix_employee_targets_employee")
    op.execute("DROP INDEX IF EXISTS a_class.ix_employee_targets_month")
    op.execute(
        "CREATE INDEX ix_employee_targets_a_employee "
        "ON a_class.employee_targets (employee_code)"
    )
    op.execute(
        "CREATE INDEX ix_employee_targets_a_month "
        "ON a_class.employee_targets (year_month)"
    )


def _restore_shadow_tables() -> None:
    for (schema, table), ddl in SHADOW_TABLE_DDL.items():
        if _table_exists(schema, table):
            continue
        op.execute(ddl)
        op.execute(
            "CREATE SEQUENCE IF NOT EXISTS {schema}.{table}_id_seq "
            "START WITH 1 INCREMENT BY 1".format(schema=schema, table=table)
        )
        op.execute(
            "ALTER TABLE {schema}.{table} ALTER COLUMN id "
            "SET DEFAULT nextval('{schema}.{table}_id_seq'::regclass)".format(
                schema=schema, table=table
            )
        )
        op.execute(
            "ALTER TABLE ONLY {schema}.{table} "
            "ADD CONSTRAINT {table}_pkey PRIMARY KEY (id)".format(
                schema=schema, table=table
            )
        )


def upgrade() -> None:
    _drop_shadow_tables()
    _drop_employee_legacy_columns()
    _rename_employee_target_columns()


def downgrade() -> None:
    # 员工目标列名回退
    if _table_exists("a_class", "employee_targets"):
        op.execute(
            "ALTER TABLE a_class.employee_targets "
            "DROP CONSTRAINT IF EXISTS uq_employee_targets_a"
        )
        for old, new in reversed(EMPLOYEE_TARGET_RENAMES):
            if _column_exists("a_class", "employee_targets", new):
                _rename_column("a_class", "employee_targets", new, old)
        op.execute(
            'ALTER TABLE a_class.employee_targets '
            'ADD CONSTRAINT "employee_targets_员工编号_年月_目标类型_key" '
            'UNIQUE ("员工编号", "年月", "目标类型")'
        )
        op.execute("DROP INDEX IF EXISTS a_class.ix_employee_targets_a_employee")
        op.execute("DROP INDEX IF EXISTS a_class.ix_employee_targets_a_month")
        op.execute(
            "CREATE INDEX ix_employee_targets_employee "
            'ON a_class.employee_targets ("员工编号")'
        )
        op.execute(
            "CREATE INDEX ix_employee_targets_month "
            'ON a_class.employee_targets ("年月")'
        )

    # 员工冗余中文列回填（数据来源就是同表的英文列）
    if _table_exists("a_class", "employees"):
        if not _column_exists("a_class", "employees", "入职日期"):
            op.execute(
                "ALTER TABLE a_class.employees ADD COLUMN IF NOT EXISTS "
                '"入职日期" date'
            )
            op.execute(
                'UPDATE a_class.employees SET "入职日期" = hire_date '
                'WHERE hire_date IS NOT NULL'
            )
        if not _column_exists("a_class", "employees", "状态"):
            op.execute(
                "ALTER TABLE a_class.employees ADD COLUMN IF NOT EXISTS "
                '"状态" character varying(32)'
            )
            op.execute(
                'UPDATE a_class.employees SET "状态" = status WHERE status IS NOT NULL'
            )

    _restore_shadow_tables()
