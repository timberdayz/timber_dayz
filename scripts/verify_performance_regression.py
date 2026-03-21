#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.request import urlopen


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT_DIR / "temp" / "outputs"
DEFAULT_BASE_URL = "http://127.0.0.1:8001"


def build_regression_plan(mode: str, backend_reachable: bool) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = [
        {
            "name": "perf-regression-tests",
            "command": [
                sys.executable,
                "-m",
                "pytest",
                "backend/tests/test_auth_token_uniqueness.py",
                "backend/tests/test_business_overview_split_probe.py",
                "backend/tests/test_business_overview_long_run.py",
                "backend/tests/test_system_monitoring.py",
                "backend/tests/test_verify_performance_regression.py",
                "-q",
            ],
        }
    ]

    if mode == "local" and backend_reachable:
        plan.extend(
            [
                {
                    "name": "high-frequency-pages-probe",
                    "command": [
                        sys.executable,
                        "scripts/high_frequency_pages_probe.py",
                        "--rounds",
                        "3",
                    ],
                },
                {
                    "name": "business-overview-split-probe",
                    "command": [
                        sys.executable,
                        "scripts/business_overview_split_probe.py",
                        "--rounds",
                        "10",
                    ],
                },
                {
                    "name": "business-overview-long-run",
                    "command": [
                        sys.executable,
                        "scripts/business_overview_long_run.py",
                        "--duration-seconds",
                        "60",
                        "--interval-seconds",
                        "30",
                    ],
                },
            ]
        )

    return plan


def backend_is_reachable(base_url: str = DEFAULT_BASE_URL, timeout: float = 5.0) -> bool:
    try:
        with urlopen(f"{base_url}/health", timeout=timeout) as response:
            return 200 <= response.status < 500
    except Exception:
        return False


def run_step(step: dict[str, Any]) -> dict[str, Any]:
    started = time.time()
    completed = subprocess.run(
        step["command"],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
    )
    return {
        "name": step["name"],
        "returncode": completed.returncode,
        "duration_seconds": round(time.time() - started, 2),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def write_summary(summary: dict[str, Any]) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / "performance_regression_summary_latest.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Unified performance regression entry")
    parser.add_argument("--mode", choices=["ci", "local"], default="local")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    reachable = backend_is_reachable(args.base_url)
    plan = build_regression_plan(mode=args.mode, backend_reachable=reachable)
    results = [run_step(step) for step in plan]
    summary = {
        "mode": args.mode,
        "backend_reachable": reachable,
        "all_passed": all(item["returncode"] == 0 for item in results),
        "steps": results,
    }
    path = write_summary(summary)
    print(str(path))
    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
