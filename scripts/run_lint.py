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
    return subprocess.call(args, cwd=str(repo_root))


if __name__ == "__main__":
    raise SystemExit(main())
