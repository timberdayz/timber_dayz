"""库存快照视图的**行为**测试（真实 PostgreSQL 容器）。

要守住的行为
------------
增量模式下同一天可能落多批采集批次。`mart.inventory_snapshot_latest` 与
`mart.inventory_snapshot_change` 过去用 ``SUM(available_stock)`` 按
(snapshot_date, SKU×仓) 聚合 —— 同一行会被**重复累加**，库存凭空翻倍。

修法：先按 (snapshot_date, SKU×仓) 用 ROW_NUMBER 取**最新一行**，再输出。

这些用例直接执行仓库里的真实 SQL 资产（不是测试里复刻一份 SQL），
所以资产改了、行为坏了，测试就会红。
"""

from pathlib import Path
from urllib.parse import urlparse, urlunparse

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[3]

HISTORY_TABLE_DDL = """
CREATE SCHEMA IF NOT EXISTS mart;
CREATE TABLE mart.inventory_snapshot_history (
    snapshot_date DATE,
    platform_code VARCHAR(64),
    shop_id VARCHAR(64),
    product_id VARCHAR(255),
    product_name TEXT,
    platform_sku VARCHAR(255),
    sku_id VARCHAR(255),
    product_sku VARCHAR(255),
    warehouse_name VARCHAR(255),
    warehouse_code VARCHAR(255),
    available_stock NUMERIC(18, 2),
    on_hand_stock NUMERIC(18, 2),
    reserved_stock NUMERIC(18, 2),
    in_transit_stock NUMERIC(18, 2),
    stockout_qty NUMERIC(18, 2),
    reorder_point NUMERIC(18, 2),
    safety_stock NUMERIC(18, 2),
    unit_cost NUMERIC(18, 2),
    inventory_value NUMERIC(18, 2),
    observed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ,
    checklist_sales_7d NUMERIC(18, 2),
    checklist_sales_30d NUMERIC(18, 2),
    checklist_sales_60d NUMERIC(18, 2),
    checklist_sales_90d NUMERIC(18, 2),
    currency_code VARCHAR(3),
    source_file_id INTEGER,
    ingest_timestamp TIMESTAMPTZ
);
"""

# 同一 (snapshot_date, SKU×仓) 的两批采集：库存从 10 变成 12
TWO_BATCH_ROWS = """
INSERT INTO mart.inventory_snapshot_history (
    snapshot_date, platform_code, shop_id, product_id, product_name,
    platform_sku, sku_id, product_sku, warehouse_name, warehouse_code,
    available_stock, on_hand_stock, reserved_stock, in_transit_stock,
    stockout_qty, reorder_point, safety_stock, unit_cost, inventory_value,
    observed_at, created_at, checklist_sales_7d, checklist_sales_30d,
    checklist_sales_60d, checklist_sales_90d, currency_code, source_file_id,
    ingest_timestamp
) VALUES
(
    DATE '2026-10-24', 'miaoshou', 'xihong', 'P-1', '测试商品',
    'PLAT-1', 'S-1', 'SKU-1', '新加坡', 'WH-1',
    10, 10, 0, 0, 0, 0, 0, 20, 200,
    TIMESTAMPTZ '2026-10-20 10:00:00+00', TIMESTAMPTZ '2025-01-01 10:00:00+00',
    0, 1, 2, 3, 'CNY', 1001, TIMESTAMPTZ '2026-10-21 16:15:00+00'
),
(
    DATE '2026-10-24', 'miaoshou', 'xihong', 'P-1', '测试商品',
    'PLAT-1', 'S-1', 'SKU-1', '新加坡', 'WH-1',
    12, 12, 0, 0, 0, 0, 0, 20, 240,
    TIMESTAMPTZ '2026-10-23 10:00:00+00', TIMESTAMPTZ '2025-01-01 10:00:00+00',
    0, 2, 3, 4, 'CNY', 1002, TIMESTAMPTZ '2026-10-24 04:39:00+00'
);
"""


async def _build_views(session):
    from backend.services.data_pipeline.sql_loader import split_sql_statements

    for statement in split_sql_statements(HISTORY_TABLE_DDL):
        await session.execute(text(statement))
    for asset in (
        "sql/mart/inventory_snapshot_latest.sql",
        "sql/mart/inventory_snapshot_change.sql",
    ):
        asset_sql = (REPO_ROOT / asset).read_text(encoding="utf-8")
        for statement in split_sql_statements(asset_sql):
            await session.execute(text(statement))
    await session.commit()


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_latest_view_does_not_double_count_same_day_batches():
    """同一天两批采集 → latest 视图只能有一行，且是最新那批的库存。"""
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:15") as pg:
        async_url = urlunparse(
            urlparse(pg.get_connection_url())._replace(scheme="postgresql+asyncpg")
        )
        engine = create_async_engine(async_url, echo=False)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            await _build_views(session)
            await session.execute(text(TWO_BATCH_ROWS))
            await session.commit()

            result = await session.execute(
                text(
                    """
                    SELECT available_stock, on_hand_stock, inventory_value,
                           observed_at, checklist_sales_90d
                    FROM mart.inventory_snapshot_latest
                    WHERE platform_code = 'miaoshou'
                      AND platform_sku = 'PLAT-1'
                      AND warehouse_name = '新加坡'
                    """
                )
            )
            rows = result.mappings().all()

            assert len(rows) == 1, "同一 SKU×仓 只能有一行，不能因多批采集而重复"
            row = rows[0]
            # 12 = 最新批次；22 = 旧实现的重复累加
            assert float(row["available_stock"]) == 12.0
            assert float(row["on_hand_stock"]) == 12.0
            assert float(row["inventory_value"]) == 240.0
            # 排序键换成 observed_at 后，取到的应是行级时间戳较新的那批
            assert row["observed_at"] == pytest.approx(
                _as_aware("2026-10-23 10:00:00+00")
            )
            assert float(row["checklist_sales_90d"]) == 4.0

        await engine.dispose()


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_change_view_does_not_double_count_same_day_batches():
    """change 视图同理：stock_delta 不能被同日多批放大。"""
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:15") as pg:
        async_url = urlunparse(
            urlparse(pg.get_connection_url())._replace(scheme="postgresql+asyncpg")
        )
        engine = create_async_engine(async_url, echo=False)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            await _build_views(session)
            await session.execute(text(TWO_BATCH_ROWS))
            await session.commit()

            result = await session.execute(
                text(
                    """
                    SELECT available_stock, on_hand_stock, inventory_value
                    FROM mart.inventory_snapshot_change
                    WHERE platform_code = 'miaoshou'
                      AND platform_sku = 'PLAT-1'
                      AND warehouse_name = '新加坡'
                    """
                )
            )
            rows = result.mappings().all()

            assert len(rows) == 1
            row = rows[0]
            assert float(row["available_stock"]) == 12.0
            assert float(row["on_hand_stock"]) == 12.0
            assert float(row["inventory_value"]) == 240.0

        await engine.dispose()


def _as_aware(text_value: str):
    from datetime import datetime

    return datetime.fromisoformat(text_value)
