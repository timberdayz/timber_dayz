from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from modules.apps.collection_center.runtime_session import RuntimeSessionScope
from tools.test_component import ComponentTester


def test_component_tester_get_session_owner_id_delegates_to_runtime_session_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tester = ComponentTester(platform="miaoshou", account_id="shop-1")

    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.resolve_runtime_session_scope",
        lambda requested_account_id, account: RuntimeSessionScope(
            session_owner_id="main-1",
            shop_account_id="shop-1",
            use_account_session_fingerprint=True,
        ),
    )

    owner_id = tester._get_session_owner_id(
        {"main_account_id": "main-1", "shop_account_id": "shop-1"}
    )

    assert owner_id == "main-1"


@pytest.mark.asyncio
async def test_component_tester_build_context_options_uses_shared_runtime_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tester = ComponentTester(platform="tiktok", account_id="shop-1")

    shared_helper = AsyncMock(
        return_value={
            "locale": "zh-CN",
            "accept_downloads": True,
            "storage_state": {"cookies": [], "origins": []},
        }
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.build_runtime_context_options",
        shared_helper,
    )

    options = await tester._build_component_browser_context_options(
        account_id="main-1",
        account_info={"login_url": "https://seller.tiktok.com"},
        storage_state={"cookies": [], "origins": []},
    )

    assert options["locale"] == "zh-CN"
    assert options["accept_downloads"] is True
    shared_helper.assert_awaited_once()
