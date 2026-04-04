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

    assert "WHERE granularity = 'monthly'" in sql_text
    assert "WHERE granularity = 'daily'" not in sql_text
    assert "monthly_order_candidates" not in sql_text
    assert "monthly_traffic_candidates" not in sql_text


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
                        ('shopee', 'shop-a', 'daily', DATE '2026-03-01', 100, 'daily-1', 1, 10),
                        ('shopee', 'shop-a', 'monthly', DATE '2026-03-01', 500, 'month-1', 5, 50)
                    """
                )
            )
            await session.execute(
                text(
                    """
                    INSERT INTO semantic.fact_analytics_atomic (
                        platform_code, shop_id, granularity, metric_date, visitor_count, page_views
                    ) VALUES
                        ('shopee', 'shop-a', 'daily', DATE '2026-03-01', 20, 30),
                        ('shopee', 'shop-a', 'monthly', DATE '2026-03-01', 200, 300)
                    """
                )
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
