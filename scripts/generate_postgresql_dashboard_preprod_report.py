#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Generate a PostgreSQL dashboard pre-production markdown report.

This script is intentionally lightweight: it can either consume captured command
output or run simple checks in the future, but its current purpose is to
standardize report generation from already executed verification results.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def parse_smoke_lines(lines: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        data = json.loads(line)
        rows.append(
            {
                "name": str(data.get("name", "")),
                "path": str(data.get("url", "")).replace(str(data.get("url", "")).split("/api/")[0], "")
                if "/api/" in str(data.get("url", ""))
                else str(data.get("url", "")),
                "status": str(data.get("status_code", "")),
                "notes": "ok" if data.get("ok") else "failed",
            }
        )
    return rows


def render_report(
    *,
    environment: str,
    base_url: str,
    branch: str,
    commit: str,
    operator: str,
    router_enabled: bool,
    startup_log_ok: bool,
    test_summary: str,
    smoke_rows: list[dict[str, str]],
    ops_ok: bool,
) -> str:
    date_str = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
    smoke_table = "\n".join(
        f"| `{row['path']}` | {row['status']} | {row['notes']} |" for row in smoke_rows
    )
    if not smoke_table:
        smoke_table = "| (none) |  |  |"

    return f"""# PostgreSQL Dashboard Pre-Prod Check Report

## Environment

- Date: {date_str}
- Environment: {environment}
- Base URL: {base_url}
- Branch: {branch}
- Commit: {commit}
- Operator: {operator}

## Router Switch

- `USE_POSTGRESQL_DASHBOARD_ROUTER=true` applied: {"yes" if router_enabled else "no"}
- Startup log shows `Dashboard router source: PostgreSQL`: {"yes" if startup_log_ok else "no"}

## Automated Verification

- `python -m pytest backend/tests/data_pipeline -q`
- Result: {test_summary}

## HTTP Smoke Verification

| Endpoint | Status | Notes |
|---|---|---|
{smoke_table}

## Ops Observability Check

- `ops.pipeline_run_log` checked: {"yes" if ops_ok else "no"}
- `ops.pipeline_step_log` checked: {"yes" if ops_ok else "no"}
- `ops.data_freshness_log` checked: {"yes" if ops_ok else "no"}
- `ops.data_lineage_registry` checked: {"yes" if ops_ok else "no"}

## Performance / Behavior Notes

- API latency observations:
- Data correctness observations:
- Cache behavior observations:

## Risk Assessment

- Remaining risk 1:
- Remaining risk 2:
- Remaining risk 3:

## Rollback Decision

- Ready to keep PostgreSQL router enabled:
- Rollback required:
- If rollback, reason:
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate PostgreSQL dashboard pre-prod report")
    parser.add_argument("--environment", default="preprod")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--branch", default="")
    parser.add_argument("--commit", default="")
    parser.add_argument("--operator", default="")
    parser.add_argument("--test-summary", default="")
    parser.add_argument("--smoke-file", default="")
    parser.add_argument("--output", required=True)
    parser.add_argument("--router-enabled", action="store_true")
    parser.add_argument("--startup-log-ok", action="store_true")
    parser.add_argument("--ops-ok", action="store_true")
    return parser.parse_args()


def main(argv: list[str] | None = None) -> int:
    import sys

    if argv is not None:
        sys.argv = [sys.argv[0], *argv]

    args = parse_args()
    smoke_rows: list[dict[str, str]] = []
    if args.smoke_file:
        smoke_text = Path(args.smoke_file).read_text(encoding="utf-8", errors="replace")
        smoke_rows = parse_smoke_lines(smoke_text.splitlines())

    report = render_report(
        environment=args.environment,
        base_url=args.base_url,
        branch=args.branch,
        commit=args.commit,
        operator=args.operator,
        router_enabled=args.router_enabled,
        startup_log_ok=args.startup_log_ok,
        test_summary=args.test_summary,
        smoke_rows=smoke_rows,
        ops_ok=args.ops_ok,
    )
    Path(args.output).write_text(report, encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
