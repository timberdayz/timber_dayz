#!/usr/bin/env python3
"""守护/契约类测试文件的分类与重复簇聚类（批次 F-3）。

为什么需要这个脚本（2026-11-13）：

仓库里的「守护/契约类」测试文件有 **258 个**（占全部测试文件 30.8%）。
数量本身不是问题，问题是**没人说得清每一个到底会不会跑**：

- 有的进了 CI 根契约清单 ⇒ 每次流水线都跑；
- 有的被别的测试 import ⇒ 别的用例会连带把它跑起来；
- 有的谁也不引用 ⇒ 只有「有人恰好改了这个文件」时，CI 的
  「本次改动到的测试文件」机制才会跑它 —— **守着一条规则，但从不被主动执行**。

第三类就是 2026-11-13 清理脚本事故的同款形状（脚本在仓库里，守护也在，
但没有任何流程调用它 ⇒ 11 天攒了 11 个匿名卷）。

本脚本给出**可复跑**的分类与重复簇清单，让「哪些守护没人跑」「哪些守护是同一份」
变成纸面上的事实，而不是印象。

用法::

    python scripts/audit_guard_tests.py                # 文本报告
    python scripts/audit_guard_tests.py --format json  # 机器可读
    python scripts/audit_guard_tests.py --min-cluster 3

判定口径（真源在本文件里，不靠记忆）：

- **守护/契约类文件**：文件名包含下列任一标记
  ``_contract`` / ``_guard`` / ``_guardrails`` / ``_invariant`` / ``_policy`` /
  ``_hygiene`` / ``_rule`` / ``_ssot`` / ``_gate``；
- **A 类（CI 硬门禁）**：路径出现在 ``.github/workflows/ci.yml`` 的根契约清单里
  ⇒ 每次 CI 都跑；
- **B 类（被引用）**：不在 A 类，但被仓库里**其它**文件按模块名引用
  ⇒ 别的用例会连带把它跑起来；
- **C 类（只在被改动时跑）**：不在 A 类，且没有任何仓库文件引用它
  ⇒ 守着一条规则，但只有「有人恰好改了这个文件」时才会跑。

重复簇：把每个文件的 AST 形状（函数角色 + 断言/glob/read 的存在性）算成签名，
签名相同的文件即为一簇 —— 同一簇里的文件是**同一份规则的多次复制**。
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
TEST_ROOTS = (PROJECT_ROOT / "backend" / "tests", PROJECT_ROOT / "tests")

#: 判定「守护/契约类测试文件」的文件名标记（真源）。
GUARD_NAME_MARKERS: Tuple[str, ...] = (
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

#: CI 根契约清单所在步骤的标题。
CI_ROOT_CONTRACT_STEP = "Run root contract tests (no DB)"


def _rel(path: Path) -> str:
    return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def is_guard_file(path: Path) -> bool:
    """该文件是不是「守护/契约类」测试文件。"""
    return any(marker in path.name for marker in GUARD_NAME_MARKERS)


def list_test_files() -> List[Path]:
    """全部 ``test_*.py``（含 data_pipeline / archive 等子目录）。"""
    files: List[Path] = []
    for root in TEST_ROOTS:
        if not root.exists():
            continue
        files.extend(sorted(root.rglob("test_*.py")))
    return files


def list_guard_files() -> List[Path]:
    return [path for path in list_test_files() if is_guard_file(path)]


def parse_ci_root_contract_list() -> Set[str]:
    """从 ci.yml 的根契约清单步骤里取出全部测试文件路径。"""
    if not CI_WORKFLOW.exists():
        return set()
    lines = _read(CI_WORKFLOW).splitlines()
    start = None
    for index, line in enumerate(lines):
        if CI_ROOT_CONTRACT_STEP in line and line.lstrip().startswith("- name:"):
            start = index
            break
    if start is None:
        return set()
    entries: Set[str] = set()
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if stripped.startswith("- name:") or stripped.startswith("- uses:"):
            break
        match = re.match(r"^((?:backend/)?tests/[^\s\\]+\.py)\s*\\?$", stripped)
        if match:
            entries.add(match.group(1))
    return entries


def parse_ci_listed_test_files() -> Set[str]:
    """ci.yml 里**所有**被显式列出的测试文件（任意 job / 任意清单）。

    ⚠️ 必须**跳过注释行**：ci.yml 在 pytest 命令上方有一段说明性注释，
    里面提到过几个「**不在**清单里」的文件 —— 把注释当成清单会把口径搞错。
    """
    if not CI_WORKFLOW.exists():
        return set()
    entries: Set[str] = set()
    for line in _read(CI_WORKFLOW).splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        entries.update(re.findall(r"((?:backend/)?tests/[A-Za-z0-9_/]+\.py)", stripped))
    return entries


def tracked_python_files() -> List[Path]:
    """git 跟踪的 Python 文件（排除本脚本自身）。"""
    try:
        output = subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), "ls-files", "*.py"],
            capture_output=True,
            check=True,
        ).stdout.decode("utf-8", errors="replace")
    except (OSError, subprocess.CalledProcessError):  # pragma: no cover - 兜底
        return []
    files = []
    for line in output.splitlines():
        line = line.strip()
        if line:
            files.append(PROJECT_ROOT / line)
    return files


def build_reference_map() -> Dict[str, Set[str]]:
    """模块名 → 引用它的文件集合（按模块名整词匹配）。

    实现要点：**单遍词法扫描**。先把 258 个守护的模块名做成集合，
    再对每个被跟踪的 Python 文件扫一遍标识符，取交集 ——
    否则就是「258 × 全仓」次全文正则，分钟级。
    """
    guards = list_guard_files()
    stem_to_rel = {_rel(guard): guard.stem for guard in guards}
    stem_set = set(stem_to_rel.values())
    references: Dict[str, Set[str]] = defaultdict(set)
    identifier_pattern = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
    for path in tracked_python_files():
        relative = _rel(path)
        try:
            text = _read(path)
        except OSError:  # pragma: no cover - 兜底
            continue
        identifiers = set(identifier_pattern.findall(text))
        hits = identifiers & stem_set
        for stem in hits:
            for guard_rel, guard_stem in stem_to_rel.items():
                if guard_stem == stem and guard_rel != relative:
                    references[guard_rel].add(relative)
    return references


def classify() -> Dict[str, List[str]]:
    """把守护文件分三类。

    A 类 = 「CI 会主动跑」：文件路径出现在 ci.yml 的**任一**测试清单里
    （根契约清单，或 migration-pg-contract 这类带服务容器的 job）。
    """
    ci_listed = parse_ci_listed_test_files()
    references = build_reference_map()
    buckets: Dict[str, List[str]] = {"A": [], "B": [], "C": []}
    for guard in list_guard_files():
        relative = _rel(guard)
        if relative in ci_listed:
            buckets["A"].append(relative)
        elif references.get(relative):
            buckets["B"].append(relative)
        else:
            buckets["C"].append(relative)
    return {key: sorted(value) for key, value in buckets.items()}


def _shape_signature(path: Path) -> Tuple[Tuple[str, Tuple[str, ...]], ...]:
    """AST 形状签名：函数角色 + 该函数里出现的关键节点类型。

    刻意**不看**标识符与字面量 —— 这样「同一份规则的不同复制」会落到同一签名。
    """
    try:
        tree = ast.parse(_read(path))
    except SyntaxError:  # pragma: no cover - 兜底
        return ()
    functions: List[Tuple[str, Tuple[str, ...]]] = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        kinds: Set[str] = set()
        for sub in ast.walk(node):
            if isinstance(sub, ast.Assert):
                kinds.add("assert")
            elif isinstance(sub, ast.Call):
                attr = getattr(sub.func, "attr", "")
                if attr == "glob":
                    kinds.add("glob")
                elif attr == "read_text":
                    kinds.add("read")
                elif attr in {"run", "check_output", "Popen"}:
                    kinds.add("exec")
            elif isinstance(sub, ast.ImportFrom) or isinstance(sub, ast.Import):
                kinds.add("import")
        role = "test" if node.name.startswith("test_") else "helper"
        functions.append((role, tuple(sorted(kinds))))
    return tuple(functions)


def cluster_by_shape(files: Iterable[str]) -> List[List[str]]:
    """按 AST 形状签名聚类，返回「成员数 ≥2」的簇。"""
    groups: Dict[Tuple[Tuple[str, Tuple[str, ...]], ...], List[str]] = defaultdict(list)
    for relative in files:
        groups[_shape_signature(PROJECT_ROOT / relative)].append(relative)
    clusters = [sorted(members) for members in groups.values() if len(members) >= 2]
    clusters.sort(key=lambda members: (-len(members), members[0]))
    return clusters


def build_report(min_cluster: int = 2) -> dict:
    test_files = list_test_files()
    guard_files = list_guard_files()
    buckets = classify()
    clusters = [
        c
        for c in cluster_by_shape(_rel(f) for f in guard_files)
        if len(c) >= min_cluster
    ]
    return {
        "total_test_files": len(test_files),
        "guard_files": len(guard_files),
        "guard_share": (
            round(len(guard_files) / len(test_files), 4) if test_files else 0.0
        ),
        "ci_root_contract_entries": len(parse_ci_root_contract_list()),
        "ci_listed_test_files": len(parse_ci_listed_test_files()),
        "classes": {
            "A_ci_hard_gate": buckets["A"],
            "B_referenced": buckets["B"],
            "C_only_on_change": buckets["C"],
        },
        "class_counts": {key: len(value) for key, value in buckets.items()},
        "duplicate_clusters": clusters,
        "cluster_count": len(clusters),
    }


def render_text(report: dict) -> str:
    lines: List[str] = []
    lines.append("=== 守护/契约类测试文件分类 ===")
    lines.append(
        "全部测试文件: {0}    守护/契约类: {1}（占 {2:.1%}）".format(
            report["total_test_files"],
            report["guard_files"],
            report["guard_share"],
        )
    )
    lines.append(
        "CI 根契约清单条目: {0}（ci.yml 全部清单 {1}）".format(
            report["ci_root_contract_entries"], report["ci_listed_test_files"]
        )
    )
    lines.append("")
    lines.append(
        "A 类（CI 硬门禁，每次都跑）      : {0}".format(report["class_counts"]["A"])
    )
    lines.append(
        "B 类（被其它文件引用，会连带跑）  : {0}".format(report["class_counts"]["B"])
    )
    lines.append(
        "C 类（无引用，只在被改动时跑）    : {0}".format(report["class_counts"]["C"])
    )
    lines.append("")
    lines.append("=== 重复簇（AST 形状相同 = 同一份规则的多次复制）===")
    lines.append("簇数: {0}".format(report["cluster_count"]))
    for index, members in enumerate(report["duplicate_clusters"], start=1):
        lines.append("")
        lines.append("[{0}] {1} 个文件".format(index, len(members)))
        for member in members:
            lines.append("    - {0}".format(member))
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="守护/契约类测试文件的分类与重复簇聚类"
    )
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--min-cluster", type=int, default=2)
    args = parser.parse_args(argv)

    report = build_report(args.min_cluster)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
