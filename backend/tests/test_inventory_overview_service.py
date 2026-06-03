from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.services.inventory.overview_service import InventoryOverviewService
from modules.core.db import FactProductMetric


@pytest_asyncio.fixture
async def inventory_overview_session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(FactProductMetric.__table__.create)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_inventory_overview_summary_uses_latest_snapshot_per_sku(inventory_overview_session):
    session = inventory_overview_session
    session.add_all(
        [
            FactProductMetric(
                platform_code="shopee",
                shop_id="shop-1",
                platform_sku="SKU-1",
                metric_date=date(2026, 6, 1),
                metric_type="inventory",
                granularity="daily",
                data_domain="inventory",
                stock=5,
                price=10,
                updated_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
            ),
            FactProductMetric(
                platform_code="shopee",
                shop_id="shop-1",
                platform_sku="SKU-1",
                metric_date=date(2026, 6, 2),
                metric_type="inventory",
                granularity="daily",
                data_domain="inventory",
                stock=12,
                price=10,
                updated_at=datetime(2026, 6, 2, tzinfo=timezone.utc),
            ),
            FactProductMetric(
                platform_code="tiktok",
                shop_id="shop-2",
                platform_sku="SKU-2",
                metric_date=date(2026, 6, 2),
                metric_type="inventory",
                granularity="daily",
                data_domain="inventory",
                stock=0,
                price=8,
                updated_at=datetime(2026, 6, 2, tzinfo=timezone.utc),
            ),
        ]
    )
    await session.commit()

    summary = await InventoryOverviewService(session).get_summary()

    assert summary.total_products == 2
    assert summary.total_stock == 12
    assert summary.out_of_stock_count == 1
    assert summary.low_stock_count == 1


@pytest.mark.asyncio
async def test_inventory_overview_products_paginates_latest_snapshots(inventory_overview_session):
    session = inventory_overview_session
    for day in (1, 2):
        session.add(
            FactProductMetric(
                platform_code="shopee",
                shop_id="shop-1",
                platform_sku="SKU-1",
                metric_date=date(2026, 6, day),
                metric_type="inventory",
                granularity="daily",
                data_domain="inventory",
                stock=day,
                price=10,
                product_name="Product 1",
                updated_at=datetime(2026, 6, day, tzinfo=timezone.utc),
            )
        )
    session.add_all(
        [
            FactProductMetric(
                platform_code="shopee",
                shop_id="shop-1",
                platform_sku="SKU-2",
                metric_date=date(2026, 6, 2),
                metric_type="inventory",
                granularity="daily",
                data_domain="inventory",
                stock=20,
                price=11,
                product_name="Product 2",
                updated_at=datetime(2026, 6, 2, tzinfo=timezone.utc),
            ),
            FactProductMetric(
                platform_code="shopee",
                shop_id="shop-1",
                platform_sku="SKU-3",
                metric_date=date(2026, 6, 2),
                metric_type="inventory",
                granularity="daily",
                data_domain="inventory",
                stock=30,
                price=12,
                product_name="Product 3",
                updated_at=datetime(2026, 6, 2, tzinfo=timezone.utc),
            ),
        ]
    )
    await session.commit()

    result = await InventoryOverviewService(session).get_products(page=2, page_size=1)

    assert result.total == 3
    assert result.page == 2
    assert len(result.data) == 1


@pytest.mark.asyncio
async def test_inventory_overview_summary_does_not_mix_products_domain_rows(inventory_overview_session):
    session = inventory_overview_session
    session.add_all(
        [
            FactProductMetric(
                platform_code="miaoshou",
                shop_id="shop-1",
                platform_sku="INV-1",
                metric_date=date(2026, 6, 2),
                metric_type="inventory",
                granularity="snapshot",
                data_domain="inventory",
                stock=8,
                price=10,
                updated_at=datetime(2026, 6, 2, tzinfo=timezone.utc),
            ),
            FactProductMetric(
                platform_code="miaoshou",
                shop_id="shop-1",
                platform_sku="PROD-1",
                metric_date=date(2026, 6, 2),
                metric_type="product",
                granularity="daily",
                data_domain="products",
                stock=999,
                price=1,
                updated_at=datetime(2026, 6, 2, tzinfo=timezone.utc),
            ),
        ]
    )
    await session.commit()

    summary = await InventoryOverviewService(session).get_summary()

    assert summary.total_products == 1
    assert summary.total_stock == 8
