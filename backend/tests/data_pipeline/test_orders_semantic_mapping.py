import json
from pathlib import Path
from datetime import date
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


def test_orders_atomic_sql_maps_current_orders_amount_and_store_fields():
    sql_text = Path("sql/semantic/orders_atomic.sql").read_text(encoding="utf-8", errors="replace")

    assert "paid_amount_raw" in sql_text
    assert "buyer_payment_rmb" in sql_text
    assert "original_amount_rmb" in sql_text
    assert "purchase_cost_rmb" in sql_text
    assert "store_label_raw" in sql_text


def test_orders_atomic_sql_resolves_shop_aliases_via_shop_accounts_and_aliases():
    sql_text = Path("sql/semantic/orders_atomic.sql").read_text(encoding="utf-8", errors="replace")

    assert "core.shop_accounts" in sql_text
    assert "core.shop_account_aliases" in sql_text
    assert "alias_normalized" in sql_text
    assert "store_name" in sql_text
    assert "platform_shop_id" in sql_text


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


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_orders_monthly_atomic_metric_date_prefers_order_time_over_metric_date_column():
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
                    INSERT INTO b_class.fact_shopee_orders_monthly (
                        platform_code, shop_id, data_domain, granularity,
                        metric_date, period_start_date, period_end_date,
                        period_start_time, period_end_time, raw_data, header_columns,
                        data_hash, ingest_timestamp, currency_code
                    ) VALUES (
                        'shopee', 'xihong', 'orders', 'monthly',
                        DATE '2026-05-01', DATE '2026-05-01', DATE '2026-05-01',
                        TIMESTAMP '2026-05-01 00:00:00', TIMESTAMP '2026-05-01 00:00:00',
                        '{"下单时间":"2026-01-05 23:37:01","order_id":"SO-METRIC-DATE-1","buyer_payment_rmb":"100","product_quantity":"2","profit_rmb":"30"}'::jsonb,
                        '["下单时间","order_id","buyer_payment_rmb","product_quantity","profit_rmb"]'::jsonb,
                        'hash-metric-date-prefers-order-time-1', TIMESTAMP '2026-05-02 10:00:00', 'SGD'
                    )
                    """
                )
            )
            await session.commit()

        async with session_factory() as session:
            await execute_sql_target(session, "semantic.shop_identity_resolution_candidates")
            await execute_sql_target(session, "semantic.fact_orders_monthly_atomic_mv")
            await session.commit()
            row = (
                await session.execute(
                    text(
                        """
                        SELECT metric_date, order_id, paid_amount, profit
                        FROM semantic.fact_orders_monthly_atomic_mv
                        """
                    )
                )
            ).mappings().first()

        assert row is not None
        assert row["metric_date"] == date(2026, 1, 1)
        assert row["order_id"] == "SO-METRIC-DATE-1"
        assert float(row["paid_amount"]) == 100.0
        assert float(row["profit"]) == 30.0

        await engine.dispose()


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_orders_monthly_atomic_prefers_rmb_paid_amount_over_local_paid_amount():
    with PostgresContainer("postgres:15") as pg:
        sync_url = pg.get_connection_url()
        parsed = urlparse(sync_url)._replace(scheme="postgresql+asyncpg")
        async_url = urlunparse(parsed)
        engine = create_async_engine(async_url, echo=False)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        raw_data = {
            "下单时间": "2026-03-08 12:00:00",
            "订单号": "SO-RMB-PAID-1",
            "店铺": "Shopee菲律宾2店",
            "实付金额(RMB)": "20",
            "实付金额": "200",
            "产品数量": "1",
            "利润(RMB)": "5",
        }

        async with session_factory() as session:
            await _create_orders_b_class_tables(session)
            await session.execute(
                text(
                    """
                    INSERT INTO b_class.fact_shopee_orders_monthly (
                        platform_code, shop_id, data_domain, granularity,
                        metric_date, period_start_date, period_end_date,
                        period_start_time, period_end_time, raw_data, header_columns,
                        data_hash, ingest_timestamp, currency_code
                    ) VALUES (
                        'shopee', 'xihong', 'orders', 'monthly',
                        DATE '2026-03-01', DATE '2026-03-01', DATE '2026-03-31',
                        TIMESTAMP '2026-03-01 00:00:00', TIMESTAMP '2026-03-31 23:59:59',
                        CAST(:raw_data AS jsonb),
                        CAST(:header_columns AS jsonb),
                        'hash-rmb-paid-priority-1', TIMESTAMP '2026-06-01 10:00:00', 'PHP'
                    )
                    """
                ),
                {
                    "raw_data": json.dumps(raw_data, ensure_ascii=False),
                    "header_columns": json.dumps(list(raw_data.keys()), ensure_ascii=False),
                },
            )
            await session.commit()

        async with session_factory() as session:
            await execute_sql_target(session, "semantic.shop_identity_resolution_candidates")
            await execute_sql_target(session, "semantic.fact_orders_monthly_atomic_mv")
            await session.commit()
            row = (
                await session.execute(
                    text(
                        """
                        SELECT order_id, paid_amount, profit
                        FROM semantic.fact_orders_monthly_atomic_mv
                        WHERE order_id = 'SO-RMB-PAID-1'
                        """
                    )
                )
            ).mappings().first()

        assert row is not None
        assert float(row["paid_amount"]) == 20.0
        assert float(row["profit"]) == 5.0

        await engine.dispose()


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_orders_atomic_prefers_rmb_profit_over_local_profit():
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
                    INSERT INTO b_class.fact_shopee_orders_daily (
                        platform_code, shop_id, data_domain, granularity,
                        metric_date, period_start_date, period_end_date,
                        period_start_time, period_end_time, raw_data, header_columns,
                        data_hash, ingest_timestamp, currency_code
                    ) VALUES (
                        'shopee', 'xihong', 'orders', 'daily',
                        DATE '2026-03-08', DATE '2026-03-08', DATE '2026-03-08',
                        TIMESTAMP '2026-03-08 00:00:00', TIMESTAMP '2026-03-08 23:59:59',
                        '{"store_name":"Shopee菲律宾2店","order_id":"SO-RMB-PROFIT-1","buyer_payment_rmb":"20","buyer_payment":"200","profit_rmb":"5","profit":"50","product_quantity":"1"}'::jsonb,
                        '["store_name","order_id","buyer_payment_rmb","buyer_payment","profit_rmb","profit","product_quantity"]'::jsonb,
                        'hash-rmb-profit-priority-1', TIMESTAMP '2026-06-01 10:00:00', 'PHP'
                    )
                    """
                )
            )
            await session.commit()

        async with session_factory() as session:
            await execute_sql_target(session, "semantic.fact_orders_atomic")
            await session.commit()
            row = (
                await session.execute(
                    text(
                        """
                        SELECT order_id, paid_amount, profit
                        FROM semantic.fact_orders_atomic
                        WHERE order_id = 'SO-RMB-PROFIT-1'
                        """
                    )
                )
            ).mappings().first()

        assert row is not None
        assert float(row["paid_amount"]) == 20.0
        assert float(row["profit"]) == 5.0

        await engine.dispose()


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_orders_atomic_resolves_shop_alias_via_shop_account_alias():
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
                    INSERT INTO core.shop_accounts (
                        platform, shop_account_id, store_name, platform_shop_id
                    ) VALUES (
                        'shopee', 'shopee_sg_3c_local', 'Shopee SG 3C', 'shop-sg-3c'
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    INSERT INTO core.shop_account_aliases (
                        shop_account_id, platform, alias_value, alias_normalized, is_primary, is_active
                    ) VALUES (
                        1, 'shopee', '3C Shop', '3c shop', true, true
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
                        'shopee', 'xihong', 'orders', 'monthly',
                        DATE '2025-09-25', DATE '2025-09-01', DATE '2025-09-30',
                        TIMESTAMP '2025-09-01 00:00:00', TIMESTAMP '2025-09-30 23:59:59',
                        '{"store_name":"3C Shop","order_id":"SO-1","buyer_payment_rmb":"100","product_quantity":"2"}'::jsonb,
                        '["store_name","order_id","buyer_payment_rmb","product_quantity"]'::jsonb,
                        'hash-shop-alias-1', TIMESTAMP '2025-09-26 10:00:00', 'SGD'
                    )
                    """
                )
            )
            await session.commit()

        async with session_factory() as session:
            await execute_sql_target(session, "semantic.fact_orders_atomic")
            await session.commit()
            rows = (
                await session.execute(
                    text(
                        """
                        SELECT platform_code, shop_id, order_id, paid_amount
                        FROM semantic.fact_orders_atomic
                        """
                    )
                )
            ).mappings().all()

        assert len(rows) == 1
        assert rows[0]["platform_code"] == "shopee"
        assert rows[0]["shop_id"] == "shop-sg-3c"
        assert rows[0]["order_id"] == "SO-1"
        assert float(rows[0]["paid_amount"]) == 100.0

        await engine.dispose()


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_orders_atomic_resolves_prefixed_store_label_via_normalized_alias():
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
                    INSERT INTO core.shop_accounts (
                        platform, shop_account_id, store_name, platform_shop_id
                    ) VALUES (
                        'shopee', 'shopee_sg_xhkj1_local', 'xhkj1.sg', '1391124228'
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    INSERT INTO core.shop_account_aliases (
                        shop_account_id, platform, alias_value, alias_normalized, is_primary, is_active
                    ) VALUES (
                        1, 'shopee', '新加坡1店', '新加坡1店', true, true
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
                        'shopee', 'xihong', 'orders', 'monthly',
                        DATE '2026-03-31', DATE '2026-03-01', DATE '2026-03-31',
                        TIMESTAMP '2026-03-01 00:00:00', TIMESTAMP '2026-03-31 23:59:59',
                        '{"店铺":"Shopee新加坡1店","order_id":"SO-PREFIX-1","buyer_payment_rmb":"120","profit_rmb":"30"}'::jsonb,
                        '["店铺","order_id","buyer_payment_rmb","profit_rmb"]'::jsonb,
                        'hash-shop-prefix-1', TIMESTAMP '2026-04-01 10:00:00', 'SGD'
                    )
                    """
                )
            )
            await session.commit()

        async with session_factory() as session:
            await execute_sql_target(session, "semantic.fact_orders_atomic")
            await session.commit()
            rows = (
                await session.execute(
                    text(
                        """
                        SELECT platform_code, shop_id, order_id, paid_amount, profit
                        FROM semantic.fact_orders_atomic
                        """
                    )
                )
            ).mappings().all()

        assert len(rows) == 1
        assert rows[0]["platform_code"] == "shopee"
        assert rows[0]["shop_id"] == "1391124228"
        assert rows[0]["order_id"] == "SO-PREFIX-1"
        assert float(rows[0]["paid_amount"]) == 120.0
        assert float(rows[0]["profit"]) == 30.0

        await engine.dispose()


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_orders_atomic_marks_account_level_shop_id_without_alias_as_unknown():
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
                    INSERT INTO b_class.fact_shopee_orders_monthly (
                        platform_code, shop_id, data_domain, granularity,
                        metric_date, period_start_date, period_end_date,
                        period_start_time, period_end_time, raw_data, header_columns,
                        data_hash, ingest_timestamp, currency_code
                    ) VALUES (
                        'shopee', 'xihong', 'orders', 'monthly',
                        DATE '2026-03-31', DATE '2026-03-01', DATE '2026-03-31',
                        TIMESTAMP '2026-03-01 00:00:00', TIMESTAMP '2026-03-31 23:59:59',
                        '{"店铺":"Shopee未认领店铺","order_id":"SO-UNKNOWN-1","buyer_payment_rmb":"120","profit_rmb":"30"}'::jsonb,
                        '["店铺","order_id","buyer_payment_rmb","profit_rmb"]'::jsonb,
                        'hash-shop-unknown-1', TIMESTAMP '2026-04-01 10:00:00', 'SGD'
                    )
                    """
                )
            )
            await session.commit()

        async with session_factory() as session:
            await execute_sql_target(session, "semantic.fact_orders_atomic")
            await session.commit()
            rows = (
                await session.execute(
                    text(
                        """
                        SELECT platform_code, shop_id, order_id
                        FROM semantic.fact_orders_atomic
                        """
                    )
                )
            ).mappings().all()

        assert len(rows) == 1
        assert rows[0]["platform_code"] == "shopee"
        assert rows[0]["shop_id"] == "unknown"
        assert rows[0]["order_id"] == "SO-UNKNOWN-1"

        await engine.dispose()


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_orders_atomic_resolves_shop_alias_via_shop_account_store_name_fallback():
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
                    INSERT INTO core.shop_accounts (
                        platform, shop_account_id, store_name, platform_shop_id
                    ) VALUES (
                        'tiktok', 'tiktok_ph_1_local', 'Philippines Shop 1', 'tiktok-shop-1'
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
                        'tiktok', 'xihong', 'orders', 'monthly',
                        DATE '2025-09-24', DATE '2025-09-01', DATE '2025-09-30',
                        TIMESTAMP '2025-09-01 00:00:00', TIMESTAMP '2025-09-30 23:59:59',
                        '{"store_name":"Philippines Shop 1","order_id":"TK-1","buyer_payment":"88","product_quantity":"1"}'::jsonb,
                        '["store_name","order_id","buyer_payment","product_quantity"]'::jsonb,
                        'hash-account-alias-1', TIMESTAMP '2025-09-25 10:00:00', 'PHP'
                    )
                    """
                )
            )
            await session.commit()

        async with session_factory() as session:
            await execute_sql_target(session, "semantic.fact_orders_atomic")
            await session.commit()
            rows = (
                await session.execute(
                    text(
                        """
                        SELECT platform_code, shop_id, order_id, paid_amount
                        FROM semantic.fact_orders_atomic
                        """
                    )
                )
            ).mappings().all()

        assert len(rows) == 1
        assert rows[0]["platform_code"] == "tiktok"
        assert rows[0]["shop_id"] == "tiktok-shop-1"
        assert rows[0]["order_id"] == "TK-1"
        assert float(rows[0]["paid_amount"]) == 88.0

        await engine.dispose()


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_orders_monthly_atomic_resolves_tiktok_alias_to_canonical_shop_id():
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
                    INSERT INTO core.shop_accounts (
                        platform, shop_account_id, store_name, platform_shop_id
                    ) VALUES (
                        'tiktok', 'tiktok_sg_hx_home_local', 'Singapore(HX Home)', NULL
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    INSERT INTO core.shop_account_aliases (
                        shop_account_id, platform, alias_value, alias_normalized, is_primary, is_active
                    ) VALUES (
                        1, 'tiktok', 'TK新加坡2店', '新加坡2店', true, true
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
                        'tiktok', 'xihong', 'orders', 'monthly',
                        DATE '2026-03-31', DATE '2026-03-01', DATE '2026-03-31',
                        TIMESTAMP '2026-03-01 00:00:00', TIMESTAMP '2026-03-31 23:59:59',
                        '{"店铺":"TK新加坡2店","订单号":"TK-MONTH-1","买家支付(RMB)":"188.23","出库数量":"1","利润(RMB)":"18"}'::jsonb,
                        '["店铺","订单号","买家支付(RMB)","出库数量","利润(RMB)"]'::jsonb,
                        'hash-tiktok-monthly-alias-1', TIMESTAMP '2026-04-01 10:00:00', 'SGD'
                    )
                    """
                )
            )
            await session.commit()

        async with session_factory() as session:
            await execute_sql_target(session, "semantic.shop_identity_resolution_candidates")
            await execute_sql_target(session, "semantic.fact_orders_monthly_atomic_mv")
            await execute_sql_target(session, "semantic.fact_orders_monthly_atomic")
            await session.commit()
            rows = (
                await session.execute(
                    text(
                        """
                        SELECT platform_code, shop_id, order_id, paid_amount, profit
                        FROM semantic.fact_orders_monthly_atomic
                        """
                    )
                )
            ).mappings().all()

        assert len(rows) == 1
        assert rows[0]["platform_code"] == "tiktok"
        assert rows[0]["shop_id"] == "tiktok_sg_hx_home_local"
        assert rows[0]["order_id"] == "TK-MONTH-1"
        assert float(rows[0]["paid_amount"]) == 188.23
        assert float(rows[0]["profit"]) == 18.0

        await engine.dispose()
