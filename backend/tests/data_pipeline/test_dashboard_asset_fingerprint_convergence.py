#!/usr/bin/env python3
"""看板资产指纹收敛的契约守护测试（批次 3.6）。

**纯源码**验证，不连数据库。

守护的是「跑一次就一定收敛」这条承诺所依赖的四件事：

1. ``refresh_dashboard_materialization_assets`` 回写的 core 指纹必须是**本次实算**的，
   不能沿用旧 state 里的值（core 定义刚被 ``recreate_views=True`` 真的重建过，
   沿用旧值等于让指纹撒谎）；
2. 指纹口径必须与 ``bootstrap_dashboard_assets`` **完全一致**
   （两边都用 ``_module_core_plan(module_name)``）——否则两条路径写进
   ``ops.dashboard_asset_state`` 的值互相打架，永远不收敛；
3. 指纹回写入口（``_upsert_dashboard_asset_state``）必须有一致性闸门：
   写入的 applied 要等于本次算出的 expected，不等就告警；
4. CLI 的默认路径必须走**顺序链**（核心重建 → 刷新物化 → 回写指纹）。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
BOOTSTRAP_FILE = (
    REPO_ROOT / "backend" / "services" / "data_pipeline" / "dashboard_bootstrap.py"
)
CLI_FILE = REPO_ROOT / "scripts" / "bootstrap_postgresql_dashboard.py"


def _read(path: Path) -> str:
    assert path.is_file(), f"文件缺失: {path}"
    return path.read_text(encoding="utf-8")


def _function_body(source: str, name: str) -> str:
    """取某个函数（同步/异步）的源码段。"""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == name
        ):
            return ast.get_source_segment(source, node) or ""
    raise AssertionError(f"找不到函数 {name}")


@pytest.fixture(scope="module")
def bootstrap_source() -> str:
    return _read(BOOTSTRAP_FILE)


@pytest.fixture(scope="module")
def cli_source() -> str:
    return _read(CLI_FILE)


def test_refresh_writes_recomputed_core_fingerprint(bootstrap_source: str) -> None:
    body = _function_body(bootstrap_source, "refresh_dashboard_materialization_assets")
    assert (
        "asset_fingerprint_expected=state.get(" not in body
    ), "不能沿用旧 state 的 expected —— core 定义刚被真的重建过"
    assert (
        "asset_fingerprint_applied=state.get(" not in body
    ), "不能沿用旧 state 的 applied —— 那会让指纹撒谎"
    assert "asset_fingerprint_expected=core_expected" in body
    assert "asset_fingerprint_applied=core_expected" in body
    assert "core_expected = _compute_targets_fingerprint(" in body


def test_refresh_uses_same_fingerprint_scope_as_bootstrap(
    bootstrap_source: str,
) -> None:
    """两条路径的指纹口径必须一致 —— 否则写进表里的值互相打架。"""
    refresh_body = _function_body(
        bootstrap_source, "refresh_dashboard_materialization_assets"
    )
    bootstrap_body = _function_body(bootstrap_source, "bootstrap_dashboard_assets")
    assert (
        "_compute_targets_fingerprint(_module_core_plan(module_name))" in refresh_body
    )
    assert "_compute_targets_fingerprint(core_targets)" in bootstrap_body
    assert (
        "_module_core_plan(module_name)" in bootstrap_body
    ), "bootstrap 侧的 core 指纹口径应与 refresh 侧一致"


def test_upsert_has_consistency_gate(bootstrap_source: str) -> None:
    body = _function_body(bootstrap_source, "_upsert_dashboard_asset_state")
    assert "asset_fingerprint_applied != asset_fingerprint_expected" in body
    assert "logger.warning" in body


def test_converge_runs_core_then_refresh(bootstrap_source: str) -> None:
    body = _function_body(bootstrap_source, "converge_dashboard_assets")
    assert body.index("bootstrap_dashboard_assets(") < body.index(
        "refresh_dashboard_materialization_assets("
    )
    assert "session.commit()" in body


def test_cli_default_path_uses_converge(cli_source: str) -> None:
    body = _function_body(cli_source, "_async_main")
    assert "converge_dashboard_assets" in body
    converge_at = body.index("converge_dashboard_assets(")
    refresh_only_at = body.index("refresh_dashboard_materialization_assets(")
    assert converge_at > refresh_only_at, "顺序链（默认路径）必须在「只刷新」分支之后"


def test_cli_keeps_refresh_only_flag_with_clear_help(cli_source: str) -> None:
    assert "--refresh-materializations" in cli_source
    assert "does NOT guarantee convergence" in cli_source


def test_cli_no_longer_imports_unused_bootstrap_entrypoint(cli_source: str) -> None:
    """CLI 默认路径不再单独调 bootstrap ⇒ 那个 import 会变成未使用(ruff F401)。"""
    tree = ast.parse(cli_source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module != "__future__":
            for alias in node.names:
                imported.add(alias.asname or alias.name)
    used = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} | {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    for name in imported:
        if name in {"converge_dashboard_assets", "inspect_dashboard_assets"}:
            continue
        assert name in used or name in {
            "DASHBOARD_ASSET_AVAILABLE_STATUSES",
            "DASHBOARD_MODULE_TARGETS",
            "DASHBOARD_REQUIRED_OBJECTS",
            "AsyncSessionLocal",
        }, f"未使用的 import: {name}"
