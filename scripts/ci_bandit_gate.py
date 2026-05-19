#!/usr/bin/env python3
"""
CI gate for Bandit JSON output.

Why this exists:
- In GitHub Actions, each `run:` step uses `bash -e`, so a plain `bandit` command
  exits non-zero on findings and prevents subsequent commands (including any
  human-friendly output) from running.
- We run Bandit with `--exit-zero` to always produce output, then enforce a
  clear policy here with an explicit summary.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fail CI based on Bandit JSON report")
    parser.add_argument("report", help="Path to bandit-report.json")
    parser.add_argument(
        "--fail-on-severity",
        action="append",
        default=["HIGH"],
        help="Repeatable. Fail when any issue matches one of these severities (default: HIGH).",
    )
    parser.add_argument(
        "--max-print",
        type=int,
        default=30,
        help="Max findings to print in the summary (default: 30).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report_path = Path(args.report)
    if not report_path.exists():
        print(f"[ERROR] Bandit report not found: {report_path}")
        return 2

    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[ERROR] Failed to parse Bandit report JSON: {exc}")
        return 2

    results = payload.get("results") or []
    fail_sev = {s.strip().upper() for s in (args.fail_on_severity or []) if s.strip()}
    matched = [r for r in results if str(r.get("issue_severity", "")).upper() in fail_sev]

    print(f"[INFO] Bandit results: total={len(results)} fail_on={sorted(fail_sev)} matched={len(matched)}")
    if matched:
        print("[INFO] Matched findings (showing up to max-print):")
        for item in matched[: max(args.max_print, 0)]:
            filename = item.get("filename", "<unknown>")
            line = item.get("line_number", "?")
            test_id = item.get("test_id", "<unknown>")
            severity = item.get("issue_severity", "<unknown>")
            confidence = item.get("issue_confidence", "<unknown>")
            text = (item.get("issue_text") or "").strip().replace("\n", " ")
            print(f"- {severity}/{confidence} {test_id} {filename}:{line} {text}")

        print(
            "[ERROR] Bandit gate failed. Fix findings or adjust severity policy in CI if intended."
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

