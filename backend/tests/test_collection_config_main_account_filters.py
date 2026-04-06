import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from modules.core.db import CollectionConfig, MainAccount


@pytest_asyncio.fixture
async def collection_config_main_account_engine():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    async with engine.begin() as conn:
        for schema_name in ("core", "a_class", "b_class", "c_class", "finance"):
            await conn.execute(text(f"ATTACH DATABASE ':memory:' AS {schema_name}"))
        await conn.run_sync(MainAccount.__table__.create)
        await conn.run_sync(CollectionConfig.__table__.create)

    yield engine
    await engine.dispose()


@pytest.fixture
def collection_config_main_account_session_factory(collection_config_main_account_engine):
    return async_sessionmaker(collection_config_main_account_engine, expire_on_commit=False)


@pytest.mark.asyncio
async def test_collection_config_model_requires_main_account_id_column():
    assert "main_account_id" in CollectionConfig.__table__.c


@pytest.mark.asyncio
async def test_collection_config_allows_same_name_for_different_main_accounts(
    collection_config_main_account_session_factory,
):
    async with collection_config_main_account_session_factory() as session:
        session.add_all(
            [
                MainAccount(
                    platform="shopee",
                    main_account_id="main-shopee-a",
                    main_account_name="Shopee Main A",
                    username="main-a",
                    password_encrypted="enc",
                    enabled=True,
                ),
                MainAccount(
                    platform="shopee",
                    main_account_id="main-shopee-b",
                    main_account_name="Shopee Main B",
                    username="main-b",
                    password_encrypted="enc",
                    enabled=True,
                ),
            ]
        )
        await session.flush()

        session.add(
            CollectionConfig(
                name="shopee-main-scope-v1",
                platform="shopee",
                main_account_id="main-shopee-a",
                account_ids=["shop-a-1"],
                data_domains=["orders"],
                sub_domains=None,
                granularity="daily",
                date_range_type="yesterday",
                execution_mode="headless",
                schedule_enabled=False,
                schedule_cron=None,
                retry_count=3,
                is_active=True,
            )
        )
        session.add(
            CollectionConfig(
                name="shopee-main-scope-v1",
                platform="shopee",
                main_account_id="main-shopee-b",
                account_ids=["shop-b-1"],
                data_domains=["orders"],
                sub_domains=None,
                granularity="daily",
                date_range_type="yesterday",
                execution_mode="headless",
                schedule_enabled=False,
                schedule_cron=None,
                retry_count=3,
                is_active=True,
            )
        )

        try:
            await session.commit()
        except IntegrityError as exc:  # pragma: no cover - current failure path before implementation
            pytest.fail(f"configs should be unique per platform + main_account_id + name: {exc}")
