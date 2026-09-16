"""Regression: miaoshou inventory export must surface pageerror details and fail fast.

ID=621 (2026-09-14 19:32:33 UTC, 253s, failed) 三层根因:
  1. https://erp.91miaoshou.com/warehouse/checklist 触发 pageerror: "undefined"
  2. browser_diagnostics 只记录 str(error) — 无 stack/filename/lineno，无法定位 JS 行
  3. inventory_export 不监听 pageerror — expect_download 干等 180s 后才超时

修复：
  - browser_diagnostics 捕获 error.stack/filename/lineno/colno/name
  - inventory_export 注册 pageerror listener + 早 fail
  - inventory_export expect_download 超时后 retry 一次
"""

import asyncio
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from modules.apps.collection_center.executor_v2 import (
    CollectionExecutorV2,
)


# ---------------------------------------------------------------------------
# 修复 1：browser_diagnostics pageerror 捕获 stack/filename/lineno
# ---------------------------------------------------------------------------


class _FakePage:
    """Minimal Playwright Page stand-in: records page.on() handlers."""

    def __init__(self):
        self.handlers: dict = {}
        self.url = "https://example.com/orders"

    def on(self, event_name, handler):
        self.handlers[event_name] = handler


class _FakeContext:
    def __init__(self):
        self.tracing = SimpleNamespace(started=False, stopped_path=None)

    async def close(self):
        pass


class _JSError:
    """Playwright pageerror event payload (mimics Playwright JSError shape)."""

    def __init__(self, *, name, message, stack, filename, lineno, colno=None):
        self.name = name
        self.message = message
        self.stack = stack
        self.filename = filename
        self.lineno = lineno
        self.colno = colno if colno is not None else 0

    def __str__(self) -> str:
        return f"{self.name}: {self.message}"


@pytest.mark.asyncio
async def test_browser_diagnostics_pageerror_records_stack_filename_lineno():
    """browser_diagnostics.pageerror 必须捕获 error.stack/filename/lineno/colno。

    ID=621 失败日志里 pageerror 只有 "error": "undefined"，缺少 stack/filename/lineno，
    导致无法定位 JS 出错位置。本测试断言这三项被写入 details。
    """
    calls = []

    async def _status_callback(task_id, progress, message, current_domain=None, details=None):
        calls.append(details or {})

    executor = CollectionExecutorV2(status_callback=_status_callback)
    context = _FakeContext()
    page = _FakePage()

    await executor._start_browser_diagnostics(
        task_id="task-inv-1",
        play_context=context,
        page=page,
        scope="main",
    )

    js_error = _JSError(
        name="TypeError",
        message="Cannot read properties of undefined (reading 'foo')",
        stack="TypeError: Cannot read properties of undefined (reading 'foo')\n"
              "    at handler (https://erp.91miaoshou.com/warehouse/checklist:123:45)\n"
              "    at XMLHttpRequest.send",
        filename="https://erp.91miaoshou.com/warehouse/checklist",
        lineno=123,
        colno=45,
    )
    page.handlers["pageerror"](js_error)
    await asyncio.sleep(0)

    pageerror_details = [
        details for details in calls
        if details.get("diagnostic_event") == "pageerror"
    ]
    assert pageerror_details, "pageerror 事件未被记录"
    details = pageerror_details[0]

    assert details.get("stack") == js_error.stack, (
        "pageerror 必须记录 error.stack 才能定位 JS 出错行（ID=621 root cause）"
    )
    assert details.get("filename") == js_error.filename, (
        "pageerror 必须记录 error.filename（脚本 URL）"
    )
    assert details.get("lineno") == 123, (
        "pageerror 必须记录 error.lineno（行号）"
    )
    assert details.get("colno") == 45, (
        "pageerror 必须记录 error.colno（列号）"
    )
    assert details.get("name") == "TypeError", (
        "pageerror 必须记录 error.name（错误类型）"
    )


@pytest.mark.asyncio
async def test_browser_diagnostics_pageerror_tolerates_missing_stack():
    """非 JSError 类型错误可能没有 stack/filename — handler 必须容忍而非崩溃。

    ID=621 真实日志里 pageerror 是 RuntimeError-style "undefined" 字符串。
    """
    calls = []

    async def _status_callback(task_id, progress, message, current_domain=None, details=None):
        calls.append(details or {})

    executor = CollectionExecutorV2(status_callback=_status_callback)
    context = _FakeContext()
    page = _FakePage()

    await executor._start_browser_diagnostics(
        task_id="task-inv-2",
        play_context=context,
        page=page,
        scope="main",
    )

    bare_error = RuntimeError("undefined")
    page.handlers["pageerror"](bare_error)
    await asyncio.sleep(0)

    pageerror_details = [
        details for details in calls
        if details.get("diagnostic_event") == "pageerror"
    ]
    assert pageerror_details, "pageerror 事件未被记录"
    details = pageerror_details[0]
    assert details.get("error") == "undefined", (
        "message 至少要保留（向后兼容现有行为 — ID=621 日志里 error 字段必须是 \"undefined\"）"
    )
    for field in ("stack", "filename", "lineno", "colno", "name"):
        details.get(field)


# ---------------------------------------------------------------------------
# 修复 2：inventory_export 注册 pageerror listener + 早 fail
# ---------------------------------------------------------------------------


class _FakeDLInfoBase:
    """dl_info stub：``value`` 是 awaitable（asyncio.Future）。

    生产代码 ``await dl_info.value`` 要求 value 是 awaitable（不是 bound method）。
    ``download=None`` 时 Future 永不 resolve（模拟 hung download，用于测试
    pageerror guard 的 fail-fast 路径）；``download=<obj>`` 时 Future 立即
    resolve（模拟正常 download 完成，用于测试 listener 清理路径）。
    """

    def __init__(self, download=None):
        self._future: asyncio.Future = asyncio.Future()
        if download is not None:
            self._future.set_result(download)

    @property
    def value(self):
        return self._future


class _FakeDLInfoNever(_FakeDLInfoBase):
    """默认构造：Future 永不 resolve（模拟 hung download）。"""

    def __init__(self):
        super().__init__(download=None)


async def _fake_export_click(page):
    """Async function used as ``_trigger_export`` mock: fires pageerror when called.

    模拟 ID=621 真实场景：点"导出"按钮 → JS 抛错 → Playwright 收到 pageerror
    事件，但 download 事件从未 fire。

    Note: 必须是模块顶层 async 函数（不能是闭包），否则被赋给实例属性
    后 Python descriptor 协议可能使其被当作 method-wrapper 而非 awaitable。
    """
    handler = page.handlers.get("pageerror")
    if handler is None:
        return
    err = SimpleNamespace(
        name="TypeError",
        message="undefined",
        stack="TypeError: undefined\n"
              "    at handler (https://erp.91miaoshou.com/warehouse/checklist:123:45)",
        filename="https://erp.91miaoshou.com/warehouse/checklist",
        lineno=123,
        colno=45,
    )
    handler(err)


class _FakeExpectDownloadCM:
    """Fake page.expect_download() context manager：模拟 hung download。"""

    def __init__(self, page, dl_info=None):
        self._page = page
        self._dl_info = dl_info

    async def __aenter__(self):
        return self._dl_info if self._dl_info is not None else _FakeDLInfoNever()

    async def __aexit__(self, *args):
        return False


class _InventoryFakePage:
    """Minimal Playwright Page stub for inventory_export.fail-fast test."""

    def __init__(self):
        self.handlers: dict = {}
        self.url = "https://erp.91miaoshou.com/warehouse/checklist"

    def on(self, event_name, handler):
        self.handlers[event_name] = handler

    def remove_listener(self, event_name, handler):
        if self.handlers.get(event_name) is handler:
            self.handlers.pop(event_name, None)

    def expect_download(self, *, timeout=None):
        return _FakeExpectDownloadCM(self, dl_info=getattr(self, "_dl_info_override", None))


def _make_export_with_mocks(ctx, page, *, click=None):
    """Build MiaoshouInventoryExport with all Playwright-dependent helpers mocked.

    Returns the export instance ready to run(). The caller controls what
    ``_trigger_export`` does via the ``click`` parameter (an async callable
    accepting ``page`` as its sole argument).
    """
    from modules.platforms.miaoshou.components.inventory_export import (
        MiaoshouInventoryExport,
    )

    export = MiaoshouInventoryExport(ctx)
    export.navigation_component.run = AsyncMock(
        return_value=SimpleNamespace(success=True, message="ok")
    )
    export.warehouse_filters_component.run = AsyncMock(
        return_value=SimpleNamespace(success=True, message="ok")
    )
    export._ensure_popup_closed = AsyncMock()
    export._click_search = AsyncMock()
    export._wait_search_results_ready = AsyncMock()
    export._open_export_dialog = AsyncMock()
    export._ensure_export_fields_all_selected = AsyncMock()
    # 直接赋值 async 函数（不是 AsyncMock 实例）— 避免 descriptor 协议误判。
    export._trigger_export = click if click is not None else AsyncMock()
    export._wait_download_complete = AsyncMock(return_value=Path("/tmp/fake.xlsx"))
    return export


@pytest.mark.asyncio
async def test_miaoshou_inventory_export_aborts_within_30s_when_pageerror_fires():
    """pageerror 触发后 inventory_export.run() 必须在 30s 内返回 success=False。

    ID=621 真实场景：expect_download 干等 180s 才超时，run() 总耗时 253s。
    测试用 asyncio.wait_for 给 run() 加 10s 上限。
    """
    from modules.components.base import ExecutionContext
    from modules.components.export.base import ExportMode

    ctx = ExecutionContext(
        platform="miaoshou",
        account={},
        config={"shop_name": "test-shop"},
    )
    page = _InventoryFakePage()
    export = _make_export_with_mocks(ctx, page, click=_fake_export_click)

    start = time.monotonic()
    try:
        result = await asyncio.wait_for(
            export.run(page, ExportMode.STANDARD), timeout=10.0
        )
    except asyncio.TimeoutError:
        elapsed = time.monotonic() - start
        pytest.fail(
            f"pageerror 后 run() 在 10s 内仍未返回（实测 {elapsed:.1f}s）"
            f"— inventory_export 没有 fail-fast 机制（ID=621 root cause）"
        )
    elapsed = time.monotonic() - start

    assert result.success is False, (
        f"pageerror 触发后应当 fail-fast 但 success=True (message={result.message!r})"
    )
    assert elapsed < 30, (
        f"pageerror 后应在 30s 内 fail-fast，实际等了 {elapsed:.1f}s"
        f"（ID=621 真实场景耗时 253s，干等 expect_download 180s）"
    )
    assert "pageerror" in result.message.lower(), (
        f"error message 应包含 'pageerror' 关键词以便快速定位 ID=621 类型问题，"
        f"实际是: {result.message!r}"
    )


@pytest.mark.asyncio
async def test_miaoshou_inventory_export_removes_pageerror_listener_after_run():
    """inventory_export.run() 结束后必须 remove pageerror listener 防止内存泄漏。

    如果不清理，重复运行 inventory_export 会累积 pageerror listener，
    每次 pageerror 触发都会被多次处理。
    """
    from modules.components.base import ExecutionContext
    from modules.components.export.base import ExportMode

    ctx = ExecutionContext(
        platform="miaoshou",
        account={},
        config={"shop_name": "test-shop"},
    )
    page = _InventoryFakePage()
    export = _make_export_with_mocks(ctx, page)  # 默认 click=None → no pageerror
    # 让 download 立即到达（dl_info.value 立即 resolve）— 走正常路径到 _wait_download_complete
    fake_download = SimpleNamespace(suggested_filename="inv.xlsx", save_as=AsyncMock())
    page._dl_info_override = _FakeDLInfoBase(download=fake_download)
    # Force _wait_download_complete to raise so run() definitely exits via exception path
    export._wait_download_complete = AsyncMock(
        side_effect=RuntimeError("download never arrived")
    )

    await export.run(page, ExportMode.STANDARD)

    assert "pageerror" not in page.handlers, (
        "inventory_export.run() 必须在 finally 中调用 page.remove_listener('pageerror') "
        "否则重复运行会累积 listener，pageerror 触发会被处理多次"
    )