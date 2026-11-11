#!/usr/bin/env python3
"""巡检第五项「候选集副本口径健康」的判定守护(纯单元, 不连库)。

为什么要有这一项
----------------
候选集的**物化副本**曾经手抄了一份正本的计算逻辑。两边靠人工保持一致 ——
一旦漂移, 漂移是**静默**的: 不报错、不告警, 看板只会表现为「某个店没人了」。

生产实测(2026-11-11, 只读探测): 副本定义里仍出现 ``core.shop_accounts`` /
``regexp_replace`` ⇒ 它在**自算**; 而副本比正本**少一条**口径
(采集方代号不进候选池) ⇒ 随时可能分叉。

⇒ 这一项把「副本是否还在自算」「副本与正本是否一致」变成**每小时**一次的自动检查,
而不是靠「改口径的人记得重建副本」。

守护的底线
----------
1. **正本都没有 ⇒ 不适用**, 不算问题(不同环境);
2. **有正本没副本** ⇒ missing(问题);
3. **副本定义不读正本 / 出现自算痕迹** ⇒ drifted(问题);
4. **定义对但内容不一致** ⇒ diverged(问题);
5. 以上任何一种都必须让巡检**判失败**(``is_success`` 为 False)并写进结论。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.services.data_pipeline.cloud_sync_integrity_service import (
    IDENTITY_CANDIDATES_MV,
    IDENTITY_CANDIDATES_VIEW,
    CloudSyncIntegrityReport,
    IdentityCandidatesCopyRow,
    collect_identity_candidates_copy,
)


class _FakeResult:
    """模拟真实的 ``Result``：**取过一次就关闭**, 再取会抛异常。"""

    def __init__(self, *, value=None, row=None) -> None:
        self._value = value
        self._row = row
        self._closed = False

    def scalar_one_or_none(self):
        if self._closed:
            raise RuntimeError("This result object is closed.")
        self._closed = True
        return self._value

    def one(self):
        if self._closed:
            raise RuntimeError("This result object is closed.")
        self._closed = True
        return self._row


class _FakeDb:
    """按 SQL 内容分发的最小 ``AsyncSession`` 替身。"""

    def __init__(
        self,
        *,
        has_view: bool = True,
        has_copy: bool = True,
        definition: str = "",
        source_rows: int = 0,
        copy_rows: int = 0,
        view_only: int = 0,
        copy_only: int = 0,
        fail_on_diff: bool = False,
    ) -> None:
        self.has_view = has_view
        self.has_copy = has_copy
        self.definition = definition
        self.source_rows = source_rows
        self.copy_rows = copy_rows
        self.view_only = view_only
        self.copy_only = copy_only
        self.fail_on_diff = fail_on_diff

    async def execute(self, statement, params=None):
        sql = str(statement)
        if "EXCEPT ALL" in sql:
            if self.fail_on_diff:
                raise RuntimeError("boom")
            return _FakeResult(row=(self.view_only, self.copy_only))
        if "pg_get_viewdef" in sql:
            return _FakeResult(value=self.definition)
        if "to_regclass" in sql:
            name = (params or {}).get("name", "")
            exists = (
                self.has_view if name == IDENTITY_CANDIDATES_VIEW else self.has_copy
            )
            return _FakeResult(value=name if exists else None)
        if "count(*)::int FROM" in sql:
            return _FakeResult(row=(self.source_rows, self.copy_rows))
        raise AssertionError("未预期的 SQL: %s" % sql[:120])


def _healthy_definition() -> str:
    return (
        "SELECT platform_code, identity_value_normalized FROM "
        "semantic.shop_identity_resolution_candidates"
    )


def _legacy_definition() -> str:
    return (
        "WITH active_shop_accounts AS (SELECT sa.id FROM core.shop_accounts sa) "
        "SELECT regexp_replace(x, 'a', 'b', 'g') FROM active_shop_accounts"
    )


async def _run(db: _FakeDb):
    return await collect_identity_candidates_copy(db)


# ---------------------------------------------------------------------------
# 判定
# ---------------------------------------------------------------------------


def test_no_source_view_means_not_applicable() -> None:
    import asyncio

    row = asyncio.run(_run(_FakeDb(has_view=False)))
    assert row is None


def test_missing_copy_is_degraded() -> None:
    import asyncio

    row = asyncio.run(_run(_FakeDb(has_copy=False)))
    assert row is not None
    assert row.status == "missing"
    assert row.is_degraded is True


def test_legacy_self_computing_copy_is_drifted() -> None:
    import asyncio

    row = asyncio.run(
        _run(
            _FakeDb(
                definition=_legacy_definition(),
                source_rows=72,
                copy_rows=72,
            )
        )
    )
    assert row is not None
    assert row.status == "drifted"
    assert row.reads_source is False
    assert row.is_degraded is True


def test_definition_without_source_reference_is_drifted() -> None:
    import asyncio

    row = asyncio.run(_run(_FakeDb(definition="SELECT 1 AS platform_code")))
    assert row is not None
    assert row.status == "drifted"


def test_content_mismatch_is_diverged() -> None:
    import asyncio

    row = asyncio.run(
        _run(
            _FakeDb(
                definition=_healthy_definition(),
                source_rows=72,
                copy_rows=70,
                view_only=2,
            )
        )
    )
    assert row is not None
    assert row.status == "diverged"
    assert row.view_only_rows == 2
    assert row.copy_only_rows == 0
    assert row.is_degraded is True


def test_healthy_copy_is_ok() -> None:
    import asyncio

    row = asyncio.run(
        _run(
            _FakeDb(
                definition=_healthy_definition(),
                source_rows=72,
                copy_rows=72,
            )
        )
    )
    assert row is not None
    assert row.status == "ok"
    assert row.reads_source is True
    assert row.copy_rows == 72
    assert row.is_degraded is False


def test_unreadable_diff_is_reported_not_swallowed() -> None:
    """比对失败也要**报出来** —— 不能当没事发生。"""
    import asyncio

    row = asyncio.run(
        _run(
            _FakeDb(
                definition=_healthy_definition(),
                source_rows=72,
                copy_rows=72,
                fail_on_diff=True,
            )
        )
    )
    assert row is not None
    assert row.status == "unknown"
    assert row.is_degraded is True


# ---------------------------------------------------------------------------
# 与巡检结论的联动
# ---------------------------------------------------------------------------


def _report(copy_row: IdentityCandidatesCopyRow | None) -> CloudSyncIntegrityReport:
    now = datetime.now(timezone.utc)
    return CloudSyncIntegrityReport(
        run_id="test",
        started_at=now,
        finished_at=now,
        identity_candidates_copy=copy_row,
    )


def test_degraded_copy_makes_the_whole_check_fail() -> None:
    report = _report(IdentityCandidatesCopyRow(status="drifted"))
    assert report.is_success is False
    assert "identity_candidates_copy" in (report.to_error_message() or "")


def test_missing_copy_row_keeps_the_check_usable() -> None:
    """不适用(``None``)不该把巡检判失败。"""
    report = _report(None)
    assert report.is_success is True


def test_healthy_copy_keeps_the_check_green() -> None:
    report = _report(IdentityCandidatesCopyRow(status="ok", copy_rows=72))
    assert report.is_success is True
    summary = report.to_summary()
    assert summary["identity_candidates_copy_status"] == "ok"
    assert summary["identity_candidates_copy_rows"] == 72


def test_summary_reports_the_copy_status() -> None:
    report = _report(IdentityCandidatesCopyRow(status="diverged", copy_rows=70))
    summary = report.to_summary()
    assert summary["identity_candidates_copy_status"] == "diverged"
    assert summary["identity_candidates_copy_rows"] == 70
