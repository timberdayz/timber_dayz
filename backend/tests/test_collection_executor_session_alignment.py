from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from modules.apps.collection_center.executor_v2 import CollectionExecutorV2
from modules.apps.collection_center.transition_gates import GateResult, GateStatus


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


@pytest.mark.asyncio
async def test_shared_login_phase_skips_login_when_persistent_runtime_gate_is_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = CollectionExecutorV2()
    executor._update_status = AsyncMock()
    executor._check_cancelled = AsyncMock()
    executor.popup_handler.close_popups = AsyncMock()
    executor._execute_python_component = AsyncMock(
        side_effect=AssertionError("login component should be skipped")
    )
    executor._ensure_login_gate_ready = AsyncMock()

    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.probe_runtime_login_gate",
        AsyncMock(
            return_value=(
                True,
                GateResult(
                    stage="login_gate",
                    status=GateStatus.READY,
                    reason="login confirmed",
                ),
            )
        ),
    )

    play_context, page, login_result = await executor._execute_shared_login_phase(
        task_id="task-1",
        platform="tiktok",
        account={"account_id": "acc-1", "login_url": "https://seller.tiktok.com"},
        params={"_runtime_session_mode": "persistent_profile"},
        context=type(
            "Ctx",
            (),
            {"current_component_index": 0, "completed_domains": [], "failed_domains": [], "collected_files": []},
        )(),
        browser=object(),
        play_context=object(),
        page=object(),
        adapter=object(),
        runtime_manifests=None,
        session_platform="tiktok",
        session_account_id="acc-1",
        save_session_after_login=False,
        start_time=__import__("datetime").datetime.now(),
        total_domains_count=0,
    )

    assert login_result is None
    assert play_context is not None
    assert page is not None
    executor._execute_python_component.assert_not_awaited()


def test_build_runtime_launch_kwargs_uses_headed_when_debug_mode_enabled() -> None:
    executor = CollectionExecutorV2()

    launch_kwargs = executor._build_runtime_launch_kwargs(debug_mode=True)

    assert launch_kwargs["headless"] is False
    assert "--start-maximized" in launch_kwargs["args"]
