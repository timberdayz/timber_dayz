#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent

    args = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-m",
        "requires_browser",
        "tests/e2e",
    ]

    return subprocess.call(args, cwd=str(repo_root))


if __name__ == "__main__":
    raise SystemExit(main())

