from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from modules.apps.collection_center.executor_v2 import CollectionExecutorV2


@pytest.mark.asyncio
async def test_executor_open_runtime_bundle_uses_persistent_profile_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = CollectionExecutorV2()
    persistent_open = AsyncMock(return_value="persistent-bundle")
    storage_open = AsyncMock(return_value="storage-bundle")

    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.open_persistent_runtime_bundle",
        persistent_open,
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.open_storage_state_runtime_bundle",
        storage_open,
    )

    result = await executor._open_runtime_bundle(
        session_runtime_mode="persistent_profile",
        browser=object(),
        browser_type=object(),
        platform="miaoshou",
        session_owner_id="main-1",
        runtime_account={"login_url": "https://erp.91miaoshou.com/login"},
        storage_state=None,
        launch_kwargs={"headless": True},
    )

    assert result == "persistent-bundle"
    persistent_open.assert_awaited_once()
    storage_open.assert_not_awaited()


@pytest.mark.asyncio
async def test_executor_open_runtime_bundle_uses_storage_state_helper_for_fanout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = CollectionExecutorV2()
    persistent_open = AsyncMock(return_value="persistent-bundle")
    storage_open = AsyncMock(return_value="storage-bundle")

    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.open_persistent_runtime_bundle",
        persistent_open,
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.open_storage_state_runtime_bundle",
        storage_open,
    )

    result = await executor._open_runtime_bundle(
        session_runtime_mode="storage_state_fanout",
        browser=object(),
        browser_type=object(),
        platform="tiktok",
        session_owner_id="main-1",
        runtime_account={"login_url": "https://seller.tiktok.com"},
        storage_state={"cookies": [], "origins": []},
        launch_kwargs={"headless": True},
    )

    assert result == "storage-bundle"
    storage_open.assert_awaited_once()
    persistent_open.assert_not_awaited()
