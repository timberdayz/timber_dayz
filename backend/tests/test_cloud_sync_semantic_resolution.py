#!/usr/bin/env python3
"""语义层可解析性巡检（批次 3.2）的契约守护测试。

**纯函数**验证，不连数据库。

守护的是这条巡检的核心语义 —— **按月分档**：

* 对齐生效日**之前**的月份 ⇒ 「已知历史遗留」，**不报警**
  （那些行按业务决定永远不修，不分档的话告警会永远红 ⇒ 告警就废了）；
* 对齐生效日**之后**的月份 ⇒ unknown 占比超阈值才报警；
* **未配置**对齐生效日 ⇒ 全部按「已知历史遗留」处理（宁可不报，也不误报）。
"""

from __future__ import annotations

import os
from datetime import date, datetime, timezone

import pytest

from backend.services.data_pipeline.cloud_sync_integrity_service import (
    ALIGNMENT_EFFECTIVE_DATE_ENV,
    SEMANTIC_UNKNOWN_RATE_THRESHOLD,
    SEMANTIC_UNKNOWN_RATE_THRESHOLD_ENV,
    CloudSyncIntegrityReport,
    SemanticResolutionRow,
    classify_semantic_resolution,
    resolve_alignment_effective_date,
    resolve_semantic_unknown_rate_threshold,
)

THRESHOLD = 0.05


def _classify(month: date, total: int, unknown: int, effective: date | None):
    return classify_semantic_resolution(
        month_start=month,
        total_rows=total,
        unknown_rows=unknown,
        alignment_effective_date=effective,
        threshold=THRESHOLD,
    )


def test_months_before_alignment_are_known_legacy_and_never_alarm() -> None:
    """分界日之前的月份即使 100% unknown 也不报警。"""
    bucket, status, rate = _classify(date(2026, 3, 1), 100, 100, date(2026, 11, 10))
    assert bucket == "known_legacy"
    assert status == "ok"
    assert rate == pytest.approx(1.0)


def test_months_after_alignment_alarm_when_rate_exceeds_threshold() -> None:
    bucket, status, rate = _classify(date(2026, 12, 1), 100, 10, date(2026, 11, 10))
    assert bucket == "post_alignment"
    assert status == "degraded"
    assert rate == pytest.approx(0.1)


def test_months_after_alignment_are_ok_when_rate_below_threshold() -> None:
    bucket, status, rate = _classify(date(2026, 12, 1), 1000, 10, date(2026, 11, 10))
    assert bucket == "post_alignment"
    assert status == "ok"
    assert rate == pytest.approx(0.01)


def test_alignment_boundary_month_is_post_alignment() -> None:
    """生效日**所在月**算「之后」—— 那个月的数据有一部分在对齐后采。"""
    bucket, _, _ = _classify(date(2026, 11, 1), 100, 100, date(2026, 11, 10))
    assert bucket == "post_alignment"


def test_missing_effective_date_treats_everything_as_known_legacy() -> None:
    """未配置生效日 ⇒ 全部按历史遗留处理（宁可不报，也不误报）。"""
    bucket, status, _ = _classify(date(2030, 1, 1), 100, 100, None)
    assert bucket == "known_legacy"
    assert status == "ok"


def test_zero_rows_yields_zero_rate() -> None:
    bucket, status, rate = _classify(date(2026, 12, 1), 0, 0, date(2026, 11, 10))
    assert rate == 0.0
    assert status == "ok"
    assert bucket == "post_alignment"


def test_resolve_alignment_effective_date(monkeypatch) -> None:
    monkeypatch.delenv(ALIGNMENT_EFFECTIVE_DATE_ENV, raising=False)
    assert resolve_alignment_effective_date() is None

    monkeypatch.setenv(ALIGNMENT_EFFECTIVE_DATE_ENV, "not-a-date")
    assert resolve_alignment_effective_date() is None

    monkeypatch.setenv(ALIGNMENT_EFFECTIVE_DATE_ENV, "2026-11-10")
    assert resolve_alignment_effective_date() == date(2026, 11, 10)


def test_resolve_semantic_unknown_rate_threshold(monkeypatch) -> None:
    monkeypatch.delenv(SEMANTIC_UNKNOWN_RATE_THRESHOLD_ENV, raising=False)
    assert resolve_semantic_unknown_rate_threshold() == SEMANTIC_UNKNOWN_RATE_THRESHOLD

    monkeypatch.setenv(SEMANTIC_UNKNOWN_RATE_THRESHOLD_ENV, "abc")
    assert resolve_semantic_unknown_rate_threshold() == SEMANTIC_UNKNOWN_RATE_THRESHOLD

    monkeypatch.setenv(SEMANTIC_UNKNOWN_RATE_THRESHOLD_ENV, "1.5")
    assert resolve_semantic_unknown_rate_threshold() == SEMANTIC_UNKNOWN_RATE_THRESHOLD

    monkeypatch.setenv(SEMANTIC_UNKNOWN_RATE_THRESHOLD_ENV, "0.2")
    assert resolve_semantic_unknown_rate_threshold() == pytest.approx(0.2)


def _report(rows: list[SemanticResolutionRow]) -> CloudSyncIntegrityReport:
    now = datetime.now(timezone.utc)
    return CloudSyncIntegrityReport(
        run_id="probe",
        started_at=now,
        finished_at=now,
        semantic_rows=rows,
    )


def test_report_counts_degraded_and_legacy_months() -> None:
    report = _report(
        [
            SemanticResolutionRow(
                month_start=date(2026, 3, 1),
                total_rows=527,
                unknown_rows=31,
                unknown_rate=31 / 527,
                bucket="known_legacy",
                status="ok",
            ),
            SemanticResolutionRow(
                month_start=date(2026, 12, 1),
                total_rows=100,
                unknown_rows=20,
                unknown_rate=0.2,
                bucket="post_alignment",
                status="degraded",
            ),
        ]
    )
    assert len(report.degraded_semantic_rows) == 1
    assert len(report.known_legacy_semantic_rows) == 1
    assert report.is_success is False

    summary = report.to_summary()
    assert summary["semantic_months_checked"] == 2
    assert summary["semantic_known_legacy_months"] == 1
    assert summary["degraded_semantic_months"] == 1
    assert "semantic_unknown_after_alignment" in (report.to_error_message() or "")


def test_report_without_degraded_months_is_success() -> None:
    report = _report(
        [
            SemanticResolutionRow(
                month_start=date(2026, 3, 1),
                total_rows=527,
                unknown_rows=31,
                unknown_rate=31 / 527,
                bucket="known_legacy",
                status="ok",
            )
        ]
    )
    assert report.is_success is True
    assert report.to_error_message() is None
    assert report.to_summary()["degraded_semantic_months"] == 0
    assert report.to_summary()["alignment_effective_date"] is None


def test_semantic_sql_has_no_bare_percent_s() -> None:
    """SQL 里不能出现裸 ``%s`` —— psycopg2 会把它当参数占位符。

    这条 SQL 只传一个命名参数, 多一个 ``%s`` 就会报「参数数量不匹配」。
    """
    from backend.services.data_pipeline import cloud_sync_integrity_service as svc

    assert "%s" not in svc._SEMANTIC_RESOLUTION_SQL
    assert "count(*) FILTER (WHERE shop_id = 'unknown')" in svc._SEMANTIC_RESOLUTION_SQL


def test_service_module_exposes_expected_symbols() -> None:
    from backend.services.data_pipeline import cloud_sync_integrity_service as svc

    for name in (
        "collect_semantic_resolution",
        "classify_semantic_resolution",
        "resolve_alignment_effective_date",
        "resolve_semantic_unknown_rate_threshold",
        "SEMANTIC_RESOLUTION_TABLE",
    ):
        assert hasattr(svc, name), name
    assert os.environ.get("PATH")  # 环境正常（防止测试被异常环境污染）
