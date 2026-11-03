from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from modules.apps.collection_center.executor_v2 import (
    CollectionExecutorV2,
    CollectionResult,
    VerificationRequiredError,
)
from modules.apps.collection_center.transition_gates import GateResult, GateStatus


REPO_ROOT = Path(__file__).resolve().parents[2]


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


# ---------------------------------------------------------------------------
# Task 4 / F4-9：模式判定收敛到一处
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_passes_resolved_runtime_mode_to_open_runtime_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """F4-9：``execute()`` 解析一次模式，并把**解析后的**模式传给 bundle 打开器。

    前置校验与「真正开 profile 目录」必须看到同一个模式结论，否则会出现
    「校验按 auto 放行、实际却走 profile」的脱节。
    """
    executor = CollectionExecutorV2()
    executor._update_status = AsyncMock()

    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.runtime_profile_exists",
        lambda platform, session_owner_id: True,
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.executor_v2._manual_storage_state_exists",
        lambda platform, account_id: False,
    )

    observed: dict = {}

    class _Ctx:
        async def close(self):
            return None

    class _Page:
        async def close(self):
            return None

    class _Bundle:
        reused_session = False
        mode = "persistent_profile"
        profile_path = "profiles/miaoshou/main-1"

        def __init__(self) -> None:
            self.context = _Ctx()
            self.page = _Page()

    async def _fake_open_runtime_bundle(**kwargs):
        observed["session_runtime_mode"] = kwargs.get("session_runtime_mode")
        observed["resolved_mode"] = kwargs.get("resolved_mode")
        return _Bundle()

    monkeypatch.setattr(executor, "_open_runtime_bundle", _fake_open_runtime_bundle)
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
                task_id="task-1", status="completed", files_collected=0
            )
        ),
    )
    monkeypatch.setattr(executor, "_cleanup_browser_runtime", AsyncMock())

    await executor.execute(
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
        session_runtime_mode="auto",
    )

    # auto 解析成 persistent_profile → 传下去的是**解析后**的模式，不是原始的 "auto"
    assert observed["session_runtime_mode"] == "persistent_profile"
    assert observed["resolved_mode"] is not None
    assert observed["resolved_mode"].mode == "persistent_profile"


@pytest.mark.asyncio
async def test_execute_raises_clear_error_when_profile_mode_lacks_browser_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """F4-9：走持久化 profile 但没有 browser_type → 清晰的 ValueError，不是 AttributeError。"""
    executor = CollectionExecutorV2()
    executor._update_status = AsyncMock()

    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.runtime_profile_exists",
        lambda platform, session_owner_id: True,
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.executor_v2._manual_storage_state_exists",
        lambda platform, account_id: False,
    )

    with pytest.raises(ValueError) as excinfo:
        await executor.execute(
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
            browser_type=None,
            session_runtime_mode="auto",
        )

    message = str(excinfo.value)
    assert "browser_type" in message
    assert "profile" in message
    # 必须是 ValueError（不是 AttributeError）
    assert not isinstance(excinfo.value, AttributeError)


@pytest.mark.asyncio
async def test_open_runtime_bundle_raises_clear_error_without_browser_type() -> None:
    """F4-9：直接调用 ``_open_runtime_bundle`` 时同样给出清晰的中文 ValueError。"""
    executor = CollectionExecutorV2()

    with pytest.raises(ValueError) as excinfo:
        await executor._open_runtime_bundle(
            session_runtime_mode="persistent_profile",
            browser=object(),
            browser_type=None,
            platform="miaoshou",
            session_owner_id="main-1",
            runtime_account={"login_url": "https://erp.91miaoshou.com/login"},
            storage_state=None,
            launch_kwargs={"headless": True},
        )

    message = str(excinfo.value)
    assert "browser_type" in message
    assert "profile" in message


@pytest.mark.asyncio
async def test_headful_profile_fallback_keeps_runtime_page_aligned_to_profile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """有头回退走 profile 后：runtime page 必须来自**持久 context**，且保留 viewport。

    原用例针对 ``_recreate_runtime_page_with_saved_session``（读会话文件 →
    ``browser.new_context`` 注入指纹），该路径已随 Task 4.5 删除（会话文件不再是
    载体）。此处改为钉住新契约：回退在**同一个 profile 目录**上开持久 context，
    viewport 沿用 runtime 策略，指纹覆盖项按 R8 剥离。

    profile 目录用 ``tmp_path``（评审 F13）：``profiles/`` 被 .gitignore 忽略，
    用仓库真实路径的话，一旦替身真的建目录就会在仓库里留下垃圾目录。
    """
    executor = CollectionExecutorV2()
    executor._ensure_login_gate_ready = AsyncMock()
    executor._run_runtime_manifest_component = AsyncMock(
        return_value=SimpleNamespace(success=True)
    )

    captured: list[dict] = []

    class _FakeContext:
        pages: list = []

        async def new_page(self):
            return object()

    class _FakeBrowserType:
        async def launch_persistent_context(self, **kwargs):
            captured.append(dict(kwargs))
            return _FakeContext()

    async def _fake_build_runtime_context_options(**kwargs):
        return {
            "locale": "zh-CN",
            "viewport": {"width": 2880, "height": 1800},
            "accept_downloads": True,
        }

    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.build_runtime_context_options",
        _fake_build_runtime_context_options,
    )

    result = await executor._run_headful_login_fallback(
        task_id="task-1",
        platform="miaoshou",
        account={"account_id": "acc-1", "login_url": "https://erp.91miaoshou.com"},
        params={"params": {}},
        browser=None,
        old_context=object(),
        session_platform="miaoshou",
        session_account_id="acc-1",
        runtime_manifests={"login": {"component": "login"}},
        proxy=None,
        browser_type=_FakeBrowserType(),
        profile_path=str(tmp_path / "profiles" / "miaoshou" / "acc-1"),
        launch_kwargs={"headless": True},
    )

    assert result[0] is True
    # 有头阶段：持久 context + 保留 viewport
    assert captured[0]["viewport"] == {"width": 2880, "height": 1800}
    assert captured[0]["user_data_dir"].endswith("acc-1")
    assert captured[0]["headless"] is False


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
async def test_shared_login_phase_applies_interaction_viewport_after_login_gate_in_headless_mode(
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
            reason="ready",
            current_url="https://seller.shopee.cn/?cnsc_shop_id=1",
        )
    )

    order: list[str] = []

    async def _prime(page, platform, account):
        order.append("prime")

    async def _apply_viewport(page, params):
        order.append("viewport")

    monkeypatch.setattr(executor, "_prime_runtime_page_for_login_gate", _prime)
    monkeypatch.setattr(executor, "_apply_runtime_interaction_viewport", _apply_viewport)

    await executor._execute_shared_login_phase(
        task_id="task-1",
        platform="shopee",
        account={"account_id": "acc-1", "login_url": "https://seller.shopee.cn/account/signin"},
        params={"_runtime_session_mode": "persistent_profile", "_actual_execution_mode": "headless"},
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

    assert order == ["prime", "viewport"]


@pytest.mark.asyncio
async def test_shared_login_phase_applies_interaction_viewport_in_headed_mode(
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
            reason="ready",
            current_url="https://seller.shopee.cn/?cnsc_shop_id=1",
        )
    )

    order: list[str] = []

    async def _prime(page, platform, account):
        order.append("prime")

    async def _apply_viewport(page, params):
        order.append("viewport")

    monkeypatch.setattr(executor, "_prime_runtime_page_for_login_gate", _prime)
    monkeypatch.setattr(executor, "_apply_runtime_interaction_viewport", _apply_viewport)

    await executor._execute_shared_login_phase(
        task_id="task-1",
        platform="shopee",
        account={"account_id": "acc-1", "login_url": "https://seller.shopee.cn/account/signin"},
        params={"_runtime_session_mode": "persistent_profile", "_actual_execution_mode": "headed"},
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

    assert order == ["prime", "viewport"]


@pytest.mark.asyncio
async def test_apply_runtime_interaction_viewport_applies_standard_size_in_headed_mode() -> None:
    page = type(
        "Page",
        (),
        {
            "calls": [],
            "set_viewport_size": AsyncMock(),
        },
    )()

    await CollectionExecutorV2._apply_runtime_interaction_viewport(
        page,
        {"_runtime_session_mode": "persistent_profile", "_actual_execution_mode": "headed"},
    )

    page.set_viewport_size.assert_awaited_once()


@pytest.mark.asyncio
async def test_apply_runtime_interaction_viewport_applies_standard_size_in_headless_mode() -> None:
    page = type(
        "Page",
        (),
        {
            "set_viewport_size": AsyncMock(),
        },
    )()

    await CollectionExecutorV2._apply_runtime_interaction_viewport(
        page,
        {"_runtime_session_mode": "persistent_profile", "_actual_execution_mode": "headless"},
    )

    page.set_viewport_size.assert_awaited_once()


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
async def test_shared_login_phase_does_not_write_session_file_after_login(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """[Task 5 / R5] 登录后**不得**再写会话文件。

    登录态只由 Chromium 持久 profile 承载；顺序路径登录后的
    ``_save_session_async`` 落盘已删除 → ``data/sessions`` 不再产生新文件。
    """
    from modules.utils.sessions import session_manager as session_manager_module

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(session_manager_module, "REPO_ROOT", repo_root)

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

    saved.assert_not_awaited()
    sessions_dir = repo_root / "data" / "sessions"
    # 验收口径：data/sessions 下**不产生新文件**（空目录不算）
    assert [p for p in sessions_dir.rglob("*") if p.is_file()] == []


@pytest.mark.asyncio
async def test_shared_login_phase_skips_blocking_tiktok_session_persist_for_reused_persistent_profile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from modules.utils.sessions import session_manager as session_manager_module

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(session_manager_module, "REPO_ROOT", repo_root)

    executor = CollectionExecutorV2()
    executor._update_status = AsyncMock()
    executor._check_cancelled = AsyncMock()
    executor.popup_handler.close_popups = AsyncMock()
    executor._execute_python_component = AsyncMock(return_value=True)
    executor._ensure_login_gate_ready = AsyncMock(
        return_value=GateResult(
            stage="login_gate",
            status=GateStatus.READY,
            reason="logged-in markers confirmed",
            current_url="https://seller.tiktokshopglobalselling.com/homepage?shop_region=MY",
        )
    )

    wait_capture = AsyncMock(side_effect=AssertionError("should not block on session persist"))
    saved = AsyncMock()
    monkeypatch.setattr(executor, "_wait_and_capture_high_quality_tiktok_session", wait_capture)
    monkeypatch.setattr(
        "modules.apps.collection_center.executor_v2._save_session_async",
        saved,
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.executor_v2._record_platform_shop_discovery_async",
        AsyncMock(),
    )

    page = type("Page", (), {"url": "https://seller.tiktokshopglobalselling.com/homepage?shop_region=MY"})()
    context = type(
        "Ctx",
        (),
        {"current_component_index": 0, "completed_domains": [], "failed_domains": [], "collected_files": []},
    )()
    params = {
        "reused_session": True,
        "_runtime_session_mode": "persistent_profile",
        "params": {"reused_session": True},
    }

    _, _, result = await executor._execute_shared_login_phase(
        task_id="task-1",
        platform="tiktok",
        account={"account_id": "acc-1", "login_url": "https://seller.tiktokshopglobalselling.com/account/login"},
        params=params,
        context=context,
        browser=object(),
        play_context=object(),
        page=page,
        adapter=object(),
        runtime_manifests=None,
        session_platform="tiktok",
        session_account_id="main-1",
        save_session_after_login=True,
        start_time=__import__("datetime").datetime.now(),
        total_domains_count=0,
    )

    assert result is None
    assert context.current_component_index == 1
    wait_capture.assert_not_awaited()
    saved.assert_not_awaited()
    sessions_dir = repo_root / "data" / "sessions"
    # 验收口径：data/sessions 下**不产生新文件**（空目录不算）
    assert [p for p in sessions_dir.rglob("*") if p.is_file()] == []


@pytest.mark.asyncio
async def test_shared_login_phase_does_not_write_session_file_for_manual_tiktok_session(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """[Task 5 / R5] 人工保存的会话同样**不再落盘**。

    这条原来是 spec D8 的反向对照（人工会话必须落盘才能被采集侧读到）；
    profile-only 之后登录态只由持久 profile 承载，人工会话文件不再是载体，
    因此「人工会话也落盘」这条规则随 ``_save_session_async`` 一起下线。
    """
    from modules.utils.sessions import session_manager as session_manager_module

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(session_manager_module, "REPO_ROOT", repo_root)

    executor = CollectionExecutorV2()
    executor._update_status = AsyncMock()
    executor._check_cancelled = AsyncMock()
    executor.popup_handler.close_popups = AsyncMock()
    executor._execute_python_component = AsyncMock(return_value=True)
    executor._ensure_login_gate_ready = AsyncMock(
        return_value=GateResult(
            stage="login_gate",
            status=GateStatus.READY,
            reason="logged-in markers confirmed",
            current_url="https://seller.tiktokshopglobalselling.com/homepage?shop_region=MY",
        )
    )

    wait_capture = AsyncMock(return_value={"cookies": ["fresh"], "origins": []})
    saved = AsyncMock(return_value=True)
    monkeypatch.setattr(executor, "_wait_and_capture_high_quality_tiktok_session", wait_capture)
    monkeypatch.setattr(
        "modules.apps.collection_center.executor_v2._save_session_async",
        saved,
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.executor_v2._record_platform_shop_discovery_async",
        AsyncMock(),
    )

    page = type("Page", (), {"url": "https://seller.tiktokshopglobalselling.com/homepage?shop_region=MY"})()
    context = type(
        "Ctx",
        (),
        {"current_component_index": 0, "completed_domains": [], "failed_domains": [], "collected_files": []},
    )()
    params = {
        "reused_session": True,
        "_runtime_session_mode": "persistent_profile",
        "session_metadata": {"manual_seeded": True, "protected": True},
        "params": {"reused_session": True},
    }

    await executor._execute_shared_login_phase(
        task_id="task-1",
        platform="tiktok",
        account={"account_id": "acc-1", "login_url": "https://seller.tiktokshopglobalselling.com/account/login"},
        params=params,
        context=context,
        browser=object(),
        play_context=object(),
        page=page,
        adapter=object(),
        runtime_manifests=None,
        session_platform="tiktok",
        session_account_id="main-1",
        save_session_after_login=True,
        start_time=__import__("datetime").datetime.now(),
        total_domains_count=0,
    )

    wait_capture.assert_not_awaited()
    saved.assert_not_awaited()
    sessions_dir = repo_root / "data" / "sessions"
    # 验收口径：data/sessions 下**不产生新文件**（空目录不算）
    assert [p for p in sessions_dir.rglob("*") if p.is_file()] == []


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
    class _NoopLock:
        async def __aenter__(self):
            return None

        async def __aexit__(self, exc_type, exc, tb):
            return None

    async def _fake_acquire_lock(**kwargs):
        return _NoopLock()

    # 账号锁在两条路径上都会被取:
    #   * profile 路径: execute() 在 try 之前取, 直到 _cleanup_browser_runtime 之后才释放;
    #   * 非 profile 路径: _run_with_main_account_session_lock 内部取。
    # 因此桩在更底层的 _acquire_main_account_session_lock 上, 两条路径都覆盖得到。
    monkeypatch.setattr(
        executor,
        "_acquire_main_account_session_lock",
        AsyncMock(side_effect=_fake_acquire_lock),
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


@pytest.mark.asyncio
async def test_start_browser_uses_standard_viewport_in_headed_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = CollectionExecutorV2()
    captured_launch: dict[str, object] = {}
    captured_context: dict[str, object] = {}

    class _FakeBrowser:
        async def new_context(self, **kwargs):
            captured_context.update(kwargs)
            return object()

    class _FakePlaywright:
        chromium = type(
            "Chromium",
            (),
            {
                "launch": AsyncMock(side_effect=lambda **kwargs: captured_launch.update(kwargs) or _FakeBrowser())
            },
        )()

        async def start(self):
            return self

    class _AsyncPlaywrightFactory:
        async def start(self):
            return _FakePlaywright()

    monkeypatch.setattr(
        "backend.utils.config.get_settings",
        lambda: type("Settings", (), {"ENVIRONMENT": "development", "browser_config": {"headless": False, "args": []}})(),
    )
    monkeypatch.setattr(
        "playwright.async_api.async_playwright",
        lambda: _AsyncPlaywrightFactory(),
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.executor_v2.runtime_session.apply_stealth_init_scripts",
        AsyncMock(),
    )

    playwright, browser, context = await executor.start_browser(debug_mode=False)

    assert playwright is not None
    assert browser is not None
    assert context is not None
    assert "--start-maximized" in captured_launch["args"]
    assert captured_context["viewport"] == {"width": 1920, "height": 1080}


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
                "selected_page_url": "https://seller.tiktok.com/account/login",
                "available_page_urls": [
                    "https://seller.tiktok.com/account/login",
                    "https://seller.tiktok.com/homepage?shop_region=MY",
                ],
                "runtime_context_summary": {
                    "locale": None,
                },
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
    assert details["selected_page_url"] == "https://seller.tiktok.com/account/login"
    assert details["available_page_urls"] == [
        "https://seller.tiktok.com/account/login",
        "https://seller.tiktok.com/homepage?shop_region=MY",
    ]
    assert details["runtime_context_summary"] == {"locale": None}
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
    from backend.services.main_account_session_coordinator import (
        MainAccountSessionCoordinator,
    )

    # P0：必须给 executor 注入**独立**的 coordinator 实例。
    # 默认拿到的是模块级单例（backend/services/main_account_session_coordinator.py:60），
    # 直接改它的方法会永久污染全局：后续用例里的第二个任务不再等锁，
    # 抢在第一个任务写入新会话前就加载了旧会话，断言假红。
    executor = CollectionExecutorV2(
        main_account_session_coordinator=MainAccountSessionCoordinator()
    )
    executor._update_status = AsyncMock()
    executor._process_files = AsyncMock(return_value=[])

    class _DummyLock:
        async def __aenter__(self):
            return None

        async def __aexit__(self, exc_type, exc, tb):
            return None

    async def _async_false(platform, main_account_id):
        return False

    async def _async_zero(platform, main_account_id):
        return 0

    # 只改这个用例自己持有的 coordinator 实例，不碰模块级单例。
    coordinator = executor.main_account_session_coordinator
    coordinator.acquire = lambda platform, main_account_id: _DummyLock()
    coordinator.is_locked = lambda platform, main_account_id: False
    coordinator.waiter_count = lambda platform, main_account_id: 0
    # 跨进程视图(Task 3 / L7): 执行器读的是异步版本, 必须一起打桩。
    coordinator.is_locked_async = _async_false
    coordinator.waiter_count_async = _async_zero

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
            # N5：账号自有代理必须原样转发给 _open_runtime_bundle（含凭据）
            "proxy_enabled": True,
            "proxy_server": "http://embedded:embeddedpass@10.0.0.9:8080",
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
    # N5：executor 转发给 _open_runtime_bundle 的 proxy 必须等于解析出的完整代理
    # （含 username/password）—— 把转发点改成 None 的变异必须被这条断言挡住。
    assert observed["proxy"] == {
        "server": "http://10.0.0.9:8080",
        "username": "embedded",
        "password": "embeddedpass",
    }


@pytest.mark.asyncio
async def test_parallel_domains_case_does_not_pollute_module_coordinator_singleton(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P0 防复发：测试**不得**污染模块级 coordinator 单例。

    单例一旦被污染（``acquire`` 换成永不阻塞的假锁），后续用例里的第二个任务
    就不再等锁 —— 抢在第一个任务写入新会话前就加载了旧会话，断言假红。
    """
    from backend.services.main_account_session_coordinator import (
        MainAccountSessionCoordinator,
        get_main_account_session_coordinator,
    )

    singleton = get_main_account_session_coordinator()
    before = (singleton.acquire, singleton.is_locked, singleton.waiter_count)

    await test_execute_parallel_domains_uses_auto_runtime_strategy_for_shared_login(
        monkeypatch
    )

    after = (singleton.acquire, singleton.is_locked, singleton.waiter_count)
    assert after == before, "模块级 coordinator 单例被用例污染了"
    # 单例必须仍是类上的原始实现（没有被实例属性覆盖）
    assert before[0] == MainAccountSessionCoordinator.acquire.__get__(singleton)
    assert before[1] == MainAccountSessionCoordinator.is_locked.__get__(singleton)
    assert before[2] == MainAccountSessionCoordinator.waiter_count.__get__(singleton)


def test_executor_does_not_duplicate_profile_bootstrap():
    """executor 侧不得再保留一份没有 TikTok 质量门禁的 profile bootstrap。

    现状：``runtime_session._bootstrap_session_from_profile_sync`` 有门禁，
    ``executor_v2`` 里又抄了一份没有门禁的 → 低质量 state 会被提升为正式会话。
    修法是复用 runtime_session 的实现，不是再抄第三份。
    """
    text = (
        REPO_ROOT / "modules" / "apps" / "collection_center" / "executor_v2.py"
    ).read_text(encoding="utf-8")
    assert "def _bootstrap_session_from_profile_sync" not in text, (
        "executor 侧仍有一份自己的 _bootstrap_session_from_profile_sync（缺 TikTok 质量门禁），"
        "应改为复用 runtime_session 的实现"
    )


def test_resolve_session_metadata_prefers_runtime_bundle_metadata() -> None:
    """bundle 上已带元数据时直接用它，不再回落到 SessionManager。"""
    bundle = type(
        "Bundle",
        (),
        {"session_metadata": {"manual_seeded": True, "protected": True}},
    )()

    metadata = CollectionExecutorV2._resolve_session_metadata(
        platform="tiktok",
        params={"main_account_id": "main-1"},
        runtime_bundle=bundle,
    )

    assert metadata == {"manual_seeded": True, "protected": True}


def test_resolve_session_metadata_falls_back_to_session_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """bundle 没有元数据时回退到 SessionManager（人工巡店会话的落盘位置）。"""
    monkeypatch.setattr(
        "modules.utils.sessions.session_manager.SessionManager.get_session_metadata",
        lambda self, platform, account_id: {"manual_seeded": True, "protected": True},
    )

    metadata = CollectionExecutorV2._resolve_session_metadata(
        platform="tiktok",
        params={"main_account_id": "main-1"},
        runtime_bundle=object(),
    )

    assert metadata == {"manual_seeded": True, "protected": True}


def test_persistent_profile_bundle_reads_manual_marker_from_disk_session(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """持久 profile 分支的 bundle 不带 session_metadata → 必须从磁盘会话读到人工标记。

    持久 profile 的 ``RuntimeContextBundle`` 由 ``runtime_session`` 构造，
    它的 ``session_metadata`` 恒为空 dict；人工巡店保存的会话落在
    ``data/sessions/<platform>/<owner>/storage_state.json`` 里，
    所以标记只能经 ``SessionManager`` 读回来。
    """
    from modules.utils.sessions import session_manager as session_manager_module

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(session_manager_module, "REPO_ROOT", repo_root)

    manager = session_manager_module.SessionManager()
    session_file = manager.get_session_path("tiktok", "main-1")
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_file.write_text(
        '{"platform": "tiktok", "account_id": "main-1", "storage_state": {},'
        ' "metadata": {"manual_seeded": true, "protected": true}}',
        encoding="utf-8",
    )

    # 持久 profile 的 bundle 不带任何 session_metadata
    persistent_bundle = type("Bundle", (), {"session_metadata": {}})()

    metadata = CollectionExecutorV2._resolve_session_metadata(
        platform="tiktok",
        params={"main_account_id": "main-1"},
        runtime_bundle=persistent_bundle,
    )

    assert metadata["manual_seeded"] is True
    assert metadata["protected"] is True


@pytest.mark.asyncio
async def test_snapshot_runtime_storage_state_returns_memory_snapshot_without_writing_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """[Task 5 / R5] 快照只在内存里：不落盘，也没有 ``persist`` 开关了。

    落盘开关下线后，谁都拿不到「顺手写一份会话文件」的能力；
    登录态的唯一载体是 Chromium 持久 profile 目录。
    """
    import inspect

    from modules.apps.collection_center import runtime_session
    from modules.utils.sessions import session_manager as session_manager_module

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(session_manager_module, "REPO_ROOT", repo_root)

    state = {"cookies": [{"name": "sid", "value": "1"}], "origins": []}
    context = SimpleNamespace(storage_state=AsyncMock(return_value=state))

    snapshot = await runtime_session.snapshot_runtime_storage_state(
        platform="miaoshou",
        session_owner_id="main-1",
        context=context,
    )

    assert snapshot == state
    sessions_dir = repo_root / "data" / "sessions"
    # 验收口径：data/sessions 下**不产生新文件**（空目录不算）
    assert [p for p in sessions_dir.rglob("*") if p.is_file()] == []

    # 落盘参数必须已经不存在（再传就是 TypeError）
    assert (
        "persist"
        not in inspect.signature(
            runtime_session.snapshot_runtime_storage_state
        ).parameters
    )
    with pytest.raises(TypeError):
        await runtime_session.snapshot_runtime_storage_state(
            platform="miaoshou",
            session_owner_id="main-1",
            context=context,
            persist=True,
        )


@pytest.mark.asyncio
async def test_parallel_domains_fails_when_storage_state_snapshot_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """[Task 5 / F5-4] 快照为空必须显式失败，不能带着 ``storage_state=None`` 扇出。

    否则每个并行采集上下文都会在登录页白跑一遍，而且**不会报错** ——
    采集「看起来跑完了」，实际什么数据都没抓到。
    """
    from backend.services.main_account_session_coordinator import (
        MainAccountSessionCoordinator,
    )
    from modules.apps.collection_center.executor_v2 import StepExecutionError

    executor = CollectionExecutorV2(
        main_account_session_coordinator=MainAccountSessionCoordinator()
    )
    executor._update_status = AsyncMock()
    executor._process_files = AsyncMock(return_value=[])

    class _DummyLock:
        async def __aenter__(self):
            return None

        async def __aexit__(self, exc_type, exc, tb):
            return None

    async def _async_false(platform, main_account_id):
        return False

    async def _async_zero(platform, main_account_id):
        return 0

    coordinator = executor.main_account_session_coordinator
    coordinator.acquire = lambda platform, main_account_id: _DummyLock()
    coordinator.is_locked = lambda platform, main_account_id: False
    coordinator.waiter_count = lambda platform, main_account_id: 0
    coordinator.is_locked_async = _async_false
    coordinator.waiter_count_async = _async_zero

    async def _fake_open_runtime_bundle(**kwargs):
        return type(
            "Bundle",
            (),
            {
                "reused_session": False,
                "context": type(
                    "Ctx", (), {"close": AsyncMock(), "cookies": AsyncMock(return_value=[])}
                )(),
                "page": type("Page", (), {"close": AsyncMock()})(),
                "mode": "persistent_profile",
            },
        )()

    browser = SimpleNamespace(new_context=AsyncMock())

    monkeypatch.setattr(executor, "_open_runtime_bundle", _fake_open_runtime_bundle)
    monkeypatch.setattr(executor, "_ensure_login_gate_ready", AsyncMock())
    monkeypatch.setattr(
        executor,
        "_run_runtime_manifest_component",
        AsyncMock(return_value=type("R", (), {"success": True})()),
    )
    # 快照读取失败 -> 返回 None（这正是 F5-4 描述的分支）
    monkeypatch.setattr(
        "modules.apps.collection_center.executor_v2.runtime_session.snapshot_runtime_storage_state",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.executor_v2._record_platform_shop_discovery_async",
        AsyncMock(),
    )

    with pytest.raises(StepExecutionError):
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
            data_domains=["orders"],
            date_range={"start": "2025-01-01", "end": "2025-01-31"},
            granularity="daily",
            browser=browser,
            browser_type=object(),
            max_parallel=1,
            debug_mode=False,
            runtime_manifests={"login": {}, "exports_by_domain": {"orders": {}}},
        )

    # 关键断言：绝不能带着 storage_state=None 继续扇出给采集上下文
    browser.new_context.assert_not_called()


@pytest.mark.asyncio
async def test_parallel_domains_fans_out_memory_snapshot_without_writing_session_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """[Task 5 / R5] 并行扇出用的是**内存里的快照**，且不落任何会话文件。

    两条断言：
    1. 扇出给采集上下文的 ``storage_state`` 就是主流程刚读到的那份内存 dict；
    2. ``data/sessions`` 下不产生新文件。
    """
    from backend.services.main_account_session_coordinator import (
        MainAccountSessionCoordinator,
    )
    from modules.utils.sessions import session_manager as session_manager_module

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(session_manager_module, "REPO_ROOT", repo_root)

    executor = CollectionExecutorV2(
        main_account_session_coordinator=MainAccountSessionCoordinator()
    )
    executor._update_status = AsyncMock()
    executor._process_files = AsyncMock(return_value=[])

    class _DummyLock:
        async def __aenter__(self):
            return None

        async def __aexit__(self, exc_type, exc, tb):
            return None

    async def _async_false(platform, main_account_id):
        return False

    async def _async_zero(platform, main_account_id):
        return 0

    coordinator = executor.main_account_session_coordinator
    coordinator.acquire = lambda platform, main_account_id: _DummyLock()
    coordinator.is_locked = lambda platform, main_account_id: False
    coordinator.waiter_count = lambda platform, main_account_id: 0
    coordinator.is_locked_async = _async_false
    coordinator.waiter_count_async = _async_zero

    async def _fake_open_runtime_bundle(**kwargs):
        return type(
            "Bundle",
            (),
            {
                "reused_session": False,
                "context": type(
                    "Ctx", (), {"close": AsyncMock(), "cookies": AsyncMock(return_value=[])}
                )(),
                "page": type("Page", (), {"close": AsyncMock()})(),
                "mode": "persistent_profile",
            },
        )()

    snapshot = {"cookies": [{"name": "sid", "value": "1"}], "origins": []}
    fanned_out = {}

    async def _fake_execute_single_domain_parallel(**kwargs):
        fanned_out["storage_state"] = kwargs.get("storage_state")
        return None, False

    monkeypatch.setattr(executor, "_open_runtime_bundle", _fake_open_runtime_bundle)
    monkeypatch.setattr(executor, "_ensure_login_gate_ready", AsyncMock())
    monkeypatch.setattr(
        executor,
        "_run_runtime_manifest_component",
        AsyncMock(return_value=type("R", (), {"success": True})()),
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.executor_v2.runtime_session.snapshot_runtime_storage_state",
        AsyncMock(return_value=snapshot),
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.executor_v2._record_platform_shop_discovery_async",
        AsyncMock(),
    )
    monkeypatch.setattr(
        executor, "_execute_single_domain_parallel", _fake_execute_single_domain_parallel
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
        data_domains=["orders"],
        date_range={"start": "2025-01-01", "end": "2025-01-31"},
        granularity="daily",
        browser=object(),
        browser_type=object(),
        max_parallel=1,
        debug_mode=False,
        runtime_manifests={"login": {}, "exports_by_domain": {"orders": {}}},
    )

    # 扇出用的是内存里的那份快照
    assert fanned_out["storage_state"] == snapshot
    # 而且没有落任何会话文件
    sessions_dir = repo_root / "data" / "sessions"
    assert [p for p in sessions_dir.rglob("*") if p.is_file()] == []


def test_load_session_does_not_write_back_to_disk(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """[Task 5 / F5-3] 读会话不得回写磁盘。

    ``load_session`` 以前会刷新 ``last_used_at`` 并把文件重写一遍 ——
    「只是读一下」也会产生磁盘写，等于会话文件体系还在被使用。
    """
    import json
    import time

    from modules.utils.sessions import session_manager as session_manager_module

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(session_manager_module, "REPO_ROOT", repo_root)

    manager = session_manager_module.SessionManager()
    session_file = manager.get_session_path("miaoshou", "main-1")
    session_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "platform": "miaoshou",
        "account_id": "main-1",
        "storage_state": {"cookies": [], "origins": []},
        "created_at": 1000.0,
        "last_used_at": 1000.0,
        "metadata": {"saved_at": time.time()},
    }
    session_file.write_text(json.dumps(payload), encoding="utf-8")
    before_content = session_file.read_text(encoding="utf-8")
    before_mtime = session_file.stat().st_mtime_ns

    session_data = manager.load_session("miaoshou", "main-1")

    assert session_data is not None
    assert session_data["storage_state"] == {"cookies": [], "origins": []}
    # 文件内容与 mtime 都必须原封不动
    assert session_file.read_text(encoding="utf-8") == before_content
    assert session_file.stat().st_mtime_ns == before_mtime
class _BlankFallbackPage:
    """回退返回的页面停在 about:blank（持久 context 的默认首屏）。"""

    def __init__(self) -> None:
        self.url = "about:blank"
        self.goto_calls: list[str] = []

    async def goto(self, url: str, **kwargs) -> None:
        self.goto_calls.append(url)
        self.url = url

    async def wait_for_load_state(self, state: str, timeout: int = 0) -> None:
        return None

    async def wait_for_timeout(self, ms: int) -> None:
        return None


@pytest.mark.asyncio
async def test_shared_login_phase_navigates_blank_page_returned_by_headful_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """评审 F1 兜底：回退返回的页面若仍是 about:blank，必须主动导航一次。

    没有这道兜底时，登录闸门必然失败（about:blank 探测不到登录态），
    而且报错只说 ``url=about:blank``，指不到真因。
    """
    executor = CollectionExecutorV2()
    executor._update_status = AsyncMock()
    executor._check_cancelled = AsyncMock()
    executor.popup_handler.close_popups = AsyncMock()
    executor._ensure_login_gate_ready = AsyncMock()

    blank_page = _BlankFallbackPage()

    async def _raise_verification(*args, **kwargs):
        raise VerificationRequiredError("manual_intervention", "shot.png")

    monkeypatch.setattr(executor, "_execute_python_component", _raise_verification)
    monkeypatch.setattr(
        executor,
        "_run_headful_login_fallback",
        AsyncMock(return_value=(True, object(), blank_page, "success")),
    )

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

    assert blank_page.goto_calls, "回退返回 about:blank 页面时必须主动导航到平台入口"
    assert blank_page.url != "about:blank"
