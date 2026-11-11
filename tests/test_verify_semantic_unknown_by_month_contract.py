#!/usr/bin/env python3
"""「逐月看语义层认不出店占比」验收脚本的契约守护(纯源码 / 纯函数, 不连库)。

守护的底线
----------
1. **口径不分叉** —— 脚本必须复用巡检的 ``collect_semantic_resolution`` /
   ``resolve_alignment_effective_date`` / ``resolve_semantic_unknown_rate_threshold``,
   **不许**自己写一份 SQL, **不许**自己写一份分档规则。
   ⇒ 否则脚本打印的「结论」和巡检会判的「结论」会悄悄分叉,
   而运维拿脚本的存档当巡检的证据 ⇒ 证据本身不可信。
2. **只读** —— 脚本源码里不许出现写库语句(INSERT/UPDATE/DELETE/DROP/CREATE/ALTER)。
3. **零字面量连接串** —— 连接串只从环境变量读, 源码里不出现 ``postgresql://``。
4. **脱敏** —— 打印与 JSON 存档里绝不含用户名 / 口令。
5. **公开别名不分叉** —— 脚本用的公开入口与巡检内部入口必须给出**同一个**结论。

为什么要有第 5 条
----------------
:func:`backend.tasks.cloud_sync_integrity_tasks.resolve_cloud_database_url_from_env`
是「仓库外脚本」与「巡检任务」共用的**唯一**云端连接串入口。
早期只有私有名 ``_resolve_...``, 脚本若自己另写一份主机名规整,
就会出现「脚本能连上、巡检连不上」⇒ 脚本的结论被误当成巡检的结论。
"""

from __future__ import annotations

import ast
import importlib.util
import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from backend.services.data_pipeline.cloud_sync_integrity_service import (
    SemanticResolutionRow,
    classify_semantic_resolution,
)
from backend.tasks.cloud_sync_integrity_tasks import (
    _resolve_cloud_database_url_from_env,
    resolve_cloud_database_url_from_env,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "verify_semantic_unknown_by_month.py"

#: 脚本必须复用的巡检口径入口(SSOT)。
REQUIRED_SERVICE_IMPORTS = (
    "collect_semantic_resolution",
    "resolve_alignment_effective_date",
    "resolve_semantic_unknown_rate_threshold",
)

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


@pytest.fixture(scope="module")
def script_source() -> str:
    assert SCRIPT_PATH.exists(), "逐月验收脚本缺失: %s" % SCRIPT_PATH
    return SCRIPT_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def script_module():
    spec = importlib.util.spec_from_file_location(
        "verify_semantic_unknown_by_month", SCRIPT_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _imported_names(source: str, module_path: str) -> set[str]:
    """取出 ``from <module_path> import (...)`` 里导入的名字。"""
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module != module_path:
            continue
        for alias in node.names:
            names.add(alias.name)
    return names


# ---------------------------------------------------------------------------
# 1. 公开别名: 与私有名必须同一个结论
# ---------------------------------------------------------------------------


def test_public_alias_matches_private_alias(monkeypatch) -> None:
    """公开名与私有名必须给出**完全相同**的规整结果(不分叉)。"""
    monkeypatch.setenv(
        "CLOUD_DATABASE_URL", "postgresql://u:p%40ss@127.0.0.1:15433/clouddb"
    )
    monkeypatch.delenv("CLOUD_SYNC_TUNNEL_ENABLED", raising=False)
    monkeypatch.delenv("CLOUD_SYNC_TUNNEL_HOST", raising=False)
    monkeypatch.delenv("CLOUD_SYNC_TUNNEL_PORT", raising=False)

    public = resolve_cloud_database_url_from_env()
    private = _resolve_cloud_database_url_from_env()
    assert public == private, "公开别名与私有名给出了不同结论 ⇒ 口径已分叉"
    assert public.url == "postgresql://u:p%40ss@127.0.0.1:15433/clouddb"


def test_public_alias_is_the_one_the_script_uses(script_module) -> None:
    """脚本必须用**公开**入口(否则脚本与巡检可能各走各的)。"""
    assert (
        script_module.resolve_cloud_database_url_from_env
        is resolve_cloud_database_url_from_env
    )


# ---------------------------------------------------------------------------
# 2. 口径 SSOT: 脚本不许自写 SQL / 自写分档
# ---------------------------------------------------------------------------


def test_script_reuses_service_layer_entrypoints(script_source: str) -> None:
    imported = _imported_names(
        script_source, "backend.services.data_pipeline.cloud_sync_integrity_service"
    )
    missing = [name for name in REQUIRED_SERVICE_IMPORTS if name not in imported]
    assert not missing, "脚本没有复用巡检口径入口: %s" % missing


def _called_names(source: str) -> set[str]:
    """取出脚本里被调用的**裸函数名**(不含属性调用)。"""
    tree = ast.parse(source)
    return {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }


def _string_literals(source: str) -> list[str]:
    tree = ast.parse(source)
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def test_script_has_no_own_sql_dialect(script_source: str) -> None:
    """脚本里不该出现 SQL 执行入口(逐月统计由巡检的 collect 负责)。"""
    called = _called_names(script_source)
    offenders = [
        name for name in ("text", "execute", "exec_driver_sql") if name in called
    ]
    assert not offenders, "脚本自己执行 SQL, 口径会与巡检分叉: %s" % offenders
    assert (
        "SEMANTIC_RESOLUTION_TABLE" not in script_source
    ), "脚本不该自己拼语义层表名(那是巡检的 SSOT)"


def test_script_has_no_own_bucket_rule(script_source: str) -> None:
    """脚本不许自己判「历史遗留 / 新问题」——分档必须来自 collect 的返回值。"""
    offenders = [
        token
        for token in (
            "boundary",
            "month_start <",
            "month_start >",
            "replace(day=1)",
            "known_legacy",
            "post_alignment",
        )
        if token in script_source
    ]
    assert not offenders, "脚本自己判了分档, 口径会与巡检分叉: %s" % offenders


def test_script_has_no_write_statements(script_source: str) -> None:
    """脚本的字符串字面量里不许出现写库语句(只读是硬底线)。"""
    offenders: list[str] = []
    for literal in _string_literals(script_source):
        upper = literal.upper()
        for keyword in FORBIDDEN_SQL_KEYWORDS:
            if keyword in upper:
                offenders.append("%s <- %r" % (keyword, literal[:60]))
    assert not offenders, "验收脚本必须是只读的, 却出现了写库语句: %s" % offenders


def test_script_has_no_literal_database_url(script_source: str) -> None:
    assert "postgresql://" not in script_source, "连接串不许写死在源码里"
    assert "postgres://" not in script_source, "连接串不许写死在源码里"


def test_script_uses_make_url_for_parsing(script_source: str) -> None:
    assert "make_url" in script_source, "连接串解析必须走 sqlalchemy.engine.make_url()"


# ---------------------------------------------------------------------------
# 3. 行为: 传给巡检的参数 / 输出与巡检分档一致
# ---------------------------------------------------------------------------


def _rows() -> list[SemanticResolutionRow]:
    """构造三个月的样例(含历史遗留月、新问题月、干净月)。"""
    return [
        SemanticResolutionRow(
            month_start=date(2026, 11, 1),
            total_rows=127,
            unknown_rows=72,
            unknown_rate=72 / 127,
            bucket="known_legacy",
            status="ok",
        ),
        SemanticResolutionRow(
            month_start=date(2026, 12, 1),
            total_rows=100,
            unknown_rows=3,
            unknown_rate=0.03,
            bucket="post_alignment",
            status="degraded",
        ),
        SemanticResolutionRow(
            month_start=date(2027, 1, 1),
            total_rows=100,
            unknown_rows=0,
            unknown_rate=0.0,
            bucket="post_alignment",
            status="ok",
        ),
    ]


@pytest.fixture
def captured_collect(monkeypatch, script_module):
    """把脚本的 ``_collect`` 换成假实现, 顺便记录它传给巡检的参数。"""
    captured: dict[str, Any] = {}

    async def fake_collect(url, effective_date, threshold):
        captured["url"] = url
        captured["effective_date"] = effective_date
        captured["threshold"] = threshold
        return _rows()

    monkeypatch.setattr(script_module, "_collect", fake_collect)
    monkeypatch.setattr(
        script_module,
        "_resolve_target",
        lambda target: "postgresql://u:p%40ss@127.0.0.1:15433/clouddb",
    )
    return captured


def test_script_passes_effective_date_and_threshold_through(
    captured_collect, script_module
) -> None:
    exit_code = script_module.main(
        ["--target", "cloud", "--effective-date", "2026-12-01", "--threshold", "0"]
    )
    assert exit_code == 1, "存在 degraded 月份时退出码必须是 1"
    assert captured_collect["effective_date"] == date(2026, 12, 1)
    assert captured_collect["threshold"] == 0.0


def test_script_reads_effective_date_from_env(
    monkeypatch, captured_collect, script_module
) -> None:
    monkeypatch.setenv("SHOP_IDENTITY_ALIGNMENT_EFFECTIVE_DATE", "2026-12-01")
    script_module.main(["--target", "cloud"])
    assert captured_collect["effective_date"] == date(2026, 12, 1)


def test_script_bucket_matches_service_classification(
    captured_collect, script_module, capsys
) -> None:
    """脚本打印的每个月的分档/状态, 必须等于巡检分类函数算出来的结果。"""
    script_module.main(["--target", "cloud", "--effective-date", "2026-12-01"])
    out = capsys.readouterr().out
    for row in _rows():
        bucket, status, rate = classify_semantic_resolution(
            month_start=row.month_start,
            total_rows=row.total_rows,
            unknown_rows=row.unknown_rows,
            alignment_effective_date=date(2026, 12, 1),
            threshold=0.0,
        )
        assert row.bucket == bucket
        assert row.status == status
        assert row.month_start.isoformat() in out
        assert bucket in out
        assert status in out


def test_script_exit_code_zero_when_clean(
    monkeypatch, captured_collect, script_module
) -> None:
    async def fake_collect(url, effective_date, threshold):
        return [
            SemanticResolutionRow(
                month_start=date(2026, 12, 1),
                total_rows=10,
                unknown_rows=0,
                unknown_rate=0.0,
                bucket="post_alignment",
                status="ok",
            )
        ]

    monkeypatch.setattr(script_module, "_collect", fake_collect)
    exit_code = script_module.main(
        ["--target", "cloud", "--effective-date", "2026-12-01"]
    )
    assert exit_code == 0


# ---------------------------------------------------------------------------
# 4. 脱敏: 打印与存档都绝不含口令
# ---------------------------------------------------------------------------


def test_script_output_never_leaks_credentials(
    captured_collect, script_module, capsys
) -> None:
    script_module.main(["--target", "cloud", "--effective-date", "2026-12-01"])
    out = capsys.readouterr().out
    assert "p%40ss" not in out, "输出里出现了口令"
    assert "u:" not in out, "输出里出现了用户名"
    assert "clouddb" in out, "输出里应当保留库名(便于定位目标)"


def test_script_json_archive_never_leaks_credentials(
    captured_collect, script_module, tmp_path, capsys
) -> None:
    archive = tmp_path / "semantic-unknown.json"
    script_module.main(
        [
            "--target",
            "cloud",
            "--effective-date",
            "2026-12-01",
            "--json",
            str(archive),
        ]
    )
    capsys.readouterr()
    payload = json.loads(archive.read_text(encoding="utf-8"))
    assert "p%40ss" not in json.dumps(payload, ensure_ascii=False)
    assert payload["alignment_effective_date"] == "2026-12-01"
    assert payload["degraded_months"] == ["2026-12-01"]
    assert len(payload["months"]) == 3
