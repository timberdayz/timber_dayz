"""删除已废弃的 ``b_class.fact_*_traffic_*`` 表(9 张)。

背景
----
``traffic`` 数据域自 v4.10.0 起废弃并入 ``analytics``,但数据库里仍留着
traffic 时代的物理表。实测本地库(2026-10-28):

    b_class.fact_miaoshou_traffic_daily/monthly/weekly   -> 0 行
    b_class.fact_shopee_traffic_daily/monthly/weekly      -> 0 行
    b_class.fact_tiktok_traffic_daily/monthly/weekly      -> 0 行

这些表的**活着的对应表**是 ``b_class.fact_*_analytics_*(同一 platform × 粒度)``:

    b_class.fact_shopee_analytics_monthly  -> 2278 行
    b_class.fact_tiktok_analytics_monthly  -> 1176 行

依赖核查(pg_depend / pg_rewrite,2026-10-28 实测):

- **没有任何视图 / 物化视图** 依赖这 9 张表;
- **没有任何外键** 引用这 9 张表(它们自身持有指向
  ``public.catalog_files`` 与 ``core.field_mapping_templates`` 的出向 FK,
  随表一起删除,不影响被引用方);
- 名字里带 traffic 的下游对象(``api.store_analysis_traffic_*`` /
  ``mart.shop_hour_traffic_kpi`` / ``public.mv_traffic_daily`` 等)
  **读的是 ``mart.shop_*_kpi`` 与 ``semantic.fact_analytics_atomic``**,
  与本批要删的表无关,不在删除影响面内。

处理方式
--------
1. **fail-closed**: 任一目标表非空 -> 中止迁移(不擅自丢数据);
2. **fail-closed**: 发现视图 / 物化视图依赖 -> 中止迁移;
3. 用 ``DROP TABLE``(不带 ``CASCADE``)删除 —— PostgreSQL 自身会对
   上面两项探测之外、我们没预料到的依赖直接报错,不会静默连带删除下游。

本迁移**不涉及 ORM**: 这 9 张表在 ``modules/core/db/schema_parts/`` 里
没有对应模型(基线迁移 ``20260805_current_schema_baseline.py`` 建的,
ORM 从未定义),因此删除后 ORM 与数据库依然一致。
"""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261028_drop_deprecated_traffic_fact_tables"
down_revision = "current_schema_20261028_catalog_files_status_check"
branch_labels = None
depends_on = None


SCHEMA = "b_class"

#: (platform, granularity) -> 表名
TARGET_TABLE_SPECS = (
    ("miaoshou", "daily"),
    ("miaoshou", "monthly"),
    ("miaoshou", "weekly"),
    ("shopee", "daily"),
    ("shopee", "monthly"),
    ("shopee", "weekly"),
    ("tiktok", "daily"),
    ("tiktok", "monthly"),
    ("tiktok", "weekly"),
)

TARGET_TABLES = tuple(
    "fact_{platform}_traffic_{granularity}".format(
        platform=platform, granularity=granularity
    )
    for platform, granularity in TARGET_TABLE_SPECS
)


def _qualified(table: str) -> str:
    return "{schema}.{table}".format(schema=SCHEMA, table=table)


def _existing_tables() -> list:
    inspector = sa.inspect(op.get_bind())
    return [
        table
        for table in TARGET_TABLES
        if inspector.has_table(table, schema=SCHEMA)
    ]


def _dependent_views(tables: list) -> list:
    """返回依赖这些表的视图 / 物化视图(``schema.name``)。"""
    if not tables:
        return []
    bind = op.get_bind()
    names = ", ".join("'{0}'".format(table) for table in tables)
    rows = bind.execute(
        sa.text(
            "SELECT DISTINCT ns.nspname, c.relname "
            "FROM pg_depend d "
            "JOIN pg_rewrite r ON r.oid = d.objid "
            "JOIN pg_class c ON c.oid = r.ev_class "
            "JOIN pg_namespace ns ON ns.oid = c.relnamespace "
            "JOIN pg_class src ON src.oid = d.refobjid "
            "WHERE d.classid = 'pg_rewrite'::regclass "
            "  AND d.refclassid = 'pg_class'::regclass "
            "  AND src.relname IN ({names}) "
            "  AND c.relkind IN ('v', 'm') "
            "ORDER BY ns.nspname, c.relname".format(names=names)
        )
    ).fetchall()
    return ["{0}.{1}".format(row[0], row[1]) for row in rows]


def _row_counts(tables: list) -> dict:
    bind = op.get_bind()
    counts = {}
    for table in tables:
        result = bind.execute(
            sa.text("SELECT COUNT(*) FROM {qualified}".format(qualified=_qualified(table)))
        )
        counts[table] = result.scalar()
    return counts


def upgrade() -> None:
    existing = _existing_tables()
    if not existing:
        # 已删除(幂等)
        return

    # 1) fail-closed: 目标表非空则中止,不擅自丢数据
    counts = _row_counts(existing)
    non_empty = {table: count for table, count in counts.items() if count}
    if non_empty:
        detail = ", ".join(
            "{0}={1}".format(table, count) for table, count in sorted(non_empty.items())
        )
        raise RuntimeError(
            "待删除的 traffic 事实表非空, 拒绝删除: {detail}. "
            "请先人工确认这些数据是否需要迁移到 analytics 对应表, 再重跑迁移。".format(
                detail=detail
            )
        )

    # 2) fail-closed: 存在下游视图 / 物化视图依赖则中止
    dependents = _dependent_views(existing)
    if dependents:
        raise RuntimeError(
            "待删除的 traffic 事实表存在下游视图/物化视图依赖, 拒绝删除: {detail}. "
            "请先处理下游依赖, 再重跑迁移。".format(detail=", ".join(dependents))
        )

    # 3) 删除(不带 CASCADE —— 由 PostgreSQL 对未预料到的依赖直接报错兜底)
    for table in existing:
        op.execute("DROP TABLE IF EXISTS {qualified}".format(qualified=_qualified(table)))


def _create_table(table: str, granularity: str) -> None:
    # 语句顺序与基线迁移 20260805_current_schema_baseline.py 一致:
    # 建表 -> 建序列 -> 序列归属 -> 设 id 默认值
    op.execute(
        """
        CREATE TABLE {qualified} (
            id bigint NOT NULL,
            platform_code character varying(32) NOT NULL,
            shop_id character varying(256),
            data_domain character varying(64) DEFAULT 'traffic'::character varying NOT NULL,
            granularity character varying(32) DEFAULT '{granularity}'::character varying NOT NULL,
            sub_domain character varying(64),
            metric_date date NOT NULL,
            period_start_date date NOT NULL,
            period_end_date date NOT NULL,
            period_start_time timestamp with time zone,
            period_end_time timestamp with time zone,
            file_id integer,
            template_id integer,
            raw_data jsonb NOT NULL,
            header_columns jsonb,
            data_hash character varying(64) NOT NULL,
            ingest_timestamp timestamp with time zone DEFAULT now() NOT NULL,
            currency_code character varying(3)
        )
        """.format(qualified=_qualified(table), granularity=granularity)
    )
    op.execute(
        "CREATE SEQUENCE {qualified}_id_seq "
        "START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1".format(
            qualified=_qualified(table)
        )
    )
    op.execute(
        "ALTER SEQUENCE {qualified}_id_seq OWNED BY {qualified}.id".format(
            qualified=_qualified(table)
        )
    )
    op.execute(
        "ALTER TABLE ONLY {qualified} ALTER COLUMN id SET DEFAULT "
        "nextval('{qualified}_id_seq'::regclass)".format(qualified=_qualified(table))
    )
    op.execute(
        "ALTER TABLE ONLY {qualified} "
        "ADD CONSTRAINT {table}_pkey PRIMARY KEY (id)".format(
            qualified=_qualified(table), table=table
        )
    )
    op.execute(
        "ALTER TABLE ONLY {qualified} "
        "ADD CONSTRAINT {table}_file_id_fkey FOREIGN KEY (file_id) "
        "REFERENCES public.catalog_files(id) ON DELETE SET NULL".format(
            qualified=_qualified(table), table=table
        )
    )
    op.execute(
        "ALTER TABLE ONLY {qualified} "
        "ADD CONSTRAINT {table}_template_id_fkey FOREIGN KEY (template_id) "
        "REFERENCES core.field_mapping_templates(id) ON DELETE SET NULL".format(
            qualified=_qualified(table), table=table
        )
    )

    btree_indexes = (
        ("currency", "currency_code"),
        ("date", "metric_date"),
        ("domain", "data_domain"),
        ("file", "file_id"),
        ("granularity", "granularity"),
        ("hash", "data_hash"),
        ("platform", "platform_code"),
        ("shop", "shop_id"),
    )
    for suffix, column in btree_indexes:
        op.execute(
            "CREATE INDEX ix_{table}_{suffix} ON {qualified} "
            "USING btree ({column})".format(
                table=table, suffix=suffix, qualified=_qualified(table), column=column
            )
        )
    op.execute(
        "CREATE INDEX ix_{table}_gin ON {qualified} USING gin (raw_data)".format(
            table=table, qualified=_qualified(table)
        )
    )
    op.execute(
        "CREATE INDEX ix_{table}_period_date ON {qualified} "
        "USING btree (period_start_date, period_end_date)".format(
            table=table, qualified=_qualified(table)
        )
    )
    op.execute(
        "CREATE INDEX ix_{table}_period_time ON {qualified} "
        "USING btree (period_start_time, period_end_time) "
        "WHERE (period_start_time IS NOT NULL)".format(
            table=table, qualified=_qualified(table)
        )
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_{table}_hash ON {qualified} "
        "USING btree (platform_code, COALESCE(shop_id, ''::character varying), "
        "data_domain, granularity, data_hash)".format(
            table=table, qualified=_qualified(table)
        )
    )


def downgrade() -> None:
    existing = _existing_tables()
    for platform, granularity in TARGET_TABLE_SPECS:
        table = "fact_{platform}_traffic_{granularity}".format(
            platform=platform, granularity=granularity
        )
        if table in existing:
            continue
        _create_table(table, granularity)
