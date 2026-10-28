"""``catalog_files.status`` 取值约束 (CHECK)。

背景
----
``catalog_files.status`` 的合法取值曾经没有任何数据库约束:
``public.catalog_files`` 只有主键与 ``check_catalog_files_storage_layer``
两条约束, ``status`` 可以写入任意字符串。

同时, 合法状态集合散落在四个地方(历史迁移字面量、后端代码字面量、
前端筛选下拉框、数据库缺失), 导致「什么是合法状态」没有唯一答案。

处理方式
--------
1. 先探测是否存在集合外的历史脏数据 —— **有就中止**(fail-closed),
   不擅自改写业务状态, 由人工确认后再处理;
2. 干净则加上 ``ck_catalog_files_status`` CHECK 约束。

合法状态集合与 ``modules/core/catalog_status.py`` 保持一致(SSOT):

    pending, processing, validated, ingested, partial_success,
    quarantined, failed, needs_shop, source_missing, template_update_required

实测本地库(495 行)的状态分布:
    ingested 435 / failed 26 / template_update_required 25 /
    processing 8 / source_missing 1 —— 全部落在合法集合内。

幂等: 约束存在时先删除再加, 保证约束定义始终等于当前 SSOT。
"""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261028_catalog_files_status_check"
down_revision = "current_schema_20261028_template_published_unique_index"
branch_labels = None
depends_on = None


TABLE = "catalog_files"
SCHEMA = "public"
CONSTRAINT_NAME = "ck_catalog_files_status"

VALID_STATUSES = (
    "pending",
    "processing",
    "validated",
    "ingested",
    "partial_success",
    "quarantined",
    "failed",
    "needs_shop",
    "source_missing",
    "template_update_required",
)


def _table_exists() -> bool:
    inspector = sa.inspect(op.get_bind())
    return inspector.has_table(TABLE, schema=SCHEMA)


def upgrade() -> None:
    if not _table_exists():
        return

    bind = op.get_bind()

    # 1) fail-closed: 存在集合外的历史脏数据时中止迁移
    valid_list = ", ".join("'{}'".format(status) for status in VALID_STATUSES)
    invalid_rows = bind.execute(
        sa.text(
            "SELECT status, COUNT(*) FROM {schema}.{table} "
            "WHERE status IS NULL OR status NOT IN ({valid}) "
            "GROUP BY status ORDER BY status".format(
                schema=SCHEMA, table=TABLE, valid=valid_list
            )
        )
    ).fetchall()
    if invalid_rows:
        detail = ", ".join("{0}({1})".format(row[0], row[1]) for row in invalid_rows)
        raise RuntimeError(
            "catalog_files.status 存在非法取值, 拒绝添加 CHECK 约束: {detail}. "
            "请先人工确认这些行的正确状态再重跑迁移。".format(detail=detail)
        )

    # 2) 幂等重建约束
    op.execute(
        "ALTER TABLE {schema}.{table} DROP CONSTRAINT IF EXISTS {constraint}".format(
            schema=SCHEMA, table=TABLE, constraint=CONSTRAINT_NAME
        )
    )
    op.execute(
        "ALTER TABLE {schema}.{table} ADD CONSTRAINT {constraint} "
        "CHECK (status IN ({valid}))".format(
            schema=SCHEMA,
            table=TABLE,
            constraint=CONSTRAINT_NAME,
            valid=valid_list,
        )
    )


def downgrade() -> None:
    if not _table_exists():
        return
    op.execute(
        "ALTER TABLE {schema}.{table} DROP CONSTRAINT IF EXISTS {constraint}".format(
            schema=SCHEMA, table=TABLE, constraint=CONSTRAINT_NAME
        )
    )
