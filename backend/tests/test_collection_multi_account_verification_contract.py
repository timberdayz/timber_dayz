from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend.routers.collection_tasks import (
    _build_task_response_payload,
    _build_task_verification_item,
    list_verification_items,
)


def _make_task(**overrides):
    now = datetime.now(timezone.utc)
    base = dict(
        id=1,
        task_id="task-1",
        platform="miaoshou",
        account="acc-1",
        status="verification_required",
        progress=40,
        current_step="等待验证码",
        files_collected=0,
        trigger_type="manual",
        data_domains=["orders"],
        sub_domains=None,
        granularity="daily",
        date_range={"start": "2026-03-01", "end": "2026-03-01"},
        time_selection=None,
        total_domains=1,
        completed_domains=[],
        failed_domains=[],
        current_domain="orders",
        debug_mode=False,
        error_message=None,
        duration_seconds=None,
        created_at=now,
        updated_at=now,
        started_at=now,
        completed_at=None,
        verification_type="graphical_captcha",
        verification_screenshot="temp/screens/task-1.png",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_build_task_response_payload_exposes_verification_contract_fields():
    payload = _build_task_response_payload(_make_task())

    assert payload["verification_type"] == "graphical_captcha"
    assert payload["verification_screenshot"] == "temp/screens/task-1.png"
    assert payload["verification_id"] == "task-1"
    assert payload["verification_message"] == "等待验证码"
    assert payload["verification_attempt_count"] == 0


def test_build_task_response_payload_exposes_config_scope_and_execution_mode():
    payload = _build_task_response_payload(
        _make_task(
            config_id=42,
            debug_mode=True,
        )
    )

    assert payload["config_id"] == 42
    assert payload["execution_mode"] == "headed"


def test_build_task_verification_item_is_scoped_per_account():
    first = _build_task_verification_item(_make_task(task_id="task-1", account="acc-1"))
    second = _build_task_verification_item(_make_task(task_id="task-1", account="acc-2"))

    assert first["verification_id"] == "task-1"
    assert first["account_id"] == "acc-1"
    assert second["account_id"] == "acc-2"
    assert first != second


@pytest.mark.asyncio
async def test_list_verification_items_filters_verification_required_tasks():
    paused = _make_task(task_id="task-1", account="acc-1", status="verification_required")
    running = _make_task(task_id="task-2", account="acc-2", status="running")
    no_verification = _make_task(
        task_id="task-3",
        account="acc-3",
        status="verification_required",
        verification_type=None,
    )

    class _Result:
        def scalars(self):
            class _Scalars:
                def all(self_inner):
                    return [paused, running, no_verification]

            return _Scalars()

    class _FakeDb:
        async def execute(self, stmt):
            return _Result()

    items = await list_verification_items(
        platform=None,
        verification_type=None,
        account_id=None,
        status="verification_required",
        db=_FakeDb(),
    )

    assert len(items) == 1
    assert items[0]["task_id"] == "task-1"
    assert items[0]["account_id"] == "acc-1"


def test_build_task_response_payload_exposes_manual_continue_mode_for_slide_captcha():
    payload = _build_task_response_payload(_make_task(verification_type="slide_captcha"))

    assert payload["verification_type"] == "slide_captcha"
    assert payload["verification_input_mode"] == "manual_continue"


def test_build_task_verification_item_exposes_manual_continue_mode_for_slide_captcha():
    item = _build_task_verification_item(_make_task(verification_type="slide_captcha"))

    assert item["verification_type"] == "slide_captcha"
    assert item["verification_input_mode"] == "manual_continue"


@pytest.mark.asyncio
async def test_list_verification_items_includes_manual_intervention_required_tasks():
    manual = _make_task(
        task_id="task-manual",
        account="acc-manual",
        status="manual_intervention_required",
        verification_type="manual_intervention",
        current_step="需要人工处理页面异常",
    )
    paused = _make_task(task_id="task-paused", account="acc-paused", status="verification_required")

    class _Result:
        def scalars(self):
            class _Scalars:
                def all(self_inner):
                    return [manual, paused]

            return _Scalars()

    class _FakeDb:
        async def execute(self, stmt):
            return _Result()

    items = await list_verification_items(
        platform=None,
        verification_type=None,
        account_id=None,
        status="verification_required",
        db=_FakeDb(),
    )

    assert len(items) == 2
    assert {item["task_id"] for item in items} == {"task-manual", "task-paused"}
