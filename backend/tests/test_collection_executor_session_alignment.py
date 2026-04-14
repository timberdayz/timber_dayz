from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from modules.apps.collection_center.executor_v2 import CollectionExecutorV2, CollectionResult
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
async def test_executor_open_runtime_bundle_auto_prefers_storage_state_helper(
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
    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.load_or_bootstrap_runtime_storage_state",
        AsyncMock(return_value={"cookies": [], "origins": []}),
    )

    result = await executor._open_runtime_bundle(
        session_runtime_mode="auto",
        browser=object(),
        browser_type=object(),
        platform="miaoshou",
        session_owner_id="main-1",
        runtime_account={"login_url": "https://erp.91miaoshou.com/login"},
        storage_state=None,
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


@pytest.mark.asyncio
async def test_shared_login_phase_skips_login_when_storage_state_runtime_gate_is_ready(
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
                    reason="storage_state gate confirmed",
                ),
            )
        ),
    )

    play_context, page, login_result = await executor._execute_shared_login_phase(
        task_id="task-1",
        platform="miaoshou",
        account={"account_id": "acc-1", "login_url": "https://erp.91miaoshou.com"},
        params={"_runtime_session_mode": "storage_state_fanout"},
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
        session_platform="miaoshou",
        session_account_id="acc-1",
        save_session_after_login=False,
        start_time=__import__("datetime").datetime.now(),
        total_domains_count=0,
    )

    assert login_result is None
    assert play_context is not None
    assert page is not None
    executor._execute_python_component.assert_not_awaited()


@pytest.mark.asyncio
async def test_shared_login_phase_records_ready_gate_after_login_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = CollectionExecutorV2()
    executor._update_status = AsyncMock()
    executor._check_cancelled = AsyncMock()
    executor.popup_handler.close_popups = AsyncMock()
    executor._execute_python_component = AsyncMock(return_value=True)

    page = type("Page", (), {"url": "https://seller.tiktok.com/homepage"})()

    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.probe_runtime_login_gate",
        AsyncMock(
            return_value=(
                False,
                GateResult(
                    stage="login_gate",
                    status=GateStatus.FAILED,
                    reason="login form visible",
                    current_url="https://seller.tiktok.com/account/login",
                ),
            )
        ),
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.check_login_gate_ready",
        AsyncMock(
            return_value=(
                True,
                GateResult(
                    stage="login_gate",
                    status=GateStatus.READY,
                    reason="login confirmed after refresh",
                    current_url="https://seller.tiktok.com/homepage",
                ),
            )
        ),
    )

    await executor._execute_shared_login_phase(
        task_id="task-1",
        platform="tiktok",
        account={"account_id": "acc-1", "login_url": "https://seller.tiktok.com"},
        params={
            "_runtime_session_mode": "persistent_profile",
            "_actual_execution_mode": "headless",
        },
        context=type(
            "Ctx",
            (),
            {"current_component_index": 0, "completed_domains": [], "failed_domains": [], "collected_files": []},
        )(),
        browser=object(),
        play_context=object(),
        page=page,
        adapter=object(),
        runtime_manifests=None,
        session_platform="tiktok",
        session_account_id="acc-1",
        save_session_after_login=False,
        start_time=__import__("datetime").datetime.now(),
        total_domains_count=0,
    )

    runtime_details = [
        call.kwargs.get("details")
        for call in executor._update_status.await_args_list
        if call.kwargs.get("details")
    ]
    assert any(
        details.get("step_id") == "login_gate_result"
        and details.get("login_gate_ready") is True
        and details.get("login_gate_reason") == "login confirmed after refresh"
        for details in runtime_details
    )


@pytest.mark.asyncio
async def test_shared_login_phase_persists_refreshed_storage_state_after_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = CollectionExecutorV2()
    executor._update_status = AsyncMock()
    executor._check_cancelled = AsyncMock()
    executor.popup_handler.close_popups = AsyncMock()
    executor._execute_python_component = AsyncMock(return_value=True)
    executor._ensure_login_gate_ready = AsyncMock(
        return_value=GateResult(
            stage="login_gate",
            status=GateStatus.READY,
            reason="login confirmed after refresh",
            current_url="https://erp.91miaoshou.com/welcome",
        )
    )

    saved = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "modules.apps.collection_center.executor_v2._save_session_async",
        saved,
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.probe_runtime_login_gate",
        AsyncMock(
            return_value=(
                False,
                GateResult(
                    stage="login_gate",
                    status=GateStatus.FAILED,
                    reason="login form visible",
                    current_url="https://erp.91miaoshou.com/login",
                ),
            )
        ),
    )

    page = type(
        "Page",
        (),
        {
            "url": "https://erp.91miaoshou.com/welcome",
            "context": type(
                "CtxObj",
                (),
                {"storage_state": AsyncMock(return_value={"cookies": ["fresh"], "origins": []})},
            )(),
        },
    )()

    await executor._execute_shared_login_phase(
        task_id="task-1",
        platform="miaoshou",
        account={"account_id": "acc-1", "login_url": "https://erp.91miaoshou.com"},
        params={"_runtime_session_mode": "storage_state_fanout"},
        context=type(
            "Ctx",
            (),
            {"current_component_index": 0, "completed_domains": [], "failed_domains": [], "collected_files": []},
        )(),
        browser=object(),
        play_context=object(),
        page=page,
        adapter=object(),
        runtime_manifests=None,
        session_platform="miaoshou",
        session_account_id="main-1",
        save_session_after_login=True,
        start_time=__import__("datetime").datetime.now(),
        total_domains_count=0,
    )

    saved.assert_awaited_once_with(
        "miaoshou",
        "main-1",
        {"cookies": ["fresh"], "origins": []},
    )


@pytest.mark.asyncio
async def test_executor_open_runtime_bundle_auto_falls_back_to_persistent_profile_when_storage_state_missing(
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
    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.load_or_bootstrap_runtime_storage_state",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.runtime_profile_exists",
        lambda platform, session_owner_id: True,
    )

    result = await executor._open_runtime_bundle(
        session_runtime_mode="auto",
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
async def test_execute_auto_mode_launchs_browser_when_no_browser_or_page_provided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = CollectionExecutorV2()
    launched_browser = object()
    browser_type = type("BrowserType", (), {"launch": AsyncMock(return_value=launched_browser)})()

    monkeypatch.setattr(
        executor,
        "_open_runtime_bundle",
        AsyncMock(
            return_value=type(
                "Bundle",
                (),
                {
                    "context": object(),
                    "page": object(),
                    "reused_session": True,
                    "mode": "storage_state_fanout",
                },
            )()
        ),
    )
    async def _fake_lock(**kwargs):
        return await kwargs["operation"]()

    monkeypatch.setattr(
        executor,
        "_run_with_main_account_session_lock",
        AsyncMock(side_effect=_fake_lock),
    )
    monkeypatch.setattr(
        executor,
        "_execute_shared_login_phase",
        AsyncMock(return_value=(object(), object(), None)),
    )
    monkeypatch.setattr(
        executor,
        "_execute_with_python_components",
        AsyncMock(
            return_value=CollectionResult(
                task_id="task-1",
                status="completed",
                files_collected=0,
            )
        ),
    )

    result = await executor.execute(
        task_id="task-1",
        platform="miaoshou",
        account_id="acc-1",
        account={"username": "u", "password": "p", "main_account_id": "main-1", "shop_account_id": "acc-1"},
        data_domains=["orders"],
        date_range={"start": "2025-01-01", "end": "2025-01-31"},
        granularity="daily",
        browser=None,
        page=None,
        browser_type=browser_type,
        session_runtime_mode="auto",
    )

    assert result.status == "completed"
    browser_type.launch.assert_awaited_once()


def test_build_runtime_launch_kwargs_uses_headed_when_debug_mode_enabled() -> None:
    executor = CollectionExecutorV2()

    launch_kwargs = executor._build_runtime_launch_kwargs(debug_mode=True)

    assert launch_kwargs["headless"] is False
    assert "--start-maximized" in launch_kwargs["args"]


def test_runtime_metadata_details_include_session_diagnostics() -> None:
    details = CollectionExecutorV2._runtime_metadata_details(
        params={
            "_actual_execution_mode": "headless",
            "_runtime_session_mode": "persistent_profile",
            "_runtime_session_diagnostics": {
                "session_owner_id": "main-1",
                "shop_account_id": "shop-1",
                "persistent_profile_path": "profiles/tiktok/main-1",
                "profile_contains_state": True,
                "runtime_strategy_reason": "storage_state_missing",
                "session_source": "persistent_profile",
                "probe_urls": [
                    "https://seller.tiktok.com/homepage",
                    "https://seller.tiktok.com/account/login",
                ],
            },
        },
        login_gate_ready=True,
        login_gate_reason="login confirmed",
        login_gate_url="https://seller.tiktok.com/homepage",
    )

    assert details["session_owner_id"] == "main-1"
    assert details["shop_account_id"] == "shop-1"
    assert details["persistent_profile_path"] == "profiles/tiktok/main-1"
    assert details["profile_contains_state"] is True
    assert details["runtime_strategy_reason"] == "storage_state_missing"
    assert details["session_source"] == "persistent_profile"
    assert details["probe_urls"] == [
        "https://seller.tiktok.com/homepage",
        "https://seller.tiktok.com/account/login",
    ]
