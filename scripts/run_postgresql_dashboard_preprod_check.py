#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Run the standard PostgreSQL dashboard pre-production verification sequence.

Example:
    python scripts/run_postgresql_dashboard_preprod_check.py --base-url http://localhost:8000
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from typing import Any


def build_preprod_steps(base_url: str) -> list[dict[str, Any]]:
    python_exe = sys.executable
    return [
        {
            "name": "data_pipeline_tests",
            "command": [
                python_exe,
                "-m",
                "pytest",
                "backend/tests/data_pipeline",
                "-q",
            ],
        },
        {
            "name": "dashboard_smoke",
            "command": [
                python_exe,
                "scripts/smoke_postgresql_dashboard_routes.py",
                "--base-url",
                base_url,
            ],
        },
        {
            "name": "ops_check",
            "command": [
                python_exe,
                "scripts/check_postgresql_dashboard_ops.py",
            ],
        },
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run PostgreSQL dashboard pre-production verification")
    parser.add_argument("--base-url", required=True, help="Base URL, e.g. http://localhost:8000")
    return parser.parse_args()


def main(argv: list[str] | None = None) -> int:
    if argv is not None:
        sys.argv = [sys.argv[0], *argv]

    args = parse_args()
    steps = build_preprod_steps(args.base_url)

    overall_ok = True
    for step in steps:
        print(f"=== {step['name']} ===")
        result = subprocess.run(step["command"], check=False)
        if result.returncode != 0:
            overall_ok = False

    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
