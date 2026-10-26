"""「并发共享数据库会话」两道守卫的自测。

守卫本身如果悄悄失效，线上事故就会重演 —— 所以两道都要有测试兜着：

1. 静态守卫 ``scripts/check_async_session_concurrency.py``
2. 运行期巡检 ``scripts/check_backend_session_race.py``
"""

from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD_PATH = REPO_ROOT / "scripts" / "check_async_session_concurrency.py"
RACE_PATH = REPO_ROOT / "scripts" / "check_backend_session_race.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


guard = _load(GUARD_PATH, "check_async_session_concurrency_guard")
race = _load(RACE_PATH, "check_backend_session_race_guard")


def _audit_source(tmp_path: Path, source: str, name: str = "sample.py"):
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return guard.audit_file(path)


# ----------------------------------------------------------------------
# 静态守卫
# ----------------------------------------------------------------------
UNSAFE_SOURCE = """
import asyncio


async def endpoint(db):
    service = DataSyncService(db)
    rows = await asyncio.gather(*[
        service.get_file_sync_readiness(item.id)
        for item in files
    ])
    return rows
"""

SAFE_SOURCE = """
import asyncio


async def endpoint(db):
    async def _one(file_id):
        async with AsyncSessionLocal() as own_db:
            return await DataSyncService(own_db).get_file_sync_readiness(file_id)

    rows = await asyncio.gather(*[_one(item.id) for item in files])
    return rows
"""


def test_guard_flags_session_shared_across_gather(tmp_path):
    """把请求级会话带进 gather → 必须报出来。"""
    findings = _audit_source(tmp_path, UNSAFE_SOURCE)

    assert findings, "并发共享会话的写法必须被守卫抓到"
    assert any("gather" in item[1] for item in findings)
    assert any(
        "service" in item[2] for item in findings
    ), f"应指出间接持有会话的对象，实际：{findings}"


def test_guard_accepts_independent_session_per_coroutine(tmp_path):
    """每个协程自开会话 → 不得误报。"""
    findings = _audit_source(tmp_path, SAFE_SOURCE)

    assert not findings, f"安全的写法不该被误报：{findings}"


def test_guard_ignores_same_name_business_function(tmp_path):
    """业务里叫 ``create_task`` 的普通函数不是 ``asyncio.create_task`` → 不得误报。"""
    source = """
async def endpoint(db, create_task):
    return await create_task(request=req, db=db)
"""
    findings = _audit_source(tmp_path, source)

    assert not findings, f"同名业务函数不该被误报：{findings}"


def test_guard_flags_create_task_with_shared_session(tmp_path):
    """``asyncio.create_task`` 带共享会话 → 同样要报。"""
    source = """
import asyncio


async def endpoint(db):
    return asyncio.create_task(do_work(db))
"""
    findings = _audit_source(tmp_path, source)

    assert findings, "create_task 共享会话也必须被守卫抓到"


# ----------------------------------------------------------------------
# 运行期巡检
# ----------------------------------------------------------------------
def test_race_detector_counts_events_not_traceback_lines(tmp_path):
    """一次事故在日志里留下几十行 traceback —— 只能算**一次**事件。"""
    log = tmp_path / "backend_main.log"
    log.write_text(
        "2026-10-26 14:11:27,434 - backend.main - ERROR - [未处理异常] "
        "GET /api/data-sync/governance/stats - 错误类型: IllegalStateChangeError, "
        "错误消息: Method 'close()' can't be called here; method 'commit()' "
        "is already in progress\n"
        "  |     raise sa_exc.IllegalStateChangeError(\n"
        "  | sqlalchemy.exc.IllegalStateChangeError: Method 'close()' can't be "
        "called here; method 'commit()' is already in progress\n"
        "2026-10-26 14:12:32,181 - backend.main - ERROR - [未处理异常] "
        "GET /api/data-sync/governance/stats - 错误类型: IllegalStateChangeError, "
        "错误消息: Method 'close()' can't be called here; method 'commit()' "
        "is already in progress\n",
        encoding="utf-8",
    )

    hits = race._scan_file(log, None)

    assert len(hits) == 2, f"应识别为 2 次事故，实际 {len(hits)}"
    assert all("governance/stats" in line for _, _, line in hits)


def test_race_detector_ignores_unrelated_errors(tmp_path):
    """普通业务错误不该被当成会话并发冲突。"""
    log = tmp_path / "backend_main.log"
    log.write_text(
        "2026-10-26 14:11:27,434 - backend.main - ERROR - [HTTP异常] "
        "GET /api/data-sync/single - 状态码: 404, 错误: 文件不存在\n",
        encoding="utf-8",
    )

    assert not race._scan_file(log, None)
