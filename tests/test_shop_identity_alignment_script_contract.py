#!/usr/bin/env python3
"""批次 2 对齐执行器的契约守护测试（纯源码 / 纯函数，不连库）。

守护的底线：

1. **默认 dry-run** —— 不加 ``--apply`` 绝不写库。
2. **先快照后写入** —— 快照路径必须出现在写库调用之前。
3. **默认只对齐 ``platform_shop_id``** —— T1 另外 5 个字段只报告不改。
4. **``updated_by`` 不接受云端取值** —— 它必须由脚本统一写成「人工修复」。
5. **删别名前必做历史行依赖检查** —— 被引用的别名要挡下来。
6. **动态标识符白名单** —— 表名/列名来自 ``information_schema``，不能直接拼进 SQL。
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "apply_shop_identity_alignment.py"


@pytest.fixture(scope="module")
def script_source() -> str:
    assert SCRIPT_PATH.exists(), f"对齐执行器缺失: {SCRIPT_PATH}"
    return SCRIPT_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def script_module():
    spec = importlib.util.spec_from_file_location(
        "shop_identity_alignment_script", SCRIPT_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _main_function_body(source: str) -> str:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            return ast.get_source_segment(source, node) or ""
    raise AssertionError("找不到 main()")


def test_dry_run_is_the_default(script_source: str) -> None:
    assert '"--apply"' in script_source
    body = _main_function_body(script_source)
    dry_run_at = body.find("if not args.apply:")
    assert dry_run_at > 0, "main() 里必须有 --apply 的判断"
    apply_calls = [
        name
        for name in ("apply_account_updates", "delete_aliases")
        if f"{name}(" in body[body.find("if not args.apply:") :]
    ]
    assert apply_calls, "dry-run 分支之后应当出现写库调用（说明流程存在）"
    # 写库调用必须位于 dry-run 的 return 之后
    dry_run_return = body.find("return 0", dry_run_at)
    first_write = min(body.find(name + "(") for name in apply_calls)
    assert first_write > dry_run_return, "写库调用必须排在 dry-run 提前返回之后"


def test_snapshot_precedes_writes(script_source: str) -> None:
    body = _main_function_body(script_source)
    snapshot_at = body.find("take_snapshot(")
    write_at = body.find("apply_account_updates(")
    assert snapshot_at > 0 and write_at > 0
    assert snapshot_at < write_at, "必须先落快照再写库"


def test_default_align_field_is_platform_shop_id_only(script_source: str) -> None:
    assert 'DEFAULT_ALIGN_FIELDS = ("platform_shop_id",)' in script_source


def test_updated_by_is_not_taken_from_cloud(script_source: str) -> None:
    assert "不接受来自云端的对齐值" in script_source
    body = _main_function_body(script_source)
    assert "updated_by" in body


def test_alias_delete_is_guarded_by_identity_source_check(script_source: str) -> None:
    """删除前必做「唯一身份来源」检查。"""
    assert "analyze_alias_usage" in script_source
    body = _main_function_body(script_source)
    assert "blocking_accounts" in body
    assert "fact_references" in body


def test_fact_row_references_do_not_block_deletion(script_source: str) -> None:
    """事实行里出现同值**不能**阻断删除。

    背景：早期版本把「事实行的 shop_id == 别名值」当作阻断条件，实测某自别名
    被 4000+ 行历史引用挡住 —— 而按「历史不修」的边界，那些行的归属早已固化、
    不再查别名表，语义层别名路也不认领平台编号，删别名并不改变它们的解析结果。
    那种判定会让该清的别名被历史值永久挡死。
    """
    body = _main_function_body(script_source)
    assert "if blocking_accounts:" in body
    assert "elif fact_refs:" in body
    blocked_at = body.find("if blocking_accounts:")
    elif_at = body.find("elif fact_refs:")
    assert blocked_at < elif_at, "事实行引用只能降级为提示，不能升级为阻断"


def test_dynamic_identifiers_are_whitelisted(script_source: str) -> None:
    assert "SAFE_IDENTIFIER" in script_source
    assert "_safe_identifier" in script_source
    module = ast.parse(script_source)
    for node in ast.walk(module):
        if isinstance(node, ast.FunctionDef) and node.name == "_safe_identifier":
            body = ast.get_source_segment(script_source, node) or ""
            assert "ValueError" in body


def _t1_row(**overrides: Any) -> dict[str, Any]:
    base = {
        "shop_account_id": "SA-1",
        "platform": "shopee",
        "status": "inconsistent",
        "diff_columns": ["platform_shop_id", "updated_by"],
        "local": {"platform_shop_id": "111", "updated_by": "system"},
        "cloud": {"platform_shop_id": "222", "updated_by": "manual"},
    }
    base.update(overrides)
    return base


def test_account_plan_only_touches_requested_fields(script_module) -> None:
    plan = {"T1": {"rows": [_t1_row()]}}
    updates = script_module.build_account_plan(plan, ("platform_shop_id",))
    assert len(updates) == 1
    assert updates[0]["changed_fields"] == ["platform_shop_id"]
    assert updates[0]["after"]["platform_shop_id"] == "222"
    assert updates[0]["reported_only_fields"] == ["updated_by"]


def test_account_plan_skips_consistent_rows(script_module) -> None:
    plan = {"T1": {"rows": [_t1_row(status="consistent")]}}
    assert script_module.build_account_plan(plan, ("platform_shop_id",)) == []


def test_alias_plan_filters_by_kind(script_module) -> None:
    plan = {
        "T2": {
            "local": {
                "delete_candidates": [
                    {
                        "alias_id": 1,
                        "alias_kind": "self_alias",
                        "alias_normalized": "111",
                    },
                    {
                        "alias_id": 2,
                        "alias_kind": "cross_account_claim",
                        "alias_normalized": "222",
                    },
                    {
                        "alias_id": 3,
                        "alias_kind": "unclaimed",
                        "alias_normalized": "333",
                    },
                ]
            }
        }
    }
    items = script_module.build_alias_plan(plan)
    assert [item["alias_id"] for item in items] == [1, 2]


def test_safe_identifier_rejects_injection(script_module) -> None:
    assert script_module._safe_identifier("fact_shopee_products_daily") == (
        "fact_shopee_products_daily"
    )
    with pytest.raises(ValueError):
        script_module._safe_identifier('fact_x"; DROP TABLE core.shop_accounts; --')
    with pytest.raises(ValueError):
        script_module._safe_identifier("")


# --------------------------------------------------------------------------- #
# 候选池刷新脚本（批次 2 步骤 2.4）
# --------------------------------------------------------------------------- #
REFRESH_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "refresh_shop_identity_candidates.py"


@pytest.fixture(scope="module")
def refresh_source() -> str:
    assert REFRESH_SCRIPT_PATH.exists(), f"候选池刷新脚本缺失: {REFRESH_SCRIPT_PATH}"
    return REFRESH_SCRIPT_PATH.read_text(encoding="utf-8")


def _code_strings(source: str) -> list[str]:
    """源码里**真正会执行的**字符串字面量（排除各类 docstring）。

    注释里解释「为什么不做 DROP CASCADE」是安全的，不能因此判红；
    但代码里真的写了 DROP 就是问题。
    """
    tree = ast.parse(source)
    docstrings: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                docstrings.add(doc)
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value not in docstrings
    ]


def test_refresh_script_never_drops_cascade(refresh_source: str) -> None:
    """批次 2 只改**数据** ⇒ 只 REFRESH，绝不 DROP ... CASCADE。

    副本资产自己的注释（`sql/semantic/shop_identity_resolution_candidates_v2_mv.sql:69-73`）
    与守护测试
    `backend/tests/data_pipeline/test_identity_candidates_materialization.py::test_materialized_view_asset_never_drops_cascade`
    都在守这条：DROP + CASCADE 会连带删掉下游对象。
    """
    for literal in _code_strings(refresh_source):
        upper = literal.upper()
        assert "DROP MATERIALIZED VIEW" not in upper
        assert "CASCADE" not in upper


def test_refresh_script_uses_migration_fingerprint_semantics(
    refresh_source: str,
) -> None:
    """指纹口径必须与迁移 ``20261105_create_identity_candidates_mv.py`` 一致。"""
    assert "md5(" in refresh_source
    assert "string_agg" in refresh_source
    assert "row_to_json" in refresh_source
    assert "ORDER BY row_json" in refresh_source


def test_refresh_script_can_check_without_refreshing(refresh_source: str) -> None:
    assert '"--check-only"' in refresh_source
    body = _main_function_body(refresh_source)
    assert "if not args.check_only:" in body


def test_refresh_script_fails_on_fingerprint_mismatch(refresh_source: str) -> None:
    body = _main_function_body(refresh_source)
    assert "return 1" in body
    assert "return 2" in body
