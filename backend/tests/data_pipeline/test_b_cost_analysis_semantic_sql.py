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

    # [*] 2026-11-08: 取数改走别名表 ⇒ SQL 里不再有手写的别名清单
    #   (旧链里有 "cogs" / "采购价" / "贴单费" 这类兜底列名)。
    assert "semantic.resolve_alias" in sql_text


def test_orders_atomic_keeps_core_amount_fields_while_adding_b_cost_fields():
    sql_text = Path("sql/semantic/orders_atomic.sql").read_text(encoding="utf-8")

    assert "sales_amount" in sql_text
    assert "paid_amount" in sql_text
    assert "profit" in sql_text


def test_orders_atomic_appends_b_cost_fields_after_legacy_columns_for_replace_safety():
    sql_text = Path("sql/semantic/orders_atomic.sql").read_text(encoding="utf-8")

    select_tail = sql_text.rsplit("SELECT", 1)[-1]
    product_quantity_pos = select_tail.find("product_quantity AS product_quantity")
    purchase_amount_pos = select_tail.find("purchase_amount,")

    assert product_quantity_pos != -1
    assert purchase_amount_pos != -1
    assert purchase_amount_pos > product_quantity_pos


def test_orders_atomic_registers_only_rmb_variants_in_the_dictionary():
    """列名清单在**字典**里, 且**只登 (RMB) 变体**。

    [*] 2026-11-08 实测: 源表每个金额列都成对出现 —— ``X``(原币) 与
    ``X(RMB)``(人民币), 两者均值差约 3 倍(shopee monthly 29629 行):
    买家支付 240.11 / 72.03, 利润 27.98 / 11.06, 仓库操作费 11.56 / 4.99。
    ⇒ 裸名列是**另一个业务事实**(原币), 登记它 = 混币种。
    ⇒ 别名清单必须只登 ``(RMB)`` 变体, 且取数改走别名表。
    """
    from backend.services.semantic_field_registry import (
        ORDER_PLATFORM_ALIASES,
        ORDER_SEMANTIC_ALIASES,
    )

    registered = set()
    for aliases in ORDER_SEMANTIC_ALIASES.values():
        registered.update(aliases)
    for per_platform in ORDER_PLATFORM_ALIASES.values():
        for aliases in per_platform.values():
            registered.update(aliases)

    # 人民币口径的真实列名必须在字典里
    required_rmb_aliases = (
        "买家支付(RMB)",
        "买家实付金额(RMB)",
        "利润(RMB)",
        "采购成本(RMB)",
        "仓库操作费(RMB)",
        "广告成本(RMB)",
        "卖家支付运费(RMB)",
        "商家运费(RMB)",
        "Shopee平台佣金(RMB)",
        "TikTok 平台佣金(RMB)",
        "Shopee voucher(RMB)",
        "卖家voucher(RMB)",
        "服务费(RMB)",
        "订单原始金额(RMB)",
        "产品原价(RMB)",
        "退款金额(RMB)",
        "预估回款金额(RMB)",
        "已结算金额(RMB)",
    )
    for alias in required_rmb_aliases:
        assert alias in registered, f"字典里没登记真实人民币列名 {alias!r}"

    # ⚠ 裸名(原币列)**不许**出现在别名清单里
    bare_aliases = (
        "利润",
        "订单原始金额",
        "仓库操作费",
        "运费",
        "商家运费",
        "服务费",
        "买家支付",
        "买家实付金额",
        "卖家支付运费",
        "退款金额",
        "预估回款金额",
        "已结算金额",
        "采购金额",
        "采购成本",
        "广告成本",
        "卖家voucher",
        "Shopee voucher",
    )
    for alias in bare_aliases:
        assert alias not in registered, f"别名清单里混进了原币列 {alias!r}"

    # 取数 SQL 里也不许再手写这些裸名(只看**取数表达式**, 注释里提到列名是允许的)
    sql_text = Path("sql/semantic/orders_atomic.sql").read_text(
        encoding="utf-8", errors="replace"
    )
    for alias in bare_aliases:
        assert (
            "raw_data->>'%s'" % alias not in sql_text
        ), f"SQL 里又手写了原币列名 {alias!r}"


def test_orders_atomic_uses_required_platform_total_cost_formulas():
    normalized = _normalized_sql()

    assert (
        "coalesce(shipping_fee,0)+"
        "coalesce(promotion_fee,0)+"
        "coalesce(platform_commission,0)+"
        "coalesce(platform_deduction_fee,0)+"
        "coalesce(platform_voucher,0)+"
        "coalesce(platform_service_fee,0)" in normalized
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
                            "订单号":"TK-BCOST-1",
                            "利润(RMB)":"50",
                            "采购成本(RMB)":"100",
                            "产品原价(RMB)":"300",
                            "仓库操作费(RMB)":"5",
                            "商家运费(RMB)":"10",
                            "广告成本(RMB)":"20",
                            "TikTok 平台佣金(RMB)":"15",
                            "平台扣费(RMB)":"3",
                            "平台代金券(RMB)":"7",
                            "服务费(RMB)":"2"
                        }'::jsonb,
                        '[]'::jsonb,
                        'hash-b-cost-cn-1', TIMESTAMP '2026-04-02 09:00:00', 'USD'
                    ),
                    (
                        'tiktok', 'shop-cost-2', 'orders', 'daily',
                        DATE '2026-04-01', DATE '2026-04-01', DATE '2026-04-01',
                        TIMESTAMP '2026-04-01 00:00:00', TIMESTAMP '2026-04-01 23:59:59',
                        '{
                            "订单号":"TK-BCOST-2",
                            "利润(RMB)":"20",
                            "采购成本(RMB)":"80",
                            "广告成本(RMB)":"12",
                            "TikTok 平台佣金(RMB)":"6",
                            "平台扣费(RMB)":"2",
                            "平台代金券(RMB)":"4",
                            "服务费(RMB)":"1"
                        }'::jsonb,
                        '[]'::jsonb,
                        'hash-b-cost-cn-2', TIMESTAMP '2026-04-02 09:05:00', 'USD'
                    ),
                    (
                        'tiktok', 'shop-cost-3', 'orders', 'daily',
                        DATE '2026-04-01', DATE '2026-04-01', DATE '2026-04-01',
                        TIMESTAMP '2026-04-01 00:00:00', TIMESTAMP '2026-04-01 23:59:59',
                        '{
                            "订单号":"TK-BCOST-3",
                            "利润(RMB)":"30",
                            "采购成本(RMB)":"81",
                            "产品原价(RMB)":"180",
                            "仓库操作费(RMB)":"9",
                            "商家运费(RMB)":"8",
                            "广告成本(RMB)":"5",
                            "TikTok 平台佣金(RMB)":"4",
                            "平台扣费(RMB)":"3",
                            "平台代金券(RMB)":"2",
                            "服务费(RMB)":"1"
                        }'::jsonb,
                        '[]'::jsonb,
                        'hash-b-cost-cogs-3', TIMESTAMP '2026-04-02 09:10:00', 'USD'
                    )
                    """
                )
            )
            await session.commit()

        async with session_factory() as session:
            await execute_sql_target(session, "semantic.alias_registry")
            await execute_sql_target(
                session, "semantic.shop_identity_resolution_candidates"
            )
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
                        platform_total_cost_known_items,
                        platform_total_cost_derived
                    FROM semantic.fact_orders_atomic
                    WHERE order_id IN ('TK-BCOST-1', 'TK-BCOST-2', 'TK-BCOST-3')
                    ORDER BY order_id
                    """
                )
            )
            rows = result.mappings().all()

        assert len(rows) == 3

        # tiktok 侧只有「运费 / 推广费 / 平台佣金」三项有真实人民币列
        # (无平台代金券、无平台服务费、无平台扣费) ⇒ 已知项数就是 3。
        assert rows[0]["order_id"] == "TK-BCOST-1"
        assert float(rows[0]["purchase_amount"]) == 100.0
        assert float(rows[0]["order_original_amount"]) == 300.0
        assert float(rows[0]["warehouse_operation_fee"]) == 5.0
        assert float(rows[0]["shipping_fee"]) == 10.0
        assert float(rows[0]["promotion_fee"]) == 20.0
        assert float(rows[0]["platform_commission"]) == 15.0
        # 平台扣费 / 平台代金券 / 平台服务费 在 tiktok 侧没有对应源列
        assert rows[0]["platform_deduction_fee"] is None
        assert rows[0]["platform_voucher"] is None
        assert rows[0]["platform_service_fee"] is None
        assert float(rows[0]["platform_total_cost_itemized"]) == 45.0
        assert float(rows[0]["platform_total_cost_derived"]) == 145.0
        assert int(rows[0]["platform_total_cost_known_items"]) == 3

        assert rows[1]["order_id"] == "TK-BCOST-2"
        assert float(rows[1]["purchase_amount"]) == 80.0
        assert rows[1]["order_original_amount"] is None
        assert rows[1]["warehouse_operation_fee"] is None
        assert rows[1]["shipping_fee"] is None
        assert float(rows[1]["promotion_fee"]) == 12.0
        assert float(rows[1]["platform_commission"]) == 6.0
        assert rows[1]["platform_deduction_fee"] is None
        assert rows[1]["platform_voucher"] is None
        assert rows[1]["platform_service_fee"] is None
        assert float(rows[1]["platform_total_cost_itemized"]) == 18.0
        assert rows[1]["platform_total_cost_derived"] is None
        assert int(rows[1]["platform_total_cost_known_items"]) == 2

        assert rows[2]["order_id"] == "TK-BCOST-3"
        assert float(rows[2]["purchase_amount"]) == 81.0
        assert float(rows[2]["order_original_amount"]) == 180.0
        assert float(rows[2]["warehouse_operation_fee"]) == 9.0
        assert float(rows[2]["shipping_fee"]) == 8.0
        assert float(rows[2]["promotion_fee"]) == 5.0
        assert float(rows[2]["platform_commission"]) == 4.0
        assert rows[2]["platform_deduction_fee"] is None
        assert rows[2]["platform_voucher"] is None
        assert rows[2]["platform_service_fee"] is None
        assert float(rows[2]["platform_total_cost_itemized"]) == 17.0
        assert float(rows[2]["platform_total_cost_derived"]) == 60.0
        assert int(rows[2]["platform_total_cost_known_items"]) == 3

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
                            "订单号":"TK-BCOST-BAD-1",
                            "利润(RMB)":"18",
                                "采购成本(RMB)":"12-3",
                                "产品原价(RMB)":"ABC",
                                "仓库操作费(RMB)":"--5",
                                "商家运费(RMB)":"1.2.3",
                                "广告成本(RMB)":"promo",
                                "TikTok 平台佣金(RMB)":"9-9",
                                "平台扣费(RMB)":"-",
                                "平台代金券(RMB)":"7..1",
                                "服务费(RMB)":"--"
                            }'::jsonb,
                        '[]'::jsonb,
                        'hash-b-cost-bad-1', TIMESTAMP '2026-04-04 09:00:00', 'USD'
                    )
                    """
                )
            )
            await session.commit()

        async with session_factory() as session:
            await execute_sql_target(session, "semantic.alias_registry")
            await execute_sql_target(
                session, "semantic.shop_identity_resolution_candidates"
            )
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
                        platform_total_cost_known_items,
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
        # ⚠ 0 只是「已知项之和」; 已知项数 = 0 ⇒ 这一行的平台成本**完全不可知**。
        assert int(row["platform_total_cost_known_items"]) == 0
        assert row["platform_total_cost_derived"] is None

        await engine.dispose()


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_orders_atomic_treats_blank_alias_value_as_missing_not_fallback():
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
                            "订单号":"TK-BCOST-FALLBACK-1",
                            "利润(RMB)":"22",
                            "采购成本(RMB)":"",
                            "产品原价(RMB)":"150",
                            "仓库操作费(RMB)":"10",
                            "服务费(RMB)":"   "
                        }'::jsonb,
                        '[]'::jsonb,
                        'hash-b-cost-fallback-1', TIMESTAMP '2026-04-05 09:00:00', 'USD'
                    )
                    """
                )
            )
            await session.commit()

        async with session_factory() as session:
            await execute_sql_target(session, "semantic.alias_registry")
            await execute_sql_target(
                session, "semantic.shop_identity_resolution_candidates"
            )
            await execute_sql_target(session, "semantic.fact_orders_atomic")
            await session.commit()
            row = (
                (
                    await session.execute(
                        text(
                            """
                        SELECT
                            order_id,
                            purchase_amount,
                            platform_service_fee,
                            platform_total_cost_itemized,
                            platform_total_cost_known_items,
                            platform_total_cost_derived
                        FROM semantic.fact_orders_atomic
                        WHERE order_id = 'TK-BCOST-FALLBACK-1'
                        """
                        )
                    )
                )
                .mappings()
                .one()
            )

        # [*] 2026-11-08: 旧链会在「当前列取不到数」时**回退到下一个别名**
        #   (采购金额 → 采购价 → 产品成本 …)。新口径是「别名表穷举 + 取不到
        #   就是取不到」⇒ 空串 / 纯空白都算**缺失**, 绝不悄悄换列。
        assert row["order_id"] == "TK-BCOST-FALLBACK-1"
        assert row["purchase_amount"] is None
        # 「服务费(RMB)」是**纯空白** ⇒ 数值清洗后为 NULL。
        assert row["platform_service_fee"] is None
        assert float(row["platform_total_cost_itemized"]) == 0.0
        assert int(row["platform_total_cost_known_items"]) == 0
        assert row["platform_total_cost_derived"] is None

        await engine.dispose()
