"""「数据刷新不再重建普通视图」+「死锁当可重试」的行为测试。

两件事都是 2026-10-26 线上事故的直接对策：
- 重建普通视图要拿 ACCESS EXCLUSIVE 排他锁 → 期间所有并发读写被挡，
  两个刷新进程还会沿视图链 ABBA 死锁
- 死锁是**事务级**失败，SAVEPOINT 救不回来 → 必须回滚整个事务重开
"""

from __future__ import annotations

from typing import Any, Optional

import pytest


class _FakeResult:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value

    def scalar(self) -> Any:
        return self._value

    def fetchall(self) -> list:
        return self._value

    def mappings(self) -> "_FakeResult":
        return self

    def all(self) -> list:
        return self._value


class _FakeSession:
    """记录执行过的 SQL，模拟一个只含视图的库。"""

    def __init__(self, view_kinds: dict[str, Optional[str]]) -> None:
        self.view_kinds = view_kinds
        self.executed: list[str] = []

    async def execute(self, statement: Any, params: Any = None) -> _FakeResult:
        text = str(statement)
        if "pg_class" in text:
            target = (params or {}).get("schema", "")
            name = (params or {}).get("name", "")
            return _FakeResult(self.view_kinds.get(f"{target}.{name}"))
        self.executed.append(text)
        return _FakeResult(None)

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

    def begin_nested(self) -> "_FakeNested":
        return _FakeNested()


class _FakeNested:
    """`db.begin_nested()` 的替身（SAVEPOINT）。"""

    async def __aenter__(self) -> "_FakeNested":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False


@pytest.mark.asyncio
async def test_data_refresh_skips_rebuilding_existing_plain_view(monkeypatch):
    """普通视图已存在 → 数据刷新时**不重建**（不抢排他锁、不挡并发读写）。"""
    from backend.services.data_pipeline import refresh_runner

    session = _FakeSession({"mart.inventory_snapshot_history": "v"})

    executed_files: list[str] = []

    async def _fake_execute_sql_file(db: Any, path: Any) -> None:
        executed_files.append(str(path))

    monkeypatch.setattr(refresh_runner, "execute_sql_file", _fake_execute_sql_file)
    monkeypatch.setattr(
        refresh_runner, "_ensure_ops_tables", lambda db: _noop()
    )

    await refresh_runner.execute_sql_target(
        session,
        "mart.inventory_snapshot_history",
        run_id="run-test",
    )

    assert executed_files == [], "普通视图不该在数据刷新时被重建"
    assert any("CREATE OR REPLACE VIEW" in text for text in session.executed) is False


@pytest.mark.asyncio
async def test_data_refresh_still_recreates_materialized_view(monkeypatch):
    """物化视图**要**重建 —— 它的数据是物理存的，刷新就是刷数据。"""
    from backend.services.data_pipeline import refresh_runner

    session = _FakeSession({"semantic.fact_orders_monthly_atomic_mv": "m"})

    executed_files: list[str] = []

    async def _fake_execute_sql_file(db: Any, path: Any) -> None:
        executed_files.append(str(path))

    monkeypatch.setattr(refresh_runner, "execute_sql_file", _fake_execute_sql_file)
    monkeypatch.setattr(refresh_runner, "_ensure_ops_tables", lambda db: _noop())

    await refresh_runner.execute_sql_target(
        session,
        "semantic.fact_orders_monthly_atomic_mv",
        run_id="run-test",
    )

    assert executed_files, "物化视图必须仍然重建"


@pytest.mark.asyncio
async def test_missing_view_is_created_on_data_refresh(monkeypatch):
    """视图**不存在** → 还是要建（否则下游查询直接失败）。"""
    from backend.services.data_pipeline import refresh_runner

    session = _FakeSession({})

    executed_files: list[str] = []

    async def _fake_execute_sql_file(db: Any, path: Any) -> None:
        executed_files.append(str(path))

    monkeypatch.setattr(refresh_runner, "execute_sql_file", _fake_execute_sql_file)
    monkeypatch.setattr(refresh_runner, "_ensure_ops_tables", lambda db: _noop())

    await refresh_runner.execute_sql_target(
        session,
        "mart.inventory_snapshot_history",
        run_id="run-test",
    )

    assert executed_files, "不存在的视图必须被创建"


@pytest.mark.asyncio
async def test_recreate_views_flag_forces_rebuild(monkeypatch):
    """显式重建入口（scripts/rebuild_views.py）→ 强制重建，不跳过。"""
    from backend.services.data_pipeline import refresh_runner

    session = _FakeSession({"mart.inventory_snapshot_history": "v"})

    executed_files: list[str] = []

    async def _fake_execute_sql_file(db: Any, path: Any) -> None:
        executed_files.append(str(path))

    monkeypatch.setattr(refresh_runner, "execute_sql_file", _fake_execute_sql_file)
    monkeypatch.setattr(refresh_runner, "_ensure_ops_tables", lambda db: _noop())

    await refresh_runner.execute_sql_target(
        session,
        "mart.inventory_snapshot_history",
        run_id="run-test",
        recreate_views=True,
    )

    assert executed_files, "显式重建时视图必须被重建"


# ----------------------------------------------------------------------
# 死锁当可重试
# ----------------------------------------------------------------------


class _FakeDeadlockError(Exception):
    """模拟 asyncpg 的 DeadlockDetectedError（带 sqlstate）。"""

    sqlstate = "40P01"


def test_deadlock_is_detected_as_retryable():
    from backend.tasks.refresh_queue_tasks import _is_retryable_lock_error

    assert _is_retryable_lock_error(_FakeDeadlockError("deadlock detected")) is True


def test_serialization_failure_is_detected_as_retryable():
    from backend.tasks.refresh_queue_tasks import _is_retryable_lock_error

    class _FakeSerializationError(Exception):
        sqlstate = "40001"

    assert _is_retryable_lock_error(_FakeSerializationError()) is True


def test_ordinary_error_is_not_retryable():
    from backend.tasks.refresh_queue_tasks import _is_retryable_lock_error

    assert _is_retryable_lock_error(ValueError("普通错误")) is False


@pytest.mark.asyncio
async def test_deadlock_rolls_back_whole_transaction_and_retries(monkeypatch):
    """死锁 → **回滚整个事务** → 退避 → 重跑整个计划。"""
    from backend.tasks import refresh_queue_tasks

    calls = {"plan": 0, "rollback": 0, "sleep": 0}

    class _Task:
        pipeline_name = "data_ingested_refresh"
        trigger_type = "data_ingested"

    class _DB:
        async def rollback(self) -> None:
            calls["rollback"] += 1

    async def _fake_plan(db: Any, **kwargs: Any) -> dict:
        calls["plan"] += 1
        if calls["plan"] == 1:
            raise _FakeDeadlockError("deadlock detected")
        return {"run_id": "run-ok", "status": "success"}

    async def _fake_sleep(seconds: float) -> None:
        calls["sleep"] += 1

    monkeypatch.setattr(refresh_queue_tasks, "execute_refresh_plan", _fake_plan)
    monkeypatch.setattr(refresh_queue_tasks.asyncio, "sleep", _fake_sleep)

    result = await refresh_queue_tasks._run_plan_with_lock_retry(
        _DB(), _Task(), ["mart.inventory_state"], {}
    )

    assert result["status"] == "success"
    assert calls["plan"] == 2, "死锁后必须重跑整个计划"
    assert calls["rollback"] == 1, "死锁是事务级失败，必须回滚整个事务"
    assert calls["sleep"] == 1, "重试前要退避"


@pytest.mark.asyncio
async def test_non_lock_error_is_not_retried(monkeypatch):
    """普通错误不重试（直接抛）。"""
    from backend.tasks import refresh_queue_tasks

    calls = {"plan": 0}

    class _Task:
        pipeline_name = "data_ingested_refresh"
        trigger_type = "data_ingested"

    class _DB:
        async def rollback(self) -> None:
            return None

    async def _fake_plan(db: Any, **kwargs: Any) -> dict:
        calls["plan"] += 1
        raise ValueError("普通错误")

    monkeypatch.setattr(refresh_queue_tasks, "execute_refresh_plan", _fake_plan)

    with pytest.raises(ValueError):
        await refresh_queue_tasks._run_plan_with_lock_retry(
            _DB(), _Task(), ["mart.inventory_state"], {}
        )

    assert calls["plan"] == 1, "普通错误不该重试"


async def _noop() -> None:
    return None
