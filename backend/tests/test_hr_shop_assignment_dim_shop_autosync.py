from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.domains.business.routers.hr_commission import _ensure_dim_shop_exists
from modules.core.db import DimPlatform, DimShop, Employee, MainAccount, ShopAccount


@pytest_asyncio.fixture
async def hr_shop_assignment_session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    async with engine.begin() as conn:
        for schema_name in ("core", "a_class", "b_class", "c_class", "finance"):
            await conn.execute(text(f"ATTACH DATABASE ':memory:' AS {schema_name}"))
        await conn.run_sync(DimPlatform.__table__.create)
        await conn.run_sync(MainAccount.__table__.create)
        await conn.run_sync(ShopAccount.__table__.create)
        await conn.run_sync(DimShop.__table__.create)
        await conn.run_sync(Employee.__table__.create)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


async def _seed_shop_account(session):
    session.add(DimPlatform(platform_code="shopee", name="Shopee", is_active=True))
    session.add(
        MainAccount(
            platform="shopee",
            main_account_id="main-1",
            username="main-user",
            password_encrypted="encrypted",
            enabled=True,
        )
    )
    session.add(Employee(id=1, employee_code="E001", name="Alice", status="active"))
    session.add(
        ShopAccount(
            platform="shopee",
            shop_account_id="shop-account-1",
            main_account_id="main-1",
            store_name="Shop One",
            platform_shop_id="shop-1",
            enabled=True,
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_ensure_dim_shop_exists_autosyncs_from_shop_account(hr_shop_assignment_session):
    await _seed_shop_account(hr_shop_assignment_session)

    shop = await _ensure_dim_shop_exists(
        hr_shop_assignment_session,
        platform_code="shopee",
        shop_id="shop-1",
    )
    await hr_shop_assignment_session.commit()

    loaded = (
        await hr_shop_assignment_session.execute(
            select(DimShop).where(
                DimShop.platform_code == "shopee",
                DimShop.shop_id == "shop-1",
            )
        )
    ).scalar_one()

    assert shop is not None
    assert loaded.shop_name == "Shop One"


def test_shop_assignment_dialog_role_is_not_disabled():
    source = Path(
        "frontend/src/domains/business/views/hr/ShopAssignment.vue"
    ).read_text(encoding="utf-8")

    assert 'v-model="form.role"' in source
    assert ':disabled="!!addForShopRow"' not in source


def test_shop_assignment_allocatable_profit_rate_uses_sync_helper():
    source = Path(
        "frontend/src/domains/business/views/hr/ShopAssignment.vue"
    ).read_text(encoding="utf-8")

    assert "setShopAllocatableProfitRate" in source
    assert '@update:model-value="(v) => setShopAllocatableProfitRate(row, v)"' in source
