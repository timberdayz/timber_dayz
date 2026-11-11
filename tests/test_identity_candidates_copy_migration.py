#!/usr/bin/env python3
"""候选集副本重建迁移 + 守护脚本的契约守护(纯源码, 不连库)。

守护的底线
----------
1. **顺序不能错** —— 依赖副本的对象必须**先让开**, 才能 DROP 副本;
   重建完必须**换回**, 否则原子层视图会指向「已不存在的旧副本」。
2. **DROP 不带 CASCADE** —— CASCADE 会连带删掉下游物化视图与看板视图
   (live 实测: 一次 ``DROP VIEW ... CASCADE`` 能连带删掉 10 个对象)。
3. **重建走资产** —— 副本定义**只有资产文件一处**; 迁移不得自己复写定义。
4. **迁移后必须自检** —— 内容逐行一致 + 定义确实读正本, 否则抛错回滚。
5. **回滚目标是迁移前的形态** —— 内嵌的旧定义**不含**正本后来加的那条口径
   (采集方代号不进候选池); 这条断言锁住「回滚=回到旧行为」, 不是「回滚=重建副本」。
6. **脚本只读 + 口径不分叉** —— 守护脚本必须复用巡检的同一个判定函数。
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = (
    PROJECT_ROOT
    / "current_migrations"
    / "versions"
    / "20261225_rebuild_identity_candidates_copy.py"
)
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "verify_identity_candidates_copy.py"

#: 迁移链上 20261225 之前的最后一个 revision。
EXPECTED_DOWN_REVISION = "current_schema_20261224_shop_identity_conflict_rows"
EXPECTED_REVISION = "current_schema_20261225_rebuild_identity_candidates_copy"

#: 正本后来加、而旧副本**没有**的那条口径。
LATE_SOURCE_RULE = "is_collection_source_identifier"

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
def migration_source() -> str:
    assert MIGRATION_PATH.exists(), "候选集副本重建迁移缺失: %s" % MIGRATION_PATH
    return MIGRATION_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def migration_module():
    spec = importlib.util.spec_from_file_location(
        "migration_rebuild_identity_candidates_copy", MIGRATION_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script_source() -> str:
    assert SCRIPT_PATH.exists(), "候选集副本守护脚本缺失: %s" % SCRIPT_PATH
    return SCRIPT_PATH.read_text(encoding="utf-8")


def _function_body(source: str, name: str) -> str:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(source, node) or ""
    raise AssertionError("找不到函数 %s" % name)


def _function_node(source: str, name: str) -> ast.FunctionDef:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError("找不到函数 %s" % name)


def _string_literals_in_function(source: str, name: str) -> list[str]:
    """函数**体**里的字符串字面量(不含 docstring 与注释)。"""
    node = _function_node(source, name)
    body = node.body
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
    ):
        body = body[1:]  # 去掉 docstring
    return [
        item.value
        for stmt in body
        for item in ast.walk(stmt)
        if isinstance(item, ast.Constant) and isinstance(item.value, str)
    ]


def _upgrade_call_order(source: str) -> list[str]:
    """upgrade() 里关键调用的出现顺序。"""
    body = _function_body(source, "upgrade")
    markers = [
        "_rebuild_resolver_function(to_source_view=True)",
        "_rebuild_source_views(to_source_view=True)",
        "DROP MATERIALIZED VIEW",
        "_execute_asset(CANDIDATES_MV_ASSET)",
        "_rebuild_resolver_function(to_source_view=False)",
        "_rebuild_source_views(to_source_view=False)",
        "_assert_copy_matches_source()",
        "_assert_copy_reads_source()",
    ]
    positions = []
    for marker in markers:
        at = body.find(marker)
        assert at > 0, "upgrade() 里缺少关键步骤: %s" % marker
        positions.append(at)
    assert positions == sorted(positions), "upgrade() 的步骤顺序不对: %s" % positions
    return markers


# ---------------------------------------------------------------------------
# 迁移本体
# ---------------------------------------------------------------------------


def test_revision_chain(migration_module) -> None:
    assert migration_module.revision == EXPECTED_REVISION
    assert migration_module.down_revision == EXPECTED_DOWN_REVISION


def test_upgrade_step_order(migration_source: str) -> None:
    markers = _upgrade_call_order(migration_source)
    assert markers, "upgrade() 必须有明确的关键步骤"


def test_drop_never_uses_cascade(migration_source: str) -> None:
    """CASCADE 会连带删掉下游物化视图与看板视图 ⇒ 一次都不许出现。

    只看**函数体里的字符串字面量**(注释与 docstring 提到 CASCADE 是允许的,
    因为那正是在解释「为什么不用 CASCADE」)。
    """
    literals = _string_literals_in_function(migration_source, "upgrade")
    drop_literals = [
        literal for literal in literals if "DROP MATERIALIZED VIEW" in literal.upper()
    ]
    assert drop_literals, "upgrade() 里必须有 DROP MATERIALIZED VIEW"
    for literal in drop_literals:
        assert "CASCADE" not in literal.upper(), (
            "DROP 副本绝不许带 CASCADE: %r" % literal
        )


def test_copy_is_rebuilt_from_the_asset(migration_source: str) -> None:
    """副本定义**只有资产文件一处**; 迁移不得自己复写定义。"""
    literals = _string_literals_in_function(migration_source, "upgrade")
    assert not [
        literal for literal in literals if "CREATE MATERIALIZED VIEW" in literal.upper()
    ], "upgrade() 不得自己写 CREATE MATERIALIZED VIEW(定义只有资产一处)"
    assert "CANDIDATES_MV_ASSET" in _function_body(migration_source, "upgrade")


def test_downgrade_restores_the_previous_shape(migration_module) -> None:
    """回滚目标是**迁移前**的副本定义 —— 不含正本后来加的那条口径。"""
    body = migration_module._LEGACY_COPY_BODY
    assert LATE_SOURCE_RULE not in body, (
        "回滚用的旧定义里不该含正本后来加的口径(%s)" % LATE_SOURCE_RULE
    )
    assert "core.shop_accounts" in body, "旧定义本就是手抄版(自算)"


def test_downgrade_also_compares_content(migration_source: str) -> None:
    body = _function_body(migration_source, "downgrade")
    assert "_assert_copy_matches_source()" in body, "回滚也必须做内容比对"


def test_definition_guard_detects_legacy_markers(migration_module) -> None:
    """定义守护必须能认出「副本在自算」的痕迹。"""
    markers = migration_module.LEGACY_DEFINITION_MARKERS
    assert "core.shop_accounts" in markers
    assert "regexp_replace" in markers
    assert "active_shop_accounts" in markers


def test_source_views_strip_cascade_drop(migration_source: str) -> None:
    """重建原子层视图时必须剥掉资产里的 ``DROP VIEW ... CASCADE``。"""
    body = _function_body(migration_source, "_rebuild_source_views")
    assert "_strip_cascade_drop" in body
    literals = _string_literals_in_function(migration_source, "_rebuild_source_views")
    assert not [
        literal for literal in literals if "CREATE OR REPLACE VIEW" in literal.upper()
    ], "原子层视图重建必须靠资产文件(里面是 CREATE OR REPLACE VIEW), 不能自己写"


def test_resolver_function_is_rebuilt_both_ways(migration_source: str) -> None:
    body = _function_body(migration_source, "_rebuild_resolver_function")
    assert "if to_source_view:" in body, "解析函数重建必须分「读正本 / 读副本」两态"
    assert "shop_identity_resolver.sql" in migration_source
    # 两个方向都必须真的被调用(upgrade 与 downgrade 各一对)。
    assert (
        migration_source.count("_rebuild_resolver_function(to_source_view=True)") >= 2
    )
    assert (
        migration_source.count("_rebuild_resolver_function(to_source_view=False)") >= 2
    )


# ---------------------------------------------------------------------------
# 守护脚本
# ---------------------------------------------------------------------------


def test_script_reuses_the_service_verdict(script_source: str) -> None:
    """脚本必须复用巡检的判定函数 ⇒ 脚本结论 = 巡检结论。"""
    assert "collect_identity_candidates_copy" in script_source
    assert "classify" not in script_source.replace(
        "collect_identity_candidates_copy", ""
    ), "脚本不许自己另写一份判定逻辑"


def test_script_is_read_only(script_source: str) -> None:
    tree = ast.parse(script_source)
    literals = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    offenders: list[str] = []
    for literal in literals:
        upper = literal.upper()
        for keyword in FORBIDDEN_SQL_KEYWORDS:
            if keyword in upper:
                offenders.append("%s <- %r" % (keyword, literal[:60]))
    assert not offenders, "守护脚本必须只读: %s" % offenders


def test_script_has_no_literal_database_url(script_source: str) -> None:
    assert "postgresql://" not in script_source
    assert "postgres://" not in script_source


def test_script_uses_make_url(script_source: str) -> None:
    assert "make_url" in script_source


def test_script_masks_credentials(script_source: str) -> None:
    assert "_masked_target" in script_source
    assert "password" not in script_source.lower().replace(
        "口令", ""
    ), "脚本里不许出现口令字段"
