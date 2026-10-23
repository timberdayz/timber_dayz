"""执行器向组件注入 logger / step_callback 的守卫测试。

对应上游 spec §7.1 A8：组件必须能拿到 logger 与步骤回调，
否则组件里的 `report_step` 会在 `base.py:83-84` 提前 return，一条事件都发不出去。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from modules.apps.collection_center.executor_v2 import CollectionExecutorV2


def _executor(status_callback: Any = None) -> CollectionExecutorV2:
    return CollectionExecutorV2(status_callback=status_callback)


def test_build_step_callback_returns_none_without_status_callback() -> None:
    assert _executor()._build_step_callback("task-1") is None


def test_build_step_callback_returns_none_without_task_id() -> None:
    async def _status(*_args: Any, **_kwargs: Any) -> None:
        return None

    assert _executor(_status)._build_step_callback("") is None


@pytest.mark.asyncio
async def test_build_step_callback_forwards_step_id_to_status_callback() -> None:
    captured: List[Tuple[Any, ...]] = []

    async def _status(task_id, progress, message, current_domain=None, details=None):
        captured.append((task_id, progress, message, current_domain, details))

    callback = _executor(_status)._build_step_callback(
        "task-1", domain="inventory", progress=42
    )
    assert callback is not None
    await callback(
        "step_start", {"step_id": "warehouse_scope_ready", "action": "打开仓库范围筛选"}
    )

    task_id, progress, message, current_domain, details = captured[0]
    assert task_id == "task-1"
    assert progress == 42
    assert current_domain == "inventory"
    # 前端 getStepLabel 依赖 details.step_id
    assert details["step_id"] == "warehouse_scope_ready"
    assert details["event_type"] == "step_start"
    assert "打开仓库范围筛选" in message


@pytest.mark.asyncio
async def test_build_step_callback_keeps_error_detail_for_failed_step() -> None:
    captured: List[Dict[str, Any]] = []

    async def _status(task_id, progress, message, current_domain=None, details=None):
        captured.append(details or {})

    callback = _executor(_status)._build_step_callback("task-1", domain="inventory")
    assert callback is not None
    await callback(
        "step_failed",
        {"step_id": "export_dialog_ready", "action": "打开导出弹窗", "error": "boom"},
    )

    assert captured[0]["error"] == "boom"
    assert captured[0]["step_id"] == "export_dialog_ready"


@pytest.mark.asyncio
async def test_build_step_callback_falls_back_to_legacy_three_arg_signature() -> None:
    captured: List[Tuple[Any, ...]] = []

    async def _legacy_status(task_id, progress, message):
        captured.append((task_id, progress, message))

    callback = _executor(_legacy_status)._build_step_callback("task-1")
    assert callback is not None
    await callback("step_start", {"step_id": "s1", "action": "a"})

    assert captured[0][0] == "task-1"


@pytest.mark.asyncio
async def test_run_runtime_manifest_component_injects_logger_and_step_callback() -> (
    None
):
    """生产注入点必须把 logger 与 step_callback 放进 ExecutionContext。"""
    captured: List[Dict[str, Any]] = []

    class _FakeComponent:
        def __init__(self, ctx: Any) -> None:
            captured.append(
                {
                    "logger": ctx.logger,
                    "step_callback": ctx.step_callback,
                    "platform": ctx.platform,
                }
            )

        async def run(self, page: Any, *args: Any, **kwargs: Any) -> Any:
            return "ok"

    async def _status(*_args: Any, **_kwargs: Any) -> None:
        return None

    executor = _executor(_status)
    executor._load_runtime_manifest_component_class = lambda manifest: _FakeComponent  # type: ignore[method-assign]

    result = await executor._run_runtime_manifest_component(
        page=object(),
        manifest={"platform": "miaoshou"},
        account={"label": "acc"},
        config={},
        task_id="task-1",
        domain="inventory",
        progress=30,
    )

    assert result == "ok"
    assert captured[0]["platform"] == "miaoshou"
    assert captured[0]["logger"] is not None
    assert captured[0]["step_callback"] is not None
