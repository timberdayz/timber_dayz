from pathlib import Path
import asyncio
import json
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock

import pytest

from modules.apps.collection_center.executor_v2 import (
    CollectionExecutorV2,
    CollectionResult,
    TaskCancelledError,
    _extract_platform_shop_context,
    _resolve_session_scope,
)


def test_execute_defines_reused_session_before_runtime_task_params_call():
    source = Path("modules/apps/collection_center/executor_v2.py").read_text(encoding="utf-8")

    reused_index = source.index("reused_session = False")
    build_params_index = source.index("params = _build_runtime_task_params(")

    assert reused_index < build_params_index


def test_resolve_session_scope_prefers_main_account_id_over_shop_account_id():
    session_owner_id, shop_account_id, use_scope = _resolve_session_scope(
        "shopee_sg_hongxi_local",
        {
            "account_id": "shopee_sg_hongxi_local",
            "main_account_id": "hongxikeji:main",
        },
    )

    assert session_owner_id == "hongxikeji:main"
    assert shop_account_id == "shopee_sg_hongxi_local"
    assert use_scope is True


def test_process_files_writes_standard_shop_identity_metadata(tmp_path, monkeypatch):
    from modules.apps.collection_center import executor_v2 as executor_module

    raw_root = tmp_path / "data" / "raw"
    source_dir = tmp_path / "downloads"
    source_dir.mkdir(parents=True)
    source_file = source_dir / "orders_export.xlsx"
    source_file.write_text("demo", encoding="utf-8")

    monkeypatch.setattr(executor_module, "get_data_raw_dir", lambda: raw_root)
    monkeypatch.setattr(
        "modules.services.catalog_scanner.register_single_file",
        lambda _path: 1,
    )

    executor = CollectionExecutorV2()

    processed = asyncio.run(
        executor._process_files(
            [str(source_file)],
            "tiktok",
            ["orders"],
            "monthly",
            account={
                "label": "TK新加坡1店",
                "account_id": "tiktok_sg_daone_mall_local",
                "shop_account_id": "tiktok_sg_daone_mall_local",
                "main_account_id": "tiktok_sg_main",
                "store_name": "DAONE Mall",
                "platform_shop_id": "",
            },
            date_range={"start_date": "2026-06-01", "end_date": "2026-06-30"},
        )
    )

    assert len(processed) == 1
    meta_path = Path(processed[0]).with_suffix(".meta.json")
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))

    collection_info = metadata["collection_info"]
    assert collection_info["main_account_id"] == "tiktok_sg_main"
    assert collection_info["shop_account_id"] == "tiktok_sg_daone_mall_local"
    assert collection_info["store_name"] == "DAONE Mall"
    assert collection_info["platform_shop_id"] is None
    assert "shop_id" in collection_info

    business_metadata = metadata["business_metadata"]
    assert business_metadata["shop_account_id"] == "tiktok_sg_daone_mall_local"
    assert business_metadata["store_name"] == "DAONE Mall"


def test_extract_platform_shop_context_reads_known_query_keys():
    payload = _extract_platform_shop_context(
        "shopee",
        "https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1227491331&shop_region=SG",
    )

    assert payload["detected_platform_shop_id"] == "1227491331"
    assert payload["detected_region"] == "SG"


@pytest.mark.asyncio
async def test_execute_requires_main_account_id_before_collection_starts():
    executor = CollectionExecutorV2()

    with pytest.raises(ValueError, match="Missing main_account_id for collection execution"):
        await executor.execute(
            task_id="task-1",
            platform="shopee",
            account_id="shop-1",
            account={"account_id": "shop-1"},
            data_domains=["products"],
            date_range={"start": "2026-04-01", "end": "2026-04-01"},
            granularity="daily",
        )


@pytest.mark.asyncio
async def test_execute_parallel_domains_requires_main_account_id_before_collection_starts():
    executor = CollectionExecutorV2()

    with pytest.raises(ValueError, match="Missing main_account_id for collection execution"):
        await executor.execute_parallel_domains(
            task_id="task-1",
            platform="shopee",
            account_id="shop-1",
            account={"account_id": "shop-1"},
            data_domains=["products"],
            date_range={"start": "2026-04-01", "end": "2026-04-01"},
            granularity="daily",
            browser=object(),
        )


@pytest.mark.asyncio
async def test_execute_shared_login_phase_receives_adapter_in_standard_execute_path(monkeypatch):
    class FakePage:
        url = "about:blank"

    class FakeContext:
        def __init__(self):
            self.browser = None

        async def new_page(self):
            return FakePage()

    class FakeBrowser:
        async def new_context(self, **kwargs):
            return FakeContext()

    executor = CollectionExecutorV2()
    executor._update_status = AsyncMock()

    monkeypatch.setattr(
        "modules.apps.collection_center.executor_v2._load_or_bootstrap_session_async",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.executor_v2._get_fingerprint_context_options_async",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.executor_v2._build_playwright_context_options_from_fingerprint",
        lambda _fp_options: {},
    )

    observed = {}

    async def fake_execute_shared_login_phase(**kwargs):
        observed["adapter"] = kwargs["adapter"]
        return kwargs["play_context"], kwargs["page"], None

    async def fake_execute_with_python_components(**kwargs):
        observed["shared_state_prepared"] = kwargs["params"].get("_main_account_shared_state_prepared")
        return "ok"

    executor._execute_shared_login_phase = fake_execute_shared_login_phase
    executor._execute_with_python_components = fake_execute_with_python_components

    result = await executor.execute(
        task_id="task-1",
        platform="shopee",
        account_id="shop-1",
        account={
            "account_id": "shop-1",
            "main_account_id": "main-1",
            "username": "demo",
            "password": "secret",
        },
        data_domains=["products"],
        date_range={"start": "2026-04-01", "end": "2026-04-01"},
        granularity="daily",
        browser=FakeBrowser(),
    )

    assert result == "ok"
    assert observed["adapter"] is not None
    assert observed["shared_state_prepared"] is True


@pytest.mark.asyncio
async def test_executor_shared_state_phase_serializes_same_main_account():
    executor = CollectionExecutorV2()
    executor._update_status = AsyncMock()

    events = []
    entered = asyncio.Event()

    async def first_operation():
        events.append("first-enter")
        entered.set()
        await asyncio.sleep(0.05)
        events.append("first-exit")
        return "first"

    async def second_operation():
        await entered.wait()
        events.append("second-enter")
        return "second"

    results = await asyncio.gather(
        executor._run_with_main_account_session_lock(
            task_id="task-1",
            platform="shopee",
            main_account_id="main-a",
            operation=first_operation,
        ),
        executor._run_with_main_account_session_lock(
            task_id="task-2",
            platform="shopee",
            main_account_id="main-a",
            operation=second_operation,
        ),
    )

    assert results == ["first", "second"]


@pytest.mark.asyncio
async def test_execute_parallel_domains_releases_account_lock_after_profile_closed(
    monkeypatch,
):
    """并行路径: 账号锁必须持有到 profile context **真正关闭**之后才释放。

    锁在 Chromium 仍占用 profile 目录时就释放 → 另一个进程可能立刻打开同一目录
    → profile 双开 → 登录态互相覆盖(Task 3 / F3)。
    """
    events = []

    class _RecordingCoordinator:
        def acquire(self, platform, main_account_id):
            coordinator = self

            class _CM:
                async def __aenter__(self):
                    coordinator.events.append("lock-acquire")
                    return None

                async def __aexit__(self, exc_type, exc, tb):
                    coordinator.events.append("lock-release")
                    return None

            return _CM()

        def is_locked(self, platform, main_account_id):
            return False

        def waiter_count(self, platform, main_account_id):
            return 0

        async def is_locked_async(self, platform, main_account_id):
            return False

        async def waiter_count_async(self, platform, main_account_id):
            return 0

    coordinator = _RecordingCoordinator()
    coordinator.events = events

    executor = CollectionExecutorV2(main_account_session_coordinator=coordinator)
    executor._update_status = AsyncMock()

    class _FakeContext:
        async def close(self):
            events.append("context-closed")

        async def cookies(self):
            return []

    class _FakePage:
        async def close(self):
            events.append("page-closed")

    async def _fake_open_runtime_bundle(**kwargs):
        events.append("profile-opened")
        return type(
            "Bundle",
            (),
            {
                "reused_session": False,
                "context": _FakeContext(),
                "page": _FakePage(),
                "mode": "persistent_profile",
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
        AsyncMock(return_value={"cookies": [], "origins": []}),
    )

    await executor.execute_parallel_domains(
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

    assert "lock-acquire" in events
    assert "lock-release" in events
    # 锁的释放必须发生在 profile context 关闭之后
    assert events.index("lock-release") > events.index("context-closed")


def test_executor_uses_platform_login_entry_service_for_formal_collection():
    source = Path("modules/apps/collection_center/executor_v2.py").read_text(encoding="utf-8")

    assert "get_platform_login_entry" in source


@pytest.mark.asyncio
async def test_executor_shared_state_phase_allows_different_main_accounts():
    executor = CollectionExecutorV2()
    executor._update_status = AsyncMock()

    first_entered = asyncio.Event()
    second_entered = asyncio.Event()

    async def first_operation():
        first_entered.set()
        await second_entered.wait()
        return "first"

    async def second_operation():
        second_entered.set()
        await first_entered.wait()
        return "second"

    results = await asyncio.wait_for(
        asyncio.gather(
            executor._run_with_main_account_session_lock(
                task_id="task-1",
                platform="shopee",
                main_account_id="main-a",
                operation=first_operation,
            ),
            executor._run_with_main_account_session_lock(
                task_id="task-2",
                platform="shopee",
                main_account_id="main-b",
                operation=second_operation,
            ),
        ),
        timeout=1,
    )

    assert results == ["first", "second"]


@pytest.mark.asyncio
async def test_execute_reloads_main_account_session_after_waiting_for_lock(
    monkeypatch: pytest.MonkeyPatch,
):
    class FakePage:
        def __init__(self, context):
            self.context = context
            self.url = "about:blank"

    class FakeContext:
        def __init__(self, version: str):
            self.version = version
            self.browser = None

        async def new_page(self):
            return FakePage(self)

        async def close(self):
            return None

    class FakeBrowser:
        def __init__(self):
            self.context_versions: list[str] = []

        async def new_context(self, **kwargs):
            storage_state = kwargs.get("storage_state") or {}
            version = storage_state.get("version", "missing")
            self.context_versions.append(version)
            return FakeContext(version)

    executor = CollectionExecutorV2()
    executor._update_status = AsyncMock()

    current_session = {"version": "stale"}
    first_phase_entered = asyncio.Event()

    async def fake_load_session(platform, account_id, account_config=None, max_age_days=30):
        return {"storage_state": dict(current_session)}

    async def fake_execute_shared_login_phase(**kwargs):
        if kwargs["task_id"] == "task-1":
            first_phase_entered.set()
            await asyncio.sleep(0.05)
            current_session["version"] = "fresh"
        return kwargs["play_context"], kwargs["page"], None

    async def fake_execute_with_python_components(**kwargs):
        return kwargs["play_context"].version

    monkeypatch.setattr(
        "modules.apps.collection_center.executor_v2._load_or_bootstrap_session_async",
        fake_load_session,
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.executor_v2._get_fingerprint_context_options_async",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.executor_v2._build_playwright_context_options_from_fingerprint",
        lambda _fp_options: {},
    )
    monkeypatch.setattr(executor, "_execute_shared_login_phase", fake_execute_shared_login_phase)
    monkeypatch.setattr(
        executor,
        "_execute_with_python_components",
        fake_execute_with_python_components,
    )

    browser = FakeBrowser()
    account = {
        "account_id": "shop-1",
        "main_account_id": "main-1",
        "username": "demo",
        "password": "secret",
    }

    first_task = asyncio.create_task(
        executor.execute(
            task_id="task-1",
            platform="tiktok",
            account_id="shop-1",
            account=account,
            data_domains=["products"],
            date_range={"start": "2026-04-01", "end": "2026-04-01"},
            granularity="daily",
            browser=browser,
        )
    )
    await first_phase_entered.wait()
    second_task = asyncio.create_task(
        executor.execute(
            task_id="task-2",
            platform="tiktok",
            account_id="shop-2",
            account={**account, "account_id": "shop-2"},
            data_domains=["products"],
            date_range={"start": "2026-04-01", "end": "2026-04-01"},
            granularity="daily",
            browser=browser,
        )
    )

    results = await asyncio.gather(first_task, second_task)

    assert results == ["stale", "fresh"]


# ---------------------------------------------------------------------------
# Task 4 / F4-8：采集异常路径不得泄漏 profile context
#
# execute() 是**两段 try**：第一段 try 的 except 分支只释放账号锁就直接 return/raise
# → 第二段的 finally 永不执行 → _cleanup_browser_runtime 被跳过 →
# Chromium 进程残留 + profile 目录的独占锁不释放 + 账号锁已释放
# → 下一个任务能双开同一 profile 目录（R6）。
# ---------------------------------------------------------------------------


class _RecordingCoordinator:
    """记录加锁/解锁时序的假协调器（与 test_main_account_session_lock 同构）。"""

    def __init__(self, events: List[str]) -> None:
        self.events = events
        self.acquired_with: List[Any] = []

    def acquire(self, platform: str, main_account_id: str):
        coordinator = self

        class _CM:
            async def __aenter__(self):
                coordinator.events.append("lock-acquire")
                coordinator.acquired_with.append((platform, main_account_id))
                return None

            async def __aexit__(self, exc_type, exc, tb):
                coordinator.events.append("lock-release")
                return None

        return _CM()

    def is_locked(self, platform: str, main_account_id: str) -> bool:
        return False

    def waiter_count(self, platform: str, main_account_id: str) -> int:
        return 0

    async def is_locked_async(self, platform: str, main_account_id: str) -> bool:
        return False

    async def waiter_count_async(self, platform: str, main_account_id: str) -> int:
        return 0


def _install_fake_profile_runtime(
    monkeypatch: pytest.MonkeyPatch,
    executor: CollectionExecutorV2,
    events: List[str],
    *,
    login_phase_error: Optional[BaseException] = None,
    diagnostics_error: Optional[BaseException] = None,
    login_result: Optional[CollectionResult] = None,
) -> Dict[str, int]:
    """装一套假的 profile 运行时，返回 close 次数计数器。

    ``diagnostics_error`` 让异常发生在 ``play_context`` **已经绑定之后**
    （``_start_browser_diagnostics``）→ 正好命中「第一段 try 的异常路径」，
    且此时 profile context 确实还开着。

    ``login_result`` 让登录阶段直接给出终态 → ``execute()`` 提前返回，
    第二段 try 根本不会执行。
    """
    state = {"context_closes": 0, "page_closes": 0}

    class _Ctx:
        async def close(self):
            state["context_closes"] += 1
            events.append("context-closed")

    class _Page:
        async def close(self):
            state["page_closes"] += 1
            events.append("page-closed")

    class _Bundle:
        reused_session = False
        mode = "persistent_profile"
        profile_path = "profiles/miaoshou/main-1"

        def __init__(self) -> None:
            self.context = _Ctx()
            self.page = _Page()

    async def _open_runtime_bundle(**kwargs):
        events.append("profile-opened")
        return _Bundle()

    async def _execute_shared_login_phase(**kwargs):
        if login_phase_error is not None:
            raise login_phase_error
        return kwargs["play_context"], kwargs["page"], login_result

    async def _start_browser_diagnostics(**kwargs):
        if diagnostics_error is not None:
            raise diagnostics_error
        return None

    monkeypatch.setattr(executor, "_open_runtime_bundle", _open_runtime_bundle)
    monkeypatch.setattr(
        executor, "_execute_shared_login_phase", _execute_shared_login_phase
    )
    monkeypatch.setattr(
        executor, "_start_browser_diagnostics", _start_browser_diagnostics
    )
    monkeypatch.setattr(
        executor,
        "_execute_with_python_components",
        AsyncMock(
            return_value=CollectionResult(
                task_id="task-1", status="completed", files_collected=0
            )
        ),
    )
    return state


async def _run_profile_collection(executor: CollectionExecutorV2) -> Any:
    return await executor.execute(
        task_id="task-1",
        platform="miaoshou",
        account_id="shop-1",
        account={
            "username": "u",
            "password": "p",
            "main_account_id": "main-1",
            "shop_account_id": "shop-1",
        },
        data_domains=["orders"],
        date_range={"start": "2025-01-01", "end": "2025-01-31"},
        granularity="daily",
        browser=object(),
        browser_type=object(),
        session_runtime_mode="persistent_profile",
    )


@pytest.mark.asyncio
async def test_execute_closes_profile_context_when_first_stage_raises(monkeypatch):
    """F4-8：第一段 try 抛异常时，profile context 仍必须被 close。

    不关的话：Chromium 进程残留 + profile 目录独占锁不释放，而账号锁已经放掉
    → 下一个任务能双开同一 profile 目录（R6）。
    """
    events: List[str] = []
    coordinator = _RecordingCoordinator(events)
    executor = CollectionExecutorV2(main_account_session_coordinator=coordinator)
    executor._update_status = AsyncMock()

    state = _install_fake_profile_runtime(
        monkeypatch,
        executor,
        events,
        diagnostics_error=RuntimeError("diagnostics boom"),
    )

    with pytest.raises(RuntimeError, match="diagnostics boom"):
        await _run_profile_collection(executor)

    assert state["context_closes"] == 1
    # 关闭必须早于释放账号锁（顺序反了就会双开同一 profile）
    assert events.index("context-closed") < events.index("lock-release")


@pytest.mark.asyncio
async def test_execute_closes_profile_context_once_on_normal_path(monkeypatch):
    """F4-8：正常路径下 profile context 只被 close 一次（幂等）。"""
    events: List[str] = []
    coordinator = _RecordingCoordinator(events)
    executor = CollectionExecutorV2(main_account_session_coordinator=coordinator)
    executor._update_status = AsyncMock()

    state = _install_fake_profile_runtime(monkeypatch, executor, events)

    result = await _run_profile_collection(executor)

    assert result.status == "completed"
    assert state["context_closes"] == 1
    assert events.index("context-closed") < events.index("lock-release")


@pytest.mark.asyncio
async def test_execute_closes_profile_context_on_cancel_path(monkeypatch):
    """F4-8：取消路径（TaskCancelledError）下 profile context 也必须被 close。"""
    events: List[str] = []
    coordinator = _RecordingCoordinator(events)
    executor = CollectionExecutorV2(main_account_session_coordinator=coordinator)
    executor._update_status = AsyncMock()

    state = _install_fake_profile_runtime(
        monkeypatch,
        executor,
        events,
        diagnostics_error=TaskCancelledError("cancelled"),
    )

    result = await _run_profile_collection(executor)

    assert result.status == "cancelled"
    assert state["context_closes"] == 1
    assert events.index("context-closed") < events.index("lock-release")


@pytest.mark.asyncio
async def test_execute_does_not_close_profile_context_twice_on_cancel(monkeypatch):
    """F4-8：登录阶段失败时 context 已被内部关过一次 → 兜底清理不能重复关。"""
    events: List[str] = []
    coordinator = _RecordingCoordinator(events)
    executor = CollectionExecutorV2(main_account_session_coordinator=coordinator)
    executor._update_status = AsyncMock()

    state = _install_fake_profile_runtime(
        monkeypatch,
        executor,
        events,
        login_phase_error=TaskCancelledError("cancelled"),
    )

    result = await _run_profile_collection(executor)

    assert result.status == "cancelled"
    # _execute_shared_login_phase 内部已关过一次 runtime_bundle.context，
    # 外层兜底清理必须幂等 → 总数仍然是 1
    assert state["context_closes"] == 1


@pytest.mark.asyncio
async def test_execute_closes_profile_context_on_early_login_result_return(monkeypatch):
    """F4-8：登录阶段直接给出终态并提前返回时，context 与账号锁都要收掉。

    提前返回 → 第二段 try 根本不执行 → 它的 finally 也不会跑。
    """
    events: List[str] = []
    coordinator = _RecordingCoordinator(events)
    executor = CollectionExecutorV2(main_account_session_coordinator=coordinator)
    executor._update_status = AsyncMock()

    state = _install_fake_profile_runtime(
        monkeypatch,
        executor,
        events,
        login_result=CollectionResult(task_id="task-1", status="failed"),
    )

    result = await _run_profile_collection(executor)

    assert result.status == "failed"
    assert state["context_closes"] == 1
    assert events.index("context-closed") < events.index("lock-release")
