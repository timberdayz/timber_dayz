"""守护「架构 SSOT 门禁的扫描范围」。

``scripts/verify_architecture_ssot.py`` 是仓库文档里反复要求的手工门禁
（README / openspec/project.md / docs/architecture/FINAL_ARCHITECTURE_STATUS.md
都写着「每次修改后运行，期望 Compliance Rate = 100%」）。

但它的扫描范围历史上**没排除 ``.worktrees/``** —— 那是别的分支的检出目录。
于是同一棵树被扫了两遍：

  * Test 1「Base 定义」把 3 个 worktree 里的 ``modules/core/db/schema.py``
    判成 DUPLICATE；
  * Test 2「重复 ORM 模型」报出 587 条「X AND .worktrees/…」，逐条都是
    当前树自己的模型和自己的副本；
  * Test 4「未归档遗留文件」同理。

⇒ 门禁长期红、红的原因又不是当前代码 ⇒ 门禁变成「狼来了」，真正出事时没人看。

本文件把三件事钉死：

  ① ``.worktrees/`` 必须被排除（别的分支的检出**不是**当前代码）；
  ② 真正的遗留文件**仍然必须被抓到**（不许把门禁改成永远绿）；
  ③ ``scripts/local_migration_backup.py`` 这类**在产**脚本必须被显式豁免，
     且豁免不是白给的 —— 断言它们确实被部署链引用，防止豁免名单腐化。
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

import scripts.verify_architecture_ssot as ssot


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def probe_dir():
    """在仓库内造一个一次性探针目录（扫描范围以仓库根为圆心，必须在仓库内）。"""
    directory = ROOT / "_ssot_probe_tmp"
    directory.mkdir(exist_ok=True)
    try:
        yield directory
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_worktree_checkouts_are_excluded_from_the_scan():
    """别的分支的检出目录不是当前代码，不能进扫描范围。"""
    assert ".worktrees" in ssot.EXCLUDED_DIRS

    assert ssot.is_excluded(
        ROOT / ".worktrees" / "release-v722" / "modules" / "core" / "db" / "schema.py"
    )
    assert ssot.is_excluded(
        ROOT / ".worktrees" / "any-branch" / "scripts" / "legacy_whatever.py"
    )


def test_current_tree_base_definition_is_the_only_one_scanned():
    """排除 worktree 之后，Base 定义只应剩 modules/core/db/schema.py 一处。"""
    found = ssot.find_base_definitions()

    assert found, "当前树必须能找到 declarative_base() 定义"
    locations = {path.relative_to(ROOT).as_posix() for path, _ in found}
    assert locations == {"modules/core/db/schema.py"}


def test_prose_mention_of_declarative_base_is_not_a_definition(probe_dir):
    """文档字符串 / 断言文案里提到 declarative_base() **不算**一个 Base 定义。

    早先的门禁是纯文本扫描，于是任何在散文里提到它的文件都被报成
    「重复的 Base 定义」—— 这个误报在 2026-11-12 就打到过本文件自己头上。
    """
    probe_file = probe_dir / "probe_module.py"
    probe_file.write_text(
        '"""模块说明里提到 declarative_base() 这个名字。"""\n'
        "\n"
        "MESSAGE = '构造 declarative_base() 的说明文字'\n",
        encoding="utf-8",
    )

    found = {path for path, _ in ssot.find_base_definitions()}
    assert probe_file not in found


def test_real_declarative_base_call_is_still_detected(probe_dir):
    """不许把门禁改成永远绿：真的 Base 定义仍然必须被抓出来。"""
    probe_file = probe_dir / "probe_base_module.py"
    probe_file.write_text(
        "from sqlalchemy.orm import declarative_base\n"
        "\n"
        "Base = declarative_base()\n",
        encoding="utf-8",
    )

    found = {path for path, _ in ssot.find_base_definitions()}
    assert probe_file in found


def test_genuine_legacy_file_is_still_detected(probe_dir):
    """不许把门禁改成永远绿：真的遗留文件仍然必须被抓出来。"""
    probe_file = probe_dir / "legacy_probe.py"
    probe_file.write_text(
        "# 故意留下的遗留文件，用于验证门禁仍然有效\n", encoding="utf-8"
    )

    detected = ssot.find_unarchived_legacy_files()
    assert probe_file in detected


def test_live_migration_backup_files_are_explicitly_allowlisted():
    """名字里带 backup 的**在产**脚本必须显式豁免。"""
    for relative in (
        "scripts/local_migration_backup.py",
        "tests/test_local_migration_backup.py",
    ):
        assert (
            ROOT / relative
        ) in ssot.ALLOWED_LEGACY_FILES, f"{relative} 未进豁免名单"


def test_allowlisted_migration_backup_files_are_really_live():
    """豁免名单不许腐化：这些文件必须真的被部署链引用，否则应当被归档。

    ``scripts/local_migration_backup.py`` 的名字里的 ``backup`` 指的是
    「它负责做备份」，**不是**「它是一份遗留的备份副本」——
    它在生产发版链上是 fail-closed 的关键件：备份工具找不到，发版脚本直接
    阻断迁移（deploy_remote_production.sh: "no backup tool means no verified
    backup"）。把它归档 = 把生产迁移变成无备份迁移。
    """
    deploy_script = (ROOT / "scripts" / "deploy_remote_production.sh").read_text(
        encoding="utf-8"
    )
    bundle_script = (ROOT / "scripts" / "build_deploy_bundle.sh").read_text(
        encoding="utf-8"
    )
    dockerfile = (ROOT / "Dockerfile.backend").read_text(encoding="utf-8")
    ci_workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )

    assert "scripts/local_migration_backup.py" in deploy_script
    assert "scripts/local_migration_backup.py" in bundle_script
    assert "COPY scripts/local_migration_backup.py" in dockerfile
    assert "tests/test_local_migration_backup.py" in ci_workflow


def test_gate_reports_full_compliance_on_the_current_tree():
    """端到端：当前树必须 100% 合规（4/4 通过）。"""
    assert ssot.main() == 0
