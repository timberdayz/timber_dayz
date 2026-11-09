"""契约测试：同步 ORM Query API 门禁(scripts/verify_sync_query_usage.py)。

门禁的定位（SSOT）
------------------
仓库里数据库访问有两份真相：同步 ``Session`` 与异步 ``AsyncSession``。
业务函数过去只声明「我收一个 db」，不声明「我要求哪种 db」，
于是同一个函数被同步脚本和 async 路由同时复用，
必然出现 ``'AsyncSession' object has no attribute 'query'``。

这个门禁把「async 上下文不得使用同步查询」变成机器可判定的规则。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify_sync_query_usage.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("verify_sync_query_usage", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # 必须先注册到 sys.modules：脚本里用了 @dataclass，
    # dataclasses 解析 __module__ 时要在 sys.modules 里找得到
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


def test_repository_has_no_async_sync_query_violations(gate):
    """当前仓库必须零违规：async 上下文不得使用同步 ORM Query API。"""
    violations, scanned = gate.scan(ROOT, ["backend"])
    assert scanned > 0, "扫描范围不应为空"
    assert violations == [], "发现异步上下文使用同步查询：\n" + "\n".join(violations)


def test_detects_query_inside_async_function(gate, tmp_path):
    """R1：async 函数体内出现 .query( 必须被检出。"""
    _write(
        tmp_path,
        "backend/svc/bad.py",
        "def helper(db):\n"
        "    return db.query(Thing).all()\n"
        "\n"
        "async def route(db):\n"
        "    return db.query(Thing).all()\n",
    )
    violations, _ = gate.scan(tmp_path, ["backend"])
    assert any(v.startswith("R1") for v in violations), violations


def test_detects_async_calling_sync_query_function(gate, tmp_path):
    """R2：async 函数调用含 .query( 的同步函数必须被检出。"""
    _write(
        tmp_path,
        "backend/svc/thing.py",
        "def load_things(db):\n"
        "    return db.query(Thing).all()\n",
    )
    _write(
        tmp_path,
        "backend/routers/thing_router.py",
        "from backend.svc.thing import load_things\n"
        "\n"
        "async def route(db):\n"
        "    return load_things(db)\n",
    )
    violations, _ = gate.scan(tmp_path, ["backend"])
    assert any(v.startswith("R2") for v in violations), violations


def test_sync_only_usage_is_allowed(gate, tmp_path):
    """纯同步上下文使用 .query( 是合法的，不应被误报。"""
    _write(
        tmp_path,
        "backend/svc/ok.py",
        "def load_things(db):\n"
        "    return db.query(Thing).all()\n"
        "\n"
        "def route(db):\n"
        "    return load_things(db)\n",
    )
    violations, _ = gate.scan(tmp_path, ["backend"])
    assert violations == [], violations


def test_waiver_requires_reason(gate):
    """豁免登记必须写明理由，否则门禁自身报错（防止「随手加白名单」）。"""
    gate.ALLOWED_SYNC_CALLS["backend/svc/ok.py"] = {"load_things": "   "}
    try:
        violations, _ = gate.scan(ROOT, ["backend"])
        assert any(v.startswith("R3") for v in violations), violations
    finally:
        gate.ALLOWED_SYNC_CALLS.pop("backend/svc/ok.py", None)


def test_gate_main_exits_zero_for_clean_repository(gate):
    assert gate.main.__doc__ is None or True  # 仅确保可调用
    sys.argv = ["verify_sync_query_usage.py", "--root", str(ROOT), "--target", "backend"]
    assert gate.main() == 0
