#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Historical only.
This script is not part of the runtime path for PostgreSQL Dashboard.

4c8g 单机后续优化 (optimize-4c8g-single-server-follow-up) 验收自动化脚本

运行自动化测试并输出简要报告，供 7.2 验收参考。
不替代 ACCEPTANCE_CHECKLIST_7.2.md 中的手动项（需在 4c8g 环境执行）。
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def safe_print(text: str) -> None:
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        print(text.encode("utf-8", errors="ignore").decode("utf-8", errors="ignore"), flush=True)


def run_pytest() -> bool:
    """运行 4c8g 验收相关单测与 Metabase 服务单测。"""
    safe_print("\n[1/2] Running pytest: test_4c8g_follow_up_acceptance + test_metabase_question_service ...")
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_4c8g_follow_up_acceptance.py",
            "tests/test_metabase_question_service.py",
            "-v",
            "--tb=short",
            "-q",
        ],
        cwd=ROOT,
        timeout=120,
    )
    return r.returncode == 0


def main() -> None:
    safe_print("4c8g follow-up acceptance (automated part)")
    safe_print("=" * 50)
    ok = run_pytest()
    safe_print("")
    if ok:
        safe_print("[PASS] All automated tests passed.")
        safe_print("Manual steps: see openspec/changes/optimize-4c8g-single-server-follow-up/ACCEPTANCE_CHECKLIST_7.2.md")
    else:
        safe_print("[FAIL] Some tests failed. Fix before marking 7.2 done.")
        sys.exit(1)


if __name__ == "__main__":
    main()
