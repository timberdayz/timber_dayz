"""给云端接收账本 ``ops.cloud_sync_receive_log`` 补上「身份裁决」的两列计数。

背景
----
2026-11-07 的采集同步丢数事故暴露了一个**账本不诚实**的问题:

``ops.cloud_sync_receive_log`` 只有一列 ``written_rows``, 记的是
「送进 writer 的行数」, 而不是「真正写进云端的行数」。
身份判定把行拒掉之后, 账本照样记满数 ——
生产上最后一条记录是 ``written_rows=72, status=completed``,
而那 72 行**一行都没落库**。

只凭 ``written_rows`` 无法回答两个关键问题:

* 这次到底有多少行**没**进云端?(丢数规模)
* 有多少行进了云端但**归属不到任何店铺**?(待人工补主数据)

因此补两列:

* ``identity_conflict_rows`` —— 因「行内身份自相矛盾」被拒、没写进云端的行数。
  只要它 > 0, 本次接收的 ``status`` 就是 ``partial_success`` 而不是 ``completed``。
* ``identity_unresolved_rows`` —— 落库但归属不到主数据账号的行数。
  这些行**照常落库**(不是丢数), 只是提醒人工补主数据。

安全边界
--------
只新增列, 不改不删任何既有列与既有数据。
``written_rows`` 的**语义**在应用侧被修正为「实际落库行数」,
但历史行的值无法回填(当时没记被拒行数), 因此保持原值不动。
"""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261222_cloud_sync_receive_log_identity_rows"
down_revision = "current_schema_20261221_collapse_duplicate_columns"
branch_labels = None
depends_on = None


SCHEMA = "ops"
TABLE_NAME = "cloud_sync_receive_log"
#: DDL 里必须写成 ``"ops"."cloud_sync_receive_log"`` ——
#: 写成 ``"ops.cloud_sync_receive_log"`` 会被 PostgreSQL 当成**一个带点的表名**,
#: 于是报 "relation ops.cloud_sync_receive_log does not exist"。
QUALIFIED_TABLE = f'"{SCHEMA}"."{TABLE_NAME}"'

#: 新增列: (列名, 列类型, 服务器默认值)
NEW_COLUMNS = (
    ("identity_conflict_rows", sa.Integer(), "0"),
    ("identity_unresolved_rows", sa.Integer(), "0"),
)


def _table_exists() -> bool:
    row = (
        op.get_bind()
        .execute(
            sa.text("SELECT to_regclass(:name)"), {"name": f"{SCHEMA}.{TABLE_NAME}"}
        )
        .scalar_one_or_none()
    )
    return row is not None


def _column_exists(column: str) -> bool:
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
            {"schema": "ops", "table": "cloud_sync_receive_log", "column": column},
        )
        .fetchone()
    )
    return row is not None


def upgrade() -> None:
    if not _table_exists():
        print(f"[WARN] 表不存在，跳过：{SCHEMA}.{TABLE_NAME}")
        return
    for column, column_type, server_default in NEW_COLUMNS:
        if _column_exists(column):
            print(f"[OK] 列已存在，跳过：{SCHEMA}.{TABLE_NAME}.{column}")
            continue
        op.execute(
            f"ALTER TABLE {QUALIFIED_TABLE} ADD COLUMN \"{column}\" {column_type} "
            f"NOT NULL DEFAULT {server_default}"
        )
        print(f"[OK] 新增列 {SCHEMA}.{TABLE_NAME}.{column}")


def downgrade() -> None:
    """回滚：删掉这两列（历史计数随之丢失）。"""
    if not _table_exists():
        return
    for column, _column_type, _server_default in NEW_COLUMNS:
        if not _column_exists(column):
            continue
        op.execute(f"ALTER TABLE {QUALIFIED_TABLE} DROP COLUMN \"{column}\"")
        print(f"[OK] 删除列 {SCHEMA}.{TABLE_NAME}.{column}")
