#!/usr/bin/env python3
"""店铺身份对账脚本的契约守护测试。

**纯源码 / 纯函数**验证，不连任何数据库 —— 采集机上没有库时也能跑。
守护的是「这个脚本以后不被改坏」的几条底线：

1. 只执行只读 SQL（不允许任何写库语句混进来）。
2. 不硬编码连接串，连接串只从环境变量读。
3. ``.env`` 加载**不覆盖**已存在的环境变量（``.env.local`` 里
   ``CLOUD_DATABASE_URL=`` 是空值，覆盖会把云端连接串清空）。
4. 输出里的连接串摘要**不含**用户名与口令。
5. T2 的「谁认领了这个别名值」判定与官方候选池口径一致
   （``sql/semantic/shop_identity_resolution_candidates_v2_mv.sql``）。
6. 别名 JOIN 走**整数外键**（``shop_account_aliases.shop_account_id`` 是 int，
   与 ``shop_accounts.shop_account_id``（varchar）同名异义）。
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "verify_shop_identity_reconciliation.py"

#: 允许出现在 text(...) 里的 SQL 首词（只读）
READ_ONLY_SQL_HEADS = {"SELECT", "WITH"}

#: 一旦出现即视为「写了库」的 SQL 首词
WRITE_SQL_HEADS = {
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "CREATE",
    "TRUNCATE",
    "GRANT",
    "REVOKE",
    "MERGE",
    "COPY",
    "REFRESH",
    "VACUUM",
    "CALL",
    "DO",
}


@pytest.fixture(scope="module")
def script_source() -> str:
    assert SCRIPT_PATH.exists(), f"对账脚本缺失: {SCRIPT_PATH}"
    return SCRIPT_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def script_module():
    spec = importlib.util.spec_from_file_location(
        "shop_identity_reconciliation_script", SCRIPT_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sql_literals(source: str) -> list[str]:
    """抽出所有作为 ``_fetch_all(...)`` 第一个 SQL 参数传入的字符串字面量。"""
    tree = ast.parse(source)
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = getattr(func, "id", None) or getattr(func, "attr", None)
        if name != "_fetch_all":
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                found.append(arg.value)
                break
    return found


def test_script_exists(script_source: str) -> None:
    assert script_source.strip()


def test_script_only_executes_readonly_sql(script_source: str) -> None:
    statements = _sql_literals(script_source)
    assert statements, "没找到任何 text(...) SQL，脚本结构可能变了"
    for sql in statements:
        head = sql.strip().split(None, 1)[0].upper() if sql.strip() else ""
        assert (
            head in READ_ONLY_SQL_HEADS
        ), f"发现非只读 SQL（首词 {head}）: {sql[:120]}"


def test_no_write_sql_verb_in_script(script_source: str) -> None:
    """兜底：源码里不应出现任何写库动词（防止绕过 text() 的写法）。"""
    for sql in _sql_literals(script_source):
        for verb in WRITE_SQL_HEADS:
            assert (
                f"{verb} " not in sql.upper()
            ), f"SQL 里出现写操作 {verb}: {sql[:120]}"


def test_no_hardcoded_connection_string(script_source: str) -> None:
    tree = ast.parse(script_source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            lowered = node.value.lower()
            assert "postgresql://" not in lowered
            assert "postgres://" not in lowered


def test_env_loading_never_overrides(script_source: str) -> None:
    """``.env`` 加载必须「先到先得」——不能覆盖进程里已有的值。

    背景：本机 ``.env.local`` 的 ``CLOUD_DATABASE_URL=`` 是**空值**，任何
    「后加载覆盖先加载」的 loader 都会把云端连接串清空。
    """
    assert "os.environ.setdefault" in script_source
    tree = ast.parse(script_source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            if name == "load_dotenv":
                for keyword in node.keywords:
                    assert not (
                        keyword.arg == "override"
                        and isinstance(keyword.value, ast.Constant)
                        and keyword.value.value is True
                    ), "load_dotenv(override=True) 会覆盖已有环境变量"
        if isinstance(node, ast.Assign):
            for target in node.targets:
                assert not (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.value, ast.Attribute)
                    and target.value.attr == "environ"
                ), "不要直接给 os.environ[...] 赋值（会覆盖已有值）"


def test_connection_summary_hides_credentials(script_module) -> None:
    # 口令里的 '@' 必须百分号编码（与仓库 .env 里的实际写法一致）
    secret = "p%40ss"
    url = f"postgresql://erp_user:{secret}@127.0.0.1:15433/xihong_erp"
    summary = script_module.describe_connection(url)
    assert summary["host"] == "127.0.0.1"
    assert summary["port"] == 15433
    assert summary["database"] == "xihong_erp"
    rendered = repr(summary)
    assert "p@ss" not in rendered
    assert "erp_user" not in rendered
    assert "password" not in summary


def test_t2_claim_criteria_matches_official_pool(script_source: str) -> None:
    assert "business_role = 'operating_store'" in script_source
    assert "enabled IS TRUE" in script_source
    assert "LOWER(NULLIF(TRIM(" in script_source


def test_alias_join_uses_integer_foreign_key(script_source: str) -> None:
    """``shop_account_aliases.shop_account_id`` 是 int（指向 ``shop_accounts.id``）。"""
    assert "s.id = saa.shop_account_id" in script_source
    assert "s.shop_account_id = saa.shop_account_id" not in script_source


def test_t3_counts_alias_source_too(script_source: str) -> None:
    assert "'alias'::varchar AS source" in script_source
    assert "HAVING COUNT(DISTINCT shop_account_id) > 1" in script_source


def _account(**overrides: Any) -> dict[str, Any]:
    base = {
        "shop_account_id": "SA-1",
        "platform": "shopee",
        "platform_shop_id": "1001",
        "platform_shop_id_status": "confirmed",
        "store_name": "店铺一",
        "enabled": True,
        "business_role": "operating_store",
        "updated_by": "manual",
    }
    base.update(overrides)
    return base


def test_compare_t1_marks_identical_rows_consistent(script_module) -> None:
    rows = [_account(), _account(shop_account_id="SA-2", platform_shop_id="1002")]
    result = script_module.compare_t1(rows, [dict(r) for r in rows])
    assert result["consistent"] == 2
    assert result["inconsistent"] == 0
    assert result["compared"] == 2


def test_compare_t1_reports_differing_columns(script_module) -> None:
    local = [_account(platform_shop_id="1001", updated_by="manual")]
    cloud = [_account(platform_shop_id="9999", updated_by="auto_bound")]
    result = script_module.compare_t1(local, cloud)
    assert result["inconsistent"] == 1
    row = result["rows"][0]
    assert row["status"] == "inconsistent"
    assert set(row["diff_columns"]) == {"platform_shop_id", "updated_by"}


def test_compare_t1_reports_missing_side(script_module) -> None:
    local = [_account()]
    cloud = [_account(shop_account_id="SA-2")]
    result = script_module.compare_t1(local, cloud)
    statuses = {row["shop_account_id"]: row["status"] for row in result["rows"]}
    assert statuses == {"SA-1": "missing_cloud", "SA-2": "missing_local"}


def test_classify_aliases_separates_self_and_cross(script_module) -> None:
    rows = [
        {
            "alias_id": 1,
            "owner_shop_account_id": "SA-1",
            "alias_value": "1001",
            "alias_normalized": "1001",
            "claimed_by_accounts": "SA-1",
            "is_active": True,
        },
        {
            "alias_id": 2,
            "owner_shop_account_id": "SA-2",
            "alias_value": "1001",
            "alias_normalized": "1001",
            "claimed_by_accounts": "SA-1",
            "is_active": True,
        },
        {
            "alias_id": 3,
            "owner_shop_account_id": "SA-3",
            "alias_value": "8888",
            "alias_normalized": "8888",
            "claimed_by_accounts": None,
            "is_active": True,
        },
    ]
    result = script_module.classify_aliases(rows)
    kinds = {row["alias_id"]: row["alias_kind"] for row in result["rows"]}
    assert kinds[1] == "self_alias"
    assert kinds[2] == "cross_account_claim"
    assert kinds[3] == "unclaimed"
    assert result["kind_counts"]["self_alias"] == 1
    assert [item["alias_id"] for item in result["delete_candidates"]] == [1, 2]
