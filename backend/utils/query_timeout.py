"""识别「数据库查询超时」，供看板降级兜底使用。

为什么需要单独一个模块
----------------------
看板的降级兜底（超时 ⇒ 返回上次成功快照）**只在超时这一种故障上触发**。
其它故障（语法错、连接断、权限不足）必须照常抛出去 —— 把它们伪装成
「数据有点旧」会把真 bug 藏起来。

超时在不同栈里长得不一样
------------------------
- asyncpg：``asyncpg.exceptions.QueryCanceledError``，
  消息是 ``canceling statement due to statement timeout``
- psycopg2：``psycopg2.errors.QueryCanceled``
- SQLAlchemy 2.0：把驱动异常包成 ``sqlalchemy.exc.DBAPIError``，
  原始异常挂在 ``.orig`` 上
- SQLAlchemy 连接池/超时：``sqlalchemy.exc.TimeoutError``
- asyncio 自身的取消：``asyncio.CancelledError``（**不算**超时 ——
  那是客户端断开或服务停机，不该拿旧数据糊弄过去）

所以判定不能只看类型，要**沿异常链一路找**：类型命中，或消息命中。
"""

from __future__ import annotations

from typing import Any, Iterator

#: PostgreSQL 取消语句时的标准措辞（asyncpg / psycopg2 都用它）。
_TIMEOUT_MESSAGE_MARKERS = (
    "canceling statement due to statement timeout",
    "canceling statement due to user request",
    "statement timeout",
    "query timeout",
    "timeout expired",
)

#: SQLAlchemy 的超时异常类型（延迟导入，避免把 sqlalchemy 拉进轻量工具链）。
_SQLALCHEMY_TIMEOUT_TYPES: tuple[type[BaseException], ...] = ()


def _sqlalchemy_timeout_types() -> tuple[type[BaseException], ...]:
    global _SQLALCHEMY_TIMEOUT_TYPES
    if not _SQLALCHEMY_TIMEOUT_TYPES:
        try:
            from sqlalchemy.exc import TimeoutError as SATimeoutError
        except Exception:  # pragma: no cover - sqlalchemy 不在时降级为纯消息判定
            _SQLALCHEMY_TIMEOUT_TYPES = ()
        else:
            _SQLALCHEMY_TIMEOUT_TYPES = (SATimeoutError,)
    return _SQLALCHEMY_TIMEOUT_TYPES


def _iter_exception_chain(exc: BaseException) -> Iterator[BaseException]:
    """沿异常链（cause / context / SQLAlchemy 的 ``orig``）逐层展开。

    去重：同一个异常对象可能通过多条路径出现，不能无限展开。
    """
    seen: set[int] = set()
    stack: list[BaseException] = [exc]
    while stack:
        current = stack.pop()
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        yield current

        candidates: list[Any] = [
            getattr(current, "__cause__", None),
            getattr(current, "__context__", None),
            # SQLAlchemy 的 DBAPIError 把驱动原始异常挂在 orig 上
            getattr(current, "orig", None),
        ]
        for candidate in candidates:
            if isinstance(candidate, BaseException):
                stack.append(candidate)


def is_query_timeout_error(exc: BaseException | None) -> bool:
    """这个异常是不是「数据库查询超时」。

    Args:
        exc: 待判定的异常（通常是 ``except`` 块里捕获到的那个）。

    Returns:
        True 表示可以走降级兜底；False 表示必须照常抛出。
    """
    if exc is None:
        return False

    # 客户端断开 / 服务停机 —— 不是超时，不降级。
    if isinstance(exc, asyncio_cancelled_error()):
        return False

    timeout_types = _sqlalchemy_timeout_types()
    for current in _iter_exception_chain(exc):
        if timeout_types and isinstance(current, timeout_types):
            return True
        message = str(current).lower()
        if any(marker in message for marker in _TIMEOUT_MESSAGE_MARKERS):
            return True
        # 驱动异常类名也认（asyncpg.exceptions.QueryCanceledError 等）
        type_name = type(current).__name__.lower()
        if "querycanceled" in type_name or "timeouterror" in type_name:
            return True
    return False


def asyncio_cancelled_error() -> type[BaseException]:
    """``asyncio.CancelledError``（不同 Python 版本继承关系不同，延迟取）。"""
    import asyncio

    return asyncio.CancelledError
