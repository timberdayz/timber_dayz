#!/usr/bin/env python3
"""发版后验收快照脚本的契约守护(纯源码, 不连库)。

守护的底线
----------
1. **只读** —— 快照脚本绝不许写库(它跑在生产库上);
2. **零字面量连接串** —— 连接串只从环境变量读;
3. **口径不分叉** —— 快照里的每个数字都必须来自**巡检自己的函数**,
   否则「快照说的」与「巡检判的」会悄悄分叉;
4. **先加载 .env 再 import 数据库模块** —— 否则脚本开箱不可用
   (``backend.models.database`` 在 import 时就按 ``DATABASE_URL`` 建引擎);
5. **脱敏** —— 快照里绝不含口令。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "verify_release_snapshot.py"

#: 脚本里绝不允许出现的写库关键字。
FORBIDDEN_SQL_KEYWORDS = (
    "INSERT INTO",
    "UPDATE ",
    "DELETE FROM",
    "DROP ",
    "CREATE ",
    "ALTER ",
    "TRUNCATE",
)

#: 快照必须复用巡检的这些入口(口径不分叉)。
REQUIRED_SERVICE_IMPORTS = (
    "collect_identity_candidates_copy",
    "collect_semantic_resolution",
    "resolve_alignment_effective_date",
    "resolve_semantic_unknown_rate_threshold",
)


@pytest.fixture(scope="module")
def script_source() -> str:
    assert SCRIPT_PATH.exists(), "发版快照脚本缺失: %s" % SCRIPT_PATH
    return SCRIPT_PATH.read_text(encoding="utf-8")


def _string_literals(source: str) -> list[str]:
    tree = ast.parse(source)
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def test_script_is_read_only(script_source: str) -> None:
    offenders: list[str] = []
    for literal in _string_literals(script_source):
        upper = literal.upper()
        for keyword in FORBIDDEN_SQL_KEYWORDS:
            if keyword in upper:
                offenders.append("%s <- %r" % (keyword, literal[:60]))
    assert not offenders, "快照脚本必须只读: %s" % offenders


def test_script_has_no_literal_database_url(script_source: str) -> None:
    assert "postgresql://" not in script_source
    assert "postgres://" not in script_source


def test_script_reuses_the_service_verdicts(script_source: str) -> None:
    """快照的每个数字都必须来自巡检自己的函数。"""
    for name in REQUIRED_SERVICE_IMPORTS:
        assert name in script_source, "快照脚本没有复用巡检入口: %s" % name


def test_script_loads_env_before_importing_database_modules(
    script_source: str,
) -> None:
    """``load_project_env`` 必须排在 ``backend.models.database`` 之前。"""
    load_at = script_source.find("load_project_env(")
    database_at = script_source.find("from backend.models.database import")
    assert load_at > 0, "快照脚本必须加载 .env"
    assert database_at > 0, "快照脚本必须用 get_async_database_url"
    assert load_at < database_at, (
        "必须先加载 .env 再 import backend.models.database"
        "(它 import 时就按 DATABASE_URL 建引擎)"
    )


def test_script_masks_credentials(script_source: str) -> None:
    assert "_masked_target" in script_source
    assert "make_url" in script_source


def test_script_reports_the_health_verdict(script_source: str) -> None:
    """快照必须给出**明确结论**(通过 / 不通过), 而不只是打印数字。"""
    assert "healthy" in script_source
    assert "return 0 if healthy else 1" in script_source
