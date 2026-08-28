"""One-time, audited reset of August 2026 derived results for the V2 rollout."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.models.database import AsyncSessionLocal
from backend.services.v2_monthly_refresh_service import V2MonthlyRefreshService

try:
    from scripts.migrate_profit_basis_to_v2 import (
        compute_batch_fingerprint,
        export_backup,
        resolve_database_url,
        write_backup_manifest,
    )
except ModuleNotFoundError:  # Direct execution from the scripts directory.
    from migrate_profit_basis_to_v2 import (  # type: ignore[no-redef]
        compute_batch_fingerprint,
        export_backup,
        resolve_database_url,
        write_backup_manifest,
    )


PERIOD_MONTH = "2026-08"
CONFIRMATION = "RESET_2026_08_TO_V2"


class AugustV2ResetSafetyError(RuntimeError):
    """Raised when the one-time reset cannot prove that it is safe."""


def _as_dict(row: Any) -> dict[str, Any]:
    return dict(row._mapping) if hasattr(row, "_mapping") else dict(row)


def collect_reset_report(database_url: str) -> dict[str, Any]:
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT
                      (SELECT COUNT(*) FROM finance.shop_profit_basis
                        WHERE period_month = :period) AS basis_rows,
                      (SELECT COUNT(*) FROM finance.shop_profit_basis
                        WHERE period_month = :period AND basis_version = 'A_ONLY_V1') AS v1_basis_rows,
                      (SELECT COUNT(*) FROM finance.shop_profit_basis
                        WHERE period_month = :period AND basis_version = 'A_PRE_COMMISSION_LABOR_V2') AS v2_basis_rows,
                      (SELECT COUNT(*) FROM finance.shop_profit_basis
                        WHERE period_month = :period AND is_locked) AS locked_basis_rows,
                      (SELECT COUNT(*) FROM finance.employee_labor_cost_allocations
                        WHERE period_month = :period) AS allocation_rows,
                      (SELECT COUNT(*) FROM c_class.employee_commissions
                        WHERE year_month = :period) AS employee_commission_rows,
                      (SELECT COUNT(*) FROM c_class.employee_performance
                        WHERE year_month = :period) AS employee_performance_rows,
                      (SELECT COUNT(*) FROM c_class.shop_commissions
                        WHERE "年月" = :period) AS shop_commission_rows,
                      (SELECT COUNT(*) FROM a_class.payroll_records
                        WHERE year_month = :period) AS payroll_rows,
                      (SELECT COALESCE(ARRAY_AGG(DISTINCT LOWER(status)), ARRAY[]::text[])
                        FROM a_class.payroll_records WHERE year_month = :period) AS payroll_statuses,
                      (SELECT COUNT(*) FROM finance.monthly_profit_settlements
                        WHERE period_month = :period) AS settlement_rows,
                      (SELECT COUNT(*) FROM a_class.operating_costs
                        WHERE "年月" = :period AND "删除时间" IS NULL) AS operating_cost_rows,
                      (SELECT COALESCE(SUM(COALESCE("成本合计", 0)), 0)
                        FROM a_class.operating_costs
                        WHERE "年月" = :period AND "删除时间" IS NULL) AS operating_cost_total,
                      (SELECT COUNT(*) FROM a_class.employee_shop_assignments
                        WHERE year_month = :period AND status = 'active') AS assignment_rows,
                      (SELECT COUNT(*) FROM a_class.salary_structures
                        WHERE status = 'active'
                          AND effective_date <= CAST(:period || '-31' AS date)) AS salary_structure_rows,
                      (SELECT COUNT(*) FROM a_class.employee_performance_inputs
                        WHERE year_month = :period AND status = 'active') AS performance_input_rows,
                      (SELECT COUNT(*) FROM a_class.employee_performance_adjustments
                        WHERE year_month = :period AND status = 'active') AS performance_adjustment_rows
                    """
                ),
                {"period": PERIOD_MONTH},
            ).mappings().one()
            report = {"period_month": PERIOD_MONTH, **_as_dict(row)}
            report["payroll_statuses"] = list(report.get("payroll_statuses") or [])
            report["source_fingerprint"] = compute_batch_fingerprint(report)
            return report
    finally:
        engine.dispose()


def validate_reset_report(report: Mapping[str, Any]) -> None:
    if str(report.get("period_month") or "") != PERIOD_MONTH:
        raise AugustV2ResetSafetyError("only the fixed August 2026 reset is allowed")
    if int(report.get("locked_basis_rows") or 0):
        raise AugustV2ResetSafetyError("locked profit basis rows prevent reset")
    if int(report.get("v2_basis_rows") or 0):
        raise AugustV2ResetSafetyError("existing V2 results prevent a repeated reset")
    statuses = {str(status).lower() for status in report.get("payroll_statuses") or []}
    if statuses - {"draft"}:
        raise AugustV2ResetSafetyError("non-draft payroll rows prevent reset")
    if int(report.get("settlement_rows") or 0):
        raise AugustV2ResetSafetyError("monthly settlement rows prevent reset")


async def _verify_admin_actor(db, actor_user_id: int) -> dict[str, Any]:
    row = (
        await db.execute(
            text(
                """
                SELECT user_id, username
                FROM core.dim_users user_account
                WHERE user_id = :user_id
                  AND is_active = TRUE
                  AND status = 'active'
                  AND (
                    is_superuser = TRUE
                    OR EXISTS (
                      SELECT 1
                      FROM core.user_roles user_role
                      JOIN core.dim_roles role ON role.role_id = user_role.role_id
                      WHERE user_role.user_id = user_account.user_id
                        AND role.is_active = TRUE
                        AND LOWER(role.role_code) = 'admin'
                    )
                  )
                """
            ),
            {"user_id": actor_user_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise AugustV2ResetSafetyError("actor user must be an active administrator")
    return _as_dict(row)


async def _clear_derived_results(db) -> dict[str, int]:
    targets = {
        "shop_profit_basis": "DELETE FROM finance.shop_profit_basis WHERE period_month = :period",
        "labor_allocations": "DELETE FROM finance.employee_labor_cost_allocations WHERE period_month = :period",
        "employee_commissions": "DELETE FROM c_class.employee_commissions WHERE year_month = :period",
        "employee_performance": "DELETE FROM c_class.employee_performance WHERE year_month = :period",
        "shop_commissions": 'DELETE FROM c_class.shop_commissions WHERE "年月" = :period',
        "draft_payroll": "DELETE FROM a_class.payroll_records WHERE year_month = :period AND status = 'draft'",
    }
    deleted: dict[str, int] = {}
    for key, statement in targets.items():
        result = await db.execute(text(statement), {"period": PERIOD_MONTH})
        deleted[key] = int(result.rowcount or 0)
    return deleted


async def _write_audit_log(
    db,
    *,
    actor: Mapping[str, Any],
    report: Mapping[str, Any],
    deleted: Mapping[str, int],
    backup_path: Path,
    manifest_path: Path,
    workflow_run_id: str | None,
) -> None:
    details = {
        "period_month": PERIOD_MONTH,
        "source_fingerprint": report["source_fingerprint"],
        "pre_reset_report": dict(report),
        "deleted_derived_rows": dict(deleted),
        "backup_path": str(backup_path),
        "manifest_path": str(manifest_path),
        "workflow_run_id": workflow_run_id,
    }
    await db.execute(
        text(
            """
            INSERT INTO public.fact_audit_logs (
              user_id, username, action_type, resource_type, resource_id,
              action_description, changes_json, ip_address, user_agent, is_success
            ) VALUES (
              :user_id, :username, 'v2_august_reset', 'profit_basis', :resource_id,
              'reset August 2026 derived results and rebuild fixed V2 basis',
              :details, 'github-actions', 'reset_august_v2_start.py', TRUE
            )
            """
        ),
        {
            "user_id": actor["user_id"],
            "username": actor["username"],
            "resource_id": PERIOD_MONTH,
            "details": json.dumps(details, ensure_ascii=False, default=str),
        },
    )


async def apply_reset(
    *,
    report: Mapping[str, Any],
    actor_user_id: int,
    backup_path: Path,
    manifest_path: Path,
    workflow_run_id: str | None,
) -> dict[str, Any]:
    validate_reset_report(report)
    async with AsyncSessionLocal() as db:
        async with db.begin():
            actor = await _verify_admin_actor(db, actor_user_id)
            deleted = await _clear_derived_results(db)
            refresh_result = await V2MonthlyRefreshService(db).refresh_month(
                PERIOD_MONTH,
                commit=False,
            )
            await _write_audit_log(
                db,
                actor=actor,
                report=report,
                deleted=deleted,
                backup_path=backup_path,
                manifest_path=manifest_path,
                workflow_run_id=workflow_run_id,
            )
    return {
        "mode": "apply",
        "period_month": PERIOD_MONTH,
        "source_fingerprint": report["source_fingerprint"],
        "backup_path": str(backup_path),
        "manifest_path": str(manifest_path),
        "deleted_derived_rows": deleted,
        "refresh_result": refresh_result,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reset August 2026 to the fixed V2 basis")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="report only (default)")
    mode.add_argument("--apply", action="store_true", help="backup, reset derived rows, and rebuild V2")
    parser.add_argument("--confirm", help=f"required literal: {CONFIRMATION}")
    parser.add_argument("--actor-user-id", type=int, help="active administrator user ID")
    parser.add_argument("--workflow-run-id", help="GitHub Actions run identifier for the audit record")
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=Path(os.getenv("PROFIT_BASIS_BACKUP_DIR", "/app/data/backups/v2")),
        help="persistent backup location inside the production backend container",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    database_url = resolve_database_url(None)
    report = collect_reset_report(database_url)
    if not args.apply:
        print(json.dumps({"mode": "dry-run", "report": report}, ensure_ascii=False, indent=2, default=str))
        return 0
    if args.confirm != CONFIRMATION:
        raise AugustV2ResetSafetyError("explicit reset confirmation is required")
    if args.actor_user_id is None or args.actor_user_id <= 0:
        raise AugustV2ResetSafetyError("an active administrator user ID is required")

    backup_path = export_backup(database_url, args.backup_dir, report["source_fingerprint"])
    manifest_path = write_backup_manifest(backup_path, {"report": report, "batch_fingerprint": report["source_fingerprint"]})
    result = asyncio.run(
        apply_reset(
            report=report,
            actor_user_id=args.actor_user_id,
            backup_path=backup_path,
            manifest_path=manifest_path,
            workflow_run_id=args.workflow_run_id,
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AugustV2ResetSafetyError as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(2)
