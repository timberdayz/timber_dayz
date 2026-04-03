import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.services.platform_shop_discovery_service import PlatformShopDiscoveryService
from modules.core.db import (
    MainAccount,
    PlatformShopDiscovery,
    ShopAccount,
    ShopAccountAlias,
    ShopAccountCapability,
)


@pytest_asyncio.fixture
async def discovery_session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.exec_driver_sql("ATTACH DATABASE ':memory:' AS core")
        await conn.run_sync(MainAccount.__table__.create)
        await conn.run_sync(ShopAccount.__table__.create)
        await conn.run_sync(ShopAccountAlias.__table__.create)
        await conn.run_sync(ShopAccountCapability.__table__.create)
        await conn.run_sync(PlatformShopDiscovery.__table__.create)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_record_manual_discovery_marks_pending_confirm_when_multiple_candidates(discovery_session):
    discovery_session.add(
        MainAccount(
            platform="shopee",
            main_account_id="hongxikeji:main",
            username="demo",
            password_encrypted="enc:demo",
            enabled=True,
        )
    )
    discovery_session.add_all(
        [
            ShopAccount(
                platform="shopee",
                shop_account_id="shopee_sg_hongxi_local",
                main_account_id="hongxikeji:main",
                store_name="HongXi SG",
                shop_region="SG",
                enabled=True,
            ),
            ShopAccount(
                platform="shopee",
                shop_account_id="shopee_sg_hongxi_local_2",
                main_account_id="hongxikeji:main",
                store_name="HongXi SG",
                shop_region="SG",
                enabled=True,
            ),
        ]
    )
    await discovery_session.commit()

    service = PlatformShopDiscoveryService()
    result = await service.record_manual_discovery(
        discovery_session,
        platform="shopee",
        main_account_id="hongxikeji:main",
        detected_store_name="HongXi SG",
        detected_platform_shop_id=None,
        detected_region="SG",
        raw_payload={"current_url": "https://seller.example/path"},
        confidence=0.8,
        source={"store_name": "dom", "region": "dom"},
        screenshot_path="temp/discovery/test.png",
    )

    assert result.match.status == "pending_confirm"
    assert result.match.candidate_count == 2
    assert result.discovery.detected_store_name == "HongXi SG"
