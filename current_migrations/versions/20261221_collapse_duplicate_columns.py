"""合并「同一事实两份副本」的重复列（回填后删除冗余列）。

背景
----
上一条迁移 ``20261220_align_orm_schema_columns`` 把中文列名改成英文字段名，
但暴露出一层更深的结构漂移：库里**同时存在**中文列和英文列，
表达的是同一件事，例如 ``a_class.attendance_records`` 里

    工作时长  double precision     <- 旧的中文列
    work_hours double precision    <- 新建的英文列

``core.data_files`` 同理：``data_type`` 与 ``file_type``、
``discovery_time`` 与 ``created_at`` 各是同一件事的两份副本。

处理方式
--------
先把旧列的值回填到新列（只补新列为 NULL 的行，不覆盖已有值），
再删除冗余列。ORM 侧已改为只认一套字段。

安全边界
--------
回填在删除之前完成，且只填 NULL，因此不会丢数据；
若目标列已存在但来源列不存在（已经是目标形态），直接跳过。
"""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261221_collapse_duplicate_columns"
down_revision = "current_schema_20261220_align_orm_schema_columns"
branch_labels = None
depends_on = None


#: 表 -> [(来源列, 目标列)]
#: 来源列的值会回填到目标列（只补 NULL），随后来源列被删除。
MERGE_COLUMNS = {
    "a_class.attendance_records": [
        ("工作时长", "work_hours"),
        ("状态", "status"),
    ],
    "core.data_files": [
        ("data_type", "file_type"),
        ("discovery_time", "created_at"),
    ],
}

#: 表 -> [只删除、不回填的列]
#: 这些列与目标列语义不同（例如 processed 是布尔、status 是状态字符串），
#: 强行合并会丢信息；ORM 已不再声明它们，直接删除。
DROP_ONLY_COLUMNS = {
    "core.data_files": ["status"],
}

#: 回滚时重建被删列用的**原始类型**（来源：静态基线 20260805 与 20261220 的列定义）。
#:
#: [*] 2026-11-09 修复：这里原先一律用 ``TEXT`` 重建，于是
#: ``a_class.attendance_records."工作时长"`` 被建成 TEXT，
#: 而目标列 ``work_hours`` 是 double precision。
#: 「回滚之后再升级」时 ``20261221.upgrade`` 会执行
#: ``UPDATE ... SET "work_hours" = "工作时长"`` ⇒ 类型不匹配直接报错，
#: 也就是**回滚之后再也升不回去**（生产演练实测复现）。
#: 回滚重建列必须用原始类型，回滚才真正可逆。
RESTORE_COLUMN_DDL = {
    ("a_class.attendance_records", "工作时长"): "double precision",
    (
        "a_class.attendance_records",
        "状态",
    ): "character varying(32) DEFAULT 'normal' NOT NULL",
    ("core.data_files", "data_type"): "character varying(50) NOT NULL DEFAULT ''",
    (
        "core.data_files",
        "discovery_time",
    ): "timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP",
}

#: 只删除不回填的列，回滚时按原类型重建
RESTORE_DROP_ONLY_DDL = {
    ("core.data_files", "status"): "character varying(50) NOT NULL DEFAULT 'registered'",
}


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


def _table_exists(table: str) -> bool:
    row = (
        op.get_bind()
        .execute(sa.text("SELECT to_regclass(:name)"), {"name": table})
        .scalar_one_or_none()
    )
    return row is not None


def _column_type(table: str, column: str) -> str:
    """取列的**基础类型**（不比较长度/精度）。

    PostgreSQL 在 ``SET target = source`` 时会做**赋值转换**：
    ``text -> varchar`` 能静默成功（可能截断），``text -> double precision``
    则直接报错。两类都是隐患，所以这里显式比对类型。
    """
    row = (
        op.get_bind()
        .execute(
            sa.text(
                """
                SELECT data_type
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
    return str(row[0]) if row is not None else ""


def _merge_columns() -> None:
    for table, pairs in MERGE_COLUMNS.items():
        if not _table_exists(table):
            print(f"[WARN] 表不存在，跳过：{table}")
            continue
        schema, name = table.split(".", 1)
        for source, target in pairs:
            if not _column_exists(table, source):
                continue
            if not _column_exists(table, target):
                print(f"[WARN] 目标列不存在，保留来源列：{table}.{source}")
                continue
            source_type = _column_type(table, source)
            target_type = _column_type(table, target)
            if source_type != target_type:
                # [*] 2026-11-09：类型不一致必须**拒绝执行**，不能让它
                # 变成一句看不懂的 PG 报错（text->varchar 还会静默截断）。
                raise RuntimeError(
                    f"[FAIL] 合并列类型不一致，拒绝回填："
                    f"{table}.{source}({source_type}) -> {table}.{target}({target_type})。"
                    f"请先把 downgrade 重建的列类型改回原始类型。"
                )
            op.execute(
                f'UPDATE "{schema}"."{name}" '
                f'SET "{target}" = "{source}" '
                f'WHERE "{target}" IS NULL AND "{source}" IS NOT NULL'
            )
            op.execute(
                f'ALTER TABLE "{schema}"."{name}" DROP COLUMN "{source}"'
            )
            print(f"[OK] 合并并删除冗余列 {table}.{source} -> {target}")


def _drop_only_columns() -> None:
    for table, columns in DROP_ONLY_COLUMNS.items():
        if not _table_exists(table):
            continue
        schema, name = table.split(".", 1)
        for column in columns:
            if not _column_exists(table, column):
                continue
            op.execute(
                f'ALTER TABLE "{schema}"."{name}" DROP COLUMN "{column}"'
            )
            print(f"[OK] 删除冗余列 {table}.{column}")


def upgrade() -> None:
    _merge_columns()
    _drop_only_columns()


def downgrade() -> None:
    """回滚：把被删的列加回来（数据无法还原，只还原结构）。

    [*] 2026-11-09：重建列必须用**原始类型**（见 ``RESTORE_COLUMN_DDL``）。
    用错类型（例如把 double precision 建成 TEXT）会让「回滚之后再升级」
    这一步的 ``UPDATE ... SET "work_hours" = "工作时长"`` 因类型不匹配报错，
    也就是回滚之后再也升不回去。
    """
    for table, pairs in MERGE_COLUMNS.items():
        if not _table_exists(table):
            continue
        schema, name = table.split(".", 1)
        for source, _target in pairs:
            if _column_exists(table, source):
                continue
            ddl = RESTORE_COLUMN_DDL.get((table, source), "TEXT")
            op.execute(
                f'ALTER TABLE "{schema}"."{name}" ADD COLUMN "{source}" {ddl}'
            )
    for table, columns in DROP_ONLY_COLUMNS.items():
        if not _table_exists(table):
            continue
        schema, name = table.split(".", 1)
        for column in columns:
            if _column_exists(table, column):
                continue
            ddl = RESTORE_DROP_ONLY_DDL.get((table, column), "TEXT")
            op.execute(
                f'ALTER TABLE "{schema}"."{name}" ADD COLUMN "{column}" {ddl}'
            )
