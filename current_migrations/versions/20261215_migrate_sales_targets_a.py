"""第三批-C：把 ``a_class.sales_targets_a`` 的事实迁移到真 SSOT，然后删表。

背景
----
``a_class.sales_targets_a`` 是「店铺月度目标」的**派生副本**（252 行）：
它由 ``backend/services/target_sync_service.py`` 从
``a_class.sales_targets``（30 行父目标）+ ``a_class.target_breakdown``
（8361 行店铺分解）同步而来，运行时有三处读它：

- ``sql/api_modules/business_overview_comparison_module.sql``（数据对比）
- ``sql/api_modules/business_overview_operational_metrics_module.sql``（经营指标）
- ``backend/services/postgresql_dashboard_service.py``（四层 fallback 技术债）

**真 SSOT 就是 ``a_class.target_breakdown``**（``breakdown_type='shop'`` 的
「店铺月度档位」行）+ 其父目标 ``a_class.sales_targets``。副本与真源之间
还隔着一层「英文列/中文列双分支 try/except」的技术债。

仓库既有的「店铺月度档位」取值（**已查清，不新造**）
--------------------------------------------------
``a_class.target_breakdown.breakdown_type`` 的 CHECK 约束只允许三个值：
``shop`` / ``time`` / ``shop_time``。其中**店铺 × 月**档位是：

- ``breakdown_type = 'shop'``
- ``period_label = 'YYYY-MM'``（月份标签，如 ``'2026-01'``）
- ``period_start`` / ``period_end`` = 该月首末日

这套约定由 ``backend/services/shop_target_workbench_service.py``
的 ``_replace_breakdowns`` 写入（``period_label=request.year_month``），
库里 2026-01 ~ 2026-12 的 240 行就是这样写的。

本迁移做五件事
--------------
1. **规范化**：给 ``breakdown_type='shop'`` 且 ``period_label IS NULL`` 的历史行
   （2025-07/08/09 的 12 行）补上 ``period_label`` / ``period_start`` /
   ``period_end``（值取自其父目标 ``a_class.sales_targets.period_start``），
   让整张表都能按 ``platform_code | shop_id | period_label(年-月)`` 定位。
   **只补 NULL，不改已有值。**
2. **迁移事实**：把 ``a_class.sales_targets_a`` 的每一行
   （``目标销售额`` → ``target_amount``、``目标订单数`` → ``target_quantity``）
   upsert 进 ``a_class.target_breakdown`` 的「店铺月度档位」行。
3. **fail-closed 校验**：逐行核对「源表每一行都有值相等的目标行」，
   只要有一行对不上就**抛错中止**，绝不带着缺口删表。
4. **重建视图**：用 ``sql/api_modules/`` 下的资产文件重建两个 API 视图
   （视图定义的 SSOT 是资产文件，迁移不抄第二份）。
5. **删表**（fail-closed）：``DROP TABLE a_class.sales_targets_a``。

关于「哪个值算数」
-----------------
本迁移以**源表**为准：若同一 ``platform_code|shop_id|年月`` 键在
``target_breakdown`` 上已有行但金额/数量不同，就把目标行**改成源表的值**
（源表是要被迁移的事实）；目标行不存在时**新增**一行（父目标取同月
``target_type='shop'`` 且 ``status='active'`` 的那个；找不到父目标 ⇒
该行无法落库 ⇒ 第 3 步校验会中止迁移，不会静默丢数据）。

数据安全性
----------
- 第 3 步校验不通过 ⇒ 迁移中止 ⇒ **表不会被删**、数据不会被丢；
- 视图先重建、再删表 ⇒ 删表后视图仍然可查（视图已不再依赖该表）；
- ``downgrade`` 会把表、序列、约束、索引按基线 DDL 重建，并从
  ``target_breakdown`` 反向回填（事实没有丢），同时把两个视图改回旧口径。
"""

from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261215_migrate_sales_targets_a"
down_revision = "current_schema_20261214_unify_operating_costs_columns"
branch_labels = None
depends_on = None


REPO_ROOT = Path(__file__).resolve().parents[2]

LEGACY_TABLE = "a_class.sales_targets_a"

#: 需要重建的视图 → 资产文件（相对仓库根）
VIEW_ASSETS = (
    (
        "api.business_overview_comparison_module",
        "sql/api_modules/business_overview_comparison_module.sql",
    ),
    (
        "api.business_overview_operational_metrics_module",
        "sql/api_modules/business_overview_operational_metrics_module.sql",
    ),
)

#: 目标行与源行的匹配条件（platform_code | shop_id | 年月）
_MATCH_CONDITION = """
                tb.breakdown_type = 'shop'
              AND st.target_type = 'shop'
              AND st.status = 'active'
              AND tb.period_label = s."年月"
              AND lower(trim(COALESCE(tb.platform_code, '')))
                  = lower(trim(COALESCE(s.platform_code, '')))
              AND tb.shop_id = s."店铺ID"
"""


def _driver_connection():
    """拿到原生 psycopg2 连接。

    ``Connection.connection`` 是**属性**（不是方法）；真正的驱动连接在它的
    ``driver_connection`` 上，后面**不能加括号**。
    """
    pool_conn = op.get_bind().connection
    return getattr(pool_conn, "driver_connection", pool_conn)


def _exec_sql_text(sql_text: str) -> None:
    """执行一段原生 SQL（**可以含多条语句**）。"""
    with _driver_connection().cursor() as cursor:
        cursor.execute(sql_text)


def _table_exists(table: str, schema: str = "a_class") -> bool:
    return sa.inspect(op.get_bind()).has_table(table, schema=schema)


def _scalar(sql: str):
    return op.get_bind().execute(sa.text(sql)).scalar_one()


def _rebuild_view(view_name: str, asset_rel_path: str) -> bool:
    """用 ``sql/`` 下的资产文件重建视图；资产缺失 → 跳过并告警。"""
    asset_path = REPO_ROOT / asset_rel_path
    if not asset_path.is_file():
        print(
            "[WARN] 资产文件缺失，跳过视图重建：{view} ← {path}".format(
                view=view_name, path=asset_rel_path
            )
        )
        return False
    _exec_sql_text(asset_path.read_text(encoding="utf-8-sig"))
    return True


def _rebuild_views() -> None:
    for view_name, asset_rel_path in VIEW_ASSETS:
        _rebuild_view(view_name, asset_rel_path)


# --------------------------------------------------------------------------
# 1) 规范化「店铺月度档位」的 period_label / period_start / period_end
# --------------------------------------------------------------------------
def _normalize_shop_breakdown_periods() -> int:
    """给 period_label 为空的店铺档位行补上月份标签（只补 NULL，不改已有值）。"""
    result = op.get_bind().execute(
        sa.text(
            """
            UPDATE a_class.target_breakdown tb
            SET period_label = to_char(COALESCE(tb.period_start, st.period_start), 'YYYY-MM'),
                period_start = COALESCE(tb.period_start, st.period_start),
                period_end = COALESCE(tb.period_end, st.period_end)
            FROM a_class.sales_targets st
            WHERE tb.target_id = st.id
              AND tb.breakdown_type = 'shop'
              AND tb.period_label IS NULL
              AND st.period_start IS NOT NULL
            RETURNING tb.id
            """
        )
    )
    return len(result.fetchall())


# --------------------------------------------------------------------------
# 2) 迁移事实
# --------------------------------------------------------------------------
def _migrate_facts() -> dict:
    """把源表的事实 upsert 进 ``a_class.target_breakdown``。"""
    updated = op.get_bind().execute(
        sa.text(
            """
            UPDATE a_class.target_breakdown tb
            SET target_amount = s."目标销售额",
                target_quantity = s."目标订单数",
                updated_at = NOW()
            FROM a_class.sales_targets st, a_class.sales_targets_a s
            WHERE tb.target_id = st.id
              AND tb.breakdown_type = 'shop'
              AND st.target_type = 'shop'
              AND st.status = 'active'
              AND tb.period_label = s."年月"
              AND lower(trim(COALESCE(tb.platform_code, '')))
                  = lower(trim(COALESCE(s.platform_code, '')))
              AND tb.shop_id = s."店铺ID"
              AND (tb.target_amount IS DISTINCT FROM s."目标销售额"
                   OR tb.target_quantity IS DISTINCT FROM s."目标订单数")
            """
        )
    ).rowcount

    inserted = op.get_bind().execute(
        sa.text(
            """
            WITH parent AS (
                SELECT DISTINCT ON (date_trunc('month', st.period_start))
                       st.id,
                       date_trunc('month', st.period_start) AS month
                FROM a_class.sales_targets st
                WHERE st.target_type = 'shop'
                  AND st.status = 'active'
                ORDER BY date_trunc('month', st.period_start), st.id
            )
            INSERT INTO a_class.target_breakdown (
                target_id,
                breakdown_type,
                platform_code,
                shop_id,
                period_start,
                period_end,
                period_label,
                target_amount,
                target_quantity,
                achieved_amount,
                achieved_quantity,
                achievement_rate,
                target_profit_amount,
                achieved_profit_amount,
                target_profit_basis_amount
            )
            SELECT p.id,
                   'shop',
                   s.platform_code,
                   s."店铺ID",
                   p.month::date,
                   (p.month + interval '1 month - 1 day')::date,
                   s."年月",
                   s."目标销售额",
                   s."目标订单数",
                   0,
                   0,
                   0,
                   0,
                   0,
                   0
            FROM a_class.sales_targets_a s
            JOIN parent p
              ON p.month = to_date(s."年月" || '-01', 'YYYY-MM-DD')
            WHERE NOT EXISTS (
                SELECT 1
                FROM a_class.target_breakdown tb
                JOIN a_class.sales_targets st ON st.id = tb.target_id
                WHERE {match}
            )
            """.format(match=_MATCH_CONDITION)
        )
    ).rowcount

    return {"updated": int(updated or 0), "inserted": int(inserted or 0)}


# --------------------------------------------------------------------------
# 3) fail-closed 校验
# --------------------------------------------------------------------------
def _verify_fact_coverage() -> None:
    """源表每一行都必须在目标表里有"值相等"的对应行，否则中止迁移。"""
    missing = _scalar(
        """
        SELECT COUNT(*)
        FROM a_class.sales_targets_a s
        WHERE NOT EXISTS (
            SELECT 1
            FROM a_class.target_breakdown tb
            JOIN a_class.sales_targets st ON st.id = tb.target_id
            WHERE {match}
              AND tb.target_amount = s."目标销售额"
              AND tb.target_quantity = s."目标订单数"
        )
        """.format(match=_MATCH_CONDITION)
    )
    if missing:
        raise RuntimeError(
            "a_class.sales_targets_a 有 {rows} 行未能在 a_class.target_breakdown "
            "找到值相等的「店铺月度档位」行, 拒绝删表; "
            "请先人工确认这些事实的落库位置, 再重跑迁移。".format(rows=missing)
        )


def _verify_view_keys(source_rows: int) -> None:
    """两个 API 视图读到的「店铺 × 月」键数必须与源表行数一致。"""
    view_rows = _scalar(
        """
        SELECT COUNT(*)
        FROM (
            SELECT DISTINCT
                tb.platform_code,
                tb.shop_id,
                tb.period_label
            FROM a_class.target_breakdown tb
            JOIN a_class.sales_targets st ON st.id = tb.target_id
            WHERE tb.breakdown_type = 'shop'
              AND st.target_type = 'shop'
              AND st.status = 'active'
              AND tb.period_label ~ '^\\d{4}-\\d{2}$'
        ) t
        """
    )
    if int(view_rows) != int(source_rows):
        raise RuntimeError(
            "迁移后的「店铺 × 月」键数({view}) 与源表行数({src}) 不一致, "
            "拒绝删表; 请先人工确认口径差异。".format(view=view_rows, src=source_rows)
        )


def _verify_monthly_totals() -> None:
    """按月的金额/数量合计必须与源表逐月一致（防止重复行导致的翻倍）。"""
    diff = _scalar(
        """
        WITH src AS (
            SELECT "年月" AS ym,
                   SUM("目标销售额") AS amt,
                   SUM("目标订单数") AS qty
            FROM a_class.sales_targets_a
            GROUP BY 1
        ),
        tgt AS (
            SELECT tb.period_label AS ym,
                   SUM(tb.target_amount) AS amt,
                   SUM(tb.target_quantity) AS qty
            FROM a_class.target_breakdown tb
            JOIN a_class.sales_targets st ON st.id = tb.target_id
            WHERE tb.breakdown_type = 'shop'
              AND st.target_type = 'shop'
              AND st.status = 'active'
              AND tb.period_label ~ '^\\d{4}-\\d{2}$'
            GROUP BY 1
        )
        SELECT COUNT(*)
        FROM (
            SELECT COALESCE(src.ym, tgt.ym) AS ym
            FROM src
            FULL OUTER JOIN tgt ON tgt.ym = src.ym
            WHERE src.amt IS DISTINCT FROM tgt.amt
               OR src.qty IS DISTINCT FROM tgt.qty
        ) d
        """
    )
    if int(diff):
        raise RuntimeError(
            "迁移后按月合计与源表有 {months} 个月不一致, 拒绝删表; "
            "请先人工确认是否存在重复行。".format(months=diff)
        )


# --------------------------------------------------------------------------
# 4) 删表（fail-closed）
# --------------------------------------------------------------------------
def _drop_legacy_table() -> None:
    if not _table_exists("sales_targets_a"):
        return
    op.execute("DROP TABLE IF EXISTS a_class.sales_targets_a")


# --------------------------------------------------------------------------
# downgrade：重建表 + 回填 + 恢复旧视图
# --------------------------------------------------------------------------
_LEGACY_TABLE_DDL = """
CREATE TABLE a_class.sales_targets_a (
    id bigint NOT NULL,
    "店铺ID" character varying(256) NOT NULL,
    "年月" character varying(7) NOT NULL,
    "目标销售额" numeric(15,2) DEFAULT 0.0 NOT NULL,
    "目标订单数" integer DEFAULT 0 NOT NULL,
    "创建时间" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "更新时间" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    platform_code character varying(32) DEFAULT 'unknown'::character varying NOT NULL
)
"""

_OLD_COMPARISON_VIEW_SQL = """
CREATE OR REPLACE VIEW api.business_overview_comparison_module AS
WITH daily AS (
    SELECT
        'daily'::varchar AS granularity,
        period_date AS period_start,
        period_date AS period_end,
        period_date AS period_key,
        platform_code,
        shop_id,
        gmv AS sales_amount,
        order_count AS sales_quantity,
        COALESCE(page_views, visitor_count) AS traffic,
        conversion_rate,
        avg_order_value,
        attach_rate,
        profit,
        NULL::numeric AS target_sales_amount,
        NULL::numeric AS target_sales_quantity
    FROM mart.shop_day_kpi
),
weekly AS (
    SELECT
        'weekly'::varchar AS granularity,
        period_week AS period_start,
        (period_week + INTERVAL '6 day')::date AS period_end,
        period_week AS period_key,
        platform_code,
        shop_id,
        gmv AS sales_amount,
        order_count AS sales_quantity,
        COALESCE(page_views, visitor_count) AS traffic,
        conversion_rate,
        avg_order_value,
        attach_rate,
        profit,
        NULL::numeric AS target_sales_amount,
        NULL::numeric AS target_sales_quantity
    FROM mart.shop_week_kpi
),
monthly_target AS (
    SELECT
        to_date("年月" || '-01', 'YYYY-MM-DD') AS period_month,
        LOWER(TRIM(COALESCE(platform_code, ''))) AS platform_code,
        "店铺ID" AS shop_id,
        COALESCE(SUM("目标销售额"), 0) AS target_sales_amount,
        COALESCE(SUM("目标订单数"), 0) AS target_sales_quantity
    FROM a_class.sales_targets_a
    GROUP BY
        to_date("年月" || '-01', 'YYYY-MM-DD'),
        LOWER(TRIM(COALESCE(platform_code, ''))),
        "店铺ID"
),
monthly AS (
    SELECT
        'monthly'::varchar AS granularity,
        m.period_month AS period_start,
        (m.period_month + INTERVAL '1 month - 1 day')::date AS period_end,
        m.period_month AS period_key,
        m.platform_code,
        m.shop_id,
        m.gmv AS sales_amount,
        m.order_count AS sales_quantity,
        COALESCE(m.page_views, m.visitor_count) AS traffic,
        m.conversion_rate,
        m.avg_order_value,
        m.attach_rate,
        m.profit,
        t.target_sales_amount,
        t.target_sales_quantity
    FROM mart.shop_month_kpi m
    LEFT JOIN monthly_target t
        ON m.period_month = t.period_month
       AND LOWER(COALESCE(m.platform_code, '')) = COALESCE(t.platform_code, '')
       AND COALESCE(m.shop_id, '') = COALESCE(t.shop_id, '')
)
SELECT * FROM daily
UNION ALL
SELECT * FROM weekly
UNION ALL
SELECT * FROM monthly;
"""

_OLD_OPERATIONAL_METRICS_VIEW_SQL = """
CREATE OR REPLACE VIEW api.business_overview_operational_metrics_module AS
WITH base_month_kpi AS (
    SELECT
        m.period_month,
        m.platform_code,
        m.shop_id,
        m.gmv,
        m.order_count,
        m.profit,
        CASE
            WHEN CURRENT_DATE < m.period_month THEN m.period_month
            WHEN CURRENT_DATE > (m.period_month + INTERVAL '1 month - 1 day')::date THEN (m.period_month + INTERVAL '1 month - 1 day')::date
            ELSE CURRENT_DATE
        END AS anchor_date,
        CASE
            WHEN CURRENT_DATE < m.period_month THEN 0::numeric
            WHEN CURRENT_DATE > (m.period_month + INTERVAL '1 month - 1 day')::date THEN 100::numeric
            ELSE ROUND(
                ((CURRENT_DATE - m.period_month + 1)::numeric * 100.0) /
                NULLIF(((m.period_month + INTERVAL '1 month - 1 day')::date - m.period_month + 1)::numeric, 0),
                2
            )
        END AS time_progress_pct
    FROM mart.shop_month_kpi m
),
monthly_targets AS (
    SELECT
        to_date("年月" || '-01', 'YYYY-MM-DD') AS period_month,
        LOWER(TRIM(COALESCE(platform_code, ''))) AS platform_code,
        "店铺ID" AS shop_id,
        SUM("目标销售额") AS monthly_target
    FROM a_class.sales_targets_a
    GROUP BY
        to_date("年月" || '-01', 'YYYY-MM-DD'),
        LOWER(TRIM(COALESCE(platform_code, ''))),
        "店铺ID"
),
monthly_costs AS (
    SELECT
        COALESCE(o.period_month, l.period_month) AS period_month,
        COALESCE(o.platform_code, l.platform_code) AS platform_code,
        COALESCE(o.shop_id, l.shop_id) AS shop_id,
        COALESCE(o.other_operating_cost, 0) AS other_operating_cost,
        COALESCE(l.pre_commission_labor_cost, 0) AS pre_commission_labor_cost,
        COALESCE(l.performance_labor_cost, 0) AS performance_labor_cost,
        COALESCE(l.commission_labor_cost, 0) AS commission_labor_cost,
        COALESCE(l.total_labor_cost, 0) AS total_labor_cost,
        COALESCE(o.other_operating_cost, 0) + COALESCE(l.total_labor_cost, 0) AS estimated_expenses,
        COALESCE(l.cost_status, 'legacy') AS cost_status
    FROM semantic.shop_month_other_operating_cost o
    FULL OUTER JOIN mart.shop_month_labor_cost l
        ON o.period_month = l.period_month
       AND o.platform_code = l.platform_code
       AND COALESCE(o.shop_id, '') = COALESCE(l.shop_id, '')
)
SELECT
    m.period_month,
    m.platform_code,
    m.shop_id,
    t.monthly_target AS monthly_target,
    m.gmv AS monthly_total_achieved,
    ds.gmv AS today_sales,
    CASE
        WHEN t.monthly_target IS NULL OR m.gmv IS NULL THEN NULL
        WHEN t.monthly_target > 0 THEN ROUND(m.gmv::numeric * 100.0 / t.monthly_target, 2)
        WHEN t.monthly_target = 0 AND m.gmv = 0 THEN 0
        ELSE NULL
    END AS monthly_achievement_rate,
    CASE
        WHEN t.monthly_target IS NULL OR m.gmv IS NULL THEN NULL
        WHEN t.monthly_target > 0 THEN ROUND((m.gmv::numeric * 100.0 / t.monthly_target) - m.time_progress_pct, 2)
        WHEN t.monthly_target = 0 AND m.gmv = 0 THEN ROUND(0 - m.time_progress_pct, 2)
        ELSE NULL
    END AS time_gap,
    m.profit AS estimated_gross_profit,
    c.other_operating_cost,
    c.pre_commission_labor_cost,
    c.performance_labor_cost,
    c.commission_labor_cost,
    c.total_labor_cost,
    c.cost_status,
    c.estimated_expenses AS estimated_expenses,
    CASE
        WHEN m.profit IS NULL OR c.estimated_expenses IS NULL THEN NULL
        ELSE (m.profit - c.estimated_expenses)
    END AS operating_result,
    CASE
        WHEN m.profit IS NULL OR c.estimated_expenses IS NULL THEN NULL
        WHEN (m.profit - c.estimated_expenses) > 0 THEN '盈利'
        ELSE '亏损'
    END AS operating_result_text,
    m.order_count AS monthly_order_count,
    ds.order_count AS today_order_count
FROM base_month_kpi m
LEFT JOIN monthly_targets t
    ON m.period_month = t.period_month
   AND LOWER(COALESCE(m.platform_code, '')) = COALESCE(t.platform_code, '')
   AND COALESCE(m.shop_id, '') = COALESCE(t.shop_id, '')
LEFT JOIN monthly_costs c
    ON m.period_month = c.period_month
   AND LOWER(COALESCE(m.platform_code, '')) = COALESCE(c.platform_code, '')
   AND COALESCE(m.shop_id, '') = COALESCE(c.shop_id, '')
LEFT JOIN mart.shop_day_kpi ds
    ON ds.period_date = m.anchor_date
   AND ds.platform_code = m.platform_code
   AND COALESCE(ds.shop_id, '') = COALESCE(m.shop_id, '');
"""


def _restore_legacy_table() -> None:
    """按基线 DDL 重建表 + 序列 + 约束 + 索引，并从 target_breakdown 回填事实。"""
    if not _table_exists("sales_targets_a"):
        _exec_sql_text(_LEGACY_TABLE_DDL)
        _exec_sql_text(
            """
            CREATE SEQUENCE IF NOT EXISTS a_class.sales_targets_a_id_seq
            START WITH 1 INCREMENT BY 1
            """
        )
        _exec_sql_text(
            """
            ALTER SEQUENCE a_class.sales_targets_a_id_seq OWNED BY a_class.sales_targets_a.id
            """
        )
        _exec_sql_text(
            """
            ALTER TABLE a_class.sales_targets_a
            ALTER COLUMN id SET DEFAULT nextval('a_class.sales_targets_a_id_seq'::regclass)
            """
        )
        _exec_sql_text(
            """
            ALTER TABLE ONLY a_class.sales_targets_a
            ADD CONSTRAINT sales_targets_a_pkey PRIMARY KEY (id)
            """
        )
        _exec_sql_text(
            """
            ALTER TABLE ONLY a_class.sales_targets_a
            ADD CONSTRAINT uq_sales_targets_a_platform_shop_month
            UNIQUE (platform_code, "店铺ID", "年月")
            """
        )
        _exec_sql_text(
            """
            CREATE INDEX IF NOT EXISTS ix_sales_targets_a_platform_shop
            ON a_class.sales_targets_a (platform_code, "店铺ID")
            """
        )
        _exec_sql_text(
            """
            CREATE INDEX IF NOT EXISTS ix_sales_targets_a_platform_month
            ON a_class.sales_targets_a (platform_code, "年月")
            """
        )
        _exec_sql_text(
            """
            CREATE INDEX IF NOT EXISTS ix_sales_targets_shop
            ON a_class.sales_targets_a ("店铺ID")
            """
        )
        _exec_sql_text(
            """
            CREATE INDEX IF NOT EXISTS ix_sales_targets_month
            ON a_class.sales_targets_a ("年月")
            """
        )

    _exec_sql_text(
        """
        INSERT INTO a_class.sales_targets_a (
            platform_code,
            "店铺ID",
            "年月",
            "目标销售额",
            "目标订单数",
            "创建时间",
            "更新时间"
        )
        SELECT LOWER(TRIM(COALESCE(tb.platform_code, ''))),
               tb.shop_id,
               tb.period_label,
               SUM(tb.target_amount),
               SUM(tb.target_quantity),
               MIN(tb.created_at),
               NOW()
        FROM a_class.target_breakdown tb
        JOIN a_class.sales_targets st ON st.id = tb.target_id
        WHERE tb.breakdown_type = 'shop'
          AND st.target_type = 'shop'
          AND st.status = 'active'
          AND tb.period_label ~ '^\\d{4}-\\d{2}$'
        GROUP BY
            LOWER(TRIM(COALESCE(tb.platform_code, ''))),
            tb.shop_id,
            tb.period_label
        ON CONFLICT (platform_code, "店铺ID", "年月") DO UPDATE SET
            "目标销售额" = EXCLUDED."目标销售额",
            "目标订单数" = EXCLUDED."目标订单数",
            "更新时间" = NOW()
        """
    )


def upgrade() -> None:
    if not _table_exists("sales_targets_a"):
        # 已经下线过：只保证视图是新口径（幂等）。
        _rebuild_views()
        return

    source_rows = int(_scalar("SELECT COUNT(*) FROM a_class.sales_targets_a"))
    print(
        "[20261215] a_class.sales_targets_a 源行数：{rows}".format(rows=source_rows)
    )

    normalized = _normalize_shop_breakdown_periods()
    print(
        "[20261215] 规范化「店铺月度档位」period_label 行数：{rows}".format(
            rows=normalized
        )
    )

    stats = _migrate_facts()
    print(
        "[20261215] 事实迁移：新增 {ins} 行 / 更新 {upd} 行".format(
            ins=stats["inserted"], upd=stats["updated"]
        )
    )

    # fail-closed：校验不过就中止，表不会被删。
    _verify_fact_coverage()
    _verify_view_keys(source_rows)
    _verify_monthly_totals()

    # 视图先切到新口径（不再依赖待删表），再删表。
    _rebuild_views()
    _drop_legacy_table()
    print("[20261215] a_class.sales_targets_a 已删除")


def downgrade() -> None:
    _restore_legacy_table()
    _exec_sql_text(_OLD_COMPARISON_VIEW_SQL)
    _exec_sql_text(_OLD_OPERATIONAL_METRICS_VIEW_SQL)
    print("[20261215] a_class.sales_targets_a 已重建并回填，两个 API 视图已恢复旧口径")
