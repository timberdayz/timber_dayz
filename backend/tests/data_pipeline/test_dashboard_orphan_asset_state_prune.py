"""孤儿记账行清理的守护测试（批次 4.1 / P3-1）。

守护的边界（与方案原文一一对应）：

1. 孤儿记账行 = ``ops.dashboard_asset_state`` 里 ``module_name``
   **不在** ``DASHBOARD_MODULE_TARGETS`` 的行；
2. ``--dry-run`` **不产生任何写入**（账本行数不变）；
3. 真删时**只删记账行** —— 不动任何物化对象 / 视图 / 表；
4. 删除前**写了日志**（module_name / 删除时间 / 行数）；
5. 清理与写记账**在同一事务**里（要么都成，要么都不成）。
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path

import pytest

from backend.services.data_pipeline import dashboard_bootstrap


ROOT_DIR = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT_DIR / "scripts" / "bootstrap_postgresql_dashboard.py"

#: 判定一条 SQL 是不是「写语句」——守护测试用它证明 dry-run 没写过东西。
_WRITE_PREFIXES = (
    "INSERT",
    "UPDATE",
    "DELETE",
    "TRUNCATE",
    "DROP",
    "ALTER",
    "CREATE",
)


def _is_write_statement(sql: str) -> bool:
    return sql.strip().upper().startswith(_WRITE_PREFIXES)


def _ledger_rows() -> list[dict]:
    """一份「有两个正常模块 + 一条孤儿行」的台账样本。"""
    return [
        {"module_name": "business_overview", "status": "ready", "run_id": "run-1"},
        {"module_name": "inventory_backlog", "status": "ready", "run_id": "run-2"},
        {"module_name": "clearance_ranking", "status": "ready", "run_id": "run-old"},
    ]


class _FakeResult:
    def __init__(self, *, rows=None, scalar=None, rowcount=0):
        self._rows = list(rows or [])
        self._scalar = scalar
        self.rowcount = rowcount

    def scalar_one_or_none(self):
        return self._scalar

    def mappings(self):
        return self._rows


class _FakeSession:
    """记录所有执行过的 SQL 与 commit —— 用来证明边界没有被越过。"""

    def __init__(self, asset_state_rows=None, *, table_exists=True, events=None):
        self.asset_state_rows = [dict(row) for row in (asset_state_rows or [])]
        self.table_exists = table_exists
        self.statements: list[tuple[str, dict]] = []
        self.commits = 0
        self.events = events if events is not None else []

    async def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append((sql, dict(params or {})))
        self.events.append(("execute", sql))
        if "to_regclass" in sql:
            table = "ops.dashboard_asset_state" if self.table_exists else None
            return _FakeResult(scalar=table)
        if "DELETE FROM" in sql.upper():
            names = set(params.get("module_names") or [])
            self.asset_state_rows = [
                row
                for row in self.asset_state_rows
                if row.get("module_name") not in names
            ]
            return _FakeResult(rowcount=len(names))
        if "SELECT" in sql.upper():
            return _FakeResult(rows=[dict(row) for row in self.asset_state_rows])
        return _FakeResult(rowcount=0)

    async def commit(self):
        self.commits += 1
        self.events.append(("commit", "commit"))

    def write_statements(self) -> list[str]:
        return [sql for sql, _ in self.statements if _is_write_statement(sql)]


def _install_bootstrap_stubs(monkeypatch, session):
    """把 bootstrap 路径上的重活（建表 / 刷资产 / 读状态）换成桩。"""

    async def fake_execute_sql_file(_session, _path):
        return None

    async def fake_execute_refresh_plan(db, targets, **kwargs):
        # 真实实现里每个目标做完就提交（物化视图锁是事务级的）。
        await db.commit()
        return "run-stub"

    async def fake_load_state(_session):
        return {}

    async def fake_inspect(_session):
        return {"ready": True, "modules": {}}

    monkeypatch.setattr(dashboard_bootstrap, "execute_sql_file", fake_execute_sql_file)
    monkeypatch.setattr(
        dashboard_bootstrap, "execute_refresh_plan", fake_execute_refresh_plan
    )
    monkeypatch.setattr(
        dashboard_bootstrap, "_load_dashboard_asset_state", fake_load_state
    )
    monkeypatch.setattr(dashboard_bootstrap, "inspect_dashboard_assets", fake_inspect)


def test_orphan_definition_matches_the_p3_1_fact():
    """事实前提：clearance_ranking 已不是模块，它的视图归 inventory_backlog 管。"""
    module_targets = dashboard_bootstrap.DASHBOARD_MODULE_TARGETS
    backlog_core = module_targets["inventory_backlog"]["core_targets"]

    assert "clearance_ranking" not in module_targets
    assert "api.sku_clearance_ranking_module" in backlog_core


@pytest.mark.asyncio
async def test_orphan_rows_are_rows_whose_module_is_not_a_known_module():
    session = _FakeSession(_ledger_rows())

    orphans = await dashboard_bootstrap.find_orphan_dashboard_asset_state_rows(session)

    names = [row["module_name"] for row in orphans]
    message = f"孤儿行识别错误: {names}"
    assert names == ["clearance_ranking"], message


@pytest.mark.asyncio
async def test_dry_run_writes_nothing_and_keeps_the_ledger_row_count():
    rows = _ledger_rows()
    session = _FakeSession(rows)

    report = await dashboard_bootstrap.prune_orphan_dashboard_asset_state(
        session, dry_run=True
    )

    message = f"dry-run 不该写库，却写了: {session.write_statements()}"
    assert session.write_statements() == [], message
    message = f"dry-run 不该提交事务，却提交了 {session.commits} 次"
    assert session.commits == 0, message
    message = f"dry-run 不该改账本行数，却变成 {len(session.asset_state_rows)}"
    assert len(session.asset_state_rows) == len(rows), message
    message = f"dry-run 报告不对: {report}"
    assert report["deleted_count"] == 0, message
    assert report["pruned"] is False, message
    assert report["would_delete_module_names"] == ["clearance_ranking"], message


@pytest.mark.asyncio
async def test_prune_deletes_only_the_orphan_ledger_rows():
    session = _FakeSession(_ledger_rows())

    report = await dashboard_bootstrap.prune_orphan_dashboard_asset_state(session)

    writes = session.write_statements()
    message = f"应当只有一条 DELETE，却有: {writes}"
    assert len(writes) == 1, message
    statement = writes[0]
    message = f"DELETE 打到了别的对象上: {statement}"
    assert "ops.dashboard_asset_state" in statement, message
    for keyword in ("DROP", "TRUNCATE", "CASCADE", "ALTER", "CREATE"):
        message = f"DELETE 含有禁用关键字 {keyword}: {statement}"
        assert keyword not in statement.upper(), message
    for schema_prefix in ("mart.", "api.", "semantic.", "core.", "b_class."):
        message = f"DELETE 碰到了业务对象 {schema_prefix}: {statement}"
        assert schema_prefix not in statement.lower(), message

    remaining = [row["module_name"] for row in session.asset_state_rows]
    message = f"删错了行，剩下: {remaining}"
    assert remaining == ["business_overview", "inventory_backlog"], message
    message = f"清理报告不对: {report}"
    assert report["deleted_count"] == 1, message
    assert report["deleted_module_names"] == ["clearance_ranking"], message


@pytest.mark.asyncio
async def test_prune_writes_the_log_before_deleting():
    events: list[tuple[str, str]] = []
    session = _FakeSession(_ledger_rows(), events=events)

    class _Recorder(logging.Handler):
        def emit(self, record):
            events.append(("log", record.getMessage()))

    recorder = _Recorder()
    logger = logging.getLogger(dashboard_bootstrap.__name__)
    previous_level = logger.level
    logger.addHandler(recorder)
    logger.setLevel(logging.WARNING)
    try:
        await dashboard_bootstrap.prune_orphan_dashboard_asset_state(session)
    finally:
        logger.removeHandler(recorder)
        logger.setLevel(previous_level)

    kinds = [kind for kind, _ in events]
    message = f"没有写下清理日志: {events}"
    assert "log" in kinds, message
    log_at = kinds.index("log")
    delete_at = next(
        index
        for index, (kind, payload) in enumerate(events)
        if kind == "execute" and "DELETE FROM" in payload.upper()
    )
    message = f"日志必须在删除之前（log_at={log_at}, delete_at={delete_at}）"
    assert log_at < delete_at, message

    log_message = events[log_at][1]
    message = f"日志没记 module_name: {log_message}"
    assert "clearance_ranking" in log_message, message
    message = f"日志没记行数: {log_message}"
    assert "行数=1" in log_message, message
    message = f"日志没记删除时间: {log_message}"
    assert "删除时间=" in log_message, message


@pytest.mark.asyncio
async def test_prune_runs_in_the_same_transaction_as_the_ledger_write(monkeypatch):
    events: list[tuple[str, str]] = []
    session = _FakeSession(_ledger_rows(), events=events)
    _install_bootstrap_stubs(monkeypatch, session)

    await dashboard_bootstrap.bootstrap_dashboard_assets(
        session, module="all", prune_orphan_asset_state=True
    )

    insert_indexes = [
        index
        for index, (kind, payload) in enumerate(events)
        if kind == "execute" and "INSERT INTO ops.dashboard_asset_state" in payload
    ]
    delete_indexes = [
        index
        for index, (kind, payload) in enumerate(events)
        if kind == "execute" and "DELETE FROM ops.dashboard_asset_state" in payload
    ]
    message = f"记账写入没发生: {events}"
    assert insert_indexes, message
    message = f"孤儿清理没发生: {events}"
    assert delete_indexes, message

    last_insert = max(insert_indexes)
    first_delete = min(delete_indexes)
    message = f"清理必须排在记账写入之后（{last_insert} vs {first_delete}）"
    assert last_insert < first_delete, message

    between = events[last_insert + 1 : first_delete]
    commits_between = [kind for kind, _ in between if kind == "commit"]
    message = f"记账写入与孤儿清理之间不能提交事务: {between}"
    assert commits_between == [], message


@pytest.mark.asyncio
async def test_prune_is_off_by_default(monkeypatch):
    session = _FakeSession(_ledger_rows())
    _install_bootstrap_stubs(monkeypatch, session)

    await dashboard_bootstrap.bootstrap_dashboard_assets(session, module="all")

    deletes = [sql for sql, _ in session.statements if "DELETE FROM" in sql.upper()]
    message = f"默认不该删任何东西，却删了: {deletes}"
    assert deletes == [], message
    remaining = [row["module_name"] for row in session.asset_state_rows]
    message = f"默认不该改账本，却变成: {remaining}"
    assert len(remaining) == 3, message


@pytest.mark.asyncio
async def test_prune_report_is_attached_to_the_write_path_report(monkeypatch):
    session = _FakeSession(_ledger_rows())
    _install_bootstrap_stubs(monkeypatch, session)

    report = await dashboard_bootstrap.bootstrap_dashboard_assets(
        session, module="all", prune_orphan_asset_state=True
    )

    prune_report = report.get("orphan_asset_state_prune")
    message = f"报告里没有孤儿清理结果: {report}"
    assert prune_report is not None, message
    message = f"孤儿清理结果不对: {prune_report}"
    assert prune_report["deleted_module_names"] == ["clearance_ranking"], message


def _load_script_module():
    spec = importlib.util.spec_from_file_location(
        "bootstrap_postgresql_dashboard_prune", SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _FakeSessionFactory:
    def __init__(self, session):
        self.session = session

    def __call__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def __aenter__(self):
        return self.session


def test_cli_dry_run_preview_writes_nothing(capsys, monkeypatch):
    script = _load_script_module()
    rows = _ledger_rows()
    session = _FakeSession(rows)
    monkeypatch.setattr(script, "AsyncSessionLocal", _FakeSessionFactory(session))

    exit_code = script.main(["--prune-orphan-asset-state", "--dry-run"])

    message = f"dry-run 退出码应为 0，却是 {exit_code}"
    assert exit_code == 0, message
    message = f"dry-run 不该写库，却写了: {session.write_statements()}"
    assert session.write_statements() == [], message
    message = f"dry-run 不该提交事务，却提交了 {session.commits} 次"
    assert session.commits == 0, message
    message = f"dry-run 不该改账本行数，却变成 {len(session.asset_state_rows)}"
    assert len(session.asset_state_rows) == len(rows), message

    output = capsys.readouterr().out
    message = f"预览输出里没有孤儿行: {output}"
    assert "clearance_ranking" in output, message
    message = f"预览输出没有标明是预览: {output}"
    assert "preview only" in output, message


def test_cli_dry_run_requires_the_prune_flag(capsys, monkeypatch):
    script = _load_script_module()
    session = _FakeSession(_ledger_rows())
    monkeypatch.setattr(script, "AsyncSessionLocal", _FakeSessionFactory(session))

    exit_code = script.main(["--dry-run"])

    message = f"缺 --prune-orphan-asset-state 时退出码应为 2，却是 {exit_code}"
    assert exit_code == 2, message
    message = f"缺 --prune-orphan-asset-state 时不该写库，却写了: {session.write_statements()}"
    assert session.write_statements() == [], message
