import pytest
from sqlalchemy import select

from backend.tests.test_collection_config_coverage_api import _seed_accounts
from modules.core.db import CollectionConfig

pytest_plugins = ("backend.tests.test_collection_config_coverage_api",)


@pytest.mark.asyncio
async def test_batch_remediation_creates_one_enabled_headless_config_per_uncovered_shop(
    collection_coverage_client,
    collection_coverage_session,
):
    await _seed_accounts(collection_coverage_session)

    response = await collection_coverage_client.post(
        "/api/collection/configs/batch-remediate",
        json={
            "shop_account_ids": ["shop-sg-1", "shop-my-1", "shop-ph-1"],
            "granularity": "daily",
        },
    )

    assert response.status_code == 200
    body = response.json()

    assert body["granularity"] == "daily"
    assert [item["shop_account_id"] for item in body["created_configs"]] == [
        "shop-my-1",
        "shop-ph-1",
    ]
    assert body["skipped_shops"] == [
        {
            "shop_account_id": "shop-sg-1",
            "reason": "already_covered",
        }
    ]

    configs = (
        await collection_coverage_session.execute(
            select(CollectionConfig).where(CollectionConfig.name.like("batch-remediate-%"))
        )
    ).scalars().all()

    assert len(configs) == 2

    my_config = next(config for config in configs if config.account_ids == ["shop-my-1"])
    assert my_config.execution_mode == "headless"
    assert my_config.is_active is True
    assert my_config.granularity == "daily"
    assert my_config.data_domains == ["orders"]
    assert my_config.sub_domains == {"orders": ["shopee", "tiktok"]}

    ph_config = next(config for config in configs if config.account_ids == ["shop-ph-1"])
    assert ph_config.execution_mode == "headless"
    assert ph_config.is_active is True
    assert ph_config.granularity == "daily"
    assert ph_config.data_domains == ["analytics", "finance", "inventory", "orders", "products"]
    assert ph_config.sub_domains == {"orders": ["shopee", "tiktok"]}


@pytest.mark.asyncio
async def test_batch_remediation_rejects_empty_shop_selection(
    collection_coverage_client,
    collection_coverage_session,
):
    await _seed_accounts(collection_coverage_session)

    response = await collection_coverage_client.post(
        "/api/collection/configs/batch-remediate",
        json={
            "shop_account_ids": [],
            "granularity": "weekly",
        },
    )

    assert response.status_code == 422
