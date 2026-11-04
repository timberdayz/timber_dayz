"""把 ``core.dim_shops`` 与「店铺账号」对齐（生产此前是 0 行）。

背景
----
看板的显示名来自这个 JOIN（``backend/services/postgresql_dashboard_service.py``）：

    LEFT JOIN core.dim_shops ds
      ON LOWER(COALESCE(ds.platform_code,'')) = LOWER(COALESCE(src.platform_code,''))
     AND COALESCE(ds.shop_id,'') = COALESCE(src.shop_id,'')

而生产 ``core.dim_shops`` **一行都没有** ⇒ 这个 JOIN 永远落空 ⇒ 显示名只能
靠 ``core.shop_accounts.store_name`` 兜底。维度表存在、却没有任何数据 —— 这是
典型的「地基没打」：任何依赖维度的逻辑都在裸奔。

为什么表是空的
--------------
``core.dim_shops`` 的唯一写入方是
``backend/services/shop_sync_service.sync_platform_account_to_dim_shop``，
它从 **旧模型** ``core.platform_accounts`` 同步。而旧模型早已被
``core.shop_accounts`` 取代（生产：旧模型 11 行残留，新模型 52 行才是权威）。
那个同步函数只在「建提成配置 / 建目标」时顺带被调用 ⇒ 从没跑过 ⇒ 表是空的。

本迁移做什么
------------
把 ``core.dim_shops`` 变成 **``core.shop_accounts`` 的派生表**（展示维度），
并让它**可重跑**：P3 改键后重跑一次即可全量对齐。

键派生必须与语义层**完全一致**
-----------------------------
语义层的身份解析（``sql/semantic/shop_identity_resolution_candidates*.sql``）用的
是：

    resolved_shop_id = COALESCE(
        NULLIF(TRIM(COALESCE(platform_shop_id,'')),''),
        NULLIF(TRIM(COALESCE(shop_account_id,'')),''),
        id::text
    )

看板 JOIN 用的 ``src.shop_id`` 正是这个值（原子层的 ``shop_id`` 列在候选数为 1
时取 ``resolved_shop_id``）。**这里必须复用同一套派生** —— 派生不一致 ⇒ JOIN
落空 ⇒ 这次修复等于没做。

安全边界
--------
- 只写 ``core.dim_platforms`` 里已存在的平台（``dim_shops.platform_code`` 有外键）。
- 同名不同账号不会造成重复行：``dim_shops`` 的主键就是
  ``(platform_code, shop_id)`` ⇒ JOIN 最多命中一行 ⇒ 不会把看板金额**翻倍**。
- 清理「源里已不存在」的派生行时**只删没人引用的行**：``core.dim_shops`` 被 10
  张业务表当外键目标（绩效、提成、告警、目标拆解……）。历史数据引用的行**必须
  留着** —— 删了就是删业务数据。「有没有人引用」从系统目录里现场读（不写死
  表名），判断不了就干脆不删（保守）。
"""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261107_align_dim_shops_with_shop_accounts"
down_revision = "current_schema_20261106_create_atomic_materialized_views"
branch_labels = None
depends_on = None


#: 派生出的行集合（幂等，可重跑）。
#:
#: 键派生与语义层逐字对齐 —— 见模块 docstring。
_ALIGN_SQL = """
INSERT INTO core.dim_shops (
    platform_code,
    shop_id,
    shop_slug,
    shop_name,
    region,
    currency,
    is_active,
    created_at,
    updated_at
)
SELECT
    LOWER(TRIM(COALESCE(sa.platform, ''))) AS platform_code,
    COALESCE(
        NULLIF(TRIM(COALESCE(sa.platform_shop_id, '')), ''),
        NULLIF(TRIM(COALESCE(sa.shop_account_id, '')), ''),
        sa.id::text
    ) AS shop_id,
    NULLIF(TRIM(COALESCE(sa.shop_account_id, '')), '') AS shop_slug,
    NULLIF(TRIM(COALESCE(sa.store_name, '')), '') AS shop_name,
    NULLIF(TRIM(COALESCE(sa.shop_region, '')), '') AS region,
    'CNY' AS currency,
    COALESCE(sa.enabled, TRUE) AS is_active,
    NOW() AS created_at,
    NOW() AS updated_at
FROM core.shop_accounts sa
INNER JOIN core.dim_platforms dp
        ON dp.platform_code = LOWER(TRIM(COALESCE(sa.platform, '')))
WHERE COALESCE(
        NULLIF(TRIM(COALESCE(sa.platform_shop_id, '')), ''),
        NULLIF(TRIM(COALESCE(sa.shop_account_id, '')), ''),
        sa.id::text
      ) IS NOT NULL
ON CONFLICT (platform_code, shop_id) DO UPDATE SET
    shop_slug = EXCLUDED.shop_slug,
    shop_name = EXCLUDED.shop_name,
    region = EXCLUDED.region,
    is_active = EXCLUDED.is_active,
    updated_at = NOW()
"""

#: 清理「源里已经不存在」的派生行 —— 让「重跑」真的是**全量对齐**。
#:
#: **只清理没有人引用的行**：``core.dim_shops`` 被 10 张业务表当外键目标
#: （绩效、提成、告警、目标拆解……）。历史数据引用的行**必须留着** —— 删了就是
#: 删业务数据，而且会直接撞外键约束让迁移失败。
#:
#: 「有没有人引用」从系统目录里现场读（不写死表名）：有指向
#: ``core.dim_shops`` 的外键，就把这些表拼成 ``NOT EXISTS`` 判定。
_PRUNE_BASE_SQL = """
DELETE FROM core.dim_shops ds
WHERE NOT EXISTS (
    SELECT 1
    FROM core.shop_accounts sa
    INNER JOIN core.dim_platforms dp
            ON dp.platform_code = LOWER(TRIM(COALESCE(sa.platform, '')))
    WHERE LOWER(TRIM(COALESCE(sa.platform, ''))) = ds.platform_code
      AND COALESCE(
              NULLIF(TRIM(COALESCE(sa.platform_shop_id, '')), ''),
              NULLIF(TRIM(COALESCE(sa.shop_account_id, '')), ''),
              sa.id::text
          ) = ds.shop_id
)
"""


def _foreign_key_references() -> (
    list[tuple[str, str, tuple[str, ...], tuple[str, ...]]]
):
    """找出所有外键指向 ``core.dim_shops`` 的表。

    返回 ``(schema, table, 源列, 目标列)`` 四元组。目标列必须正好是
    ``(platform_code, shop_id)`` 才有办法生成等值判定 —— 其它的外键一律
    视为「不可安全判定」⇒ 调用方会跳过清理（保守）。
    """
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT
                src_ns.nspname,
                src.relname,
                ARRAY(
                    SELECT att.attname
                    FROM unnest(con.conkey) WITH ORDINALITY AS k(attnum, ord)
                    JOIN pg_attribute att
                      ON att.attrelid = con.conrelid AND att.attnum = k.attnum
                    ORDER BY k.ord
                ) AS src_cols,
                ARRAY(
                    SELECT att.attname
                    FROM unnest(con.confkey) WITH ORDINALITY AS k(attnum, ord)
                    JOIN pg_attribute att
                      ON att.attrelid = con.confrelid AND att.attnum = k.attnum
                    ORDER BY k.ord
                ) AS tgt_cols
            FROM pg_constraint con
            JOIN pg_class src ON src.oid = con.conrelid
            JOIN pg_namespace src_ns ON src_ns.oid = src.relnamespace
            JOIN pg_class tgt ON tgt.oid = con.confrelid
            JOIN pg_namespace tgt_ns ON tgt_ns.oid = tgt.relnamespace
            WHERE con.contype = 'f'
              AND tgt_ns.nspname = 'core'
              AND tgt.relname = 'dim_shops'
            """
        )
    ).all()
    return [(str(row[0]), str(row[1]), tuple(row[2]), tuple(row[3])) for row in rows]


def _build_prune_sql() -> str | None:
    """生成「只删没人引用的行」的 DELETE；无法安全判定时返回 None（不删）。"""
    references = _foreign_key_references()
    if not references:
        return _PRUNE_BASE_SQL

    conditions: list[str] = []
    for schema, table, src_cols, tgt_cols in references:
        if tuple(tgt_cols) != ("platform_code", "shop_id"):
            # 目标列不是 (platform_code, shop_id) ⇒ 生成不出等值判定 ⇒ 保守起见
            # 放弃清理（宁可不删，也不要误删业务数据）。
            print(
                "[WARN] dim_shops 存在非标准外键（{schema}.{table} → {cols}），跳过陈旧行清理".format(
                    schema=schema, table=table, cols=list(tgt_cols)
                )
            )
            return None
        eq = " AND ".join(
            "t.{src} = ds.{tgt}".format(src=src, tgt=tgt)
            for src, tgt in zip(src_cols, tgt_cols)
        )
        conditions.append(
            "NOT EXISTS (SELECT 1 FROM {schema}.{table} t WHERE {eq})".format(
                schema=schema, table=table, eq=eq
            )
        )
    return _PRUNE_BASE_SQL + "  AND " + "\n  AND ".join(conditions) + "\n"


def _table_exists(schema: str, table: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table, schema=schema)


def _row_count(schema: str, table: str) -> int:
    bind = op.get_bind()
    return int(
        bind.execute(
            sa.text(
                "SELECT count(*)::int FROM {schema}.{table}".format(
                    schema=schema, table=table
                )
            )
        ).scalar_one()
    )


def upgrade() -> None:
    if not _table_exists("core", "dim_shops"):
        print("[WARN] core.dim_shops 不存在，跳过对齐")
        return
    if not _table_exists("core", "shop_accounts"):
        print("[WARN] core.shop_accounts 不存在，跳过对齐")
        return

    before = _row_count("core", "dim_shops")
    op.get_bind().execute(sa.text(_ALIGN_SQL))
    prune_sql = _build_prune_sql()
    if prune_sql:
        op.get_bind().execute(sa.text(prune_sql))
    after = _row_count("core", "dim_shops")
    print(
        "[OK] core.dim_shops 与 core.shop_accounts 对齐：{before} → {after} 行".format(
            before=before, after=after
        )
    )


def downgrade() -> None:
    """回滚：清空 ``core.dim_shops``。

    回滚不恢复旧内容 —— 旧内容本来就只有「旧模型同步来的那几行」，
    而旧模型早已不是权威来源。回滚后看板显示名继续靠
    ``core.shop_accounts.store_name`` 兜底（与迁移前一致）。
    """
    if not _table_exists("core", "dim_shops"):
        return
    op.get_bind().execute(sa.text("DELETE FROM core.dim_shops"))
