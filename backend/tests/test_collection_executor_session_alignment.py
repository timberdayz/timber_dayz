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
        "modules.apps.collection_center.runtime_session.load_runtime_session_candidate",
        AsyncMock(
            return_value=type(
                "Candidate",
                (),
                {
                    "storage_state": {"cookies": [], "origins": []},
                    "metadata": {},
                    "manual_seeded": False,
                },
            )()
        ),
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
async def test_shared_login_phase_does_not_probe_runtime_gate_before_login_component(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = CollectionExecutorV2()
    executor._update_status = AsyncMock()
    executor._check_cancelled = AsyncMock()
    executor.popup_handler.close_popups = AsyncMock()
    executor._execute_python_component = AsyncMock(return_value=True)
    executor._ensure_login_gate_ready = AsyncMock()

    probe_mock = AsyncMock()
    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.probe_runtime_login_gate",
        probe_mock,
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
    executor._execute_python_component.assert_awaited_once()
    probe_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_shared_login_phase_primes_page_before_login_component(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = CollectionExecutorV2()
    executor._update_status = AsyncMock()
    executor._check_cancelled = AsyncMock()
    executor.popup_handler.close_popups = AsyncMock()
    executor._execute_python_component = AsyncMock(return_value=True)
    executor._ensure_login_gate_ready = AsyncMock()

    order: list[str] = []

    async def _prime(page, platform, account):
        order.append("prime")

    async def _execute_component(*args, **kwargs):
        order.append("login")
        return True

    monkeypatch.setattr(executor, "_prime_runtime_page_for_login_gate", _prime)
    monkeypatch.setattr(executor, "_execute_python_component", _execute_component)

    await executor._execute_shared_login_phase(
        task_id="task-1",
        platform="shopee",
        account={"account_id": "acc-1", "login_url": "https://seller.shopee.cn/account/signin"},
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
        session_platform="shopee",
        session_account_id="main-1",
        save_session_after_login=False,
        start_time=__import__("datetime").datetime.now(),
        total_domains_count=0,
    )

    assert order == ["prime", "login"]


@pytest.mark.asyncio
async def test_shared_login_phase_does_not_probe_storage_state_runtime_gate_before_login_component(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = CollectionExecutorV2()
    executor._update_status = AsyncMock()
    executor._check_cancelled = AsyncMock()
    executor.popup_handler.close_popups = AsyncMock()
    executor._execute_python_component = AsyncMock(return_value=True)
    executor._ensure_login_gate_ready = AsyncMock()

    probe_mock = AsyncMock()
    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.probe_runtime_login_gate",
        probe_mock,
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
    executor._execute_python_component.assert_awaited_once()
    probe_mock.assert_not_awaited()


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
        executor,
        "_wait_and_capture_high_quality_tiktok_session",
        AsyncMock(return_value={"cookies": ["fresh"], "origins": []}),
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
async def test_wait_and_capture_high_quality_tiktok_session_waits_for_stable_quality(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = CollectionExecutorV2()

    states = [
        {"cookies": [{"name": "ttwid", "domain": ".tiktokshopglobalselling.com", "path": "/"}], "origins": []},
        {
            "cookies": [
                {"name": "sessionid", "domain": ".tiktokshopglobalselling.com", "path": "/"},
                {"name": "sid_tt", "domain": ".tiktokshopglobalselling.com", "path": "/"},
                {"name": "passport_csrf_token", "domain": ".tiktokshopglobalselling.com", "path": "/"},
                {"name": "user_oec_info", "domain": "seller.us.tiktokshopglobalselling.com", "path": "/"},
                {"name": "global_seller_id_unified_seller_env", "domain": ".tiktokshopglobalselling.com", "path": "/"},
                {"name": "app_id_unified_seller_env", "domain": ".tiktokshopglobalselling.com", "path": "/"},
                {"name": "oec_seller_id_unified_seller_env", "domain": ".tiktokshopglobalselling.com", "path": "/"},
                {"name": "i18next", "domain": "seller.us.tiktokshopglobalselling.com", "path": "/"},
                {"name": "ATLAS_LANG", "domain": "seller.us.tiktokshopglobalselling.com", "path": "/"},
                {"name": "ttwid", "domain": ".tiktokshopglobalselling.com", "path": "/"},
                {"name": "msToken", "domain": "seller.us.tiktokshopglobalselling.com", "path": "/"},
                {"name": "passport_auth_status", "domain": ".tiktokshopglobalselling.com", "path": "/"},
            ],
            "origins": [],
        },
    ]

    page = type(
        "Page",
        (),
        {
            "context": object(),
            "wait_for_timeout": AsyncMock(),
        },
    )()

    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.check_login_gate_ready",
        AsyncMock(side_effect=[
            (False, GateResult(stage="login_gate", status=GateStatus.FAILED, reason="bootstrapping")),
            (True, GateResult(stage="login_gate", status=GateStatus.READY, reason="ready")),
            (True, GateResult(stage="login_gate", status=GateStatus.READY, reason="ready")),
            (True, GateResult(stage="login_gate", status=GateStatus.READY, reason="ready")),
        ]),
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.read_context_storage_state",
        AsyncMock(side_effect=[states[0], states[1], states[1], states[1]]),
    )

    state = await executor._wait_and_capture_high_quality_tiktok_session(
        page=page,
        session_platform="tiktok",
        session_account_id="acc-1",
        timeout_ms=1000,
        poll_ms=1,
        stable_hits_required=3,
    )

    assert state == states[1]


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


@pytest.mark.asyncio
async def test_execute_parallel_domains_uses_auto_runtime_strategy_for_shared_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = CollectionExecutorV2()
    executor._update_status = AsyncMock()
    executor._process_files = AsyncMock(return_value=[])

    class _DummyLock:
        async def __aenter__(self):
            return None

        async def __aexit__(self, exc_type, exc, tb):
            return None

    executor.main_account_session_coordinator.acquire = lambda platform, main_account_id: _DummyLock()
    executor.main_account_session_coordinator.is_locked = lambda platform, main_account_id: False
    executor.main_account_session_coordinator.waiter_count = lambda platform, main_account_id: 0

    observed = {}

    async def _fake_open_runtime_bundle(**kwargs):
        observed.update(kwargs)
        return type(
            "Bundle",
            (),
            {
                "reused_session": False,
                "context": type("Ctx", (), {"close": AsyncMock(), "cookies": AsyncMock(return_value=[])})(),
                "page": type("Page", (), {"close": AsyncMock()})(),
                "mode": "storage_state_fanout",
            },
        )()

    monkeypatch.setattr(executor, "_open_runtime_bundle", _fake_open_runtime_bundle)
    monkeypatch.setattr(executor, "_ensure_login_gate_ready", AsyncMock())
    monkeypatch.setattr(
        executor,
        "_run_runtime_manifest_component",
        AsyncMock(return_value=type("R", (), {"success": True})()),
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.executor_v2.runtime_session.snapshot_runtime_storage_state",
        AsyncMock(return_value={"cookies": [], "origins": []}),
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.executor_v2._record_platform_shop_discovery_async",
        AsyncMock(),
    )
    monkeypatch.setattr(
        executor,
        "_wait_and_capture_high_quality_tiktok_session",
        AsyncMock(
            return_value={
                "cookies": [
                    {"name": "sessionid", "domain": ".tiktokshopglobalselling.com", "path": "/"},
                    {"name": "sid_tt", "domain": ".tiktokshopglobalselling.com", "path": "/"},
                    {"name": "passport_csrf_token", "domain": ".tiktokshopglobalselling.com", "path": "/"},
                    {"name": "user_oec_info", "domain": "seller.tiktokshopglobalselling.com", "path": "/"},
                    {"name": "global_seller_id_unified_seller_env", "domain": ".tiktokshopglobalselling.com", "path": "/"},
                    {"name": "app_id_unified_seller_env", "domain": ".tiktokshopglobalselling.com", "path": "/"},
                    {"name": "oec_seller_id_unified_seller_env", "domain": ".tiktokshopglobalselling.com", "path": "/"},
                    {"name": "ttwid", "domain": ".tiktokshopglobalselling.com", "path": "/"},
                    {"name": "ATLAS_LANG", "domain": "seller.tiktokshopglobalselling.com", "path": "/"},
                    {"name": "i18next", "domain": "seller.tiktokshopglobalselling.com", "path": "/"},
                    {"name": "msToken", "domain": "seller.tiktokshopglobalselling.com", "path": "/"},
                    {"name": "passport_auth_status", "domain": ".tiktokshopglobalselling.com", "path": "/"},
                ],
                "origins": [],
            }
        ),
    )

    result = await executor.execute_parallel_domains(
        task_id="task-1",
        platform="tiktok",
        account_id="shop-1",
        account={
            "account_id": "shop-1",
            "shop_account_id": "shop-1",
            "main_account_id": "main-1",
            "login_url": "https://seller.tiktok.com/account/login",
        },
        data_domains=[],
        date_range={"start": "2025-01-01", "end": "2025-01-31"},
        granularity="daily",
        browser=object(),
        browser_type=object(),
        max_parallel=3,
        debug_mode=False,
        runtime_manifests={"login": {}, "exports_by_domain": {}},
    )

    assert result.status == "failed"
    assert result.error_message == "No data domains provided"
    assert observed["session_runtime_mode"] == "auto"
