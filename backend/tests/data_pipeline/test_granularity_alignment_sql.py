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
    assert "fact_shopee_orders_monthly" in orders_sql_text
    assert "fact_tiktok_orders_daily" not in orders_sql_text
    assert "fact_miaoshou_orders_weekly" not in orders_sql_text
    assert "fact_shopee_analytics_monthly" in analytics_sql_text
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


def test_annual_summary_shop_month_does_not_force_missing_costs_to_zero():
    sql_text = _read_sql("sql/mart/annual_summary_shop_month.sql")

    assert "COALESCE(c.total_cost, 0) AS total_cost" not in sql_text
    assert "COALESCE(m.profit, 0)" not in sql_text
    assert "COALESCE(m.gmv, 0)" not in sql_text


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
                    CREATE TABLE core.platform_accounts (
                        id SERIAL PRIMARY KEY,
                        account_id VARCHAR(100) NOT NULL,
                        platform VARCHAR(50) NOT NULL,
                        account_alias VARCHAR(200),
                        store_name VARCHAR(200) NOT NULL,
                        shop_id VARCHAR(256)
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
                        platform_code, shop_id, metric_date, raw_data, data_hash, ingest_timestamp
                    ) VALUES (
                        'shopee',
                        'shop-a',
                        DATE '2026-03-01',
                        '{"order_id":"month-1","paid_amount":"500","product_quantity":"5","profit":"50"}'::jsonb,
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
                        platform_code, shop_id, metric_date, raw_data, data_hash, ingest_timestamp
                    ) VALUES (
                        'shopee',
                        'shop-a',
                        DATE '2026-03-01',
                        '{"visitor_count":"200","page_views":"300"}'::jsonb,
                        'month-traffic-1',
                        TIMESTAMP '2026-03-02 10:00:00'
                    )
                    """
                )
            )
            await execute_sql_target(session, "semantic.fact_orders_monthly_atomic")
            await execute_sql_target(session, "semantic.fact_analytics_monthly_atomic")
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
                        page_views NUMERIC
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
