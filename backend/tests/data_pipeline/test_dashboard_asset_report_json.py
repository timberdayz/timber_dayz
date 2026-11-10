"""看板资产报告的 **JSON 可序列化**守护测试。

事故现场（2026-11-10）
----------------------
    python scripts/bootstrap_postgresql_dashboard.py --module all --check --json
    → TypeError: Object of type datetime is not JSON serializable

根因链
------
1. ``ops.pipeline_run_log`` 里 ``status='running'`` 的行被**原样**塞进报告
   （``started_at`` / ``completed_at`` 都是 ``timestamptz`` ⇒ 驱动返回 ``datetime``）；
2. 报告被 ``json.dumps(report, ensure_ascii=False)`` 直接序列化（没有 ``default=``）。

⇒ **只要有一趟合法的刷新正在跑**，这条命令就崩。
运维最需要机器可读结论的时刻，恰恰是这条命令不可用的时刻。

这里守的是三个断点：

1. 归一化：**一个**递归入口把 ``datetime`` / ``date`` / ``Decimal`` 收敛掉，
   同时不破坏 ``_normalize_json_value`` 的既有契约（非 dict → ``{}``）；
2. 报告：任何分支下都不含非 JSON 原生类型；
3. CLI：``--check --json`` 端到端不抛异常，时间戳是 ISO 字符串。
"""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pytest

import scripts.bootstrap_postgresql_dashboard as dashboard_cli
from backend.services.data_pipeline import dashboard_bootstrap

_RUNNING_STARTED_AT = datetime(2026, 11, 10, 21, 30, 5)
_RUNNING_COMPLETED_AT = datetime(2026, 11, 10, 21, 34, 45)


class _FakeResult:
    """够用的查询结果替身（只实现被 ``dashboard_bootstrap`` 用到的那几个方法）。"""

    def __init__(self, *, scalar=None, rows=None):
        self._scalar = scalar
        self._rows = list(rows or [])

    def scalar_one_or_none(self):
        return self._scalar

    def scalar_one(self):
        return self._scalar

    def mappings(self):
        return self._rows

    def fetchall(self):
        return self._rows


class _FakeSession:
    """只回放 ``_load_active_dashboard_refresh_runs`` 需要的那两条查询。"""

    def __init__(self, *, running_rows=None):
        self._running_rows = list(running_rows or [])
        self.executed: list[str] = []

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        self.executed.append(sql)
        if "to_regclass('ops.pipeline_run_log')" in sql:
            return _FakeResult(scalar="ops.pipeline_run_log")
        if "FROM ops.pipeline_run_log" in sql:
            return _FakeResult(rows=self._running_rows)
        if "to_regclass('ops.dashboard_asset_state')" in sql:
            return _FakeResult(scalar=None)
        return _FakeResult(rows=[])

    async def commit(self):
        return None


class _FakeSessionContext:
    """让 CLI 的 ``async with AsyncSessionLocal() as session`` 能跑起来。"""

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *_exc_info):
        return False


def _running_row() -> dict:
    """一行 ``status='running'`` 的看板刷新记录（含两个 ``datetime``）。"""
    return {
        "pipeline_name": "dashboard_materialization_refresh.business_overview",
        "run_id": "run-active-1",
        "status": "running",
        "started_at": _RUNNING_STARTED_AT,
        "completed_at": _RUNNING_COMPLETED_AT,
        "context": {"module_name": "business_overview", "target_count": 2},
    }


def _install_fake_assets(monkeypatch) -> None:
    """把「库里资产都在」这一事实钉死（沿用同类测试的打桩方式）。"""
    existing_objects = set()
    for module_name in dashboard_bootstrap.DASHBOARD_MODULE_TARGETS:
        existing_objects.update(dashboard_bootstrap._module_core_plan(module_name))
        existing_objects.update(dashboard_bootstrap._module_refresh_plan(module_name))
    existing_objects.update(dashboard_bootstrap.DASHBOARD_REQUIRED_OBJECTS)

    async def fake_collect(_session):
        return set(dashboard_bootstrap.DASHBOARD_REQUIRED_SCHEMAS), existing_objects

    monkeypatch.setattr(dashboard_bootstrap, "_collect_existing_assets", fake_collect)


def _iter_values(value: Any):
    """递归遍历报告里的每一个叶子值。"""
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _iter_values(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_values(item)
    else:
        yield value


# ── 断点 1：归一化收敛到一个入口，且不破坏既有契约 ─────────────────────────


def test_normalize_json_value_keeps_existing_dict_contract():
    """jsonb 载荷（``context`` / ``details_json``）仍然正常工作。"""
    payload = {"module_name": "business_overview", "target_count": 2}

    normalized = dashboard_bootstrap._normalize_json_value(payload)

    assert normalized == payload
    # 归一化返回的是**副本** ⇒ 调用方随便改都不会污染库里的载荷。
    assert normalized is not payload


@pytest.mark.parametrize("value", [None, [], ["a"], "abc", 123, 3.5, True])
def test_normalize_json_value_returns_empty_dict_for_non_dict(value):
    """非 dict 一律返回 ``{}`` —— 既有 4 个调用点依赖这个行为。"""
    assert dashboard_bootstrap._normalize_json_value(value) == {}


def test_normalize_json_value_converts_nested_datetime_and_decimal():
    """嵌套的 ``datetime`` / ``date`` / ``Decimal`` 都要被收敛掉。"""
    normalized = dashboard_bootstrap._normalize_json_value(
        {
            "started_at": _RUNNING_STARTED_AT,
            "day": date(2026, 11, 10),
            "ratio": Decimal("0.125"),
            "nested": {"completed_at": _RUNNING_COMPLETED_AT},
        }
    )

    assert normalized["started_at"] == "2026-11-10T21:30:05"
    assert normalized["day"] == "2026-11-10"
    assert normalized["ratio"] == 0.125
    assert isinstance(normalized["ratio"], float)
    assert normalized["nested"]["completed_at"] == "2026-11-10T21:34:45"
    # 不带 ``default=`` 的 ``json.dumps`` 也必须成功。
    json.dumps(normalized)


def test_normalize_json_value_recurses_into_lists_and_tuples():
    """``list`` / ``tuple`` 里的元素也要逐层归一化。"""
    normalized = dashboard_bootstrap._normalize_json_value(
        {
            "items": [_RUNNING_STARTED_AT, {"when": date(2026, 1, 2)}],
            "pair": (Decimal("1.5"), "x"),
        }
    )

    assert normalized["items"][0] == "2026-11-10T21:30:05"
    assert normalized["items"][1]["when"] == "2026-01-02"
    assert normalized["pair"] == [1.5, "x"]


def test_build_module_report_normalizes_active_refresh_run():
    """模块报告里的 ``active_refresh_run`` 本身就得是 JSON 安全的。"""
    report = dashboard_bootstrap._build_module_report(
        module_name="business_overview",
        module_state=None,
        existing_objects=set(),
        active_refresh_run={
            "run_id": "run-active",
            "started_at": _RUNNING_STARTED_AT,
        },
    )

    assert report["active_refresh_run"]["started_at"] == "2026-11-10T21:30:05"
    json.dumps(report, ensure_ascii=False)


# ── 断点 2：报告里不允许有非 JSON 原生类型 ─────────────────────────────────


@pytest.mark.asyncio
async def test_inspect_dashboard_assets_serializes_active_refresh_run_timestamps(
    monkeypatch,
):
    """有 ``running`` 行时，报告里的时间戳必须是 ISO 字符串而不是 ``datetime``。"""
    _install_fake_assets(monkeypatch)
    session = _FakeSession(running_rows=[_running_row()])

    report = await dashboard_bootstrap.inspect_dashboard_assets(session)

    active = report["modules"]["business_overview"]["active_refresh_run"]
    assert active is not None
    assert isinstance(active["started_at"], str)
    assert active["started_at"] == _RUNNING_STARTED_AT.isoformat()
    assert isinstance(active["completed_at"], str)
    assert active["completed_at"] == _RUNNING_COMPLETED_AT.isoformat()
    # 关键断言：**不带 ``default=`` 的 ``json.dumps`` 也必须成功**。
    assert json.loads(json.dumps(report, ensure_ascii=False))["modules"]


@pytest.mark.asyncio
async def test_report_contains_no_non_json_native_types(monkeypatch):
    """整份报告递归断言：不含 ``datetime`` / ``date`` / ``Decimal``。"""
    _install_fake_assets(monkeypatch)
    session = _FakeSession(running_rows=[_running_row()])

    report = await dashboard_bootstrap.inspect_dashboard_assets(session)

    offenders = [
        value
        for value in _iter_values(report)
        if isinstance(value, (datetime, date, Decimal))
    ]
    assert offenders == []
    json.dumps(report, ensure_ascii=False)


# ── 断点 3：CLI 端到端不崩 ─────────────────────────────────────────────────


def test_cli_check_json_does_not_crash_while_a_refresh_is_running(monkeypatch, capsys):
    """``--check --json`` 在有刷新在跑时必须照样打印出机器可读结论。"""
    _install_fake_assets(monkeypatch)
    session = _FakeSession(running_rows=[_running_row()])
    monkeypatch.setattr(
        dashboard_cli, "AsyncSessionLocal", lambda: _FakeSessionContext(session)
    )

    exit_code = dashboard_cli.main(["--module", "all", "--check", "--json"])

    payload = json.loads(capsys.readouterr().out)
    active = payload["modules"]["business_overview"]["active_refresh_run"]
    assert isinstance(active["started_at"], str)
    assert active["started_at"] == _RUNNING_STARTED_AT.isoformat()
    assert isinstance(exit_code, int)


def test_cli_print_report_falls_back_to_string_for_leftover_datetime(capsys):
    """最后一道兜底：万一上游还有漏网之鱼，CLI 也不能崩。"""
    dashboard_cli._print_report({"started_at": _RUNNING_STARTED_AT}, True)

    assert json.loads(capsys.readouterr().out)["started_at"] == str(_RUNNING_STARTED_AT)
