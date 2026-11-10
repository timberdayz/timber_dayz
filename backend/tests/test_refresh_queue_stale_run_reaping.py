#!/usr/bin/env python3
"""僵尸 run 回收的契约守护测试（P2-2 / 批次 3.5）。

**纯源码**验证，不连数据库 —— 采集机与 CI runner 上没有库时也能跑。

守护的是四条底线：

1. **回收范围是全族** —— 不能再退回封闭白名单
   （白名单一漏，新增的 run 族就又会出现「僵尸永远停在 running」）。
2. **必须留痕** —— ``error_message`` 里要能读出 ``run_id`` / ``pipeline_name`` /
   滞留时长，否则「这条为什么变成 failed」只能靠回放日志。
3. **已有错误信息不被覆盖** —— 原来失败过的那条，错误原因要留住。
4. **阈值安全** —— 45 分钟必须大于刷新队列任务的硬超时（1800 秒 = 30 分钟），
   否则还在正常跑的长任务会被误杀。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REAPER_FILE = PROJECT_ROOT / "backend" / "tasks" / "refresh_queue_tasks.py"
DASHBOARD_BOOTSTRAP_FILE = (
    PROJECT_ROOT / "backend" / "services" / "data_pipeline" / "dashboard_bootstrap.py"
)


@pytest.fixture(scope="module")
def reaper_source() -> str:
    assert REAPER_FILE.exists(), f"回收器缺失: {REAPER_FILE}"
    return REAPER_FILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def dashboard_bootstrap_source() -> str:
    assert DASHBOARD_BOOTSTRAP_FILE.exists()
    return DASHBOARD_BOOTSTRAP_FILE.read_text(encoding="utf-8")


def _reaper_sql(source: str) -> str:
    """抽出回收器里那条 UPDATE 的 SQL 文本。"""
    match = re.search(
        r"UPDATE\s+ops\.pipeline_run_log.*?RETURNING[^'\"]*",
        source,
        re.DOTALL,
    )
    assert match, "找不到回收器里的 UPDATE 语句"
    return match.group(0)


def test_reaper_covers_every_pipeline_family(reaper_source: str) -> None:
    """回收范围必须是**全族** —— 不能再有 pipeline_name 白名单。"""
    sql = _reaper_sql(reaper_source)
    assert "pipeline_name LIKE" not in sql
    assert "trigger_source =" not in sql
    # 全族的唯一条件就是「running + 超阈值」
    assert "WHERE status = 'running'" in sql
    assert "started_at < NOW()" in sql
    assert "make_interval(mins => CAST(:stale_minutes AS integer))" in sql


def test_reaper_leaves_a_trace(reaper_source: str) -> None:
    """必须留痕：run_id / pipeline_name / 滞留时长都要能读出来。

    ⚠ 拼接**不能**用 ``format('...%s...')`` —— ``%s`` 会被 psycopg2 当成参数
    占位符，而这条 SQL 只传一个参数 ⇒ 执行时报「参数数量不匹配」。
    所以一律用 ``||`` 拼字符串。
    """
    sql = _reaper_sql(reaper_source)
    assert "stale_run_reaped_by_safety_net" in sql
    assert "run_id=" in sql
    assert "pipeline=" in sql
    assert "stale_minutes=" in sql
    assert "RETURNING id, run_id, pipeline_name" in sql
    assert "format(" not in sql, "别用 format() 的 %s —— 会被 psycopg2 当参数占位符"
    assert "%s" not in sql, "SQL 里不能出现裸 %s（psycopg2 会当参数占位符）"


def test_reaper_keeps_previous_error_message(reaper_source: str) -> None:
    """已有错误信息要**追加**，不能被回收痕迹覆盖掉。"""
    sql = _reaper_sql(reaper_source)
    assert "CONCAT_WS" in sql
    assert "NULLIF(TRIM(COALESCE(error_message, '')), '')" in sql
    assert "COALESCE(\n                        error_message," not in sql


def test_reaper_never_deletes_rows(reaper_source: str) -> None:
    """回收只改状态，不删行 —— 行是排查历史的一部分。"""
    sql = _reaper_sql(reaper_source)
    assert "DELETE" not in sql.upper()


def test_stale_threshold_exceeds_task_time_limit(reaper_source: str) -> None:
    """阈值必须大于刷新队列任务的硬超时（1800 秒 = 30 分钟）。"""
    assert "STALE_PIPELINE_RUN_MINUTES = 45" in reaper_source
    match = re.search(r"time_limit\s*=\s*(\d+)", reaper_source)
    assert match, "找不到刷新队列任务的 time_limit"
    assert int(match.group(1)) == 1800
    assert 45 > 1800 / 60


def test_reaper_symbol_renamed_consistently(reaper_source: str) -> None:
    """函数与常量改名后不能留旧名字的残骸。"""
    assert "_reap_stale_pipeline_runs" in reaper_source
    assert "_reap_stale_dashboard_refresh_runs" not in reaper_source
    assert "STALE_DASHBOARD_REFRESH_RUN_MINUTES" not in reaper_source


def test_active_row_check_keeps_narrow_whitelist(
    dashboard_bootstrap_source: str,
) -> None:
    """活跃行判定**故意保持窄白名单**，不得跟着回收器一起放宽。

    它回答的是「这个看板模块是不是正在刷新」—— 放宽成全族会把
    「任意流水线正在跑」误报成「看板正在刷新」。
    扩面回收只会让那边的僵尸行变成 ``failed``、不再被当成「正在刷新」，
    两边**不需要**同步放宽。
    """
    sql = _active_row_sql(dashboard_bootstrap_source)
    assert "status = 'running'" in sql
    assert "dashboard_materialization_refresh.%" in sql
    assert "dashboard_materialization_rebuild_core.%" in sql
    assert "trigger_source = 'materialization_refresh'" in sql
    assert "dashboard_safety_net_repair" not in sql


def _active_row_sql(source: str) -> str:
    match = re.search(
        r"FROM\s+ops\.pipeline_run_log.*?ORDER BY started_at DESC",
        source,
        re.DOTALL,
    )
    assert match, "找不到活跃行判定的 SQL"
    return match.group(0)


def test_reaper_module_has_no_syntax_error() -> None:
    """改完的模块至少要能被 Python 解析（挡掉低级语法错）。"""
    ast.parse(REAPER_FILE.read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_reaper_runtime_reads_reaped_rows_via_sqlalchemy_contract() -> None:
    """回收器的**运行路径**必须真能把回收行读出来（不能只扫源码）。

    为什么源码扫描不够 —— 2026-11-11 实测：
    批次 3.5 把回收器从 ``result.fetchall()`` 改成 ``result.mappings().all()``
    （SQLAlchemy 2.0 的标准用法），而
    ``backend/tests/data_pipeline/test_dashboard_asset_self_lock_guardrails.py``
    里的 fake 仍返回 list ⇒ ``AttributeError: 'list' object has no attribute
    'all'`` ⇒ 那条守护测试直接红掉；又因为 CI 的 ``test (3.11)``
    **只跑本次改动到的测试文件**，这个文件没被跑到 ⇒ 红了好几天没人看见。

    ⇒ 这里补一条**真跑**的用例：fake 按 SQLAlchemy 2.0 的
    ``mappings().all()`` 契约给行。只要生产代码再改一次结果消费方式，
    这条用例会立刻红。
    """
    from backend.tasks import refresh_queue_tasks as task_module

    class _MappingRows:
        """``MappingResult`` 的最小替身：既有 ``.all()`` 也能迭代。"""

        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return list(self._rows)

        def __iter__(self):
            return iter(self._rows)

    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def mappings(self):
            return _MappingRows(self._rows)

    class _Session:
        def __init__(self):
            self.committed = 0
            self.statements: list[str] = []

        async def execute(self, stmt, params=None):
            self.statements.append(str(stmt))
            return _Result(
                [
                    {"id": 1, "run_id": "run-1", "pipeline_name": "any_family"},
                    {"id": 2, "run_id": "run-2", "pipeline_name": "another_family"},
                ]
            )

        async def commit(self):
            self.committed += 1

    session = _Session()
    reaped = await task_module._reap_stale_pipeline_runs(session)

    assert reaped == 2, "回收器没把回收行读出来 —— 结果消费方式与 fake 的契约对不上"
    assert session.committed == 1
    assert any(
        "UPDATE ops.pipeline_run_log" in sql for sql in session.statements
    ), "回收器没有发那条 UPDATE"
