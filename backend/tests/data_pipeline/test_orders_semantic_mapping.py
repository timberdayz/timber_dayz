from pathlib import Path
from urllib.parse import urlparse, urlunparse

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from backend.services.data_pipeline.refresh_runner import execute_sql_target


def test_orders_atomic_sql_exists_and_creates_semantic_view():
    sql_path = Path("sql/semantic/orders_atomic.sql")
    assert sql_path.exists()

    sql_text = sql_path.read_text(encoding="utf-8")
    assert "CREATE SCHEMA IF NOT EXISTS semantic" in sql_text
    assert "CREATE OR REPLACE VIEW semantic.fact_orders_atomic AS" in sql_text


def test_orders_atomic_sql_exposes_core_standard_fields():
    sql_text = Path("sql/semantic/orders_atomic.sql").read_text(encoding="utf-8")
    for field_name in (
        "platform_code",
        "shop_id",
        "order_id",
        "order_status",
        "sales_amount",
        "paid_amount",
        "profit",
        "product_quantity",
        "platform_total_cost_itemized",
        "currency_code",
        "data_hash",
        "ingest_timestamp",
    ):
        assert field_name in sql_text


def test_orders_atomic_sql_maps_real_paid_amount_and_store_name_fields():
    sql_text = Path("sql/semantic/orders_atomic.sql").read_text(encoding="utf-8", errors="replace")

    assert "paid_amount_raw" in sql_text
    assert "sales_amount_raw" in sql_text
    assert "store_label_raw" in sql_text


def test_orders_atomic_sql_resolves_shop_aliases_via_account_aliases():
    sql_text = Path("sql/semantic/orders_atomic.sql").read_text(encoding="utf-8", errors="replace")

    assert "public.account_aliases" in sql_text
    assert "core.platform_accounts" in sql_text
    assert "store_label_raw" in sql_text
    assert "target_type" in sql_text
    assert "target_id" in sql_text


def _orders_table_names() -> tuple[str, ...]:
    return (
        "fact_shopee_orders_daily",
        "fact_shopee_orders_weekly",
        "fact_shopee_orders_monthly",
        "fact_tiktok_orders_daily",
        "fact_tiktok_orders_weekly",
        "fact_tiktok_orders_monthly",
        "fact_miaoshou_orders_daily",
        "fact_miaoshou_orders_weekly",
        "fact_miaoshou_orders_monthly",
    )


async def _create_orders_b_class_tables(session) -> None:
    await session.execute(text("CREATE SCHEMA IF NOT EXISTS b_class"))
    await session.execute(text("CREATE SCHEMA IF NOT EXISTS semantic"))
    await session.execute(text("CREATE SCHEMA IF NOT EXISTS core"))

    for table_name in _orders_table_names():
        await session.execute(
            text(
                f"""
                CREATE TABLE b_class.{table_name} (
                    platform_code VARCHAR(32),
                    shop_id VARCHAR(256),
                    data_domain VARCHAR(64),
                    granularity VARCHAR(32),
                    metric_date DATE,
                    period_start_date DATE,
                    period_end_date DATE,
                    period_start_time TIMESTAMP,
                    period_end_time TIMESTAMP,
                    raw_data JSONB,
                    header_columns JSONB,
                    data_hash VARCHAR(128),
                    ingest_timestamp TIMESTAMP,
                    currency_code VARCHAR(8)
                )
                """
            )
        )

    await session.execute(
        text(
            """
            CREATE TABLE public.account_aliases (
                id SERIAL PRIMARY KEY,
                platform VARCHAR(32) NOT NULL,
                data_domain VARCHAR(64) NOT NULL,
                account VARCHAR(128),
                site VARCHAR(64),
                store_label_raw VARCHAR(256) NOT NULL,
                target_type VARCHAR(32) NOT NULL,
                target_id VARCHAR(128) NOT NULL,
                confidence DOUBLE PRECISION,
                active BOOLEAN NOT NULL DEFAULT TRUE
            )
            """
        )
    )
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


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_orders_atomic_resolves_shop_alias_to_target_shop_id():
    with PostgresContainer("postgres:15") as pg:
        sync_url = pg.get_connection_url()
        parsed = urlparse(sync_url)._replace(scheme="postgresql+asyncpg")
        async_url = urlunparse(parsed)
        engine = create_async_engine(async_url, echo=False)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async with session_factory() as session:
            await _create_orders_b_class_tables(session)
            await session.execute(
                text(
                    """
                    INSERT INTO public.account_aliases (
                        platform, data_domain, account, site, store_label_raw,
                        target_type, target_id, confidence, active
                    ) VALUES (
                        'shopee', 'orders', NULL, '新加坡', '3C店',
                        'shop', 'shopee新加坡3C店', 1.0, TRUE
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    INSERT INTO b_class.fact_shopee_orders_monthly (
                        platform_code, shop_id, data_domain, granularity,
                        metric_date, period_start_date, period_end_date,
                        period_start_time, period_end_time, raw_data, header_columns,
                        data_hash, ingest_timestamp, currency_code
                    ) VALUES (
                        'shopee', 'none', 'orders', 'monthly',
                        DATE '2025-09-25', DATE '2025-09-01', DATE '2025-09-30',
                        TIMESTAMP '2025-09-01 00:00:00', TIMESTAMP '2025-09-30 23:59:59',
                        '{"店铺":"3C店","站点":"新加坡","订单号":"SO-1","实付金额":"100","产品数量":"2"}'::jsonb,
                        '["店铺","站点","订单号","实付金额","产品数量"]'::jsonb,
                        'hash-shop-alias-1', TIMESTAMP '2025-09-26 10:00:00', 'SGD'
                    )
                    """
                )
            )
            await session.commit()

        async with session_factory() as session:
            await execute_sql_target(session, "semantic.fact_orders_atomic")
            await session.commit()
            result = await session.execute(
                text(
                    """
                    SELECT platform_code, shop_id, order_id, paid_amount
                    FROM semantic.fact_orders_atomic
                    """
                )
            )
            rows = result.mappings().all()

        assert len(rows) == 1
        assert rows[0]["platform_code"] == "shopee"
        assert rows[0]["shop_id"] == "shopee新加坡3C店"
        assert rows[0]["order_id"] == "SO-1"
        assert float(rows[0]["paid_amount"]) == 100.0

        await engine.dispose()


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_orders_atomic_resolves_shop_alias_to_platform_account_when_alias_targets_account():
    with PostgresContainer("postgres:15") as pg:
        sync_url = pg.get_connection_url()
        parsed = urlparse(sync_url)._replace(scheme="postgresql+asyncpg")
        async_url = urlunparse(parsed)
        engine = create_async_engine(async_url, echo=False)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async with session_factory() as session:
            await _create_orders_b_class_tables(session)
            await session.execute(
                text(
                    """
                    INSERT INTO core.platform_accounts (
                        account_id, platform, account_alias, store_name, shop_id
                    ) VALUES (
                        'Tiktok 1店', 'tiktok', '', 'Tiktok 1店', 'Tiktok 1店'
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    INSERT INTO public.account_aliases (
                        platform, data_domain, account, site, store_label_raw,
                        target_type, target_id, confidence, active
                    ) VALUES (
                        'tiktok', 'orders', NULL, '菲律宾', '菲律宾1店',
                        'account', 'Tiktok 1店', 1.0, TRUE
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    INSERT INTO b_class.fact_tiktok_orders_monthly (
                        platform_code, shop_id, data_domain, granularity,
                        metric_date, period_start_date, period_end_date,
                        period_start_time, period_end_time, raw_data, header_columns,
                        data_hash, ingest_timestamp, currency_code
                    ) VALUES (
                        'tiktok', 'none', 'orders', 'monthly',
                        DATE '2025-09-24', DATE '2025-09-01', DATE '2025-09-30',
                        TIMESTAMP '2025-09-01 00:00:00', TIMESTAMP '2025-09-30 23:59:59',
                        '{"店铺":"菲律宾1店","站点":"菲律宾","订单号":"TK-1","买家实付金额":"88","产品数量":"1"}'::jsonb,
                        '["店铺","站点","订单号","买家实付金额","产品数量"]'::jsonb,
                        'hash-account-alias-1', TIMESTAMP '2025-09-25 10:00:00', 'PHP'
                    )
                    """
                )
            )
            await session.commit()

        async with session_factory() as session:
            await execute_sql_target(session, "semantic.fact_orders_atomic")
            await session.commit()
            result = await session.execute(
                text(
                    """
                    SELECT platform_code, shop_id, order_id, paid_amount
                    FROM semantic.fact_orders_atomic
                    """
                )
            )
            rows = result.mappings().all()

        assert len(rows) == 1
        assert rows[0]["platform_code"] == "tiktok"
        assert rows[0]["shop_id"] == "Tiktok 1店"
        assert rows[0]["order_id"] == "TK-1"
        assert float(rows[0]["paid_amount"]) == 88.0

        await engine.dispose()
