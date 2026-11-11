#!/usr/bin/env python3
"""「云端巡检够不着云端」时**往本地台账留痕**的守护(纯单元, 不连库)。

背景
----
2026-11-07 采集同步丢数事故的直接成因是: **巡检永远 skipped**,
云端停在 11-06 再也没动过, 而**没有任何一条记录**说明「我看不见」。

⇒ 所以「看不见」这件事本身必须**留痕**:
云端不可达时云端那侧的 ``ops.pipeline_run_log`` 写不进去,
只有**本地**台账能留下「巡检还活着、但它够不着云端」的证据。

守护的底线
----------
1. **可达性要先探** —— 必须先 ``SELECT 1``, 才能把「连不上」与「连上了但数据有问题」分开;
2. **不可达 ⇒ 留痕 + 原样抛出** —— 不能把异常吞掉(celery 必须看得见失败);
3. **留痕失败不许影响主流程** —— 留痕自己抛异常时, 抛出来的仍应是**原**异常;
4. **留痕里不许有口令** —— 连接串形态的异常消息必须脱敏;
5. **没配连接串时不算故障** —— 那是「未启用」, 返回 skipped, 不写 failed 记录。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from backend.services.data_pipeline.cloud_sync_integrity_service import (
    CloudSyncIntegrityReport,
)
from backend.tasks import cloud_sync_integrity_tasks as mod


class _FakeResult:
    def __init__(self, value: Any = None) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value

    def fetchall(self) -> list[Any]:
        return []


class _FakeDb:
    """最小可用的 ``AsyncSession`` 替身。"""

    def __init__(
        self, *, fail_on: str | None = None, fail_exc: Exception | None = None
    ):
        self.fail_on = fail_on
        self.fail_exc = fail_exc
        self.calls: list[tuple[str, dict[str, Any] | None]] = []
        self.committed = False
        self.closed = False

    async def execute(self, statement: Any, params: dict[str, Any] | None = None):
        rendered = str(statement)
        self.calls.append((rendered, params))
        if self.fail_on and self.fail_on in rendered:
            raise self.fail_exc or RuntimeError("boom")
        return _FakeResult()

    async def commit(self) -> None:
        self.committed = True

    async def close(self) -> None:
        self.closed = True

    async def __aenter__(self) -> "_FakeDb":
        return self

    async def __aexit__(self, *exc_info: Any) -> bool:
        return False


class _FakeSessionFactory:
    def __init__(self, db: _FakeDb) -> None:
        self._db = db

    def __call__(self) -> _FakeDb:
        return self._db


def _fake_engine() -> Any:
    class _Engine:
        async def dispose(self) -> None:
            return None

    return _Engine()


def _install_engine(monkeypatch, db: _FakeDb) -> None:
    monkeypatch.setattr(mod, "create_async_engine", lambda *a, **k: _fake_engine())
    monkeypatch.setattr(mod, "async_sessionmaker", lambda **k: _FakeSessionFactory(db))


def _report() -> CloudSyncIntegrityReport:
    now = datetime.now(timezone.utc)
    return CloudSyncIntegrityReport(
        run_id="cloud_sync_integrity_test",
        started_at=now,
        finished_at=now,
    )


# ---------------------------------------------------------------------------
# 脱敏
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, must_not_contain",
    [
        (
            "postgresql://timber:sup3rs3cret@134.175.222.171:5432/cloud",
            "sup3rs3cret",
        ),
        (
            "postgresql+asyncpg://timber:p%40ss%2Fword@127.0.0.1:15433/cloud",
            "p%40ss%2Fword",
        ),
    ],
)
def test_redact_credentials_removes_password(raw: str, must_not_contain: str) -> None:
    redacted = mod.redact_credentials(raw)
    assert must_not_contain not in redacted
    assert "***" in redacted
    assert "timber" in redacted


def test_redact_credentials_keeps_plain_message() -> None:
    assert mod.redact_credentials("connection refused") == "connection refused"
    assert mod.redact_credentials("") == ""


# ---------------------------------------------------------------------------
# 编排: 探活 → 留痕 → 原样抛出
# ---------------------------------------------------------------------------


def test_unreachable_cloud_leaves_local_trace_and_reraises(monkeypatch) -> None:
    monkeypatch.setenv("CLOUD_DATABASE_URL", "postgresql://u:p%40ss@127.0.0.1:15433/db")
    probe_error = ConnectionRefusedError("connection refused")
    db = _FakeDb(fail_on="SELECT 1", fail_exc=probe_error)
    _install_engine(monkeypatch, db)

    traced: dict[str, Any] = {}

    async def fake_trace(reason: str, detail: str) -> bool:
        traced["reason"] = reason
        traced["detail"] = detail
        return True

    monkeypatch.setattr(mod, "_record_cloud_check_failure_locally", fake_trace)

    with pytest.raises(ConnectionRefusedError):
        import asyncio

        asyncio.run(mod._run_check())

    assert traced["reason"] == "cloud_unreachable"
    assert "connection refused" in traced["detail"]


def test_trace_failure_never_masks_the_original_error(monkeypatch) -> None:
    """留痕自己炸了, 抛出来的仍必须是**原**异常(探活失败)。"""
    monkeypatch.setenv("CLOUD_DATABASE_URL", "postgresql://u:p%40ss@127.0.0.1:15433/db")
    db = _FakeDb(fail_on="SELECT 1", fail_exc=ConnectionRefusedError("boom"))
    _install_engine(monkeypatch, db)

    async def exploding_trace(reason: str, detail: str) -> bool:
        raise RuntimeError("trace itself failed")

    monkeypatch.setattr(mod, "_record_cloud_check_failure_locally", exploding_trace)

    import asyncio

    with pytest.raises(ConnectionRefusedError):
        asyncio.run(mod._run_check())


def test_reachable_cloud_but_check_failed_is_distinguished(monkeypatch) -> None:
    """探活过了、巡检自己失败 ⇒ reason 是 cloud_check_failed, 不是不可达。"""
    monkeypatch.setenv("CLOUD_DATABASE_URL", "postgresql://u:p%40ss@127.0.0.1:15433/db")
    db = _FakeDb()
    _install_engine(monkeypatch, db)

    async def failing_check(db_session, *, trigger_source: str = "scheduler"):
        raise RuntimeError("query blew up")

    monkeypatch.setattr(mod, "run_cloud_sync_integrity_check", failing_check)

    traced: dict[str, Any] = {}

    async def fake_trace(reason: str, detail: str) -> bool:
        traced["reason"] = reason
        return True

    monkeypatch.setattr(mod, "_record_cloud_check_failure_locally", fake_trace)

    import asyncio

    with pytest.raises(RuntimeError):
        asyncio.run(mod._run_check())

    assert traced["reason"] == "cloud_check_failed"


def test_successful_check_does_not_leave_failure_trace(monkeypatch) -> None:
    monkeypatch.setenv("CLOUD_DATABASE_URL", "postgresql://u:p%40ss@127.0.0.1:15433/db")
    db = _FakeDb()
    _install_engine(monkeypatch, db)

    async def ok_check(db_session, *, trigger_source: str = "scheduler"):
        return _report()

    monkeypatch.setattr(mod, "run_cloud_sync_integrity_check", ok_check)

    traced: list[str] = []

    async def fake_trace(reason: str, detail: str) -> bool:
        traced.append(reason)
        return True

    monkeypatch.setattr(mod, "_record_cloud_check_failure_locally", fake_trace)

    import asyncio

    summary = asyncio.run(mod._run_check())
    assert summary["status"] == "success"
    assert not traced


def test_missing_cloud_url_is_skipped_without_trace(monkeypatch) -> None:
    """没配连接串 ⇒ skipped, **不写** failed 记录(那是「未启用」, 不是故障)。"""
    monkeypatch.delenv("CLOUD_DATABASE_URL", raising=False)
    traced: list[str] = []

    async def fake_trace(reason: str, detail: str) -> bool:
        traced.append(reason)
        return True

    monkeypatch.setattr(mod, "_record_cloud_check_failure_locally", fake_trace)

    import asyncio

    summary = asyncio.run(mod._run_check())
    assert summary["status"] == "skipped"
    assert not traced


# ---------------------------------------------------------------------------
# 留痕本身: 写进本地 ops 表
# ---------------------------------------------------------------------------


def test_local_trace_writes_failed_record_into_ops_table(monkeypatch) -> None:
    db = _FakeDb()
    monkeypatch.setattr(mod, "AsyncSessionLocal", _FakeSessionFactory(db))

    import asyncio

    ok = asyncio.run(
        mod._record_cloud_check_failure_locally(
            "cloud_unreachable",
            "OSError: postgresql://timber:sup3rs3cret@134.175.222.171:5432/cloud refused",
        )
    )
    assert ok is True
    assert db.committed is True
    assert len(db.calls) == 1
    sql, params = db.calls[0]
    assert "ops.pipeline_run_log" in sql
    assert params is not None
    assert params["pipeline_name"] == mod.CLOUD_UNREACHABLE_PIPELINE_NAME
    assert "'failed'" in sql, "留痕必须是 failed 状态(不是 skipped)"
    assert "sup3rs3cret" not in str(params)
    assert "***" in str(params)


def test_local_trace_failure_is_swallowed(monkeypatch) -> None:
    """留痕写不进去(本地库也不可达等) ⇒ 返回 False, 不抛。"""
    db = _FakeDb(fail_on="INSERT INTO", fail_exc=RuntimeError("local db down"))
    monkeypatch.setattr(mod, "AsyncSessionLocal", _FakeSessionFactory(db))

    import asyncio

    ok = asyncio.run(
        mod._record_cloud_check_failure_locally("cloud_unreachable", "boom")
    )
    assert ok is False
