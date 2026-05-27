import asyncio
from types import SimpleNamespace

import pytest

from modules.apps.collection_center.executor_v2 import (
    BrowserDiagnosticsSession,
    CollectionExecutorV2,
)


class _FakePage:
    def __init__(self):
        self.handlers = {}
        self.url = "https://example.com/orders"

    def on(self, event_name, handler):
        self.handlers[event_name] = handler


class _FakeTracing:
    def __init__(self):
        self.started = False
        self.stopped_path = None

    async def start(self, **kwargs):
        self.started = True

    async def stop(self, path=None):
        self.stopped_path = path


class _FakeContext:
    def __init__(self):
        self.tracing = _FakeTracing()
        self.closed = False

    async def close(self):
        self.closed = True


class _Closable:
    def __init__(self, label, events, *, fail=False):
        self.label = label
        self.events = events
        self.fail = fail

    async def close(self):
        self.events.append(self.label)
        if self.fail:
            raise RuntimeError(f"{self.label} failed")


@pytest.mark.asyncio
async def test_browser_diagnostics_emit_runtime_events():
    calls = []

    async def _status_callback(task_id, progress, message, current_domain=None, details=None):
        calls.append(
            {
                "task_id": task_id,
                "progress": progress,
                "message": message,
                "current_domain": current_domain,
                "details": details,
            }
        )

    executor = CollectionExecutorV2(status_callback=_status_callback)
    await executor._update_status("task-1", 42, "采集中", current_domain="orders")

    context = _FakeContext()
    page = _FakePage()

    session = await executor._start_browser_diagnostics(
        task_id="task-1",
        play_context=context,
        page=page,
        scope="main",
    )

    page.handlers["pageerror"](RuntimeError("boom"))
    page.handlers["requestfailed"](SimpleNamespace(url="https://api.example.com", method="GET", failure=lambda: "net::ERR_ABORTED"))
    page.handlers["console"](SimpleNamespace(type=lambda: "warning", text=lambda: "deprecated api"))
    await asyncio.sleep(0)

    diagnostic_events = [
        item["details"]["diagnostic_event"]
        for item in calls
        if item.get("details")
    ]

    assert session.trace_path is not None
    assert "pageerror" in diagnostic_events
    assert "requestfailed" in diagnostic_events
    assert "console" in diagnostic_events


@pytest.mark.asyncio
async def test_browser_diagnostics_stop_records_trace_path_on_failure():
    calls = []

    async def _status_callback(task_id, progress, message, current_domain=None, details=None):
        calls.append(details or {})

    executor = CollectionExecutorV2(status_callback=_status_callback)
    await executor._update_status("task-2", 88, "导出中", current_domain="orders")

    context = _FakeContext()
    diagnostics = BrowserDiagnosticsSession(trace_path="temp/traces/task-2/main.zip")

    await executor._stop_browser_diagnostics(
        task_id="task-2",
        play_context=context,
        diagnostics=diagnostics,
        failed=True,
        scope="main",
    )

    assert context.tracing.stopped_path == "temp/traces/task-2/main.zip"
    assert any(item.get("diagnostic_event") == "trace_saved" for item in calls)


@pytest.mark.asyncio
async def test_cleanup_browser_runtime_closes_page_context_and_browser():
    executor = CollectionExecutorV2(status_callback=None)
    events = []
    context = _FakeContext()
    page = _Closable("page", events)
    browser = _Closable("browser", events)
    extra_context = _Closable("extra_context", events)

    await executor._cleanup_browser_runtime(
        task_id="task-3",
        page=page,
        play_context=context,
        browser=browser,
        diagnostics=None,
        failed=False,
        scope="main",
        extra_context=extra_context,
    )

    assert events == ["page", "extra_context", "browser"]
    assert context.closed is True


@pytest.mark.asyncio
async def test_cleanup_browser_runtime_tolerates_close_failures():
    executor = CollectionExecutorV2(status_callback=None)
    context = _FakeContext()

    await executor._cleanup_browser_runtime(
        task_id="task-4",
        page=_Closable("page", [], fail=True),
        play_context=context,
        browser=_Closable("browser", [], fail=True),
        diagnostics=None,
        failed=False,
        scope="main",
    )

    assert context.closed is True
