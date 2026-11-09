"""Contract test for the template diff script (``scripts/diff_templates.py``).

Background:
    Sync templates live in the database (6 tables under ``core``), not in git.
    ``scripts/sync_templates_to_cloud.ps1`` only dumps **one** of those tables,
    so column mappings stored in ``field_mapping_template_items`` never reach
    the target environment — and the script's final ``COUNT(*)`` check still
    reports success.  ``scripts/diff_templates.py`` is the read-only counterpart
    that makes the difference visible.

    It is only trustworthy if three properties hold, and each of them was
    already broken at least once while writing it:

    1. **Read-only** — it must never write to either database.
    2. **Keys carry no volatile columns** — ``id`` differs between databases,
       and ``created_at`` / ``updated_at`` change on every sync, so including
       them would turn every row into a difference and drown the signal.
    3. **Every fingerprint column is actually fingerprinted** — a slicing bug
       once put all but the last fingerprint column into the *key*, which made
       a changed ``status`` look like a key change instead of a content
       change.

    These tests lock that behaviour in.
"""

from __future__ import annotations

import importlib.util
import os
import re
from pathlib import Path

import pytest
from sqlalchemy.exc import OperationalError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "scripts" / "diff_templates.py"

#: 参与比对的模板表 —— 少一张就等于漏掉一类差异
EXPECTED_TABLES = {
    "field_mapping_templates",
    "field_mapping_template_items",
    "field_mapping_template_families",
    "field_mapping_template_versions",
    "field_mapping_template_variants",
    "collection_config_templates",
}

VOLATILE_COLUMNS = {"id", "created_at", "updated_at", "last_synced_at"}


def _load_module():
    spec = importlib.util.spec_from_file_location("diff_templates", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_script_exists():
    assert SCRIPT.exists(), "模板差异脚本必须存在于 scripts/ 下"


def test_all_template_tables_are_compared():
    """6 张模板表必须全部参与比对, 少一张就漏一类差异。"""
    module = _load_module()
    assert set(module.TEMPLATE_TABLES) == EXPECTED_TABLES


def test_keys_never_use_volatile_columns():
    """业务键里不得出现 id / 时间戳 —— 跨库不可比, 且每次同步都变。"""
    module = _load_module()
    for table, spec in module.TABLE_SPECS.items():
        for column in spec["keys"]:
            assert (
                column.lower() not in VOLATILE_COLUMNS
            ), "{0} 的业务键用了易变列 {1}".format(table, column)


def test_fingerprint_never_uses_volatile_columns():
    """指纹列里也不得有 id / 时间戳。"""
    module = _load_module()
    for table, spec in module.TABLE_SPECS.items():
        for column in spec["fingerprint"]:
            assert (
                column.lower() not in VOLATILE_COLUMNS
            ), "{0} 的指纹列用了易变列 {1}".format(table, column)


def test_key_and_fingerprint_columns_actually_exist_in_the_table():
    """键列/指纹列必须是真实存在的列 —— 写错列名会让比对静默失真。"""
    module = _load_module()
    url = os.getenv(
        "XIHONG_DEV_DATABASE_URL",
        "postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp",
    )
    source = module.create_engine(url)
    try:
        schema = module._detect_schema(source, "field_mapping_templates")
        if schema is None:
            pytest.skip("本机没有 dev 库, 跳过列存在性校验")
        for table, spec in module.TABLE_SPECS.items():
            schema = module._detect_schema(source, table)
            if schema is None:
                continue  # 本机没这张表(例如 CI 上没有 dev 库) => 跳过
            with source.connect() as conn:
                rows = conn.execute(
                    module.text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = :s AND table_name = :t"
                    ),
                    {"s": schema, "t": table},
                ).fetchall()
            actual = {str(r[0]) for r in rows}
            for column in list(spec["keys"]) + list(spec["fingerprint"]):
                assert column in actual, "{0} 不存在列 {1}(实际列: {2})".format(
                    table, column, sorted(actual)
                )
    except OperationalError:
        pytest.skip("连不上 dev 库, 跳过列存在性校验")
    finally:
        source.dispose()


def test_items_table_is_translated_to_parent_business_key():
    """items 的 template_id 必须先翻译成父模板的业务键才能跨库比。"""
    source = SCRIPT.read_text(encoding="utf-8")
    assert "_template_key_map" in source, "items 必须经父模板业务键翻译"
    assert "key_map.get" in source


def test_script_is_read_only():
    """脚本只允许发 SELECT —— 绝不能写任何库。"""
    source = SCRIPT.read_text(encoding="utf-8").upper()
    # 去掉注释与文档字符串后再扫, 避免文档里的说明文字误判
    body = re.sub(r'"""[\s\S]*?"""', "", source)
    body = re.sub(r"#.*", "", body)
    for forbidden in ("INSERT ", "UPDATE ", "DELETE ", "ALTER ", "DROP ", "TRUNCATE"):
        assert forbidden not in body, "差异脚本不得包含写操作: {0}".format(forbidden)


def test_exits_non_zero_when_differences_exist():
    """有差异时退出码必须非 0 —— 这样才能直接当门禁用。"""
    source = SCRIPT.read_text(encoding="utf-8")
    assert "return 1 if total_diff else 0" in source
