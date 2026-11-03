#!/usr/bin/env python3
"""对比两次 pytest 的 junitxml **失败集合**（不是计数）。

用法::

    python scripts/diff_pytest_junit.py <before.xml> <after.xml> [前缀过滤, 如 backend]

    # 导出一次运行的失败用例清单，作为可长期引用的基线快照
    python scripts/diff_pytest_junit.py --save-baseline <junit.xml> <out.txt> [前缀过滤]

输出::

    NEW     = 只在 after 里失败的用例（**回归**）
    FIXED   = 只在 before 里失败的用例（被修好）
    COMMON  = 两次都失败的用例（既有失败）
    ADDED   = after 新增的用例（总数变化，不算失败）
    REMOVED = after 消失的用例（总数变化，不算失败）

退出码：存在 NEW 失败时为 1，否则为 0（可直接用于门禁）。

为什么必须比对「集合」而不是「计数」
--------------------------------

仓库既有基线本身就有大量失败（见
``docs/superpowers/plans/2026-11-02-collection-profile-only-architecture.md``
的 Task 10），所以「失败数没变多」这种计数口径会被无关的抖动掩盖。
判定「零新增失败」只能用**失败用例 id 的集合差**。

关于用例 id
----------

pytest 的 junitxml **不写** ``id`` 属性，只有 ``classname`` 和 ``name``。
早期版本误用 ``case.get("id")`` 会把同一类里的所有用例塌缩成同一个键，
导致「新增失败」被漏判。正确键是 ``classname::name``。
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def collect(path: str, prefix: str | None) -> tuple[dict[str, str], set[str]]:
    """返回 (失败用例 id -> 原因, 全部用例 id)。"""
    failures: dict[str, str] = {}
    all_ids: set[str] = set()
    root = ET.parse(path).getroot()
    for case in root.iter("testcase"):
        classname = (case.get("classname") or "").strip()
        name = (case.get("name") or "").strip()
        full = f"{classname}::{name}" if classname else name
        if not full or full == "::":
            # 没有可辨识身份 -> 用序号兜底，保证不与其他用例碰撞
            full = f"__unnamed__{len(all_ids)}"
        if prefix and not full.startswith(prefix):
            continue
        all_ids.add(full)
        for kind in ("failure", "error"):
            node = case.find(kind)
            if node is not None:
                reason = (node.get("message") or node.text or "").strip().splitlines()
                failures[full] = (reason[0] if reason else kind)[:220]
                break
    return failures, all_ids


def save_baseline(junit_path: str, out_path: str, prefix: str | None) -> int:
    """把某次运行的**失败用例 id 清单**导出成基线快照文件。

    用途：仓库自带一批既有失败用例，「零新增失败」这件事要能被复现，
    就必须有一份**可长期引用的基线清单**，而不是每次现跑现比。
    """
    failures, _all_ids = collect(junit_path, prefix)
    lines = sorted(failures)
    # 显式 LF：仓库 .gitattributes 统一行尾，Windows 默认的 CRLF 会被改写
    with Path(out_path).open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")
    print(f"[baseline] {len(lines)} failing cases -> {out_path}")
    return 0


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--save-baseline":
        if len(sys.argv) < 4:
            print(__doc__)
            return 2
        return save_baseline(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)

    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    before_path = sys.argv[1]
    after_path = sys.argv[2]
    prefix = sys.argv[3] if len(sys.argv) > 3 else None

    for candidate in (before_path, after_path):
        if not Path(candidate).exists():
            print(f"[ERROR] junit xml not found: {candidate}", file=sys.stderr)
            return 2

    before_fail, before_all = collect(before_path, prefix)
    after_fail, after_all = collect(after_path, prefix)

    new = sorted(set(after_fail) - set(before_fail))
    fixed = sorted(set(before_fail) - set(after_fail))
    common = sorted(set(before_fail) & set(after_fail))
    added = sorted(after_all - before_all)
    removed = sorted(before_all - after_all)

    scope = f"[{prefix}] " if prefix else ""
    print(f"{scope}before: {len(before_fail)} failed / {len(before_all)} collected")
    print(f"{scope}after : {len(after_fail)} failed / {len(after_all)} collected")
    print(f"{scope}NEW failures    = {len(new)}")
    for item in new:
        print(f"    + {item}  ::  {after_fail[item]}")
    print(f"{scope}FIXED failures  = {len(fixed)}")
    for item in fixed:
        print(f"    - {item}  ::  {before_fail[item]}")
    print(f"{scope}COMMON failures = {len(common)}")
    print(f"{scope}ADDED cases     = {len(added)}")
    for item in added:
        print(f"    + {item}")
    print(f"{scope}REMOVED cases   = {len(removed)}")
    for item in removed:
        print(f"    - {item}")

    return 1 if new else 0


if __name__ == "__main__":
    raise SystemExit(main())
