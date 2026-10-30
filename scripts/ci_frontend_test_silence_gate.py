#!/usr/bin/env python3
"""CI gate：禁止「哑测试」（silent tests）。

什么是哑测试
------------
测试文件**因为路径错误直接崩掉**，断言一次都没执行，却伪装成一条普通的测试失败。
这类测试最危险的地方在于：它看起来「在跑」、CI 也是红的，于是**没有人怀疑它的结论**——
实际上它一条契约都没守住。

真实案例（2026-10-30 发现）
---------------------------
``frontend/scripts/`` 内部混用了两套 cwd 约定：13 个按 ``frontend/`` 解析，
4 个按**仓库根**解析。按主流约定（``cd frontend`` 后 ``node --test``）跑时，
那 4 个在 ``readFileSync`` 处 ENOENT 崩溃、断言从未执行，长期伪装成失败。
更糟的是：**CI 里根本没有前端测试步骤**，所以没人发现。

本门禁做两件事
--------------
1. **静态检查**（便宜，先跑）：扫描测试文件里**字面量路径**的
   ``readFileSync`` / ``existsSync`` / 动态 ``import()``，
   按仓库约定（相对 ``frontend/``）逐个验证文件确实存在。
   ⇒ 在跑测试之前就把上一轮那类 bug 抓出来。
2. **运行时检查**：跑一次 ``node --test``，扫描输出里的「根本没跑起来」信号
   （``ENOENT`` / ``ERR_MODULE_NOT_FOUND`` / ``Cannot find module`` …），
   把它们**单独**列出来报警。

**普通断言失败不归本门禁管**（仓库当前有已知失败基线），
门禁只对「哑测试」亮红灯，避免把已知红灯和真问题混在一起。

退出码
------
* ``0`` 通过（可能附带普通断言失败的统计）
* ``1`` 发现哑测试
* ``2`` 门禁自身出错（例如 node 不可用）
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = REPO_ROOT / "frontend"

# 测试文件所在目录（相对仓库根）
TEST_DIRS = ("scripts", "tests")
TEST_GLOBS = ("scripts/**/*.test.mjs", "tests/**/*.test.mjs")

# 「根本没跑起来」的特征串
SILENT_RUNTIME_SIGNALS = (
    "ENOENT",
    "ERR_MODULE_NOT_FOUND",
    "MODULE_NOT_FOUND",
    "Cannot find module",
    "ERR_UNSUPPORTED_DIR_IMPORT",
)

# 测试文件里读取路径的三种写法（只认字面量，动态路径交给运行时检查）
_LITERAL_PATH_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(r"readFileSync\(\s*['\"`]([^'\"`\n]+)['\"`]"),
    re.compile(r"existsSync\(\s*['\"`]([^'\"`\n]+)['\"`]"),
    re.compile(r"readFileSync\(\s*new URL\(\s*['\"`]([^'\"`\n]+)['\"`]"),
    re.compile(r"import\(\s*['\"`]([^'\"`\n]+)['\"`]\s*\)"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fail CI when frontend guard tests are 'silent' (crashed before asserting)"
    )
    parser.add_argument(
        "--static-only",
        action="store_true",
        help="Only run the static literal-path check (no node --test run).",
    )
    parser.add_argument(
        "--skip-runtime",
        action="store_true",
        help="Only run the static literal-path check.",
    )
    parser.add_argument(
        "--log",
        help="Analyze an existing node --test log instead of running the suite.",
    )
    parser.add_argument(
        "--frontend-dir",
        help="Frontend directory to scan (default: <repo>/frontend).",
    )
    parser.add_argument(
        "--max-print",
        type=int,
        default=40,
        help="Max findings printed in the summary (default: 40).",
    )
    return parser.parse_args()


def iter_test_files(frontend_dir: Path) -> List[Path]:
    files: List[Path] = []
    for test_dir in TEST_DIRS:
        base = frontend_dir / test_dir
        if not base.is_dir():
            continue
        files.extend(sorted(base.rglob("*.test.mjs")))
    return files


def _is_ignorable_literal(literal: str) -> bool:
    """字面量路径里明显不是仓库内文件的（URL、绝对路径、模板串）。"""
    text = literal.strip()
    if not text:
        return True
    if text.startswith(("http://", "https://", "data:", "node:")):
        return True
    if text.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:[\\/]", text):
        return True
    if "${" in text or "%s" in text or "{" in text:
        return True
    return False


def check_static_paths(frontend_dir: Path) -> List[str]:
    """静态检查：测试文件引用的字面量路径必须真实存在（相对 frontend/）。"""
    problems: List[str] = []
    for test_file in iter_test_files(frontend_dir):
        try:
            source = test_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            problems.append(f"{test_file}: 读取失败 {exc}")
            continue
        for pattern in _LITERAL_PATH_PATTERNS:
            for match in pattern.finditer(source):
                literal = match.group(1)
                if _is_ignorable_literal(literal):
                    continue
                # 仓库约定：相对 frontend/ 解析
                target = (frontend_dir / literal).resolve()
                if target.exists():
                    continue
                # 有些测试用 new URL(..., import.meta.url) 相对自己所在目录
                alternative = (test_file.parent / literal).resolve()
                if alternative.exists():
                    continue
                line_no = source.count("\n", 0, match.start()) + 1
                problems.append(
                    f"{test_file}:{line_no}: 引用的路径不存在 "
                    f"（相对 frontend/ 解析）：{literal}"
                )
    return problems


def run_frontend_tests(frontend_dir: Path) -> Tuple[int, str]:
    if not (frontend_dir / "package.json").exists():
        return 2, f"{frontend_dir / 'package.json'} 不存在"
    env = dict(os.environ)
    env.pop("NODE_OPTIONS", None)
    try:
        proc = subprocess.run(
            ["node", "--test", *TEST_GLOBS],
            cwd=frontend_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
        )
    except FileNotFoundError as exc:
        return 2, f"node 不可用：{exc}"
    return proc.returncode, proc.stdout.decode("utf-8", errors="replace")


def find_silent_runtime_failures(output: str) -> List[str]:
    """从 node --test 输出里找出「测试根本没跑起来」的失败。"""
    problems: List[str] = []
    lines = output.splitlines()
    for index, line in enumerate(lines):
        if not any(signal in line for signal in SILENT_RUNTIME_SIGNALS):
            continue
        # 向上找最近的文件标识行（node --test 的子测试标题里带文件 URL）
        context = ""
        for back in range(index, max(index - 40, -1), -1):
            candidate = lines[back].strip()
            if ".test.mjs" in candidate:
                context = candidate
                break
        snippet = line.strip()
        if context and context not in snippet:
            snippet = f"{context} :: {snippet}"
        problems.append(snippet)
    # 去重（同一处错误常在 summary 里再出现一次）
    return list(dict.fromkeys(problems))


def summarize_ordinary_failures(output: str) -> Dict[str, int]:
    """统计普通断言失败（只做汇报，不作为门禁依据）。

    node --test 的输出里失败用例有两种写法：
      * TAP 明细：``not ok 1 - 用例名``
      * 汇总行  ：``✖ 用例名 (12ms)``
    两种都算。
    """
    tap_failures = re.findall(
        r"^\s*not ok \d+ - (.+?)(?:\s+\(\d+(?:\.\d+)?ms\))?\s*$",
        output,
        re.M,
    )
    summary_failures = re.findall(
        r"^\s*[\u2716x]\s+(.+?)(?:\s+\(\d+(?:\.\d+)?ms\))?\s*$",
        output,
        re.M,
    )
    names = {
        name.strip()
        for name in [*tap_failures, *summary_failures]
        if name.strip() and not name.strip().endswith(":")
    }
    return {"ordinary_failures": len(names)}


def main() -> int:
    args = parse_args()

    frontend_dir = (
        Path(args.frontend_dir).resolve() if args.frontend_dir else FRONTEND_DIR
    )
    if not frontend_dir.is_dir():
        print(f"[ERROR] frontend 目录不存在：{frontend_dir}")
        return 2

    static_problems = check_static_paths(frontend_dir)
    runtime_problems: List[str] = []
    stats: Dict[str, int] = {}

    if not args.static_only:
        if args.log:
            log_path = Path(args.log)
            if not log_path.exists():
                print(f"[ERROR] 日志不存在：{log_path}")
                return 2
            output = log_path.read_text(encoding="utf-8", errors="replace")
        else:
            print("[INFO] 运行前端测试（node --test）...")
            code, output = run_frontend_tests(frontend_dir)
            if code == 2:
                print(f"[ERROR] {output}")
                return 2
            stats = summarize_ordinary_failures(output)
        runtime_problems = find_silent_runtime_failures(output)

    total = len(static_problems) + len(runtime_problems)

    print("[INFO] 哑测试门禁结果：")
    print(f"  静态路径检查问题数: {len(static_problems)}")
    print(f"  运行时「没跑起来」问题数: {len(runtime_problems)}")
    if stats:
        print(
            f"  普通断言失败数（不作为门禁依据）: {stats.get('ordinary_failures', 0)}"
        )

    if total:
        print("\n[ERROR] 发现哑测试：下列测试在断言执行前就崩掉了，结论不可信：")
        limit = max(args.max_print, 0)
        for item in static_problems[:limit]:
            print(f"  - [静态] {item}")
        for item in runtime_problems[: max(limit - len(static_problems), 0)]:
            print(f"  - [运行时] {item}")
        if total > limit:
            print(f"  ... 还有 {total - limit} 条未打印")
        print(
            "[ERROR] 请修掉这些测试的路径问题（仓库约定：相对 frontend/ 解析路径），"
            "或确认它们确实不再是哑测试。"
        )
        return 1

    print("[OK] 未发现哑测试。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
