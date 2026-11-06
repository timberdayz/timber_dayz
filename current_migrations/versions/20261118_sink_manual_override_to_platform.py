"""Sink the manual minimum-price override to SKU × platform (Stage 2.1b).

Three things happen here, and all three are **data-safety** fixes rather than
new features:

1. **The manual override moves out of ``core.dim_erp_sku``.**

   ``core.dim_erp_sku.min_selling_price_override`` was a *company-level* value,
   but the floor it caps is a **SKU × platform** quantity (TikTok 27.27% vs
   Shopee 41.65% other-cost rate).  A company-level cap cannot express
   "Shopee needs a higher floor than TikTok".

   Worse, that column lives on a table the **采集机 → 云端** sync truncates:
   ``scripts/sync_product_center_to_cloud.py`` runs
   ``TRUNCATE "core"."dim_erp_sku" RESTART IDENTITY CASCADE``.  Every sync
   therefore **wiped the override** — the guardrail cap silently disappeared.
   The override moves to ``finance.sku_platform_pricing``, which is not part of
   the sync table list.

   Legacy values are copied to **every priceable sales platform** so the
   "applies to all platforms" semantics of the old company-level column is
   preserved exactly (a platform with no row simply keeps the system floor).

2. **The two foreign keys on ``finance.sku_platform_pricing`` are dropped.**

   PostgreSQL's ``TRUNCATE ... CASCADE`` truncates *every* table that has a
   foreign-key reference to the truncated table, **regardless of the
   referenced side's ``ondelete``** — RESTRICT, CASCADE and NO ACTION behave
   identically here.  With the FKs in place, the sync's
   ``TRUNCATE core.dim_erp_sku CASCADE`` would wipe the new override table
   anyway, so moving the column alone would not have fixed anything.

   This mirrors ``ops.price_adjust_baselines``, which likewise stores a bare
   ``sku_id`` integer with no foreign key.

3. **The legacy column and its CHECK constraint are dropped.**

The migration is idempotent: every object is guarded by an existence check.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from pathlib import Path


revision = "current_schema_20261118_sink_manual_override_to_platform"
down_revision = "current_schema_20261117_remediate_shopee_row_identity_conflicts"
branch_labels = None
depends_on = None


#: 仓库根（资产文件定位）。
REPO_ROOT = Path(__file__).resolve().parents[2]

#: 清货排名的只读视图资产。它**选过** ``core.dim_erp_sku.min_selling_price_override``，
#: 删列之前必须先把它重建（否则 PostgreSQL 报 DependentObjectsStillExist）。
CLEARANCE_VIEW_ASSET = "sql/api_modules/sku_clearance_ranking_module.sql"
CLEARANCE_VIEW_NAME = "api.sku_clearance_ranking_module"

#: 回滚时要恢复的**旧**视图定义（还带着被删掉的列）。
#: 正本资产文件已经不带那一列了，所以回滚路径必须自带一份旧定义。
_OLD_CLEARANCE_VIEW_SQL = """
DROP VIEW IF EXISTS api.sku_clearance_ranking_module;

CREATE VIEW api.sku_clearance_ranking_module AS
WITH state AS (
    SELECT
        platform_code,
        sku_key,
        MAX(CURRENT_DATE - stock_added_at::date)        AS days_since_restock,
        SUM(COALESCE(available_stock, 0))              AS current_qty,
        SUM(COALESCE(on_hand_stock, 0))                AS on_hand_qty,
        SUM(COALESCE(inventory_value, 0))              AS inventory_value,
        COUNT(DISTINCT warehouse_name)                 AS warehouse_count,
        MAX(checklist_sales_90d)                       AS checklist_sales_90d,
        MAX(checklist_sales_30d)                       AS sold_units_30d,
        MAX(last_metric_date)                          AS snapshot_date
    FROM mart.inventory_state
    WHERE sku_key IS NOT NULL
      AND available_stock > 0
    GROUP BY platform_code, sku_key
),
erp AS (
    SELECT
        sku_id,
        sku_key,
        sku_name,
        default_purchase_cost,
        reference_selling_price,
        min_selling_price_override
    FROM core.dim_erp_sku
)
SELECT
    s.snapshot_date,
    s.platform_code,
    s.sku_key                           AS product_sku,
    s.sku_key,
    COALESCE(erp.sku_name, s.sku_key)   AS product_name,
    s.current_qty,
    s.on_hand_qty,
    s.inventory_value,
    s.warehouse_count,
    s.days_since_restock,
    s.checklist_sales_90d,
    COALESCE(s.sold_units_30d, 0)       AS sold_units_30d,
    erp.sku_id,
    erp.default_purchase_cost,
    erp.reference_selling_price,
    erp.min_selling_price_override
FROM state s
LEFT JOIN erp
       ON erp.sku_key = s.sku_key;
"""


#: ``finance.sku_platform_pricing`` 上要摘掉的外键约束名。
#: SQLAlchemy 的默认命名：``<table>_<column>_fkey``。
_FK_CONSTRAINTS = (
    ("sku_platform_pricing", "finance", "sku_platform_pricing_sku_id_fkey"),
    ("sku_platform_pricing", "finance", "sku_platform_pricing_platform_code_fkey"),
)

#: 人工覆盖值的来源标记 —— 从 SKU 级旧列迁过来的。
_MIGRATED_SOURCE = "migrated_from_sku_level"


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table: str, schema: str) -> bool:
    return _inspector().has_table(table, schema=schema)


def _has_column(table: str, schema: str, name: str) -> bool:
    return _has_table(table, schema) and name in {
        column["name"] for column in _inspector().get_columns(table, schema=schema)
    }


def _driver_connection():
    """拿到原生 psycopg2 连接（``Connection.connection`` 是**属性**，不是可调用对象）。"""
    pool_conn = op.get_bind().connection
    return getattr(pool_conn, "driver_connection", pool_conn)


def _exec_sql_text(sql_text: str) -> None:
    """执行一段原生 SQL（可以含多条语句）。

    走 psycopg2 的**简单查询协议** —— 数据库自己按分号切分。
    """
    with _driver_connection().cursor() as cursor:
        cursor.execute(sql_text)


def _rebuild_clearance_view() -> None:
    """按**正本资产**重建清货排名视图。

    为什么必须先重建：视图 ``api.sku_clearance_ranking_module`` 选过
    ``core.dim_erp_sku.min_selling_price_override`` ⇒ 删列前不重建视图，
    PostgreSQL 会直接拒绝：
    ``cannot drop column ... because other objects depend on it``。

    视图**没有下游物化视图**（pg_depend 实测只有它自己）⇒ 用不带 CASCADE 的
    DROP + CREATE 重建是安全的，不会连带删掉别的东西。

    正本资产里那一列已经被去掉（人工覆盖改由 Python 侧按平台加载），
    所以重建后视图的列数会少一列 —— 这正是本阶段要的口径。
    """
    asset_path = REPO_ROOT / CLEARANCE_VIEW_ASSET
    if not asset_path.is_file():
        print("[WARN] 资产文件缺失，跳过视图重建：{0}".format(CLEARANCE_VIEW_ASSET))
        return
    _exec_sql_text(asset_path.read_text(encoding="utf-8"))


def _restore_old_clearance_view() -> None:
    """回滚：把带旧列的旧视图定义装回去。"""
    _exec_sql_text(_OLD_CLEARANCE_VIEW_SQL)


def _has_constraint(table: str, schema: str, name: str) -> bool:
    """约束是否存在（直接查 ``pg_constraint``，跨版本最稳）。"""
    if not _has_table(table, schema):
        return False
    row = op.get_bind().execute(
        sa.text(
            "SELECT 1 FROM pg_constraint c "
            "JOIN pg_class t ON t.oid = c.conrelid "
            "JOIN pg_namespace n ON n.oid = t.relnamespace "
            "WHERE n.nspname = :schema AND t.relname = :table AND c.conname = :name"
        ),
        {"schema": schema, "table": table, "name": name},
    ).first()
    return row is not None


def _drop_fk(name: str) -> None:
    """摘掉一个外键约束（存在才摘）。"""
    op.execute(
        sa.text(
            "ALTER TABLE finance.sku_platform_pricing "
            "DROP CONSTRAINT IF EXISTS {0}".format(name)
        )
    )


def _create_fk(name: str, column: str, target: str) -> None:
    op.execute(
        sa.text(
            "ALTER TABLE finance.sku_platform_pricing "
            "ADD CONSTRAINT {0} FOREIGN KEY ({1}) REFERENCES {2}".format(
                name, column, target
            )
        )
    )


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1) 摘掉外键 —— 否则同步的 TRUNCATE CASCADE 会把这张表一起清空
    # ------------------------------------------------------------------
    for _table, _schema, name in _FK_CONSTRAINTS:
        _drop_fk(name)

    # ------------------------------------------------------------------
    # 2) SKU 级旧列的人工覆盖 → 平台级新表
    # ------------------------------------------------------------------
    if (
        _has_table("sku_platform_pricing", "finance")
        and _has_column("dim_erp_sku", "core", "min_selling_price_override")
    ):
        # 旧值是**公司级**的（对所有平台生效）⇒ 复制到**每一个可定价销售平台**。
        # 「可定价」= platform_role='sales' AND other_cost_rate IS NOT NULL
        # （没有 other_cost_rate 算不出成本线，建了覆盖也用不上）。
        # ⚠️ Alembic 的 ``op.execute(sqltext, execution_options=None)`` 的第二个参数是
        # **keyword-only 的执行选项**，不是 SQL 绑定参数 ⇒ 传绑定参数必须走
        # ``op.get_bind().execute(text, params)``。
        op.get_bind().execute(
            sa.text(
                """
                INSERT INTO finance.sku_platform_pricing (
                    sku_id, platform_code, min_selling_price_override,
                    min_selling_price_source, created_at, updated_at
                )
                SELECT s.sku_id,
                       p.platform_code,
                       s.min_selling_price_override,
                       :source,
                       NOW(),
                       NOW()
                FROM core.dim_erp_sku s
                JOIN core.dim_platforms p
                  ON p.platform_role = 'sales'
                 AND p.other_cost_rate IS NOT NULL
                WHERE s.min_selling_price_override IS NOT NULL
                ON CONFLICT (sku_id, platform_code) DO NOTHING
                """
            ),
            {"source": _MIGRATED_SOURCE},
        )

    # ------------------------------------------------------------------
    # 3) 删旧列 + 它的 CHECK 约束
    #    ⚠️ 必须**先重建视图**：清货排名视图选过这一列，不重建就删列 ⇒
    #    PostgreSQL 报 DependentObjectsStillExist。
    # ------------------------------------------------------------------
    if _has_column("dim_erp_sku", "core", "min_selling_price_override"):
        _rebuild_clearance_view()
        if _has_constraint(
            "dim_erp_sku", "core", "ck_dim_erp_sku_min_selling_price_override"
        ):
            op.execute(
                sa.text(
                    "ALTER TABLE core.dim_erp_sku "
                    "DROP CONSTRAINT IF EXISTS ck_dim_erp_sku_min_selling_price_override"
                )
            )
        op.drop_column(
            "dim_erp_sku", "min_selling_price_override", schema="core"
        )


def downgrade() -> None:
    # ------------------------------------------------------------------
    # 1) 加回旧列 + CHECK
    # ------------------------------------------------------------------
    if _has_table("dim_erp_sku", "core") and not _has_column(
        "dim_erp_sku", "core", "min_selling_price_override"
    ):
        op.add_column(
            "dim_erp_sku",
            sa.Column("min_selling_price_override", sa.Numeric(18, 2), nullable=True),
            schema="core",
        )
        op.execute(
            sa.text(
                "ALTER TABLE core.dim_erp_sku ADD CONSTRAINT "
                "ck_dim_erp_sku_min_selling_price_override "
                "CHECK (min_selling_price_override IS NULL "
                "OR min_selling_price_override > 0)"
            )
        )
        # 视图也要跟着装回旧定义（它选过这一列）
        _restore_old_clearance_view()

    # ------------------------------------------------------------------
    # 2) 平台级覆盖值 → SKU 级旧列
    #    一个 SKU 可能有多个平台不同的覆盖值，旧列只放得下一个
    #    ⇒ 取**平台字典序最小**的那条（与 20261115 的 downgrade 同一套取法）。
    #    这会**丢信息**：回滚后只剩一个平台的覆盖值。
    #    这是「公司级旧列」这个模型本身的容量上限，不是本次迁移引入的。
    # ------------------------------------------------------------------
    if (
        _has_table("sku_platform_pricing", "finance")
        and _has_column("dim_erp_sku", "core", "min_selling_price_override")
    ):
        op.execute(
            sa.text(
                """
                UPDATE core.dim_erp_sku s
                SET min_selling_price_override = src.min_selling_price_override
                FROM (
                    SELECT DISTINCT ON (sku_id)
                           sku_id, min_selling_price_override
                    FROM finance.sku_platform_pricing
                    WHERE min_selling_price_override IS NOT NULL
                    ORDER BY sku_id, platform_code
                ) src
                WHERE s.sku_id = src.sku_id
                """
            )
        )

    # ------------------------------------------------------------------
    # 3) 加回外键
    # ------------------------------------------------------------------
    if _has_table("sku_platform_pricing", "finance"):
        for _table, _schema, name in _FK_CONSTRAINTS:
            if not _has_constraint("sku_platform_pricing", "finance", name):
                if name.endswith("_sku_id_fkey"):
                    _create_fk(
                        name, "sku_id", "core.dim_erp_sku(sku_id)"
                    )
                else:
                    _create_fk(
                        name,
                        "platform_code",
                        "core.dim_platforms(platform_code)",
                    )
