#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent

    # Keep typecheck actionable:
    # - ensure mypy is installed and configured
    # - run on a small "runtime surface" subset
    targets = [
        "backend/routers/dashboard_api.py",
        "modules/core/db/schema.py",
        "modules/utils/email_otp_service.py",
    ]

    args = [
        sys.executable,
        "-m",
        "mypy",
        "--config-file",
        "pyproject.toml",
        "--explicit-package-bases",
        "--follow-imports=skip",
        *targets,
    ]
    return subprocess.call(args, cwd=str(repo_root))


if __name__ == "__main__":
    raise SystemExit(main())
