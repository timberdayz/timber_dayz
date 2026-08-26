#!/usr/bin/env python3
"""Safely migrate profit-basis and labor allocation records to V2.

The command is deliberately read-only by default. ``--apply`` requires a
complete source-data report and refuses to operate on protected payroll or
settlement records. ``--dry-run`` may query production data but never writes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url


V2_VERSION = "A_PRE_COMMISSION_LABOR_V2"
LABOR_V2_CALCULATION_VERSION = "LABOR_COST_V2"
PROTECTED_PAYROLL_STATUSES = frozenset({"confirmed", "paid", "approved"})
PROTECTED_SETTLEMENT_STATUSES = frozenset(
    {"submitted", "approved", "locked", "completed", "paid"}
)


class MigrationSafetyError(RuntimeError):
    """Raised when the migration cannot be proven safe to apply."""


def compute_batch_fingerprint(payload: Mapping[str, Any]) -> str:
    """Return a deterministic SHA-256 fingerprint for a migration report."""
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _jsonable(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    return value


def _row_dict(row: Any) -> dict[str, Any]:
    return {key: _jsonable(value) for key, value in row._mapping.items()}


def resolve_database_url(explicit_url: str | None = None) -> str:
    """Resolve a database URL without printing credentials."""
    database_url = (explicit_url or os.getenv("CLOUD_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip()
    if not database_url:
        raise MigrationSafetyError("DATABASE_URL or CLOUD_DATABASE_URL is required")
    try:
        parsed = make_url(database_url)
    except Exception as exc:
        raise MigrationSafetyError("invalid database URL") from exc
    if parsed.drivername.split("+")[0] not in {"postgresql", "postgres"}:
        raise MigrationSafetyError("migration requires a PostgreSQL database")
    return database_url


def _protected_statuses(report: Mapping[str, Any]) -> list[str]:
    problems: list[str] = []
    for month in report.get("months", []):
        period = month.get("period_month", "unknown")
        payroll_statuses = {str(status).lower() for status in month.get("payroll_statuses", [])}
        protected_payroll = sorted(payroll_statuses & PROTECTED_PAYROLL_STATUSES)
        if protected_payroll:
            problems.append(f"{period}: payroll status {','.join(protected_payroll)}")
        settlement_status = str(month.get("settlement_status") or "").lower()
        if settlement_status in PROTECTED_SETTLEMENT_STATUSES:
            problems.append(f"{period}: settlement status {settlement_status}")
        if month.get("payroll_locked") and not protected_payroll:
            problems.append(f"{period}: payroll is locked")
    return problems


def validate_apply_report(report: Mapping[str, Any]) -> None:
    """Fail closed unless every month has complete, mutable source data."""
    protected = _protected_statuses(report)
    missing = [
        str(month.get("period_month", "unknown"))
        for month in report.get("months", [])
        if month.get("missing_labor_allocation")
    ]
    locked_basis = [
        str(month.get("period_month", "unknown"))
        for month in report.get("months", [])
        if int(month.get("locked_basis_rows") or 0) > 0
    ]
    if protected:
        raise MigrationSafetyError("protected payroll/settlement data: " + "; ".join(protected))
    if locked_basis:
        raise MigrationSafetyError("locked profit-basis snapshots for: " + ", ".join(locked_basis))
    if missing:
        raise MigrationSafetyError("missing labor allocation for: " + ", ".join(missing))
    if not report.get("months"):
        raise MigrationSafetyError("no migration source rows found")


def _query_month_report(connection: Any) -> dict[str, Any]:
    """Build a month-level report from all migration source tables."""
    rows = connection.execute(
        text(
            """
            WITH months AS (
                SELECT period_month FROM finance.shop_profit_basis
                UNION SELECT year_month FROM a_class.payroll_records
                UNION SELECT period_month FROM finance.employee_labor_cost_allocations
                UNION SELECT period_month FROM finance.monthly_profit_settlements
            ), basis AS (
                SELECT period_month, COUNT(*) AS basis_rows,
                       COUNT(*) FILTER (WHERE basis_version = 'A_ONLY_V1') AS v1_rows,
                       COUNT(*) FILTER (WHERE is_locked) AS locked_basis_rows,
                       COALESCE(SUM(orders_profit_amount), 0) AS orders_profit_amount,
                       COALESCE(SUM(a_class_cost_amount), 0) AS legacy_a_cost_amount,
                       COALESCE(SUM(profit_basis_amount), 0) AS legacy_profit_basis_amount
                FROM finance.shop_profit_basis GROUP BY period_month
            ), payroll AS (
                SELECT year_month AS period_month, COUNT(*) AS payroll_rows,
                       ARRAY_AGG(DISTINCT LOWER(status)) FILTER (WHERE status IS NOT NULL) AS payroll_statuses,
                       BOOL_OR(status IN ('confirmed', 'paid', 'approved')) AS payroll_locked
                FROM a_class.payroll_records GROUP BY year_month
            ), allocations AS (
                SELECT period_month, COUNT(*) AS allocation_rows,
                       COALESCE(SUM(pre_commission_amount), 0) AS pre_commission_amount
                FROM finance.employee_labor_cost_allocations
                WHERE allocation_scope = 'shop' GROUP BY period_month
            ), costs AS (
                SELECT "年月" AS period_month,
                       COALESCE(SUM(COALESCE("成本合计", 0) - COALESCE("人力费用", 0)), 0)
                           AS other_a_class_cost_amount
                FROM a_class.operating_costs
                WHERE "删除时间" IS NULL
                GROUP BY "年月"
            ), settlements AS (
                SELECT period_month, status AS settlement_status
                FROM finance.monthly_profit_settlements
            )
            SELECT months.period_month,
                   COALESCE(basis.basis_rows, 0) AS basis_rows,
                   COALESCE(basis.v1_rows, 0) AS v1_rows,
                   COALESCE(basis.locked_basis_rows, 0) AS locked_basis_rows,
                   COALESCE(basis.orders_profit_amount, 0) AS orders_profit_amount,
                   COALESCE(basis.legacy_a_cost_amount, 0) AS legacy_a_cost_amount,
                   COALESCE(basis.legacy_profit_basis_amount, 0) AS legacy_profit_basis_amount,
                   COALESCE(payroll.payroll_rows, 0) AS payroll_rows,
                   COALESCE(payroll.payroll_statuses, ARRAY[]::text[]) AS payroll_statuses,
                   COALESCE(payroll.payroll_locked, FALSE) AS payroll_locked,
                   COALESCE(allocations.allocation_rows, 0) AS allocation_rows,
                   COALESCE(allocations.pre_commission_amount, 0) AS pre_commission_amount,
                   COALESCE(costs.other_a_class_cost_amount, 0) AS other_a_class_cost_amount,
                   COALESCE(basis.orders_profit_amount, 0)
                     - COALESCE(costs.other_a_class_cost_amount, 0)
                     - COALESCE(allocations.pre_commission_amount, 0)
                     AS projected_v2_profit_basis_amount,
                   COALESCE(basis.orders_profit_amount, 0)
                     - COALESCE(costs.other_a_class_cost_amount, 0)
                     - COALESCE(allocations.pre_commission_amount, 0)
                     - COALESCE(basis.legacy_profit_basis_amount, 0)
                     AS estimated_profit_basis_impact_amount,
                   settlements.settlement_status
            FROM months
            LEFT JOIN basis USING (period_month)
            LEFT JOIN payroll USING (period_month)
            LEFT JOIN allocations USING (period_month)
            LEFT JOIN costs USING (period_month)
            LEFT JOIN settlements USING (period_month)
            ORDER BY months.period_month
            """
        )
    ).fetchall()
    months = []
    for row in rows:
        item = _row_dict(row)
        item["payroll_statuses"] = list(item.get("payroll_statuses") or [])
        item["missing_labor_allocation"] = bool(item["payroll_rows"] and not item["allocation_rows"])
        months.append(item)
    report: dict[str, Any] = {"months": months}
    report["batch_fingerprint"] = compute_batch_fingerprint(report)
    return report


def collect_report(database_url: str) -> dict[str, Any]:
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            return _query_month_report(connection)
    finally:
        engine.dispose()


def _pg_dump_command(database_url: str, output_path: Path) -> tuple[list[str], dict[str, str]]:
    parsed: URL = make_url(database_url)
    if parsed.drivername.split("+")[0] not in {"postgresql", "postgres"}:
        raise MigrationSafetyError("backup requires a PostgreSQL database")
    command = ["pg_dump", "--no-owner", "--no-acl", "--format=custom", "--file", str(output_path)]
    if parsed.host:
        command.extend(["--host", parsed.host])
    if parsed.port:
        command.extend(["--port", str(parsed.port)])
    if parsed.username:
        command.extend(["--username", parsed.username])
    if parsed.database:
        command.extend(["--dbname", parsed.database])
    environment = os.environ.copy()
    if parsed.password:
        environment["PGPASSWORD"] = parsed.password
    return command, environment


def export_backup(database_url: str, backup_dir: Path, fingerprint: str) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = backup_dir / f"profit_basis_v2_{timestamp}_{fingerprint[:12]}.dump"
    command, environment = _pg_dump_command(database_url, output_path)
    try:
        subprocess.run(command, env=environment, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise MigrationSafetyError("pg_dump is required before --apply") from exc
    except subprocess.CalledProcessError as exc:
        raise MigrationSafetyError(f"pg_dump failed: {exc.stderr.strip() or exc.returncode}") from exc
    return output_path


def write_backup_manifest(
    backup_path: Path,
    report: Mapping[str, Any],
) -> Path:
    """Store the immutable dry-run evidence next to the pre-apply dump."""
    dump_hash = hashlib.sha256(backup_path.read_bytes()).hexdigest()
    manifest_path = backup_path.with_suffix(".manifest.json")
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "backup_file": backup_path.name,
        "backup_sha256": dump_hash,
        "batch_fingerprint": report["batch_fingerprint"],
        "report": report,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, default=_jsonable),
        encoding="utf-8",
    )
    return manifest_path


def _apply_sql(connection: Any, report: Mapping[str, Any]) -> int:
    """Convert V1 rows and allocations in one transaction."""
    # A preflight collision check prevents violating the unique V2 key.
    collision = connection.execute(
        text(
            """
            SELECT COUNT(*) FROM finance.shop_profit_basis old
            JOIN finance.shop_profit_basis current
              ON current.period_month = old.period_month
             AND current.platform_code = old.platform_code
             AND current.shop_id = old.shop_id
             AND current.basis_version = :v2
            WHERE old.basis_version = 'A_ONLY_V1'
            """
        ),
        {"v2": V2_VERSION},
    ).scalar_one()
    if int(collision or 0):
        raise MigrationSafetyError(f"{collision} V1 rows already have a V2 key")

    allocation_collision = connection.execute(
        text(
            """
            SELECT COUNT(*)
            FROM finance.employee_labor_cost_allocations old
            JOIN finance.employee_labor_cost_allocations current
              ON current.period_month = old.period_month
             AND current.employee_code = old.employee_code
             AND current.allocation_scope = old.allocation_scope
             AND current.platform_code IS NOT DISTINCT FROM old.platform_code
             AND current.shop_id IS NOT DISTINCT FROM old.shop_id
             AND current.calculation_version = :labor_version
            WHERE old.calculation_version = 'LABOR_COST_V1'
            """
        ),
        {"labor_version": LABOR_V2_CALCULATION_VERSION},
    ).scalar_one()
    if int(allocation_collision or 0):
        raise MigrationSafetyError(
            f"{allocation_collision} V1 labor allocations already have a V2 key"
        )

    connection.execute(
        text(
            """
            UPDATE finance.employee_labor_cost_allocations
               SET calculation_version = :labor_version,
                   updated_at = CURRENT_TIMESTAMP
             WHERE calculation_version = 'LABOR_COST_V1'
            """
        ),
        {"labor_version": LABOR_V2_CALCULATION_VERSION},
    )
    result = connection.execute(
        text(
            """
            UPDATE finance.shop_profit_basis basis
               SET basis_version = :v2,
                   a_class_cost_amount = costs.other_cost + costs.labor_cost,
                   profit_basis_amount = basis.orders_profit_amount - costs.other_cost - costs.labor_cost,
                   updated_at = CURRENT_TIMESTAMP
              FROM (
                    SELECT source.id AS basis_id,
                           COALESCE((SELECT SUM(COALESCE("成本合计", 0) - COALESCE("人力费用", 0))
                                      FROM a_class.operating_costs op
                                     WHERE op."年月" = source.period_month
                                       AND op."店铺ID" = source.shop_id
                                       AND LOWER(COALESCE(op.platform_code, '')) = LOWER(source.platform_code)
                                       AND op."删除时间" IS NULL), 0) AS other_cost,
                           COALESCE((SELECT SUM(pre_commission_amount)
                                      FROM finance.employee_labor_cost_allocations alloc
                                     WHERE alloc.period_month = source.period_month
                                       AND alloc.platform_code = source.platform_code
                                       AND alloc.shop_id = source.shop_id
                                       AND alloc.allocation_scope = 'shop'
                                       AND alloc.calculation_version = :labor_version), 0) AS labor_cost
                      FROM finance.shop_profit_basis source
                     WHERE source.basis_version = 'A_ONLY_V1'
               ) costs
             WHERE basis.id = costs.basis_id
               AND basis.basis_version = 'A_ONLY_V1'
            """
        ),
        {"v2": V2_VERSION, "labor_version": LABOR_V2_CALCULATION_VERSION},
    )
    return int(result.rowcount or 0)


def apply_migration(database_url: str, report: Mapping[str, Any]) -> dict[str, Any]:
    validate_apply_report(report)
    backup_dir = Path(os.getenv("PROFIT_BASIS_BACKUP_DIR", "backups"))
    backup_path = export_backup(database_url, backup_dir, str(report["batch_fingerprint"]))
    manifest_path = write_backup_manifest(backup_path, report)
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            updated_rows = _apply_sql(connection, report)
    finally:
        engine.dispose()
    return {
        "mode": "apply",
        "updated_rows": updated_rows,
        "backup_path": str(backup_path),
        "manifest_path": str(manifest_path),
    }


def run(*, report: Mapping[str, Any], apply: bool, backup_dir: Path | None = None, database_url: str | None = None) -> dict[str, Any]:
    """Run a supplied report; useful for tests and operational wrappers."""
    if not apply:
        return {"mode": "dry-run", "report": report}
    if backup_dir is not None:
        os.environ["PROFIT_BASIS_BACKUP_DIR"] = str(backup_dir)
    resolved_url = resolve_database_url(database_url)
    return apply_migration(resolved_url, report)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Migrate profit basis data to V2 safely")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="read and report only (default)")
    mode.add_argument("--apply", action="store_true", help="backup then apply; protected data aborts")
    parser.add_argument("--database-url", help="PostgreSQL URL; defaults to CLOUD_DATABASE_URL")
    parser.add_argument("--backup-dir", type=Path, default=Path("backups"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    is_apply = bool(args.apply)
    try:
        database_url = resolve_database_url(args.database_url)
        report = collect_report(database_url)
        if is_apply:
            os.environ["PROFIT_BASIS_BACKUP_DIR"] = str(args.backup_dir)
            result = apply_migration(database_url, report)
        else:
            result = {"mode": "dry-run", "report": report}
        print(json.dumps(result, ensure_ascii=False, indent=2, default=_jsonable))
        return 0
    except MigrationSafetyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
