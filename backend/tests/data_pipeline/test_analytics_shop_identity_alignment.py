from urllib.parse import urlparse, urlunparse

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from backend.services.data_pipeline.refresh_runner import execute_sql_target


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_analytics_monthly_atomic_resolves_shop_account_identity_to_canonical_shop_id():
    with PostgresContainer("postgres:15") as pg:
        sync_url = pg.get_connection_url()
        parsed = urlparse(sync_url)._replace(scheme="postgresql+asyncpg")
        async_url = urlunparse(parsed)
        engine = create_async_engine(async_url, echo=False)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async with session_factory() as session:
            await session.execute(text("CREATE SCHEMA IF NOT EXISTS b_class"))
            await session.execute(text("CREATE SCHEMA IF NOT EXISTS core"))
            await session.execute(text("CREATE SCHEMA IF NOT EXISTS semantic"))
            await session.execute(
                text(
                    """
                    CREATE TABLE core.shop_accounts (
                        id SERIAL PRIMARY KEY,
                        platform VARCHAR(50) NOT NULL,
                        shop_account_id VARCHAR(100) NOT NULL,
                        store_name VARCHAR(200) NOT NULL,
                        platform_shop_id VARCHAR(256)
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
                        is_active BOOLEAN DEFAULT TRUE
                    )
                    """
                )
            )
            for table_name in (
                "b_class.fact_shopee_analytics_monthly",
                "b_class.fact_tiktok_analytics_monthly",
                "b_class.fact_miaoshou_analytics_monthly",
            ):
                await session.execute(
                    text(
                        f"""
                        CREATE TABLE {table_name} (
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
                    INSERT INTO core.shop_accounts (
                        platform, shop_account_id, store_name, platform_shop_id
                    ) VALUES (
                        'tiktok', 'tiktok_sg_hx_home_local', 'Singapore(HX Home)', '1227491331'
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    INSERT INTO b_class.fact_tiktok_analytics_monthly (
                        platform_code, shop_id, metric_date, raw_data, data_hash, ingest_timestamp
                    ) VALUES (
                        'tiktok', 'tiktok_sg_hx_home_local', DATE '2026-03-01',
                        '{"page_views":"321","visitor_count":"123"}'::jsonb,
                        'analytics-shop-identity-1', TIMESTAMP '2026-03-02 10:00:00'
                    )
                    """
                )
            )
            await session.commit()

        async with session_factory() as session:
            await execute_sql_target(session, "semantic.shop_identity_resolution_candidates")
            await execute_sql_target(session, "semantic.fact_analytics_monthly_atomic")
            await session.commit()
            row = (
                await session.execute(
                    text(
                        """
                        SELECT shop_id, visitor_count, page_views
                        FROM semantic.fact_analytics_monthly_atomic
                        WHERE platform_code = 'tiktok'
                          AND metric_date = DATE '2026-03-01'
                        """
                    )
                )
            ).mappings().one()

        assert row["shop_id"] == "1227491331"
        assert float(row["visitor_count"]) == 123.0
        assert float(row["page_views"]) == 321.0

        await engine.dispose()
