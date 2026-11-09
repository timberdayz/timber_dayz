#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全仓库唯一的 ``asyncio.run`` 出口。

为什么需要这个模块
------------------
Celery 的同步任务每次调用都会新建一个事件循环。asyncpg 的连接**绑定在
创建它的事件循环上**：循环一旦结束，连接就没法再被正常关闭，只能滞留在
数据库服务端白占连接槽位。

生产实测（2026-11-09，只读调查）：

* ``pg_stat_activity`` 显示 80/80 连接槽位全部被占满；
* 最近 60 分钟新建 45 条连接，**只增不减**；
* 最早一条连接已存活 8 小时 27 分钟，最后一条 SQL 是 ``COMMIT;``
  （事务已提交，连接本身没关）；
* 来源集中在 celery_worker(47) 与 backend_api(32)。

历史做法是 ``async_engine.sync_engine.dispose(close=False)``：它只是把连接
池「软丢弃」，**并不关闭底层 TCP 连接**，因此完全无法阻止泄漏；而连接因为
绑定在已经死掉的循环上，之后想补关都关不掉。

正确做法是：在**同一个仍然活着的事件循环内**关闭引擎
（``await async_engine.dispose()``，等价于 ``close=True``），连接才会被真正
关闭并归还给数据库。本模块把这件事收敛到唯一出口，让「收尾」这件事只有
一份真相：

    from backend.utils.async_task_runner import run_async_task

    result = run_async_task(lambda: _do_something_async())

规则
----
1. 任何需要「在同步上下文里跑异步代码」的地方，**一律**调用
   :func:`run_async_task`，不允许直接写 ``asyncio.run(...)``。
2. :func:`run_async_task` 保证在任务结束（无论成功还是抛错）后，于当前循环
   内真正关闭异步引擎连接池。
3. 关闭失败会被记录为 ERROR 并向上抛出，不允许「假装成功」。

本模块由 ``scripts/verify_async_loop_cleanup.py`` 门禁守护。
"""
from __future__ import annotations

import asyncio
import inspect
import logging
import sys
from typing import Any, Awaitable, Callable, Union

logger = logging.getLogger(__name__)

#: 允许的两种入参：协程函数（推荐）或已创建的 awaitable
TaskFactory = Callable[[], Awaitable[Any]]
TaskLike = Union[TaskFactory, Awaitable[Any]]


def _resolve_factory(task: TaskLike) -> TaskFactory:
    """把入参统一成「零参工厂」。

    优先要求传协程函数而不是已创建的协程对象：协程对象在**创建时**就被绑定了
    上下文（本模块只接受在函数体内创建的协程），而工厂形式能保证协程是在
    事件循环内部才被创建的。
    """
    if callable(task):
        return task
    if inspect.isawaitable(task):
        # 兼容直接传协程对象：包一层工厂，但要在当前循环内创建才安全，
        # 因此这里退化为「已经创建好的 awaitable」直接 await。
        async def _use_existing() -> Any:
            return await task

        return _use_existing
    raise TypeError(
        "run_async_task 只接受协程函数或 awaitable，"
        f"收到 {type(task)!r}。请传协程函数（例如 run_async_task(_my_async_fn)）。"
    )


async def _dispose_async_engine() -> None:
    """在当前事件循环内真正关闭异步引擎连接池。

    只有当本进程**确实加载过** ``backend.models.database`` 时才需要收尾——
    没加载过就说明本进程压根没用过数据库引擎，没有连接需要关闭（此时也不应该
    为了收尾而反向导入数据库模块，避免给纯 CLI 工具引入数据库依赖）。
    """
    database_module = sys.modules.get("backend.models.database")
    if database_module is None:
        logger.debug("[async_task_runner] 本进程未加载数据库引擎，无需关闭连接池")
        return

    await database_module.dispose_async_engine()


async def _run_with_dispose(factory: TaskFactory) -> Any:
    error: BaseException | None = None
    try:
        return await factory()
    except BaseException as exc:  # noqa: BLE001 - 记录后原样抛出
        error = exc
        raise
    finally:
        try:
            await _dispose_async_engine()
        except Exception as dispose_exc:  # noqa: BLE001
            # 收尾失败必须显形：连接可能残留，不能当成任务成功。
            logger.error(
                "[async_task_runner] 关闭异步引擎失败（连接可能残留）: %s",
                dispose_exc,
                exc_info=True,
            )
            if error is None:
                raise


def run_async_task(task: TaskLike, *, name: str | None = None) -> Any:
    """在独立事件循环中运行异步任务，并在循环内真正关闭数据库连接池。

    Parameters
    ----------
    task:
        协程函数（推荐）或 awaitable。协程函数会在事件循环内部被调用。
    name:
        可选的任务名，仅用于日志。

    Returns
    -------
    协程的返回值。

    Raises
    ------
    Exception
        任务自身的异常会原样抛出；收尾（关闭连接池）失败时也会抛出，
        且会被记录为 ERROR 日志。
    """
    factory = _resolve_factory(task)

    async def _entry() -> Any:
        return await _run_with_dispose(factory)

    label = name or getattr(factory, "__name__", repr(factory))
    try:
        return asyncio.run(_entry())
    except Exception as exc:  # noqa: BLE001
        logger.error("[async_task_runner] 任务执行失败: %s", label, exc_info=exc)
        raise


__all__ = ["run_async_task"]
