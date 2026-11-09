"""契约测试：异步循环收尾门禁(scripts/verify_async_loop_cleanup.py)。

门禁的定位（SSOT）
------------------
生产连接泄漏的根因是「异步任务怎么收尾」没有唯一做法：有人用
``dispose(close=False)``（不关连接），有人直接裸调 ``asyncio.run(...)``
（连接绑定在已结束的循环上，关不掉）。生产实测 80/80 槽位被占满。

这个门禁把「异步任务必须走统一出口、必须真正关闭连接池」变成机器可判定的规则。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify_async_loop_cleanup.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("verify_async_loop_cleanup", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate():
    return _load_gate()


def _write(tmp_path: Path, rel: str, content: str) -> None:
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def test_gate_script_exists():
    assert SCRIPT.exists(), "门禁脚本必须存在于 scripts/ 下"


def test_repository_has_no_violations(gate):
    """当前仓库必须零违规。"""
    violations, scanned = gate.scan(ROOT, ["backend", "modules"])
    assert scanned > 0, "扫描范围不应为空"
    assert violations == [], "发现异步收尾违规：\n" + "\n".join(violations)


def test_detects_bare_asyncio_run(gate, tmp_path):
    """R1：业务代码里裸调 asyncio.run( 必须被检出。"""
    _write(
        tmp_path,
        "backend/tasks/bad.py",
        "import asyncio\n" "\n" "def task():\n" "    return asyncio.run(_work())\n",
    )
    violations, _ = gate.scan(tmp_path, ["backend"])
    assert any(v.startswith("R1") for v in violations), violations


def test_detects_soft_dispose(gate, tmp_path):
    """R2：dispose(close=False)（不关连接）必须被检出。"""
    _write(
        tmp_path,
        "backend/services/bad.py",
        "def drop(engine):\n" "    engine.sync_engine.dispose(close=False)\n",
    )
    violations, _ = gate.scan(tmp_path, ["backend"])
    assert any(v.startswith("R2") for v in violations), violations


def test_detects_reset_helper_call(gate, tmp_path):
    """R3：调用兜底函数 reset_async_engine_pool_for_new_loop 必须被检出。"""
    _write(
        tmp_path,
        "backend/tasks/bad.py",
        "from backend.models.database import reset_async_engine_pool_for_new_loop\n"
        "\n"
        "def task():\n"
        "    reset_async_engine_pool_for_new_loop()\n",
    )
    violations, _ = gate.scan(tmp_path, ["backend"])
    assert any(v.startswith("R3") for v in violations), violations


def test_unified_runner_is_allowed(gate, tmp_path):
    """统一出口自身允许裸 asyncio.run(（它就是唯一出口）。"""
    _write(
        tmp_path,
        "backend/utils/async_task_runner.py",
        "import asyncio\n"
        "\n"
        "def run_async_task(factory):\n"
        "    return asyncio.run(factory())\n",
    )
    violations, _ = gate.scan(tmp_path, ["backend"])
    assert violations == [], violations


def test_waiver_requires_reason(gate):
    """豁免登记必须写明理由，否则门禁自身报错（防止「随手加白名单」）。"""
    gate.ALLOWED_ASYNCIO_RUN["backend/tasks/ok.py"] = {10: "   "}
    try:
        violations, _ = gate.scan(ROOT, ["backend"])
        assert any(v.startswith("R4") for v in violations), violations
    finally:
        gate.ALLOWED_ASYNCIO_RUN.pop("backend/tasks/ok.py", None)


def test_detects_unclosed_session(gate, tmp_path):
    """R5：自建会话却不关闭，必须被检出（async 引擎用 NullPool，漏关＝漏连接）。"""
    _write(
        tmp_path,
        "backend/services/bad.py",
        "from backend.models.database import AsyncSessionLocal\n"
        "\n"
        "async def write():\n"
        "    db = AsyncSessionLocal()\n"
        "    await db.execute('select 1')\n",
    )
    violations, _ = gate.scan(tmp_path, ["backend"])
    assert any(v.startswith("R5") for v in violations), violations


def test_session_closed_in_finally_is_allowed(gate, tmp_path):
    """R5：finally 里 await db.close() 是正确写法，不该被拦。"""
    _write(
        tmp_path,
        "backend/services/ok.py",
        "from backend.models.database import AsyncSessionLocal\n"
        "\n"
        "async def write():\n"
        "    db = AsyncSessionLocal()\n"
        "    try:\n"
        "        await db.execute('select 1')\n"
        "    finally:\n"
        "        await db.close()\n",
    )
    violations, _ = gate.scan(tmp_path, ["backend"])
    assert not any(v.startswith("R5") for v in violations), violations


def test_async_with_session_is_allowed(gate, tmp_path):
    """R5：``async with AsyncSessionLocal()`` 天然会关，不该被拦。"""
    _write(
        tmp_path,
        "backend/services/ok.py",
        "from backend.models.database import AsyncSessionLocal\n"
        "\n"
        "async def write():\n"
        "    async with AsyncSessionLocal() as db:\n"
        "        await db.execute('select 1')\n",
    )
    violations, _ = gate.scan(tmp_path, ["backend"])
    assert not any(v.startswith("R5") for v in violations), violations


def test_unclosed_session_waiver_requires_reason(gate):
    """R5 的豁免同样必须写明理由。"""
    gate.ALLOWED_UNCLOSED_SESSIONS["backend/tasks/ok.py"] = {10: ""}
    try:
        violations, _ = gate.scan(ROOT, ["backend"])
        assert any(v.startswith("R4") for v in violations), violations
    finally:
        gate.ALLOWED_UNCLOSED_SESSIONS.pop("backend/tasks/ok.py", None)


def test_gate_main_exits_zero_for_clean_repository(gate):
    sys.argv = ["verify_async_loop_cleanup.py", "--root", str(ROOT)]
    assert gate.main() == 0
