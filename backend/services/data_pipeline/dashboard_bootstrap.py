from __future__ import annotations

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

    return {
        "ready": not missing_schemas and not missing_objects,
        "existing_schemas": sorted(existing_schemas),
        "missing_schemas": missing_schemas,
        "missing_objects": missing_objects,
    }


async def bootstrap_dashboard_assets(session: AsyncSession) -> dict[str, Any]:
    await execute_sql_file(session, "sql/ops/create_pipeline_tables.sql")
    await execute_sql_file(session, "sql/ops/create_field_alias_rules.sql")
    run_id = await execute_refresh_plan(
        session,
        targets=DASHBOARD_BOOTSTRAP_TARGETS,
        pipeline_name="bootstrap_postgresql_dashboard",
        trigger_source="bootstrap",
        context={"target_count": len(DASHBOARD_BOOTSTRAP_TARGETS)},
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
