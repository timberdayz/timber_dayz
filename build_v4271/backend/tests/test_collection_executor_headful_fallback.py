from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from modules.apps.collection_center.executor_v2 import (
    CollectionExecutorV2,
    TaskContext,
    VerificationRequiredError,
)


@pytest.mark.asyncio
async def test_executor_requires_headful_login_fallback_for_manual_continue_types():
    executor = CollectionExecutorV2()

    assert executor._requires_headful_login_fallback("manual_intervention") is True
    assert executor._requires_headful_login_fallback("slide_captcha") is True
    assert executor._requires_headful_login_fallback("otp") is False


@pytest.mark.asyncio
async def test_executor_login_loop_uses_headful_fallback_and_continues_with_new_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = CollectionExecutorV2()
    executor._update_status = AsyncMock()
    executor._check_cancelled = AsyncMock()
    executor._ensure_login_gate_ready = AsyncMock()
    executor._process_files = AsyncMock(return_value=[])
    executor.popup_handler.close_popups = AsyncMock()

    fallback_page = object()
    monkeypatch.setattr(
        executor,
        "_execute_python_component",
        AsyncMock(side_effect=VerificationRequiredError("manual_intervention", "shot.png")),
    )
    monkeypatch.setattr(
        executor,
        "_run_headful_login_fallback",
        AsyncMock(return_value=(True, object(), fallback_page)),
    )

    result = await executor._execute_with_python_components(
        task_id="task-1",
        platform="tiktok",
        account={"account_id": "acc-1", "login_url": "https://seller.tiktokglobalshop.com"},
        params={"params": {}},
        context=TaskContext(
            task_id="task-1",
            platform="tiktok",
            account_id="acc-1",
            data_domains=[],
            date_range={"start": "2026-03-01", "end": "2026-03-01"},
            granularity="daily",
        ),
        browser=object(),
        play_context=object(),
        page=object(),
        step_popup_handler=object(),
        task_download_dir=object(),
        data_domains=[],
        sub_domains=None,
        total_domains_count=0,
        start_time=__import__("datetime").datetime.now(),
        save_session_after_login=False,
        session_platform="tiktok",
        session_account_id="acc-1",
        runtime_manifests=None,
    )

    executor._run_headful_login_fallback.assert_awaited_once()
    executor._ensure_login_gate_ready.assert_awaited_once_with(fallback_page, "tiktok")
    assert result.status == "completed"


@pytest.mark.asyncio
async def test_executor_graphical_captcha_timeout_returns_paused_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = CollectionExecutorV2()
    executor._update_status = AsyncMock()
    executor._check_cancelled = AsyncMock()
    executor.popup_handler.close_popups = AsyncMock()

    monkeypatch.setattr(
        executor,
        "_execute_python_component",
        AsyncMock(side_effect=VerificationRequiredError("graphical_captcha", "shot.png")),
    )
    monkeypatch.setattr(
        executor,
        "_wait_verification_and_continue",
        AsyncMock(return_value=None),
    )

    result = await executor._execute_with_python_components(
        task_id="task-1",
        platform="miaoshou",
        account={"account_id": "acc-1", "login_url": "https://example.com"},
        params={"params": {}},
        context=TaskContext(
            task_id="task-1",
            platform="miaoshou",
            account_id="acc-1",
            data_domains=[],
            date_range={"start": "2026-03-01", "end": "2026-03-01"},
            granularity="daily",
        ),
        browser=object(),
        play_context=object(),
        page=object(),
        step_popup_handler=object(),
        task_download_dir=object(),
        data_domains=[],
        sub_domains=None,
        total_domains_count=0,
        start_time=__import__("datetime").datetime.now(),
        save_session_after_login=False,
        session_platform="miaoshou",
        session_account_id="acc-1",
        runtime_manifests=None,
    )

    assert result.status == "paused"
    assert result.error_message == "验证码等待超时"


@pytest.mark.asyncio
async def test_executor_manual_continue_timeout_returns_manual_intervention_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = CollectionExecutorV2()
    executor._update_status = AsyncMock()
    executor._check_cancelled = AsyncMock()
    executor.popup_handler.close_popups = AsyncMock()

    monkeypatch.setattr(
        executor,
        "_execute_python_component",
        AsyncMock(side_effect=VerificationRequiredError("slide_captcha", "shot.png")),
    )
    monkeypatch.setattr(
        executor,
        "_wait_verification_and_continue",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        executor,
        "_run_headful_login_fallback",
        AsyncMock(return_value=(False, object(), None, "timeout")),
    )

    result = await executor._execute_with_python_components(
        task_id="task-1",
        platform="tiktok",
        account={"account_id": "acc-1", "login_url": "https://example.com"},
        params={"params": {}},
        context=TaskContext(
            task_id="task-1",
            platform="tiktok",
            account_id="acc-1",
            data_domains=[],
            date_range={"start": "2026-03-01", "end": "2026-03-01"},
            granularity="daily",
        ),
        browser=object(),
        play_context=object(),
        page=object(),
        step_popup_handler=object(),
        task_download_dir=object(),
        data_domains=[],
        sub_domains=None,
        total_domains_count=0,
        start_time=__import__("datetime").datetime.now(),
        save_session_after_login=False,
        session_platform="tiktok",
        session_account_id="acc-1",
        runtime_manifests=None,
    )

    assert result.status == "manual_intervention_required"
    assert result.error_message == "等待人工处理超时"
