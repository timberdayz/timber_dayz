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
from decimal import Decimal
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
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_jsonable,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
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


def validate_apply_report(
    report: Mapping[str, Any],
    *,
    allow_protected: bool = False,
    migration_batch_id: str | None = None,
    actor_user_id: int | None = None,
    reason: str | None = None,
) -> None:
    """Fail closed unless every month has complete, mutable source data."""
    protected = _protected_statuses(report)
    missing = [
        str(month.get("period_month", "unknown"))
        for month in report.get("months", [])
        if month.get("missing_labor_allocation")
    ]
    missing_shops = [
        f"{month.get('period_month', 'unknown')}: {shop_id}"
        for month in report.get("months", [])
        for shop_id in month.get("missing_labor_shop_ids", [])
    ]
    locked_basis = [
        str(month.get("period_month", "unknown"))
        for month in report.get("months", [])
        if int(month.get("locked_basis_rows") or 0) > 0
    ]
    if protected and not allow_protected:
        raise MigrationSafetyError("protected payroll/settlement data: " + "; ".join(protected))
    if allow_protected and protected:
        if not str(migration_batch_id or "").strip():
            raise MigrationSafetyError("migration batch id is required for protected history")
        if actor_user_id is None or int(actor_user_id) <= 0:
            raise MigrationSafetyError("actor user id is required for protected history")
        if not str(reason or "").strip():
            raise MigrationSafetyError("reason is required for protected history")
    if locked_basis:
        raise MigrationSafetyError("locked profit-basis snapshots for: " + ", ".join(locked_basis))
    if missing:
        raise MigrationSafetyError("missing labor allocation for: " + ", ".join(missing))
    if missing_shops:
        raise MigrationSafetyError(
            "missing labor allocation for shops: " + "; ".join(missing_shops)
        )
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
            ), basis_shops AS (
                SELECT period_month, LOWER(platform_code) AS platform_code, shop_id
                FROM finance.shop_profit_basis
                WHERE basis_version = 'A_ONLY_V1'
            ), allocations AS (
                SELECT period_month, COUNT(*) AS allocation_rows,
                       ARRAY_AGG(DISTINCT calculation_version) AS allocation_versions,
                       COALESCE(SUM(pre_commission_amount), 0) AS pre_commission_amount
                FROM finance.employee_labor_cost_allocations
                WHERE allocation_scope = 'shop'
                  AND calculation_version IN ('LABOR_COST_V1', 'LABOR_COST_V2')
                GROUP BY period_month
            ), missing_labor_shops AS (
                SELECT basis_shops.period_month,
                       ARRAY_AGG(basis_shops.platform_code || '|' || basis_shops.shop_id
                                 ORDER BY basis_shops.platform_code, basis_shops.shop_id)
                           AS missing_labor_shop_ids
                FROM basis_shops
                LEFT JOIN finance.employee_labor_cost_allocations allocation
                  ON allocation.period_month = basis_shops.period_month
                 AND LOWER(COALESCE(allocation.platform_code, '')) = basis_shops.platform_code
                 AND allocation.shop_id = basis_shops.shop_id
                 AND allocation.allocation_scope = 'shop'
                 AND allocation.calculation_version IN ('LABOR_COST_V1', 'LABOR_COST_V2')
                WHERE allocation.id IS NULL
                GROUP BY basis_shops.period_month
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
                   COALESCE(allocations.allocation_versions, ARRAY[]::text[]) AS allocation_versions,
                   COALESCE(allocations.pre_commission_amount, 0) AS pre_commission_amount,
                   COALESCE(missing_labor_shops.missing_labor_shop_ids, ARRAY[]::text[])
                       AS missing_labor_shop_ids,
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
            LEFT JOIN missing_labor_shops USING (period_month)
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
        item["allocation_versions"] = list(item.get("allocation_versions") or [])
        item["missing_labor_shop_ids"] = list(item.get("missing_labor_shop_ids") or [])
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
                   other_a_class_cost_amount = costs.other_cost,
                   pre_commission_labor_cost_amount = costs.labor_cost,
                   a_class_cost_amount = costs.other_cost + costs.labor_cost,
                   profit_basis_amount = basis.orders_profit_amount - costs.other_cost - costs.labor_cost,
                   cost_status = 'projected',
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


def _reopen_protected_history(
    connection: Any,
    *,
    migration_batch_id: str,
    actor_user_id: int,
    reason: str,
) -> None:
    """Reopen protected history only inside an explicit, audited migration batch."""
    username = connection.execute(
        text("SELECT username FROM core.dim_users WHERE user_id = :user_id"),
        {"user_id": actor_user_id},
    ).scalar_one_or_none()
    if not username:
        raise MigrationSafetyError("actor user id does not resolve to an active audit identity")

    months = connection.execute(
        text(
            """
            SELECT DISTINCT period_month FROM finance.shop_profit_basis
            UNION SELECT DISTINCT year_month FROM a_class.payroll_records
            UNION SELECT DISTINCT period_month FROM finance.monthly_profit_settlements
            """
        )
    ).scalars().all()
    for period_month in months:
        payroll_before = connection.execute(
            text(
                """
                SELECT COUNT(*) FROM a_class.payroll_records
                WHERE year_month = :period_month AND status IN ('confirmed', 'paid', 'approved')
                """
            ),
            {"period_month": period_month},
        ).scalar_one()
        settlement_before = connection.execute(
            text(
                """
                SELECT COUNT(*) FROM finance.monthly_profit_settlements
                WHERE period_month = :period_month
                  AND status IN ('submitted', 'approved', 'locked', 'completed', 'paid')
                """
            ),
            {"period_month": period_month},
        ).scalar_one()
        if not int(payroll_before or 0) and not int(settlement_before or 0):
            continue

        connection.execute(
            text(
                """
                UPDATE a_class.payroll_records
                   SET status = 'draft', pay_date = NULL, updated_at = CURRENT_TIMESTAMP
                 WHERE year_month = :period_month
                   AND status IN ('confirmed', 'paid', 'approved')
                """
            ),
            {"period_month": period_month},
        )
        settlement_ids = connection.execute(
            text(
                """
                SELECT id FROM finance.monthly_profit_settlements
                WHERE period_month = :period_month
                  AND status IN ('submitted', 'approved', 'locked', 'completed', 'paid')
                """
            ),
            {"period_month": period_month},
        ).scalars().all()
        if settlement_ids:
            for table_name in (
                "monthly_profit_shop_basis_snapshots",
                "monthly_profit_employee_commission_snapshots",
                "monthly_profit_employee_performance_snapshots",
                "monthly_profit_payroll_snapshots",
            ):
                connection.execute(
                    text(
                        f"UPDATE finance.{table_name} SET snapshot_status = 'superseded' "
                        "WHERE settlement_id = ANY(:settlement_ids) AND snapshot_status = 'active'"
                    ),
                    {"settlement_ids": settlement_ids},
                )
            connection.execute(
                text(
                    """
                    UPDATE finance.monthly_profit_settlements
                       SET status = 'draft', locked_at = NULL, approved_by = NULL,
                           approved_at = NULL, updated_at = CURRENT_TIMESTAMP
                     WHERE id = ANY(:settlement_ids)
                    """
                ),
                {"settlement_ids": settlement_ids},
            )
        connection.execute(
            text(
                """
                UPDATE finance.shop_profit_basis
                   SET is_locked = FALSE, updated_at = CURRENT_TIMESTAMP
                 WHERE period_month = :period_month
                """
            ),
            {"period_month": period_month},
        )
        connection.execute(
            text(
                """
                UPDATE finance.employee_labor_cost_allocations
                   SET source_payroll_status = 'draft', calculation_status = 'projected',
                       pre_commission_locked_at = NULL, updated_at = CURRENT_TIMESTAMP
                 WHERE period_month = :period_month
                """
            ),
            {"period_month": period_month},
        )
        connection.execute(
            text(
                """
                INSERT INTO public.fact_audit_logs (
                    user_id, username, action_type, resource_type, resource_id,
                    action_description, changes_json, ip_address, user_agent, is_success
                ) VALUES (
                    :user_id, :username, 'v2_history_reopen', 'profit_basis_migration',
                    :resource_id, :description, :details, 'migration-script', 'migration-script', TRUE
                )
                """
            ),
            {
                "user_id": actor_user_id,
                "username": username,
                "resource_id": str(period_month),
                "description": "reopened protected history for V2 profit-basis migration",
                "details": json.dumps(
                    {
                        "migration_batch_id": migration_batch_id,
                        "reason": reason,
                        "payroll_records_reopened": int(payroll_before or 0),
                        "settlements_reopened": int(settlement_before or 0),
                    },
                    ensure_ascii=False,
                ),
            },
        )


def apply_migration(
    database_url: str,
    report: Mapping[str, Any],
    *,
    allow_protected: bool = False,
    migration_batch_id: str | None = None,
    actor_user_id: int | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    validate_apply_report(
        report,
        allow_protected=allow_protected,
        migration_batch_id=migration_batch_id,
        actor_user_id=actor_user_id,
        reason=reason,
    )
    backup_dir = Path(os.getenv("PROFIT_BASIS_BACKUP_DIR", "backups"))
    backup_path = export_backup(database_url, backup_dir, str(report["batch_fingerprint"]))
    manifest_path = write_backup_manifest(backup_path, report)
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            if allow_protected:
                _reopen_protected_history(
                    connection,
                    migration_batch_id=str(migration_batch_id),
                    actor_user_id=int(actor_user_id),
                    reason=str(reason),
                )
            updated_rows = _apply_sql(connection, report)
    finally:
        engine.dispose()
    return {
        "mode": "apply",
        "updated_rows": updated_rows,
        "backup_path": str(backup_path),
        "manifest_path": str(manifest_path),
    }


def reopen_protected_history(
    database_url: str,
    report: Mapping[str, Any],
    *,
    migration_batch_id: str | None,
    actor_user_id: int | None,
    reason: str | None,
) -> dict[str, Any]:
    """Explicit first stage for histories that must refresh allocations before apply."""
    # The first-stage command is allowed to run before allocations exist, but it
    # still requires the same audited administrator context as --allow-protected.
    if not str(migration_batch_id or "").strip() or actor_user_id is None or not str(reason or "").strip():
        raise MigrationSafetyError("migration batch id, actor user id, and reason are required for protected history")
    backup_dir = Path(os.getenv("PROFIT_BASIS_BACKUP_DIR", "backups"))
    backup_path = export_backup(database_url, backup_dir, str(report["batch_fingerprint"]))
    manifest_path = write_backup_manifest(backup_path, report)
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            _reopen_protected_history(
                connection,
                migration_batch_id=str(migration_batch_id),
                actor_user_id=int(actor_user_id),
                reason=str(reason),
            )
    finally:
        engine.dispose()
    return {
        "mode": "reopen-protected",
        "backup_path": str(backup_path),
        "manifest_path": str(manifest_path),
        "next_step": "run the normal monthly payroll refresh, then rerun --apply",
    }


def run(*, report: Mapping[str, Any], apply: bool, backup_dir: Path | None = None, database_url: str | None = None, allow_protected: bool = False, migration_batch_id: str | None = None, actor_user_id: int | None = None, reason: str | None = None) -> dict[str, Any]:
    """Run a supplied report; useful for tests and operational wrappers."""
    if not apply:
        return {"mode": "dry-run", "report": report}
    if backup_dir is not None:
        os.environ["PROFIT_BASIS_BACKUP_DIR"] = str(backup_dir)
    resolved_url = resolve_database_url(database_url)
    return apply_migration(
        resolved_url,
        report,
        allow_protected=allow_protected,
        migration_batch_id=migration_batch_id,
        actor_user_id=actor_user_id,
        reason=reason,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Migrate profit basis data to V2 safely")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="read and report only (default)")
    mode.add_argument("--apply", action="store_true", help="backup then apply; protected data aborts")
    mode.add_argument("--reopen-protected", action="store_true", help="audited first stage: reopen protected history before payroll allocation refresh")
    parser.add_argument("--database-url", help="PostgreSQL URL; defaults to CLOUD_DATABASE_URL")
    parser.add_argument("--backup-dir", type=Path, default=Path("backups"))
    parser.add_argument("--allow-protected", action="store_true", help="reopen protected history only with the required audited migration context")
    parser.add_argument("--migration-batch-id", help="required with --allow-protected")
    parser.add_argument("--actor-user-id", type=int, help="required with --allow-protected")
    parser.add_argument("--reason", help="required with --allow-protected")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    is_apply = bool(args.apply)
    try:
        database_url = resolve_database_url(args.database_url)
        report = collect_report(database_url)
        if args.reopen_protected:
            os.environ["PROFIT_BASIS_BACKUP_DIR"] = str(args.backup_dir)
            result = reopen_protected_history(
                database_url,
                report,
                migration_batch_id=args.migration_batch_id,
                actor_user_id=args.actor_user_id,
                reason=args.reason,
            )
        elif is_apply:
            os.environ["PROFIT_BASIS_BACKUP_DIR"] = str(args.backup_dir)
            result = apply_migration(
                database_url,
                report,
                allow_protected=bool(args.allow_protected),
                migration_batch_id=args.migration_batch_id,
                actor_user_id=args.actor_user_id,
                reason=args.reason,
            )
        else:
            result = {"mode": "dry-run", "report": report}
        print(json.dumps(result, ensure_ascii=False, indent=2, default=_jsonable))
        return 0
    except MigrationSafetyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
