#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent

    args = [
        "ruff",
        "check",
        # Only lint runtime-ish code by default.
        "backend",
        "modules",
        "scripts",
        # Keep the lint gate actionable for a legacy codebase:
        # - E9: syntax/indentation errors
        # - F7/F63: common runtime-ish issues (e.g., invalid format, syntax helpers)
        "--select=E9,F7,F63",
    ]
    exit_code = subprocess.call(args, cwd=str(repo_root))

    # 自定义门禁：并发上下文里共享数据库会话（SQLAlchemy Session 非并发安全）
    # 2026-10-26 线上事故：governance/stats 连报 4 次 500，页面概览整片变成 --。
    session_race = subprocess.call(
        [sys.executable, "scripts/check_async_session_concurrency.py"],
        cwd=str(repo_root),
    )

    return exit_code or session_race


if __name__ == "__main__":
    raise SystemExit(main())
