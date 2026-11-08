from pathlib import Path

import pytest
from sqlalchemy import text


def _read_sql(path_str: str) -> str:
    return Path(path_str).read_text(encoding="utf-8")


def test_shop_week_kpi_does_not_fallback_to_daily():
    sql_text = _read_sql("sql/mart/shop_week_kpi.sql")

    assert "WHERE granularity = 'weekly'" in sql_text
    assert "WHERE granularity = 'daily'" not in sql_text
    assert "weekly_order_candidates" not in sql_text
    assert "weekly_traffic_candidates" not in sql_text


def test_shop_month_kpi_does_not_fallback_to_daily():
    sql_text = _read_sql("sql/mart/shop_month_kpi.sql")
    orders_sql_text = _read_sql("sql/semantic/orders_monthly_atomic.sql")
    analytics_sql_text = _read_sql("sql/semantic/analytics_monthly_atomic.sql")

    assert "semantic.fact_orders_monthly_atomic" in sql_text
    assert "semantic.fact_analytics_monthly_atomic" in sql_text
    # 月粒度事实表已由月度物化视图提供，月度视图只允许指向该 MV，不得回退日/周粒度源
    assert "semantic.fact_orders_monthly_atomic_mv" in orders_sql_text
    assert "fact_tiktok_orders_daily" not in orders_sql_text
    assert "fact_miaoshou_orders_weekly" not in orders_sql_text
    assert "fact_orders_daily" not in orders_sql_text
    assert "fact_orders_weekly" not in orders_sql_text
    assert "semantic.fact_analytics_monthly_atomic_mv" in analytics_sql_text
    assert "fact_tiktok_analytics_daily" not in analytics_sql_text
    assert "fact_miaoshou_analytics_weekly" not in analytics_sql_text


def test_shop_week_kpi_preserves_missing_metrics_without_forcing_zero():
    sql_text = _read_sql("sql/mart/shop_week_kpi.sql")

    assert "COALESCE(o.gmv, 0) AS gmv" not in sql_text
    assert "COALESCE(t.visitor_count, 0) AS visitor_count" not in sql_text
    assert "COALESCE(o.profit, 0) AS profit" not in sql_text


def test_shop_month_kpi_preserves_missing_metrics_without_forcing_zero():
    sql_text = _read_sql("sql/mart/shop_month_kpi.sql")

    assert "COALESCE(o.gmv, 0) AS gmv" not in sql_text
    assert "COALESCE(t.visitor_count, 0) AS visitor_count" not in sql_text
    assert "COALESCE(o.profit, 0) AS profit" not in sql_text


def test_platform_month_kpi_does_not_force_missing_rollups_to_zero():
    sql_text = _read_sql("sql/mart/platform_month_kpi.sql")

    assert "COALESCE(SUM(gmv), 0) AS gmv" not in sql_text
    assert "COALESCE(SUM(visitor_count), 0) AS visitor_count" not in sql_text
    assert "COALESCE(SUM(profit), 0) AS profit" not in sql_text


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_shop_month_kpi_uses_monthly_only_without_daily_fallback():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from testcontainers.postgres import PostgresContainer
    from urllib.parse import urlparse, urlunparse

    from backend.services.data_pipeline.refresh_runner import execute_sql_target

    with PostgresContainer("postgres:15") as pg:
        sync_url = pg.get_connection_url()
        parsed = urlparse(sync_url)._replace(scheme="postgresql+asyncpg")
        async_url = urlunparse(parsed)
        engine = create_async_engine(async_url, echo=False)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async with session_factory() as session:
            await session.execute(text("CREATE SCHEMA IF NOT EXISTS b_class"))
            await session.execute(text("CREATE SCHEMA IF NOT EXISTS core"))
            await session.execute(
                text(
                    """
                    CREATE TABLE core.shop_accounts (
                        id SERIAL PRIMARY KEY,
                        platform VARCHAR(50) NOT NULL,
                        shop_account_id VARCHAR(100) NOT NULL,
                        store_name VARCHAR(200) NOT NULL,
                        platform_shop_id VARCHAR(256),
                        shop_region VARCHAR(50),
                        enabled BOOLEAN NOT NULL DEFAULT TRUE,
                        business_role VARCHAR(50) NOT NULL DEFAULT 'operating_store'
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE TABLE core.shop_account_aliases (
                        id SERIAL PRIMARY KEY,
                        shop_account_id INTEGER NOT NULL,
                        platform VARCHAR(50) NOT NULL,
                        alias_value VARCHAR(200) NOT NULL,
                        alias_normalized VARCHAR(200) NOT NULL,
                        is_primary BOOLEAN DEFAULT FALSE,
                        is_active BOOLEAN DEFAULT TRUE,
                        shop_region VARCHAR(50)
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    INSERT INTO core.shop_accounts (
                        platform, shop_account_id, store_name, platform_shop_id, shop_region
                    ) VALUES (
                        'shopee', 'shopee_shop_a_local', 'Shop A', 'shop-a', 'SG'
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE TABLE b_class.fact_shopee_orders_monthly (
                        platform_code VARCHAR(32),
                        shop_id VARCHAR(256),
                        -- 语义层的月度物化视图正文要从 b_class 源表直读
                        -- data_domain / granularity ⇒ mock 表缺列建视图就报错。
                        data_domain VARCHAR(32),
                        granularity VARCHAR(32),
                        metric_date DATE,
                        raw_data JSONB,
                        data_hash VARCHAR(128),
                        ingest_timestamp TIMESTAMP
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE TABLE b_class.fact_tiktok_orders_monthly (
                        platform_code VARCHAR(32),
                        shop_id VARCHAR(256),
                        -- 语义层的月度物化视图正文要从 b_class 源表直读
                        -- data_domain / granularity ⇒ mock 表缺列建视图就报错。
                        data_domain VARCHAR(32),
                        granularity VARCHAR(32),
                        metric_date DATE,
                        raw_data JSONB,
                        data_hash VARCHAR(128),
                        ingest_timestamp TIMESTAMP
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE TABLE b_class.fact_miaoshou_orders_monthly (
                        platform_code VARCHAR(32),
                        shop_id VARCHAR(256),
                        -- 语义层的月度物化视图正文要从 b_class 源表直读
                        -- data_domain / granularity ⇒ mock 表缺列建视图就报错。
                        data_domain VARCHAR(32),
                        granularity VARCHAR(32),
                        metric_date DATE,
                        raw_data JSONB,
                        data_hash VARCHAR(128),
                        ingest_timestamp TIMESTAMP
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE TABLE b_class.fact_shopee_analytics_monthly (
                        platform_code VARCHAR(32),
                        shop_id VARCHAR(256),
                        -- 语义层的月度物化视图正文要从 b_class 源表直读
                        -- data_domain / granularity ⇒ mock 表缺列建视图就报错。
                        data_domain VARCHAR(32),
                        granularity VARCHAR(32),
                        metric_date DATE,
                        raw_data JSONB,
                        data_hash VARCHAR(128),
                        ingest_timestamp TIMESTAMP
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE TABLE b_class.fact_tiktok_analytics_monthly (
                        platform_code VARCHAR(32),
                        shop_id VARCHAR(256),
                        -- 语义层的月度物化视图正文要从 b_class 源表直读
                        -- data_domain / granularity ⇒ mock 表缺列建视图就报错。
                        data_domain VARCHAR(32),
                        granularity VARCHAR(32),
                        metric_date DATE,
                        raw_data JSONB,
                        data_hash VARCHAR(128),
                        ingest_timestamp TIMESTAMP
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE TABLE b_class.fact_miaoshou_analytics_monthly (
                        platform_code VARCHAR(32),
                        shop_id VARCHAR(256),
                        -- 语义层的月度物化视图正文要从 b_class 源表直读
                        -- data_domain / granularity ⇒ mock 表缺列建视图就报错。
                        data_domain VARCHAR(32),
                        granularity VARCHAR(32),
                        metric_date DATE,
                        raw_data JSONB,
                        data_hash VARCHAR(128),
                        ingest_timestamp TIMESTAMP
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    INSERT INTO b_class.fact_shopee_orders_monthly (
                        platform_code, shop_id, data_domain, granularity,
                        metric_date, raw_data, data_hash, ingest_timestamp
                    ) VALUES (
                        'shopee',
                        'shop-a',
                        'orders',
                        'monthly',
                        DATE '2026-03-01',
                        -- [*] orders 域取数改走别名表(semantic.resolve_alias) ⇒
                        -- raw_data 的键必须是**登记过的真实源表头**:
                        --   买家支付(RMB) → paid_amount (shopee 的 (RMB) 变体)
                        --   利润(RMB)     → profit
                        --   销售数量      → 视图列 product_quantity(语义键 sales_volume)
                        --   订单编号      → order_id
                        -- 裸名(原币列)/英文列名都命不中 ⇒ 取不到就是 NULL。
                        '{"订单编号":"month-1","买家支付(RMB)":"500","销售数量":"5","利润(RMB)":"50"}'::jsonb,
                        'month-order-1',
                        TIMESTAMP '2026-03-02 10:00:00'
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    INSERT INTO b_class.fact_shopee_analytics_monthly (
                        platform_code, shop_id, data_domain, granularity,
                        metric_date, raw_data, data_hash, ingest_timestamp
                    ) VALUES (
                        'shopee',
                        'shop-a',
                        'analytics',
                        'monthly',
                        DATE '2026-03-01',
                        '{"visitor_count":"200","page_views":"300"}'::jsonb,
                        'month-traffic-1',
                        TIMESTAMP '2026-03-02 10:00:00'
                    )
                    """
                )
            )
            # [*] resolve_dependencies=True 会把别名资产(semantic.alias_registry:
            #     表 semantic.semantic_field_aliases + 函数 semantic.resolve_alias)
            #     与店铺身份候选集一起排在前面执行 —— orders 域取数已经改走别名表,
            #     别名资产不在 ⇒ 建视图报 "function semantic.resolve_alias does not exist"。
            await execute_sql_target(
                session,
                "semantic.fact_orders_monthly_atomic",
                resolve_dependencies=True,
            )
            await execute_sql_target(
                session,
                "semantic.fact_analytics_monthly_atomic",
                resolve_dependencies=True,
            )
            await execute_sql_target(session, "mart.shop_month_kpi")
            await session.commit()

            row = (
                await session.execute(
                    text(
                        """
                        SELECT gmv, order_count, visitor_count, total_items, profit
                        FROM mart.shop_month_kpi
                        WHERE period_month = DATE '2026-03-01'
                          AND platform_code = 'shopee'
                          AND shop_id = 'shop-a'
                        """
                    )
                )
            ).fetchone()

            assert row == (500, 1, 200, 5, 50)

        await engine.dispose()


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_shop_day_kpi_keeps_missing_traffic_as_null():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from testcontainers.postgres import PostgresContainer
    from urllib.parse import urlparse, urlunparse

    from backend.services.data_pipeline.refresh_runner import execute_sql_target

    with PostgresContainer("postgres:15") as pg:
        sync_url = pg.get_connection_url()
        parsed = urlparse(sync_url)._replace(scheme="postgresql+asyncpg")
        async_url = urlunparse(parsed)
        engine = create_async_engine(async_url, echo=False)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async with session_factory() as session:
            await session.execute(text("CREATE SCHEMA IF NOT EXISTS semantic"))
            await session.execute(
                text(
                    """
                    CREATE TABLE semantic.fact_orders_atomic (
                        platform_code VARCHAR(32),
                        shop_id VARCHAR(256),
                        granularity VARCHAR(32),
                        metric_date DATE,
                        paid_amount NUMERIC,
                        order_id VARCHAR(128),
                        product_quantity NUMERIC,
                        profit NUMERIC
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE TABLE semantic.fact_analytics_atomic (
                        platform_code VARCHAR(32),
                        shop_id VARCHAR(256),
                        granularity VARCHAR(32),
                        metric_date DATE,
                        visitor_count NUMERIC,
                        page_views NUMERIC,
                        impressions NUMERIC
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    INSERT INTO semantic.fact_orders_atomic (
                        platform_code, shop_id, granularity, metric_date,
                        paid_amount, order_id, product_quantity, profit
                    ) VALUES
                        ('shopee', 'shop-a', 'daily', DATE '2026-03-01', 100, 'daily-1', 1, 10)
                    """
                )
            )
            # 原子层的物化副本（2026-11-04）：mart.shop_day_kpi 改读物化视图
            # → 测试库必须先把这两个 MV 建出来。
            # ⚠️ 必须建在 INSERT **之后**：物化视图是「建的那一刻」把数据拍平，
            #    早建就会拿到空表。
            await session.execute(
                text(
                    """
                    CREATE MATERIALIZED VIEW semantic.fact_orders_atomic_mv
                    AS SELECT * FROM semantic.fact_orders_atomic
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE MATERIALIZED VIEW semantic.fact_analytics_atomic_mv
                    AS SELECT * FROM semantic.fact_analytics_atomic
                    """
                )
            )
            await execute_sql_target(session, "mart.shop_day_kpi")
            await session.commit()

            row = (
                await session.execute(
                    text(
                        """
                        SELECT gmv, order_count, visitor_count, page_views, conversion_rate
                        FROM mart.shop_day_kpi
                        WHERE period_date = DATE '2026-03-01'
                          AND platform_code = 'shopee'
                          AND shop_id = 'shop-a'
                        """
                    )
                )
            ).fetchone()

            assert row == (100, 1, None, None, None)

        await engine.dispose()
