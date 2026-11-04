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
- 清理「源里已不存在」的历史行时**不带 CASCADE**：若历史业务表（绩效、提成、
  告警等 10 张表都有外键指向 ``dim_shops``）仍引用着某一行，删除会直接报错
  ⇒ 迁移失败（fail-closed），不会悄悄改坏业务数据。
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

#: 清掉「源里已经不存在」的派生行 —— 让「重跑」真的是**全量对齐**。
#:
#: 不带 CASCADE：历史业务表对 ``core.dim_shops`` 有外键，若仍引用着某一行，
#: 删除会直接报错 ⇒ 迁移失败（fail-closed），而不是悄悄删掉业务数据。
_PRUNE_SQL = """
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
    op.get_bind().execute(sa.text(_PRUNE_SQL))
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
