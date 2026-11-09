"""引导清单（bootstrap manifest）的守护用例 —— 「空库从零建库」的唯一真相点。

背景
----
``current_schema_20261116_add_tiktok_export_store_name_aliases`` 是数据修复型迁移,
它要求 6 个 TikTok 出口账号**已经存在**（fail-closed 前置检查）。空库上这些账号不存在
⇒ 整条链在该步中止（实测：报 6 条「账号不存在」）。

⇒ 「空库从零建库」必须走**两段式引导**（先升到 20261116 的前一个节点 → 注入引导账号
→ 再升到 head），清单的真源是 ``scripts/bootstrap_seed_manifest.py``。

本用例钉死三件事:

1. **清单与迁移常量逐字一致** —— 以前门禁清单是独立复制的一份, 靠人肉同步,
   漂移的表现是「门禁突然报『账号不存在』」, 极难定位;
2. **清单与 Python 侧归一化一致** —— ``alias_normalized`` 必须等于
   ``normalize_alias_key(alias_value)``, 否则「认领了却匹配不上」;
3. **清单与引导流程的门禁** —— 运维清单缺字段 / 多账号 / 区域不符都必须在动库前报出来,
   空库误跑迁移必须在写路径上被挡下并给出可执行指引。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.utils.text_normalization import normalize_alias_key  # noqa: E402
from scripts.bootstrap_seed_manifest import (  # noqa: E402
    BOOTSTRAP_TIKTOK_ACCOUNTS,
    PRECHECK_TARGET_REVISION,
    BootstrapManifestError,
    build_gate_rows,
    build_operator_rows,
    required_manifest_template,
)


def _load_module(module_name: str, relative_path: str):
    """按文件路径加载模块(迁移文件名以数字开头, 不能直接 import)。"""
    module_path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _migration_module():
    return _load_module(
        "current_migration_20261116_tiktok_export_aliases",
        "current_migrations/versions/20261116_add_tiktok_export_store_name_aliases.py",
    )


def _operator_manifest(**overrides):
    """一份完整的运维清单；``overrides`` 用来故意破坏某一项。"""
    payload = required_manifest_template()
    payload["main_account"] = {
        "platform": "tiktok",
        "main_account_id": "real_main_account",
        "username": "real_username",
        "password_encrypted": "encrypted-secret",
        "main_account_name": "真实主账号",
    }
    for block in payload["shop_accounts"]:
        block["store_name"] = "真实显示名 {sid}".format(sid=block["shop_account_id"])
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# 1) 清单与迁移常量逐字一致
# ---------------------------------------------------------------------------
def test_manifest_accounts_match_migration_constants():
    """引导清单必须与 20261116 的 _TIKTOK_EXPORT_ALIASES 逐字一致。"""
    migration = _migration_module()

    migration_rows = [
        (item[0], item[1], item[2], item[3])
        for item in migration._TIKTOK_EXPORT_ALIASES
    ]
    manifest_rows = [
        (
            item.alias_value,
            item.alias_normalized,
            item.shop_account_id,
            item.shop_region,
        )
        for item in BOOTSTRAP_TIKTOK_ACCOUNTS
    ]

    assert manifest_rows == migration_rows, (
        "引导清单与 20261116 的 _TIKTOK_EXPORT_ALIASES 不一致 —— "
        "空库引导会失败(报「账号不存在」)"
    )


def test_manifest_accounts_are_unique_and_non_empty():
    account_ids = [item.shop_account_id for item in BOOTSTRAP_TIKTOK_ACCOUNTS]
    assert account_ids, "引导清单不能为空"
    assert len(account_ids) == len(set(account_ids)), "引导账号 id 有重复"
    assert all(sid.strip() for sid in account_ids), "引导账号 id 不能为空"
    assert all(item.shop_region.strip() for item in BOOTSTRAP_TIKTOK_ACCOUNTS)


def test_manifest_alias_normalized_matches_python_normalizer():
    """alias_normalized 必须等于 Python 侧归一化的结果(跨层一致性)。"""
    for item in BOOTSTRAP_TIKTOK_ACCOUNTS:
        assert item.alias_normalized == normalize_alias_key(
            item.alias_value
        ), "alias_normalized 与 normalize_alias_key 不一致: {sid}".format(
            sid=item.shop_account_id
        )


def test_precheck_target_is_the_revision_right_before_the_data_migration():
    """第一段迁移必须正好停在 20261116 的**前一个**节点。

    停早了 ⇒ 账号表还不存在, 注入会失败;
    停晚了 ⇒ 20261116 已经跑过, 注入就失去了意义。
    """
    migration = _migration_module()
    assert PRECHECK_TARGET_REVISION == migration.down_revision


def test_gate_seed_module_delegates_to_the_shared_manifest():
    """门禁种子模块不再自己维护清单, 必须与共享清单一致。"""
    seed = _load_module(
        "migration_gate_seed_data_under_test",
        "scripts/migration_gate_seed_data.py",
    )
    manifest_rows = [
        (item.shop_account_id, item.shop_region) for item in BOOTSTRAP_TIKTOK_ACCOUNTS
    ]
    assert list(seed.GATE_TIKTOK_ACCOUNTS) == manifest_rows


# ---------------------------------------------------------------------------
# 2) 运维清单的校验（必须动库前报清楚）
# ---------------------------------------------------------------------------
def test_operator_manifest_accepts_a_complete_manifest():
    main_row, shop_rows = build_operator_rows(_operator_manifest())
    assert main_row["main_account_id"] == "real_main_account"
    assert len(shop_rows) == len(BOOTSTRAP_TIKTOK_ACCOUNTS)
    assert {row["shop_account_id"] for row in shop_rows} == {
        item.shop_account_id for item in BOOTSTRAP_TIKTOK_ACCOUNTS
    }
    assert all(row["business_role"] == "operating_store" for row in shop_rows)


def test_operator_manifest_requires_every_account():
    payload = _operator_manifest()
    payload["shop_accounts"] = payload["shop_accounts"][:-1]
    with pytest.raises(BootstrapManifestError) as excinfo:
        build_operator_rows(payload)
    assert "tiktok_sg_hx_home_local" in str(excinfo.value)


def test_operator_manifest_rejects_unknown_account():
    payload = _operator_manifest()
    payload["shop_accounts"].append(
        {"shop_account_id": "tiktok_unknown_shop", "store_name": "多出来的店"}
    )
    with pytest.raises(BootstrapManifestError) as excinfo:
        build_operator_rows(payload)
    assert "tiktok_unknown_shop" in str(excinfo.value)


def test_operator_manifest_rejects_region_mismatch():
    payload = _operator_manifest()
    payload["shop_accounts"][0]["shop_region"] = "XX"
    with pytest.raises(BootstrapManifestError) as excinfo:
        build_operator_rows(payload)
    assert "区域不符" in str(excinfo.value)


def test_operator_manifest_rejects_missing_store_name():
    payload = _operator_manifest()
    payload["shop_accounts"][0]["store_name"] = "   "
    with pytest.raises(BootstrapManifestError) as excinfo:
        build_operator_rows(payload)
    assert "store_name" in str(excinfo.value)


def test_operator_manifest_requires_main_account_credentials():
    payload = _operator_manifest()
    payload["main_account"].pop("password_encrypted")
    with pytest.raises(BootstrapManifestError) as excinfo:
        build_operator_rows(payload)
    assert "password_encrypted" in str(excinfo.value)


def test_gate_profile_covers_the_same_accounts_as_the_operator_profile():
    """占位值 profile 与运维 profile 覆盖**同一批**账号 —— 不能各写一份清单。"""
    _main_row, gate_rows = build_gate_rows()
    _main_row, operator_rows = build_operator_rows(_operator_manifest())
    assert {row["shop_account_id"] for row in gate_rows} == {
        row["shop_account_id"] for row in operator_rows
    }


def test_required_manifest_template_lists_every_account():
    template = required_manifest_template()
    assert {block["shop_account_id"] for block in template["shop_accounts"]} == {
        item.shop_account_id for item in BOOTSTRAP_TIKTOK_ACCOUNTS
    }
    # 模板必须是合法 JSON（运维要直接拿去填）
    assert json.loads(json.dumps(template, ensure_ascii=False))


# ---------------------------------------------------------------------------
# 3) 写路径上的空库守卫
# ---------------------------------------------------------------------------
def test_fresh_empty_database_is_refused_on_the_write_path():
    """空库上直接跑 current-schema 链必须被挡下, 并给出可执行指引。"""
    from scripts.run_current_schema_migrations import (
        MigrationSafetyError,
        MigrationState,
        _assert_not_fresh_empty_database,
    )

    empty_state = MigrationState(
        database_empty=True,
        current_revision=None,
        legacy_revision=None,
        schema_fingerprint=None,
    )
    with pytest.raises(MigrationSafetyError) as excinfo:
        _assert_not_fresh_empty_database(empty_state)
    message = str(excinfo.value)
    assert "bootstrap_fresh_environment.py" in message
    assert "20261116" in message
    for item in BOOTSTRAP_TIKTOK_ACCOUNTS:
        assert item.shop_account_id in message


def test_non_empty_database_passes_the_fresh_empty_guard():
    from scripts.run_current_schema_migrations import (
        MigrationState,
        _assert_not_fresh_empty_database,
    )

    state = MigrationState(
        database_empty=False,
        current_revision="current_schema_20261223_collection_source_identifiers",
        legacy_revision=None,
        schema_fingerprint="fingerprint",
    )
    _assert_not_fresh_empty_database(state)


def test_bootstrap_cli_requires_a_manifest_for_real_environments(capsys):
    """真实环境不给清单就拒绝执行 —— 绝不静默伪造业务数据。"""
    from scripts.bootstrap_fresh_environment import main as bootstrap_main

    assert bootstrap_main(["--database-url", "postgresql://x/y"]) == 2
    output = capsys.readouterr().out
    assert "--manifest" in output


def test_bootstrap_cli_prints_a_usable_template(capsys):
    from scripts.bootstrap_fresh_environment import main as bootstrap_main

    assert bootstrap_main(["--print-template"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["shop_accounts"]) == len(BOOTSTRAP_TIKTOK_ACCOUNTS)


def test_two_phase_bootstrap_runs_phase_one_then_seed_then_phase_two():
    """两段式的顺序必须锁住: 第一段迁移 → 注入账号 → 第二段迁移。

    顺序错了, 空库引导要么注入不到账号(表还没建), 要么注入了也没意义(迁移已跑过)。
    """
    script_text = (REPO_ROOT / "scripts" / "bootstrap_fresh_environment.py").read_text(
        encoding="utf-8"
    )
    # 只在实现函数体内定位 —— 文件顶部的 import 行不算步骤。
    body = script_text[script_text.index("def run_two_phase_bootstrap(") :]

    first_run = body.index("PRECHECK_TARGET_REVISION,")
    seed_call = body.index("apply_bootstrap_accounts(")
    second_run = body.index("run_current_schema_migrations.py")

    assert first_run < seed_call < second_run


def test_migration_gate_delegates_to_the_shared_two_phase_bootstrap():
    """门禁必须复用共享实现 —— 不能再各写一份两段式流程。"""
    gate_text = (REPO_ROOT / "scripts" / "validate_migrations_fresh_db.py").read_text(
        encoding="utf-8"
    )
    assert "run_two_phase_bootstrap(" in gate_text
