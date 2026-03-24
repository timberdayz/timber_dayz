from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer
from urllib.parse import urlparse, urlunparse


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_load_shop_monthly_metrics_reads_postgresql_shop_racing_module():
    from backend.services.postgresql_shop_metrics_service import load_shop_monthly_metrics

    with PostgresContainer("postgres:15") as pg:
        sync_url = pg.get_connection_url()
        parsed = urlparse(sync_url)._replace(scheme="postgresql+asyncpg")
        async_url = urlunparse(parsed)
        engine = create_async_engine(async_url, echo=False)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async with session_factory() as session:
            await session.execute(
                __import__("sqlalchemy").text("CREATE SCHEMA IF NOT EXISTS api")
            )
            await session.execute(
                __import__("sqlalchemy").text(
                    """
                    CREATE OR REPLACE VIEW api.business_overview_shop_racing_module AS
                    SELECT
                        'monthly'::varchar AS granularity,
                        DATE '2026-03-01' AS period_key,
                        'shopee'::varchar AS platform_code,
                        'shop-a'::varchar AS shop_id,
                        1234::numeric AS gmv,
                        50::numeric AS order_count,
                        24.68::numeric AS avg_order_value,
                        1.2::numeric AS attach_rate,
                        321::numeric AS profit,
                        1500::numeric AS target_amount,
                        82.27::numeric AS achievement_rate
                    """
                )
            )
            await session.commit()

            metrics = await load_shop_monthly_metrics(session, "2026-03")

            assert metrics["shopee|shop-a"]["monthly_sales"] == 1234.0
            assert metrics["shopee|shop-a"]["monthly_profit"] == 321.0
            assert metrics["shopee|shop-a"]["achievement_rate"] == 82.27

        await engine.dispose()


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_load_shop_monthly_target_achievement_uses_postgresql_shop_racing_module():
    from backend.services.postgresql_shop_metrics_service import load_shop_monthly_target_achievement

    with PostgresContainer("postgres:15") as pg:
        sync_url = pg.get_connection_url()
        parsed = urlparse(sync_url)._replace(scheme="postgresql+asyncpg")
        async_url = urlunparse(parsed)
        engine = create_async_engine(async_url, echo=False)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async with session_factory() as session:
            await session.execute(
                __import__("sqlalchemy").text("CREATE SCHEMA IF NOT EXISTS api")
            )
            await session.execute(
                __import__("sqlalchemy").text(
                    """
                    CREATE OR REPLACE VIEW api.business_overview_shop_racing_module AS
                    SELECT
                        'monthly'::varchar AS granularity,
                        DATE '2026-03-01' AS period_key,
                        'shopee'::varchar AS platform_code,
                        'shop-a'::varchar AS shop_id,
                        1234::numeric AS gmv,
                        50::numeric AS order_count,
                        24.68::numeric AS avg_order_value,
                        1.2::numeric AS attach_rate,
                        321::numeric AS profit,
                        1500::numeric AS target_amount,
                        82.27::numeric AS achievement_rate
                    """
                )
            )
            await session.commit()

            rows = await load_shop_monthly_target_achievement(session, "2026-03")

            assert rows["shopee|shop-a"]["target"] == 1500.0
            assert rows["shopee|shop-a"]["achieved"] == 1234.0
            assert rows["shopee|shop-a"]["platform_code"] == "shopee"
            assert rows["shopee|shop-a"]["shop_id"] == "shop-a"

        await engine.dispose()
