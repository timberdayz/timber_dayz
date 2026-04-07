#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Single-environment direct PostgreSQL Dashboard cutover helper.

Purpose:
- reinforce the `xihong` admin account
- optionally clean business test data in safe schemas
- print the exact next deployment and verification steps for the single cloud environment scenario
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import text


ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.models.database import AsyncSessionLocal


DEFAULT_CLEANUP_SCHEMAS = ["a_class", "b_class", "c_class"]


def build_cutover_steps(cleanup_enabled: bool) -> list[dict[str, Any]]:
    steps = [
        {"name": "query_admin_users", "command": [sys.executable, "scripts/query_admin_users.py"]},
        {"name": "ensure_all_roles", "command": [sys.executable, "scripts/ensure_all_roles.py"]},
        {"name": "create_admin_user", "command": [sys.executable, "scripts/create_admin_user.py"]},
    ]
    if cleanup_enabled:
        steps.append({"name": "cleanup_business_test_data", "command": ["internal"]})
    return steps


async def discover_cleanup_tables(schemas: list[str]) -> list[str]:
    sql = text(
        """
        SELECT quote_ident(table_schema) || '.' || quote_ident(table_name) AS full_name
        FROM information_schema.tables
        WHERE table_type = 'BASE TABLE'
          AND table_schema = ANY(:schemas)
        ORDER BY table_schema, table_name
        """
    )
    async with AsyncSessionLocal() as session:
        result = await session.execute(sql, {"schemas": schemas})
        return [row[0] for row in result.fetchall()]


async def cleanup_business_test_data(schemas: list[str], execute_cleanup: bool) -> list[str]:
    tables = await discover_cleanup_tables(schemas)
    if not tables:
        return []

    if execute_cleanup:
        truncate_sql = "TRUNCATE TABLE " + ", ".join(tables) + " RESTART IDENTITY CASCADE"
        async with AsyncSessionLocal() as session:
            await session.execute(text(truncate_sql))
            await session.commit()
    return tables


def run_subprocess_step(command: list[str]) -> int:
    result = subprocess.run(command, cwd=ROOT_DIR, check=False)
    return result.returncode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run single-environment PostgreSQL dashboard cutover helper")
    parser.add_argument(
        "--cleanup-schemas",
        default=",".join(DEFAULT_CLEANUP_SCHEMAS),
        help="Comma separated schemas to clean. Default: a_class,b_class,c_class",
    )
    parser.add_argument(
        "--execute-cleanup",
        action="store_true",
        help="Actually truncate discovered business tables. Default is dry-run",
    )
    return parser.parse_args()


async def async_main(args: argparse.Namespace) -> int:
    schemas = [item.strip() for item in args.cleanup_schemas.split(",") if item.strip()]
    steps = build_cutover_steps(cleanup_enabled=True)

    print("=== Single-environment PostgreSQL Dashboard cutover ===")
    print("Target schemas:", ", ".join(schemas))
    print("Cleanup mode:", "EXECUTE" if args.execute_cleanup else "DRY-RUN")
    print()

    for step in steps:
        if step["name"] == "cleanup_business_test_data":
            tables = await cleanup_business_test_data(schemas, execute_cleanup=args.execute_cleanup)
            print(f"=== {step['name']} ===")
            if not tables:
                print("(no business tables found)")
            else:
                for table in tables:
                    print(table)
                if args.execute_cleanup:
                    print("[OK] business test data cleanup executed")
                else:
                    print("[INFO] dry-run only, no table was truncated")
            print()
            continue

        print(f"=== {step['name']} ===")
        code = run_subprocess_step(step["command"])
        if code != 0:
            return code
        print()

    print("=== next steps ===")
    print("1. Set USE_POSTGRESQL_DASHBOARD_ROUTER=true")
    print("2. Set ENABLE_METABASE_PROXY=false")
    print("3. Deploy using the existing tag-driven production path")
    print("4. Run scripts/run_postgresql_dashboard_preprod_check.py --base-url <cloud_base_url>")
    print("5. Run scripts/check_postgresql_dashboard_ops.py")
    print("6. Generate the report with scripts/generate_postgresql_dashboard_preprod_report.py")
    return 0


def main(argv: list[str] | None = None) -> int:
    if argv is not None:
        sys.argv = [sys.argv[0], *argv]
    args = parse_args()
    return asyncio.run(async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
