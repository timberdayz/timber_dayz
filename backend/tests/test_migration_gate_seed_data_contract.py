"""C2 守护用例: 迁移门禁的种子数据必须与迁移常量逐字一致。

背景
----
``scripts/validate_migrations_fresh_db.py`` 是「全新空库跑全量 current-schema
迁移」的门禁。它被 20261116(数据修复型迁移)卡住过: 那个迁移的 fail-closed
前置检查要求 6 个 TikTok 店铺账号已存在, 空库上必然失败。

修法是门禁脚本**分段迁移 + 注入最小前置账号数据**
(见 ``scripts/migration_gate_seed_data.py``)。

⚠ 这个修法有一个**致命耦合点**: 种子清单里的账号 id / 区域必须与迁移里
硬编码的 ``_TIKTOK_EXPORT_ALIASES`` **逐字一致** —— 不一致的话门禁会重新失败,
而且失败信息是「账号不存在」, 极难定位。
⇒ 本用例把这个耦合**钉死**。
"""

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


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


def _seed_module():
    return _load_module(
        "migration_gate_seed_data_under_test",
        "scripts/migration_gate_seed_data.py",
    )


def test_gate_seed_accounts_match_migration_constants():
    """种子账号清单必须与迁移里的硬编码清单逐字一致(id + 区域)。"""
    migration = _migration_module()
    seed = _seed_module()

    migration_rows = [(item[2], item[3]) for item in migration._TIKTOK_EXPORT_ALIASES]
    seed_rows = list(seed.GATE_TIKTOK_ACCOUNTS)

    assert seed_rows == migration_rows, (
        "门禁种子账号清单与 20261116 的 _TIKTOK_EXPORT_ALIASES 不一致 —— "
        "空库门禁会重新失败(报「账号不存在」)"
    )


def test_gate_seed_accounts_are_unique_and_non_empty():
    """账号 id 不能重复, 也不能为空。"""
    seed = _seed_module()

    account_ids = [sid for sid, _ in seed.GATE_TIKTOK_ACCOUNTS]
    assert account_ids, "种子账号清单不能为空"
    assert len(account_ids) == len(set(account_ids)), "种子账号 id 有重复"
    assert all(sid.strip() for sid in account_ids), "种子账号 id 不能为空"
    assert all(region.strip() for _, region in seed.GATE_TIKTOK_ACCOUNTS)


def test_gate_precheck_target_is_the_revision_right_before_the_data_migration():
    """第一段迁移必须正好停在 20261116 的**前一个**节点。

    停早了 ⇒ 种子表还不存在, 注入会失败;
    停晚了 ⇒ 20261116 已经跑过, 注入就失去了意义。
    """
    gate = _load_module(
        "validate_migrations_fresh_db_under_test",
        "scripts/validate_migrations_fresh_db.py",
    )
    migration = _migration_module()

    assert (
        gate.PRECHECK_TARGET_REVISION == migration.down_revision
    ), "门禁的第一段迁移目标必须等于 20261116 的 down_revision"


def test_gate_script_runs_seed_injection_between_the_two_migration_phases():
    """门禁必须**先跑第一段 → 再注入种子 → 再跑第二段**。

    ⚠ 2026-11-10 起, 这段两段式流程被**上提**到共享实现
    ``scripts/bootstrap_fresh_environment.py::run_two_phase_bootstrap``
    （真实新环境入口、临时库门禁、本地重建三处共用同一份实现）。
    ⇒ 顺序的守护点也从门禁脚本迁到共享实现上, 门禁脚本只负责**调用**它 ——
    避免「三处各写一份两段式流程」再次漂移。
    """
    gate_text = (REPO_ROOT / "scripts" / "validate_migrations_fresh_db.py").read_text(
        encoding="utf-8"
    )
    assert (
        "run_two_phase_bootstrap(" in gate_text
    ), "门禁脚本必须调用共享的两段式引导实现, 不能自己再写一份"

    shared_text = (REPO_ROOT / "scripts" / "bootstrap_fresh_environment.py").read_text(
        encoding="utf-8"
    )
    # 只在实现函数体内定位 —— 文件顶部的 import 行不算步骤。
    body = shared_text[shared_text.index("def run_two_phase_bootstrap(") :]

    first_run = body.index("PRECHECK_TARGET_REVISION,")
    seed_call = body.index("apply_bootstrap_accounts(")
    second_run = body.index("run_current_schema_migrations.py")

    assert (
        first_run < seed_call < second_run
    ), "两段式引导的顺序必须是: 第一段迁移 -> 注入种子 -> 第二段迁移"
