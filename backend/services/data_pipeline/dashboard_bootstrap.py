from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.data_pipeline.refresh_registry import SQL_TARGET_PATHS, topologically_sort_targets
from backend.services.data_pipeline.refresh_runner import execute_refresh_plan, execute_sql_file


DASHBOARD_BOOTSTRAP_TARGETS = topologically_sort_targets(list(SQL_TARGET_PATHS.keys()))
DASHBOARD_REQUIRED_SCHEMAS = ("semantic", "mart", "api", "ops")
OPS_TABLES = (
    "ops.pipeline_run_log",
    "ops.pipeline_step_log",
    "ops.data_freshness_log",
    "ops.data_lineage_registry",
)
EXTRA_TABLES = (
    "core.field_alias_rules",
)
DASHBOARD_REQUIRED_OBJECTS = [*DASHBOARD_BOOTSTRAP_TARGETS, *OPS_TABLES, *EXTRA_TABLES]


def _compute_dashboard_assets_fingerprint() -> str:
    """Stable fingerprint for dashboard SQL assets, used for drift detection.

    Note: This is intentionally file-content-based (not DB-based) so that local
    code changes reliably trigger a bootstrap refresh on the same database.
    """
    hasher = hashlib.sha256()
    root = Path(__file__).resolve().parents[3]

    paths: list[Path] = []
    for target, rel_path in SQL_TARGET_PATHS.items():
        _ = target
        paths.append(root / rel_path)
    paths.append(root / "sql" / "ops" / "create_pipeline_tables.sql")
    paths.append(root / "sql" / "ops" / "create_field_alias_rules.sql")

    for path in sorted({p.resolve() for p in paths}, key=lambda p: str(p).lower()):
        hasher.update(str(path).encode("utf-8"))
        hasher.update(b"\0")
        try:
            content = path.read_bytes()
        except FileNotFoundError:
            content = b""
        hasher.update(content)
        hasher.update(b"\0")

    return hasher.hexdigest()


async def inspect_dashboard_assets(session: AsyncSession) -> dict[str, Any]:
    schema_result = await session.execute(
        text(
            """
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name = ANY(:schemas)
            ORDER BY schema_name
            """
        ),
        {"schemas": list(DASHBOARD_REQUIRED_SCHEMAS)},
    )
    existing_schemas = {row[0] for row in schema_result.fetchall()}

    object_result = await session.execute(
        text(
            """
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_schema = ANY(:schemas)
            UNION
            SELECT table_schema, table_name
            FROM information_schema.views
            WHERE table_schema = ANY(:schemas)
            UNION
            SELECT schemaname AS table_schema, matviewname AS table_name
            FROM pg_matviews
            WHERE schemaname = ANY(:schemas)
            """
        ),
        {"schemas": ["semantic", "mart", "api", "ops", "core"]},
    )
    existing_objects = {f"{row[0]}.{row[1]}" for row in object_result.fetchall()}

    missing_schemas = [schema for schema in DASHBOARD_REQUIRED_SCHEMAS if schema not in existing_schemas]
    missing_objects = [name for name in DASHBOARD_REQUIRED_OBJECTS if name not in existing_objects]

    expected_fingerprint = _compute_dashboard_assets_fingerprint()
    last_fingerprint = None
    drift = False

    # Drift detection: if assets exist but were bootstrapped under a different SQL fingerprint,
    # treat as "not ready" so run.py can re-bootstrap automatically.
    try:
        reg = await session.execute(text("SELECT to_regclass('ops.pipeline_run_log')"))
        pipeline_run_log_exists = reg.scalar_one_or_none() is not None
        if pipeline_run_log_exists:
            result = await session.execute(
                text(
                    """
                    SELECT context->>'assets_fingerprint'
                    FROM ops.pipeline_run_log
                    WHERE pipeline_name = 'bootstrap_postgresql_dashboard'
                      AND status = 'success'
                    ORDER BY completed_at DESC NULLS LAST, started_at DESC
                    LIMIT 1
                    """
                )
            )
            last_fingerprint = result.scalar_one_or_none()
            drift = (last_fingerprint != expected_fingerprint) if last_fingerprint else True
    except Exception:
        # If we cannot read bootstrap history, don't hard-fail readiness on drift.
        drift = False

    return {
        "ready": (not missing_schemas and not missing_objects and not drift),
        "existing_schemas": sorted(existing_schemas),
        "missing_schemas": missing_schemas,
        "missing_objects": missing_objects,
        "assets_fingerprint_expected": expected_fingerprint,
        "assets_fingerprint_last": last_fingerprint,
        "assets_drift": drift,
    }


async def bootstrap_dashboard_assets(session: AsyncSession) -> dict[str, Any]:
    # Bootstrap may rebuild large semantic/materialized assets and can exceed
    # the normal 120s query timeout configured for interactive runtime traffic.
    await session.execute(text("SET LOCAL statement_timeout = 0"))
    await execute_sql_file(session, "sql/ops/create_pipeline_tables.sql")
    await execute_sql_file(session, "sql/ops/create_field_alias_rules.sql")
    fingerprint = _compute_dashboard_assets_fingerprint()
    run_id = await execute_refresh_plan(
        session,
        targets=DASHBOARD_BOOTSTRAP_TARGETS,
        pipeline_name="bootstrap_postgresql_dashboard",
        trigger_source="bootstrap",
        context={
            "target_count": len(DASHBOARD_BOOTSTRAP_TARGETS),
            "assets_fingerprint": fingerprint,
        },
    )
    report = await inspect_dashboard_assets(session)
    report["run_id"] = run_id
    return report


async def bootstrap_dashboard_assets_if_needed(session: AsyncSession) -> dict[str, Any]:
    report = await inspect_dashboard_assets(session)
    if report["ready"]:
        report["bootstrapped"] = False
        return report

    report = await bootstrap_dashboard_assets(session)
    report["bootstrapped"] = True
    return report
