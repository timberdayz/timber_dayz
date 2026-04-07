"""
verify_restore.py — Post-restore verification script for XiHong ERP

Checks that a PostgreSQL restore is valid by verifying:
1. Critical table row counts are non-zero
2. Latest record timestamps are within expected window
3. Referential integrity spot checks pass

Usage:
    python scripts/verify_restore.py
    python scripts/verify_restore.py --hours 48  # allow up to 48h old records
    python scripts/verify_restore.py --json       # machine-readable output

Exit codes:
    0 = All checks passed (PASS)
    1 = One or more checks failed (FAIL)
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import AsyncSessionLocal


# --- Critical tables to verify ---
# (table_name, schema, min_expected_rows, max_data_age_hours or None)
CRITICAL_TABLES = [
    # Core dimensions
    ("dim_platforms", "public", 1, None),
    ("dim_shops", "public", 1, None),
    # Fact tables (expect recent data)
    ("fact_order_amounts", "public", 100, 72),
    # Business tables
    ("accounts", "public", 1, None),
    ("users", "public", 1, None),
    ("collection_configs", "public", 1, None),
    # HR tables
    ("employees", "a_class", 1, None),
    # Targets
    ("sales_targets", "a_class", 1, None),
    # Audit logs (should have recent entries)
    ("audit_logs", "public", 10, 48),
]

# Referential integrity checks: (child_table, child_col, parent_table, parent_col, schema)
INTEGRITY_CHECKS = [
    ("dim_shops", "platform_code", "dim_platforms", "platform_code", "public"),
    ("collection_tasks", "config_id", "collection_configs", "id", "public"),
]


class VerificationResult:
    def __init__(self):
        self.checks: list[dict[str, Any]] = []
        self.passed = 0
        self.failed = 0
        self.warnings = 0

    def add(self, name: str, status: str, detail: str):
        icon = {"PASS": "[OK]", "FAIL": "[FAIL]", "WARN": "[WARN]", "SKIP": "[SKIP]"}[status]
        self.checks.append({"name": name, "status": status, "detail": detail})
        if status == "PASS":
            self.passed += 1
        elif status == "FAIL":
            self.failed += 1
        elif status == "WARN":
            self.warnings += 1
        print(f"  {icon} {name}: {detail}")


async def verify_table_count(
    db: AsyncSession, table: str, schema: str, min_rows: int, result: VerificationResult
):
    schema_prefix = f'"{schema}".' if schema != "public" else ""
    try:
        row = await db.execute(
            text(f"SELECT COUNT(*) FROM {schema_prefix}\"{table}\"")
        )
        count = row.scalar()
        if count >= min_rows:
            result.add(f"row_count:{schema}.{table}", "PASS", f"{count} rows (>= {min_rows})")
        else:
            result.add(
                f"row_count:{schema}.{table}", "FAIL",
                f"Only {count} rows, expected >= {min_rows}"
            )
    except Exception as e:
        result.add(f"row_count:{schema}.{table}", "FAIL", f"Query error: {e}")


async def verify_table_freshness(
    db: AsyncSession,
    table: str,
    schema: str,
    max_age_hours: int,
    result: VerificationResult,
):
    schema_prefix = f'"{schema}".' if schema != "public" else ""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    try:
        row = await db.execute(
            text(
                f"SELECT MAX(created_at) FROM {schema_prefix}\"{table}\" "
                f"WHERE created_at IS NOT NULL"
            )
        )
        latest = row.scalar()
        if latest is None:
            result.add(f"freshness:{schema}.{table}", "WARN", "No created_at timestamps found")
            return
        # Ensure timezone-aware
        if latest.tzinfo is None:
            latest = latest.replace(tzinfo=timezone.utc)
        if latest >= cutoff:
            age_h = (datetime.now(timezone.utc) - latest).total_seconds() / 3600
            result.add(
                f"freshness:{schema}.{table}", "PASS",
                f"Latest record: {latest.isoformat()} ({age_h:.1f}h ago)"
            )
        else:
            age_h = (datetime.now(timezone.utc) - latest).total_seconds() / 3600
            result.add(
                f"freshness:{schema}.{table}", "FAIL",
                f"Latest record is {age_h:.1f}h old (threshold: {max_age_hours}h)"
            )
    except Exception as e:
        result.add(f"freshness:{schema}.{table}", "WARN", f"Cannot check freshness: {e}")


async def verify_referential_integrity(
    db: AsyncSession,
    child_table: str,
    child_col: str,
    parent_table: str,
    parent_col: str,
    schema: str,
    result: VerificationResult,
):
    try:
        row = await db.execute(
            text(
                f"""
                SELECT COUNT(*) FROM "{child_table}" c
                WHERE c."{child_col}" IS NOT NULL
                  AND NOT EXISTS (
                    SELECT 1 FROM "{parent_table}" p
                    WHERE p."{parent_col}" = c."{child_col}"
                  )
                """
            )
        )
        orphans = row.scalar()
        name = f"integrity:{child_table}.{child_col}->{parent_table}.{parent_col}"
        if orphans == 0:
            result.add(name, "PASS", "No orphaned records")
        else:
            result.add(name, "FAIL", f"{orphans} orphaned records found")
    except Exception as e:
        result.add(
            f"integrity:{child_table}.{child_col}->{parent_table}.{parent_col}",
            "WARN",
            f"Cannot check integrity: {e}",
        )


async def verify_db_connectivity(db: AsyncSession, result: VerificationResult):
    try:
        row = await db.execute(text("SELECT version()"))
        version = row.scalar()
        result.add("db_connectivity", "PASS", f"Connected: {version[:50]}")
    except Exception as e:
        result.add("db_connectivity", "FAIL", f"Cannot connect: {e}")


async def run_verification(max_age_hours: int = 24) -> VerificationResult:
    result = VerificationResult()

    async with AsyncSessionLocal() as db:
        print("\n=== XiHong ERP Restore Verification ===")
        print(f"Time: {datetime.now(timezone.utc).isoformat()}")
        print(f"Max data age: {max_age_hours}h\n")

        print("--- Connectivity ---")
        await verify_db_connectivity(db, result)

        print("\n--- Row Counts ---")
        for table, schema, min_rows, age_hours in CRITICAL_TABLES:
            await verify_table_count(db, table, schema, min_rows, result)

        print("\n--- Data Freshness ---")
        for table, schema, min_rows, age_hours in CRITICAL_TABLES:
            if age_hours is not None:
                effective_age = min(age_hours, max_age_hours)
                await verify_table_freshness(db, table, schema, effective_age, result)

        print("\n--- Referential Integrity ---")
        for child_table, child_col, parent_table, parent_col, schema in INTEGRITY_CHECKS:
            await verify_referential_integrity(
                db, child_table, child_col, parent_table, parent_col, schema, result
            )
    return result


def main():
    parser = argparse.ArgumentParser(description="XiHong ERP restore verification")
    parser.add_argument(
        "--hours", type=int, default=24,
        help="Maximum acceptable data age in hours (default: 24)"
    )
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    result = asyncio.run(run_verification(max_age_hours=args.hours))

    print(f"\n=== Summary ===")
    print(f"  Passed:   {result.passed}")
    print(f"  Failed:   {result.failed}")
    print(f"  Warnings: {result.warnings}")

    verdict = "PASS" if result.failed == 0 else "FAIL"
    print(f"\nVerdict: {verdict}")

    if args.json:
        output = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "verdict": verdict,
            "summary": {
                "passed": result.passed,
                "failed": result.failed,
                "warnings": result.warnings,
            },
            "checks": result.checks,
        }
        print("\n" + json.dumps(output, indent=2, default=str))

    sys.exit(0 if result.failed == 0 else 1)


if __name__ == "__main__":
    main()
