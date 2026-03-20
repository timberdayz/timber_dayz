#!/usr/bin/env python3
"""
Emit changed Python files for CI checks.

Output modes:
- default: newline-separated file list
- --shell: space-separated, shell-quoted file list
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess  # nosec B404 - controlled local git invocations for CI diff detection
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALLOWED_PREFIXES = ("backend/", "modules/", "tests/", "scripts/")


def run_git(*args: str) -> str:
    result = subprocess.run(  # nosec - fixed git invocation on repository-local paths
        ["git", *args],
        cwd=PROJECT_ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def detect_range() -> str:
    event_name = os.getenv("GITHUB_EVENT_NAME", "").strip()
    github_sha = os.getenv("GITHUB_SHA", "").strip()
    github_base_ref = os.getenv("GITHUB_BASE_REF", "").strip()
    github_event_before = os.getenv("GITHUB_EVENT_BEFORE", "").strip()

    if event_name == "pull_request" and github_base_ref:
        run_git("fetch", "origin", github_base_ref, "--depth=1")
        base_sha = run_git("merge-base", "HEAD", f"origin/{github_base_ref}")
        return f"{base_sha}..HEAD"

    if (
        github_event_before
        and github_sha
        and github_event_before != "0000000000000000000000000000000000000000"
    ):
        return f"{github_event_before}..{github_sha}"

    try:
        previous = run_git("rev-parse", "HEAD~1")
        return f"{previous}..HEAD"
    except subprocess.CalledProcessError:
        return "HEAD"


def changed_python_files(diff_range: str) -> list[str]:
    if diff_range == "HEAD":
        raw = run_git("ls-files")
    else:
        raw = run_git("diff", "--name-only", "--diff-filter=ACMR", diff_range)

    files: list[str] = []
    for line in raw.splitlines():
        path = line.strip().replace("\\", "/")
        if not path.endswith(".py"):
            continue
        if not path.startswith(ALLOWED_PREFIXES):
            continue
        if Path(PROJECT_ROOT / path).exists():
            files.append(path)
    return sorted(dict.fromkeys(files))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--shell", action="store_true", help="Emit a shell-quoted single-line list"
    )
    parser.add_argument(
        "--exclude-tests",
        action="store_true",
        help="Exclude test files from the emitted list",
    )
    args = parser.parse_args()

    diff_range = detect_range()
    files = changed_python_files(diff_range)
    if args.exclude_tests:
        files = [
            path
            for path in files
            if not path.startswith("tests/") and not path.startswith("backend/tests/")
        ]

    if args.shell:
        print(" ".join(shlex.quote(path) for path in files))
    else:
        for path in files:
            print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
