"""语义别名归一化解析能力 —— 迁移契约测试（2026-11-08）。

对应交付物:
* ``current_migrations/versions/20261130_semantic_alias_normalized_resolution.py``
* ``sql/semantic/semantic_alias_normalize_asset.sql``
* ``scripts/generate_semantic_alias_normalize_asset.py``

为什么这些断言重要
------------------
PG 侧归一化与 Python 侧归一化是**两份独立实现**(迁移必须自包含, 不允许 import
backend)。两份实现一旦漂移, 视图就会"PG 认为相等、Python 认为不相等" ⇒
同一列名在两个系统里被解析成不同的语义字段, 且**没有任何报错**。

所以本文件把 fail-closed 契约固化成**纯 Python 断言**(不依赖数据库):

1. 迁移里硬编码的期望归一结果, 必须与 Python 侧逐条一致
   —— 迁移执行时就是拿这批期望去比对 PG 的返回, 断言它们一致 ⇒
      PG 一旦偏离 Python, 迁移会回滚;
2. SQL 资产必须**自包含**(不 import backend)且与字典**可重生成**;
3. seed 只登 products 域, 绝不落 ``data_domain='*'``(全局桶会跨域污染)。
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
MIGRATION_PATH = (
    ROOT
    / "current_migrations"
    / "versions"
    / "20261130_semantic_alias_normalized_resolution.py"
)
ASSET_PATH = ROOT / "sql" / "semantic" / "semantic_alias_normalize_asset.sql"
GENERATOR_PATH = ROOT / "scripts" / "generate_semantic_alias_normalize_asset.py"


def _load_migration_module():
    """按文件路径加载迁移模块(迁移目录不是包)。"""
    spec = importlib.util.spec_from_file_location(
        "semantic_alias_normalized_resolution_migration", MIGRATION_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def migration_module():
    return _load_migration_module()


@pytest.fixture(scope="module")
def asset_text() -> str:
    return ASSET_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. fail-closed 契约: 迁移里的期望值必须与 Python 侧一致
# ---------------------------------------------------------------------------


def test_migration_expectations_match_python_normalization(migration_module):
    """迁移硬编码的期望归一结果, 必须逐条等于 Python 侧输出。

    迁移执行时拿这批期望去比对 PG 侧返回值; 这里保证期望本身没写错、
    也没跟 Python 侧漂移 —— 漂了就等于 fail-closed 在比一个错的基准。
    """
    from backend.services.semantic_field_registry import normalize_semantic_alias

    cases = migration_module._NORMALIZATION_CASES
    assert len(cases) >= 30, f"归一化自检用例过少: {len(cases)}"

    mismatches = [
        (raw, expected, normalize_semantic_alias(raw))
        for raw, expected in cases
        if normalize_semantic_alias(raw) != expected
    ]
    assert (
        not mismatches
    ), "迁移里的期望归一结果与 Python 侧不一致(迁移会误判 PG 或误放行): " + "; ".join(
        f"{r!r} 期望 {e!r} 实得 {a!r}" for r, e, a in mismatches
    )


def test_migration_self_check_is_fail_closed(migration_module):
    """自检必须"不一致即抛错", 而不是只记日志。"""
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "_assert_normalization_matches" in source
    assert "raise RuntimeError" in source
    # 自检必须真的被 upgrade() 调用
    assert "_assert_normalization_matches(bind)" in source
    assert "_assert_seed_landed(bind)" in source


def test_migration_does_not_import_backend(migration_module):
    """迁移必须自包含 —— 不允许 import backend.*(注释里提到 backend 不算)。"""
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    assert not re.search(r"^\s*(from|import)\s+backend\b", source, flags=re.M)


def test_migration_uses_sql_asset_as_single_source(migration_module):
    """SQL 资产是唯一正本; 迁移不得内联复制 SQL 文本。"""
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "semantic_alias_normalize_asset.sql" in source
    # 迁移里不应出现资产里的函数定义(否则会有两份 SQL 漂移)
    assert "CREATE OR REPLACE FUNCTION semantic.normalize_alias" not in source
    assert "CREATE OR REPLACE FUNCTION semantic.resolve_alias_normalized" not in source


# ---------------------------------------------------------------------------
# 2. SQL 资产: 自包含 + 与字典可重生成
# ---------------------------------------------------------------------------


def test_asset_is_self_contained(asset_text):
    """资产不得 import backend —— 它要能在迁移里独立执行。"""
    assert "import backend" not in asset_text
    assert "from backend" not in asset_text


def test_asset_defines_both_functions(asset_text):
    assert "CREATE OR REPLACE FUNCTION semantic.normalize_alias" in asset_text
    assert "CREATE OR REPLACE FUNCTION semantic.resolve_alias_normalized" in asset_text


def test_asset_seed_only_targets_products_domain(asset_text):
    """全局桶(data_domain='*')会在所有域优先生效 ⇒ 跨域污染 ⇒ 禁止。"""
    seed_rows = re.findall(
        r"\(\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'\s*,",
        asset_text,
    )
    assert seed_rows, "资产里没有找到任何 seed 行"
    domains = {row[0] for row in seed_rows}
    assert domains == {"products"}, f"seed 出现了 products 以外的域: {sorted(domains)}"


def test_asset_seed_rows_are_still_backed_by_dictionary(asset_text):
    """资产里的 seed 行必须**仍然**被当前字典背书。

    归一化资产是**由字典生成**的快照
    (``scripts/generate_semantic_alias_normalize_asset.py``), 而迁移在执行时
    **读的就是仓库里这份资产** ⇒ 资产与字典必须始终一致,
    否则新装环境按资产落库、字典却认这套别名 ⇒ 两边解析结果不一致。

    断言是**不变量**而不是"逐条相等":

    * 资产里的每一条 (标准字段, 别名) 都必须仍能在当前字典里找到
      ⇒ 资产里**没有凭空发明**的别名;
    * 资产里的行必须是当前字典派生结果(products 域)的**子集**
      ⇒ 资产不会跑到字典前面去。
    """
    from scripts.generate_semantic_alias_normalize_asset import (
        _collect_products_aliases,
    )

    expected = _collect_products_aliases()
    expected_keys = {
        (standard_field, raw_alias, normalized)
        for _domain, standard_field, raw_alias, normalized in expected
    }

    seed_rows = re.findall(
        r"\(\s*'products'\s*,\s*'([^']+)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'\s*,",
        asset_text,
    )
    actual = [
        (standard_field, raw_alias, normalized)
        for standard_field, raw_alias, normalized in seed_rows
    ]
    assert actual, "资产里没有 seed 行"

    missing = [item for item in actual if item not in expected_keys]
    assert not missing, "冻结资产里有字典已不再背书的别名(资产与字典漂移): " + repr(
        missing[:5]
    )


def test_asset_rows_are_internally_consistent(asset_text):
    """资产内部的 seed 行必须自洽: raw_alias 的归一形态与登记的 normalized_alias 一致。

    这条不变量与字典演进无关 ⇒ 资产冻结后依然成立 ⇒ 是"冻结资产"能长期
    自证清白的唯一可靠判据。
    """
    from backend.services.semantic_field_registry import normalize_semantic_alias

    seed_rows = re.findall(
        r"\(\s*'products'\s*,\s*'([^']+)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'\s*,",
        asset_text,
    )
    assert seed_rows, "资产里没有 seed 行"
    for standard_field, raw_alias, normalized in seed_rows:
        assert normalize_semantic_alias(raw_alias) == normalized, (
            f"{standard_field} / {raw_alias!r} 的归一形态与登记值不一致: "
            f"{normalize_semantic_alias(raw_alias)!r} != {normalized!r}"
        )


def test_generator_exists_and_is_self_contained():
    source = GENERATOR_PATH.read_text(encoding="utf-8")
    assert "normalize_semantic_alias" in source
    assert "DOMAIN_SEMANTIC_ALIASES" in source


# ---------------------------------------------------------------------------
# 3. 口径与解析语义(资产级)
# ---------------------------------------------------------------------------


def test_asset_normalization_keeps_caliber_suffix(asset_text):
    """归一化**不得**剥口径后缀 —— 已下单/已付款是不同业务事实(实测差 5.15%)。

    判据: 凡是 raw_alias 里带了口径词的别名, 它的 normalized_alias 必须
    **原样保留**该口径词 —— 一旦被剥掉, 两套口径就会塌陷成同一个字段。
    """
    seed_rows = re.findall(
        r"\(\s*'products'\s*,\s*'([^']+)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'\s*,",
        asset_text,
    )
    caliber_words = ("已付款订单", "已下订单", "已确定订单", "已确认订单")
    checked = 0
    for _standard_field, raw_alias, normalized in seed_rows:
        for word in caliber_words:
            if word in raw_alias:
                checked += 1
                assert (
                    word in normalized
                ), f"口径词 {word!r} 在归一化时被剥掉了: {raw_alias!r} -> {normalized!r}"
    assert checked > 0, "seed 里没有任何带口径词的别名, 断言没生效"


def test_asset_resolver_prefers_domain_then_platform_then_confidence(asset_text):
    """解析优先级: 域内优先 > 平台匹配 > 粒度匹配 > 置信度 > 来源 > id。"""
    compact = re.sub(r"\s+", " ", asset_text)
    for fragment in (
        "CASE WHEN alias.data_domain = resolve_alias_normalized.data_domain THEN 0",
        "CASE WHEN alias.platform_code = resolve_alias_normalized.platform_code THEN 0",
        "CASE WHEN alias.granularity = resolve_alias_normalized.granularity THEN 0",
        "alias.confidence DESC",
        "WHEN 'manual' THEN 0",
    ):
        assert fragment in compact, f"资产里缺少解析优先级片段: {fragment!r}"
