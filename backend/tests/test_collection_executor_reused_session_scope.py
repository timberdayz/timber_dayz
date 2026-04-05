from pathlib import Path
import asyncio
from unittest.mock import AsyncMock

import pytest

from modules.apps.collection_center.executor_v2 import (
    CollectionExecutorV2,
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


def test_execute_parallel_domains_mentions_main_account_shared_state_preparation():
    source = Path("modules/apps/collection_center/executor_v2.py").read_text(encoding="utf-8")

    parallel_index = source.index("async def execute_parallel_domains(")
    lock_markers = [
        "_run_with_main_account_session_lock(",
        "main_account_session_coordinator.acquire(",
    ]

    assert any(source.find(marker, parallel_index) > parallel_index for marker in lock_markers)


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
