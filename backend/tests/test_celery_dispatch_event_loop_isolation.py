"""Celery 派发「不许把 asyncio 事件循环冻住」的守护用例（2026-11-10 新增）。

为什么要有这一组用例
--------------------
生产实测（Redis **健康**，在 ``backend_api`` 容器内实测，与生产代码同一条路径）：

    Redis PING 中位数 **0.07 ms**
    broker 建连 **1.31 ms**
    完整派发 ``send_task(..., ignore_result=True)`` 中位数 **0.52 ms**

⇒ **正常状态下派发根本不是瓶颈**；台账里那个「4.1 秒」是 **Redis 不可达时的
退化阻塞**，和当年的 16~17 秒同源，不是日常耗时。

真正的剩余风险是：退化时这个阻塞**同步发生在 API 的 asyncio 事件循环里**
⇒ Redis 一抖，**全站请求一起挂起**（这才是「Redis 一抖整个 API 500」的机制）。

因此这里锁死两条契约：

1. **async 上下文里的 Celery 派发必须走 ``dispatch_task``**
   （AST 扫描整个 ``backend/`` 与 ``modules/``，发现裸 ``.delay()`` /
   ``.apply_async()`` 直接失败）；
2. **``dispatch_task`` 必须在线程里发布** —— 派发阻塞期间事件循环照常调度
   （行为级验证：一次 1 秒的假派发期间，心跳协程必须至少跑好几轮）。

第 2 条已有同族用例覆盖「超时/重试有上限」与「``ignore_result``」：
``backend/tests/test_celery_dispatch_resilience.py``。
"""

from __future__ import annotations

import ast
import asyncio
import contextlib
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCANNED_DIRS = ("backend", "modules")

# 派发动作的三种形态：``delay()`` / ``apply_async()`` / ``send_task()``
DISPATCH_METHODS = ("delay", "apply_async", "send_task")


def _async_context_dispatch_calls() -> list[tuple[str, int, str]]:
    """找出所有**位于 async 函数体内**的裸 Celery 派发调用。

    返回 ``(相对路径, 行号, 宿主函数名)`` 三元组列表。

    宿主函数用**真实包含关系**判定（``lineno <= call <= end_lineno``）——
    只按起始行号取「最内层」会误判：嵌套函数可能定义得更早却在调用点之前
    就已经结束了。
    """
    hits: list[tuple[str, int, str]] = []

    for dirname in SCANNED_DIRS:
        base = REPO_ROOT / dirname
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            # 测试目录自身不在契约范围内（测试里故意造阻塞派发）
            if "tests" in path.relative_to(REPO_ROOT).parts:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            except (SyntaxError, UnicodeDecodeError):
                continue

            functions = [
                node
                for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]

            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if not isinstance(func, ast.Attribute):
                    continue
                if func.attr not in DISPATCH_METHODS:
                    continue

                host = None
                for fn in functions:
                    end_lineno = getattr(fn, "end_lineno", None) or fn.lineno
                    if fn.lineno <= node.lineno <= end_lineno:
                        if host is None or fn.lineno > host.lineno:
                            host = fn
                if host is None or not isinstance(host, ast.AsyncFunctionDef):
                    continue

                rel = path.relative_to(REPO_ROOT).as_posix()
                hits.append((rel, node.lineno, host.name))

    return hits


def test_async_dispatch_sites_must_go_through_dispatch_task():
    """async 上下文里**不许**直接调用 ``.delay()`` / ``.apply_async()``。

    直接调用意味着发布动作（可能同步阻塞数秒）跑在事件循环里 ⇒ Redis 不可达时
    全站请求一起挂起。必须改成 ``await dispatch_task(...)``。
    """
    hits = _async_context_dispatch_calls()
    offenders = [f"{rel}:{line} (在 async 函数 {host} 内)" for rel, line, host in hits]

    assert not offenders, (
        "以下 async 上下文里出现了裸 Celery 派发调用 —— "
        "Redis 不可达时它会在事件循环里同步阻塞数秒，把全站请求一起挂住。\n"
        "请改用 `await dispatch_task(task, ...)`"
        f"（backend/utils/celery_dispatch.py）：\n  " + "\n  ".join(offenders)
    )


class _FakeTask:
    """模拟 Celery 任务对象，可指定阻塞时长或抛错。"""

    def __init__(self, block_seconds: float = 0.0, error: Exception | None = None):
        self.block_seconds = block_seconds
        self.error = error
        self.calls: list[dict] = []

    def apply_async(self, args=None, kwargs=None, **options):
        self.calls.append({"args": args, "kwargs": kwargs, "options": options})
        if self.block_seconds:
            time.sleep(self.block_seconds)
        if self.error is not None:
            raise self.error
        return f"async-result-{len(self.calls)}"


@pytest.mark.asyncio
async def test_dispatch_task_does_not_freeze_the_event_loop():
    """派发阻塞期间，事件循环必须照常调度其它协程。

    这是「Redis 一抖全站挂起」得以根治的**行为级**保证：
    假派发阻塞 1 秒，心跳协程必须在这段时间里跑过多轮。
    """
    from backend.utils.celery_dispatch import dispatch_task

    task = _FakeTask(block_seconds=1.0)
    ticks: list[float] = []

    async def _heartbeat():
        while True:
            ticks.append(time.perf_counter())
            await asyncio.sleep(0.05)

    heartbeat = asyncio.create_task(_heartbeat())
    try:
        started = time.perf_counter()
        result = await dispatch_task(task, args=(1,), kwargs={"a": 2}, priority=3)
        elapsed = time.perf_counter() - started
    finally:
        heartbeat.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat

    assert result == "async-result-1"
    assert elapsed >= 1.0, "假派发没有真的阻塞 —— 本用例自身失效"
    assert len(ticks) >= 5, (
        f"派发期间事件循环只跑了 {len(ticks)} 次心跳 —— "
        "说明发布动作仍然跑在事件循环里（Redis 不可达时会冻住全站）"
    )


@pytest.mark.asyncio
async def test_dispatch_task_forwards_arguments_and_options():
    """``dispatch_task`` 必须原样转发 args / kwargs / 其它选项。"""
    from backend.utils.celery_dispatch import dispatch_task

    task = _FakeTask()
    result = await dispatch_task(
        task,
        args=("file-1",),
        kwargs={"only_with_template": True},
        priority=7,
        queue="data_sync",
    )

    assert result == "async-result-1"
    assert len(task.calls) == 1
    call = task.calls[0]
    assert call["args"] == ("file-1",)
    assert call["kwargs"] == {"only_with_template": True}
    assert call["options"] == {"priority": 7, "queue": "data_sync"}


@pytest.mark.asyncio
async def test_dispatch_task_propagates_publish_errors():
    """发布失败必须照常抛出 —— 不能被吞掉。

    调用点原有的 ``except`` 兜底（以及「派发失败就不置成功标记」这类语义）
    依赖这个异常；这里若吞掉异常，派发失败会被误判成成功。
    """
    from backend.utils.celery_dispatch import dispatch_task

    task = _FakeTask(error=RuntimeError("redis unreachable"))

    with pytest.raises(RuntimeError, match="redis unreachable"):
        await dispatch_task(task)


def test_celery_degraded_path_blocking_budget_is_tight():
    """退化路径（Redis 不可达）的阻塞预算必须够小。

    2026-11-10 实测：同机房 Redis 正常建连是毫秒级（0.07 ms），
    所以建连超时给到 **1 秒**已经足够容忍一次网络抖动；再久就是
    「它已经不在了」。发布重试同样只保留 1 次。

    这些只影响「连不上」时的行为：Redis 正常时派发耗时不变。
    """
    from backend.celery_app import celery_app

    for label, options in (
        ("broker_transport_options", celery_app.conf.broker_transport_options),
        (
            "result_backend_transport_options",
            celery_app.conf.result_backend_transport_options,
        ),
    ):
        assert isinstance(options, dict), f"{label} 必须显式配置"
        timeout = options.get("socket_connect_timeout")
        assert timeout is not None, f"{label} 缺少 socket_connect_timeout"
        assert 0 < float(timeout) <= 2, (
            f"{label} 的 socket_connect_timeout 过大: {timeout} —— "
            "Redis 是同机房服务，正常建连是毫秒级，2 秒已足够容忍网络抖动"
        )
        policy = options.get("retry_policy") or {}
        assert policy.get("max_retries") is not None, f"{label} 缺少重试上限"
        assert policy["max_retries"] <= 1, (
            f"{label} 的重试次数过多(={policy['max_retries']}) —— "
            "Redis 不可达时每一次重试都是一段同步阻塞"
        )
