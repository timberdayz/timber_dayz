from pathlib import Path
from urllib.parse import urlparse, urlunparse

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from backend.services.data_pipeline.refresh_runner import execute_sql_target

def _normalized_sql() -> str:
    sql_text = Path("sql/semantic/orders_atomic.sql").read_text(encoding="utf-8")
    return "".join(sql_text.lower().split())


def test_orders_atomic_exposes_b_cost_fields_in_semantic_view():
    sql_text = Path("sql/semantic/orders_atomic.sql").read_text(encoding="utf-8")

    required_fields = (
        "purchase_amount",
        "order_original_amount",
        "warehouse_operation_fee",
        "shipping_fee",
        "promotion_fee",
        "platform_commission",
        "platform_deduction_fee",
        "platform_voucher",
        "platform_service_fee",
        "platform_total_cost_itemized",
        "platform_total_cost_derived",
    )
    for field_name in required_fields:
        assert field_name in sql_text

    assert "cogs" in sql_text


def test_orders_atomic_keeps_core_amount_fields_while_adding_b_cost_fields():
    sql_text = Path("sql/semantic/orders_atomic.sql").read_text(encoding="utf-8")

    assert "sales_amount" in sql_text
    assert "paid_amount" in sql_text
    assert "profit" in sql_text


def test_orders_atomic_covers_required_b_cost_chinese_aliases():
    sql_text = Path("sql/semantic/orders_atomic.sql").read_text(
        encoding="utf-8", errors="replace"
    )

    required_aliases = (
        "采购金额",
        "采购价",
        "产品成本",
        "订单原始金额",
        "产品折后价格",
        "产品折后金额",
        "产品原价",
        "仓库操作费",
        "贴单费",
        "运费",
        "商家运费",
        "推广费",
        "平台推广费",
        "平台收取推广费",
        "营销推广费",
        "平台佣金",
        "佣金",
        "总佣金",
        "TikTok Shop平台佣金",
        "平台扣费",
        "平台扣款",
        "TikTok Shop平台扣费",
        "代金券",
        "平台代金券",
        "平台优惠券",
        "服务费",
        "平台服务费",
        "平台收取服务费",
        "TikTok Shop平台服务费",
    )

    for alias in required_aliases:
        assert alias in sql_text


def test_orders_atomic_uses_required_platform_total_cost_formulas():
    normalized = _normalized_sql()

    assert (
        "coalesce(shipping_fee,0)+"
        "coalesce(promotion_fee,0)+"
        "coalesce(platform_commission,0)+"
        "coalesce(platform_deduction_fee,0)+"
        "coalesce(platform_voucher,0)+"
        "coalesce(platform_service_fee,0)"
        in normalized
    )

    assert (
        "order_original_amount-purchase_amount-profit-warehouse_operation_fee"
        in normalized
    )


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
async def test_orders_atomic_parses_b_cost_fields_from_chinese_raw_data_keys():
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
                    INSERT INTO b_class.fact_tiktok_orders_daily (
                        platform_code, shop_id, data_domain, granularity,
                        metric_date, period_start_date, period_end_date,
                        period_start_time, period_end_time, raw_data, header_columns,
                        data_hash, ingest_timestamp, currency_code
                    ) VALUES
                    (
                        'tiktok', 'shop-cost-1', 'orders', 'daily',
                        DATE '2026-04-01', DATE '2026-04-01', DATE '2026-04-01',
                        TIMESTAMP '2026-04-01 00:00:00', TIMESTAMP '2026-04-01 23:59:59',
                        '{
                            "order_id":"TK-BCOST-1",
                            "利润":"50",
                            "采购价":"100",
                            "产品折后价格":"300",
                            "贴单费":"5",
                            "商家运费":"10",
                            "平台收取推广费":"20",
                            "TikTok Shop平台佣金":"15",
                            "平台扣款":"3",
                            "平台优惠券":"7",
                            "平台收取服务费":"2"
                        }'::jsonb,
                        '[]'::jsonb,
                        'hash-b-cost-cn-1', TIMESTAMP '2026-04-02 09:00:00', 'USD'
                    ),
                    (
                        'tiktok', 'shop-cost-2', 'orders', 'daily',
                        DATE '2026-04-01', DATE '2026-04-01', DATE '2026-04-01',
                        TIMESTAMP '2026-04-01 00:00:00', TIMESTAMP '2026-04-01 23:59:59',
                        '{
                            "order_id":"TK-BCOST-2",
                            "利润":"20",
                            "产品成本":"80",
                            "营销推广费":"12",
                            "佣金":"6",
                            "TikTok Shop平台扣费":"2",
                            "代金券":"4",
                            "服务费":"1"
                        }'::jsonb,
                        '[]'::jsonb,
                        'hash-b-cost-cn-2', TIMESTAMP '2026-04-02 09:05:00', 'USD'
                    ),
                    (
                        'tiktok', 'shop-cost-3', 'orders', 'daily',
                        DATE '2026-04-01', DATE '2026-04-01', DATE '2026-04-01',
                        TIMESTAMP '2026-04-01 00:00:00', TIMESTAMP '2026-04-01 23:59:59',
                        '{
                            "order_id":"TK-BCOST-3",
                            "profit":"30",
                            "cogs":"81",
                            "order_original_amount":"180",
                            "warehouse_operation_fee":"9",
                            "shipping_fee":"8",
                            "promotion_fee":"5",
                            "platform_commission":"4",
                            "platform_deduction_fee":"3",
                            "platform_voucher":"2",
                            "platform_service_fee":"1"
                        }'::jsonb,
                        '[]'::jsonb,
                        'hash-b-cost-cogs-3', TIMESTAMP '2026-04-02 09:10:00', 'USD'
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
                    SELECT
                        order_id,
                        purchase_amount,
                        order_original_amount,
                        warehouse_operation_fee,
                        shipping_fee,
                        promotion_fee,
                        platform_commission,
                        platform_deduction_fee,
                        platform_voucher,
                        platform_service_fee,
                        platform_total_cost_itemized,
                        platform_total_cost_derived
                    FROM semantic.fact_orders_atomic
                    WHERE order_id IN ('TK-BCOST-1', 'TK-BCOST-2', 'TK-BCOST-3')
                    ORDER BY order_id
                    """
                )
            )
            rows = result.mappings().all()

        assert len(rows) == 3

        assert rows[0]["order_id"] == "TK-BCOST-1"
        assert float(rows[0]["purchase_amount"]) == 100.0
        assert float(rows[0]["order_original_amount"]) == 300.0
        assert float(rows[0]["warehouse_operation_fee"]) == 5.0
        assert float(rows[0]["shipping_fee"]) == 10.0
        assert float(rows[0]["promotion_fee"]) == 20.0
        assert float(rows[0]["platform_commission"]) == 15.0
        assert float(rows[0]["platform_deduction_fee"]) == 3.0
        assert float(rows[0]["platform_voucher"]) == 7.0
        assert float(rows[0]["platform_service_fee"]) == 2.0
        assert float(rows[0]["platform_total_cost_itemized"]) == 57.0
        assert float(rows[0]["platform_total_cost_derived"]) == 145.0

        assert rows[1]["order_id"] == "TK-BCOST-2"
        assert float(rows[1]["purchase_amount"]) == 80.0
        assert rows[1]["order_original_amount"] is None
        assert rows[1]["warehouse_operation_fee"] is None
        assert rows[1]["shipping_fee"] is None
        assert float(rows[1]["promotion_fee"]) == 12.0
        assert float(rows[1]["platform_commission"]) == 6.0
        assert float(rows[1]["platform_deduction_fee"]) == 2.0
        assert float(rows[1]["platform_voucher"]) == 4.0
        assert float(rows[1]["platform_service_fee"]) == 1.0
        assert float(rows[1]["platform_total_cost_itemized"]) == 25.0
        assert rows[1]["platform_total_cost_derived"] is None

        assert rows[2]["order_id"] == "TK-BCOST-3"
        assert float(rows[2]["purchase_amount"]) == 81.0
        assert float(rows[2]["order_original_amount"]) == 180.0
        assert float(rows[2]["warehouse_operation_fee"]) == 9.0
        assert float(rows[2]["shipping_fee"]) == 8.0
        assert float(rows[2]["promotion_fee"]) == 5.0
        assert float(rows[2]["platform_commission"]) == 4.0
        assert float(rows[2]["platform_deduction_fee"]) == 3.0
        assert float(rows[2]["platform_voucher"]) == 2.0
        assert float(rows[2]["platform_service_fee"]) == 1.0
        assert float(rows[2]["platform_total_cost_itemized"]) == 23.0
        assert float(rows[2]["platform_total_cost_derived"]) == 60.0

        await engine.dispose()


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_orders_atomic_keeps_view_queryable_when_b_cost_amount_strings_are_malformed():
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
                    INSERT INTO b_class.fact_tiktok_orders_daily (
                        platform_code, shop_id, data_domain, granularity,
                        metric_date, period_start_date, period_end_date,
                        period_start_time, period_end_time, raw_data, header_columns,
                        data_hash, ingest_timestamp, currency_code
                    ) VALUES (
                        'tiktok', 'shop-cost-bad', 'orders', 'daily',
                        DATE '2026-04-03', DATE '2026-04-03', DATE '2026-04-03',
                        TIMESTAMP '2026-04-03 00:00:00', TIMESTAMP '2026-04-03 23:59:59',
                        '{
                            "order_id":"TK-BCOST-BAD-1",
                            "profit":"18",
                                "purchase_amount":"12-3",
                                "order_original_amount":"ABC",
                                "warehouse_operation_fee":"--5",
                                "shipping_fee":"1.2.3",
                                "promotion_fee":"promo",
                                "platform_commission":"9-9",
                                "platform_deduction_fee":"-",
                                "platform_voucher":"7..1",
                                "platform_service_fee":"--"
                            }'::jsonb,
                        '[]'::jsonb,
                        'hash-b-cost-bad-1', TIMESTAMP '2026-04-04 09:00:00', 'USD'
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
                    SELECT
                        order_id,
                        purchase_amount,
                        order_original_amount,
                        warehouse_operation_fee,
                        shipping_fee,
                        promotion_fee,
                        platform_commission,
                        platform_deduction_fee,
                        platform_voucher,
                        platform_service_fee,
                        platform_total_cost_itemized,
                        platform_total_cost_derived
                    FROM semantic.fact_orders_atomic
                    WHERE order_id = 'TK-BCOST-BAD-1'
                    """
                )
            )
            row = result.mappings().one()

        assert row["order_id"] == "TK-BCOST-BAD-1"
        assert row["purchase_amount"] is None
        assert row["order_original_amount"] is None
        assert row["warehouse_operation_fee"] is None
        assert row["shipping_fee"] is None
        assert row["promotion_fee"] is None
        assert row["platform_commission"] is None
        assert row["platform_deduction_fee"] is None
        assert row["platform_voucher"] is None
        assert row["platform_service_fee"] is None
        assert float(row["platform_total_cost_itemized"]) == 0.0
        assert row["platform_total_cost_derived"] is None

        await engine.dispose()


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_orders_atomic_falls_back_when_b_cost_alias_value_is_empty_string():
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
                    INSERT INTO b_class.fact_tiktok_orders_daily (
                        platform_code, shop_id, data_domain, granularity,
                        metric_date, period_start_date, period_end_date,
                        period_start_time, period_end_time, raw_data, header_columns,
                        data_hash, ingest_timestamp, currency_code
                    ) VALUES (
                        'tiktok', 'shop-cost-fallback', 'orders', 'daily',
                        DATE '2026-04-05', DATE '2026-04-05', DATE '2026-04-05',
                        TIMESTAMP '2026-04-05 00:00:00', TIMESTAMP '2026-04-05 23:59:59',
                        '{
                            "order_id":"TK-BCOST-FALLBACK-1",
                            "profit":"22",
                            "cogs":"",
                            "purchase_amount":"88",
                            "order_original_amount":"150",
                            "warehouse_operation_fee":"10",
                            "platform_service_fee":"   ",
                            "service_fee":"6"
                        }'::jsonb,
                        '[]'::jsonb,
                        'hash-b-cost-fallback-1', TIMESTAMP '2026-04-05 09:00:00', 'USD'
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
                        SELECT
                            order_id,
                            purchase_amount,
                            platform_service_fee,
                            platform_total_cost_itemized,
                            platform_total_cost_derived
                        FROM semantic.fact_orders_atomic
                        WHERE order_id = 'TK-BCOST-FALLBACK-1'
                        """
                    )
                )
            ).mappings().one()

        assert row["order_id"] == "TK-BCOST-FALLBACK-1"
        assert float(row["purchase_amount"]) == 88.0
        assert float(row["platform_service_fee"]) == 6.0
        assert float(row["platform_total_cost_itemized"]) == 6.0
        assert float(row["platform_total_cost_derived"]) == 30.0

        await engine.dispose()
