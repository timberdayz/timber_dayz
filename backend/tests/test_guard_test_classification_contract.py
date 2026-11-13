"""契约测试：守护/契约类测试文件的分类审计（批次 F-3）。

背景（2026-11-13 实测）：

仓库里「守护/契约类」测试文件 **258 个**（占全部 838 个测试文件的 30.8%）。
数量本身不是问题，问题是**没人说得清每一个到底会不会跑**：

- 进了 CI 根契约清单的 ⇒ 每次流水线都跑；
- 被别的文件 import 的 ⇒ 别的用例会连带把它跑起来；
- 谁也不引用的 ⇒ 只有「有人恰好改了这个文件」时，CI 的「本次改动到的测试文件」
  机制才会跑它 —— **守着一条规则，但从不被主动执行**。

最后那类就是 2026-11-13 清理脚本事故的同款形状（脚本在仓库里、守护也在，
但没有任何流程调用它 ⇒ 11 天攒了 11 个匿名卷）。

本守护锁住四件事：

1. 审计脚本 ``scripts/audit_guard_tests.py`` **能跑**且产出结构完整的报告；
2. 分类**覆盖每一个**守护文件（不遗漏、不重复计数）—— 否则分类本身不可信；
3. A 类（CI 硬门禁）与 CI 根契约清单**严格一致** —— 两份清单不许各说各话；
4. **合并锁**：批次 F-3 把 11 个同构的 timestamp_defaults 守护合并成 1 个参数化文件，
   旧文件不许复活（复活 = 同一份规则维护两遍），新文件必须覆盖那 11 个迁移。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Set

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
AUDIT_SCRIPT = SCRIPTS_DIR / "audit_guard_tests.py"
CI_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"

GUARD_RELATIVE = "backend/tests/test_guard_test_classification_contract.py"

#: 批次 F-3 合并掉的 11 个旧守护（复活 = 同一份规则维护两遍）。
MERGED_AWAY_GUARDS = (
    "backend/tests/test_a_class_business_tables_timestamp_defaults_migration_contract.py",
    "backend/tests/test_a_class_tail_tables_timestamp_defaults_migration_contract.py",
    "backend/tests/test_c_class_timestamp_defaults_migration_contract.py",
    "backend/tests/test_control_plane_timestamp_defaults_migration_contract.py",
    "backend/tests/test_core_dimensions_timestamp_defaults_migration_contract.py",
    "backend/tests/test_core_metadata_tables_timestamp_defaults_migration_contract.py",
    "backend/tests/test_core_runtime_tables_timestamp_defaults_migration_contract.py",
    "backend/tests/test_dim_shops_timestamp_defaults_migration_contract.py",
    "backend/tests/test_finance_timestamp_defaults_migration_contract.py",
    "backend/tests/test_public_system_tables_timestamp_defaults_migration_contract.py",
    "backend/tests/test_target_breakdown_timestamp_defaults_migration_contract.py",
)

#: 合并后的参数化守护。
MERGED_GUARD = "backend/tests/test_timestamp_defaults_migrations_contract.py"


@pytest.fixture(scope="module")
def report() -> Dict:
    """跑一次审计脚本，返回它的 JSON 报告。"""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    completed = subprocess.run(
        [sys.executable, str(AUDIT_SCRIPT), "--format", "json"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        check=True,
        env=env,
    )
    return json.loads(completed.stdout.decode("utf-8", errors="replace"))


def _ci_listed_test_files() -> Set[str]:
    """独立解析 ci.yml 里列出的测试文件（不复用审计脚本的解析器）。

    ⚠️ 必须**跳过注释行**：ci.yml 在 pytest 命令上方有一段说明性注释，
    里面提到过几个「**不在**清单里」的文件（例如需要真库、由 migration-pg-contract
    job 托管的那几个）。把它们算进来 = 把「注释里提到」误当成「清单里列了」。
    """
    ci_text = CI_WORKFLOW.read_text(encoding="utf-8", errors="replace")
    entries: Set[str] = set()
    for line in ci_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        entries.update(re.findall(r"((?:backend/)?tests/[A-Za-z0-9_/]+\.py)", stripped))
    return entries


def test_audit_script_exists():
    assert AUDIT_SCRIPT.exists(), "守护审计脚本必须存在: {0}".format(
        AUDIT_SCRIPT.relative_to(PROJECT_ROOT)
    )


def test_audit_script_produces_a_complete_report(report: Dict):
    """报告结构必须完整 —— 分类报告缺字段 = 分类不可信。"""
    for key in (
        "total_test_files",
        "guard_files",
        "class_counts",
        "classes",
        "duplicate_clusters",
    ):
        assert key in report, "审计报告缺少字段「{0}」".format(key)
    assert report["total_test_files"] > 0
    assert report["guard_files"] > 0
    assert report["guard_share"] > 0


def test_classification_covers_every_guard_file(report: Dict):
    """A + B + C 必须等于守护文件总数，且三类互不重叠。"""
    counts = report["class_counts"]
    total = counts["A"] + counts["B"] + counts["C"]
    assert (
        total == report["guard_files"]
    ), "分类覆盖不全: A+B+C={0} != 守护文件总数 {1}".format(
        total, report["guard_files"]
    )
    seen: Set[str] = set()
    for members in report["classes"].values():
        for member in members:
            assert member not in seen, "守护文件被重复归类: {0}".format(member)
            seen.add(member)
    assert len(seen) == report["guard_files"]


def test_class_a_matches_ci_root_contract_list(report: Dict):
    """A 类（CI 硬门禁）必须与 CI 根契约清单里的守护文件**严格一致**。

    两份清单各说各话 = 分类报告不可信 —— 所以这一条是分类审计的地基。
    这里用**独立**的正则解析 ci.yml（不复用审计脚本里的解析器），
    否则「脚本自己跟自己比」等于没比。
    """
    listed = _ci_listed_test_files()
    listed_guards = {
        entry
        for entry in listed
        if any(
            marker in Path(entry).name
            for marker in (
                "_contract",
                "_guard",
                "_guardrails",
                "_invariant",
                "_policy",
                "_hygiene",
                "_rule",
                "_ssot",
                "_gate",
            )
        )
    }
    assert (
        set(report["classes"]["A_ci_hard_gate"]) == listed_guards
    ), "A 类与 CI 根契约清单不一致:\n  审计脚本: {0}\n  CI 清单: {1}".format(
        sorted(report["classes"]["A_ci_hard_gate"]), sorted(listed_guards)
    )


def test_merged_away_guards_do_not_come_back():
    """**合并锁**：11 个被合并掉的旧守护不许复活。

    复活 = 同一份规则维护两遍 —— 正是批次 F-3 要消灭的形态。
    """
    alive = [
        relative
        for relative in MERGED_AWAY_GUARDS
        if (PROJECT_ROOT / relative).exists()
    ]
    assert not alive, "这些旧守护已经被合并，不该复活: {0}".format(alive)


def test_merged_guard_exists_and_covers_the_eleven_migrations():
    """合并后的参数化守护必须存在，且仍覆盖那 11 个迁移。"""
    merged_path = PROJECT_ROOT / MERGED_GUARD
    assert merged_path.exists(), "合并后的守护必须存在: {0}".format(MERGED_GUARD)

    sys.path.insert(0, str(merged_path.parent))
    try:
        import test_timestamp_defaults_migrations_contract as merged
    finally:
        if sys.path and sys.path[0] == str(merged_path.parent):
            sys.path.pop(0)

    covered: Set[str] = set()
    for spec in merged.SPECS:
        covered.update(path.name for path in merged.VERSIONS_DIR.glob(spec.glob))
    assert len(covered) == 11, "合并后的守护只覆盖了 {0} 个迁移（应为 11 个）".format(
        len(covered)
    )


def test_guard_itself_is_in_ci_root_contract_list():
    """没人调用的守护不是守护。"""
    ci_text = CI_WORKFLOW.read_text(encoding="utf-8", errors="replace")
    assert (
        GUARD_RELATIVE in ci_text
    ), "{0} 不在 CI 根契约清单里 ⇒ 这份守护在 CI 上不会跑".format(GUARD_RELATIVE)
