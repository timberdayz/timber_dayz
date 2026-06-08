from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.data_pipeline.refresh_registry import (
    PIPELINE_DEPENDENCIES,
    SQL_TARGET_PATHS,
)
from backend.services.data_pipeline.refresh_runner import execute_refresh_plan, execute_sql_file, extract_run_id


DASHBOARD_MODULE_TARGETS: dict[str, dict[str, list[str]]] = {
    "business_overview": {
        "core_targets": [
            "api.business_overview_kpi_module",
            "api.business_overview_comparison_platform_module",
            "api.business_overview_comparison_module",
            "api.business_overview_shop_racing_module",
            "api.business_overview_shop_racing_monthly_module",
            "api.business_overview_traffic_ranking_module",
            "api.business_overview_inventory_backlog_module",
            "api.inventory_backlog_summary_module",
            "api.business_overview_operational_metrics_module",
        ],
        "refresh_targets": [
            "semantic.fact_orders_monthly_atomic_mv",
            "semantic.fact_analytics_monthly_atomic_mv",
        ],
    },
    "clearance_ranking": {
        "core_targets": [
            "api.inventory_backlog_summary_module",
            "api.clearance_ranking_module",
        ],
        "refresh_targets": [],
    },
}

DASHBOARD_REQUIRED_SCHEMAS = ("semantic", "mart", "api", "ops")
OPS_TABLES = (
    "ops.pipeline_run_log",
    "ops.pipeline_step_log",
    "ops.data_freshness_log",
    "ops.data_lineage_registry",
    "ops.dashboard_asset_state",
)
EXTRA_TABLES = ("core.field_alias_rules",)

DASHBOARD_BOOTSTRAP_TARGETS = sorted(
    {
        target
        for module in DASHBOARD_MODULE_TARGETS.values()
        for target in module["core_targets"]
    }
)
DASHBOARD_REQUIRED_OBJECTS = [
    *sorted(
        {
            target
            for module in DASHBOARD_MODULE_TARGETS.values()
            for target in [*module["core_targets"], *module["refresh_targets"]]
        }
    ),
    *OPS_TABLES,
    *EXTRA_TABLES,
]

_DASHBOARD_BOOTSTRAP_LOCK_KEY = 918_240_113


def _resolve_module_names(module: str = "all") -> list[str]:
    if module == "all":
        return list(DASHBOARD_MODULE_TARGETS.keys())
    if module not in DASHBOARD_MODULE_TARGETS:
        raise ValueError(f"Unknown dashboard module: {module}")
    return [module]


def _topological_sort_targets(
    targets: list[str],
    *,
    blocked_targets: set[str] | None = None,
) -> list[str]:
    ordered: list[str] = []
    blocked = blocked_targets or set()
    temporary: set[str] = set()
    permanent: set[str] = set(blocked)

    def visit(target: str) -> None:
        if target in permanent:
            return
        if target in temporary:
            raise ValueError(f"Cycle detected in refresh dependency graph at {target}")
        temporary.add(target)
        for dependency in PIPELINE_DEPENDENCIES.get(target, []):
            visit(dependency)
        temporary.remove(target)
        permanent.add(target)
        if target not in ordered:
            ordered.append(target)

    for target in targets:
        visit(target)
    return ordered


def _module_core_plan(module_name: str) -> list[str]:
    module = DASHBOARD_MODULE_TARGETS[module_name]
    return _topological_sort_targets(
        module["core_targets"],
        blocked_targets=set(module["refresh_targets"]),
    )


def _module_refresh_plan(module_name: str) -> list[str]:
    module = DASHBOARD_MODULE_TARGETS[module_name]
    refresh_targets = module["refresh_targets"]
    return _topological_sort_targets(refresh_targets) if refresh_targets else []


def _all_dashboard_core_plan() -> list[str]:
    targets: list[str] = []
    for module_name in DASHBOARD_MODULE_TARGETS:
        targets.extend(_module_core_plan(module_name))
    ordered: list[str] = []
    for target in targets:
        if target not in ordered:
            ordered.append(target)
    return ordered


def _compute_targets_fingerprint(targets: list[str]) -> str | None:
    if not targets:
        return None

    hasher = hashlib.sha256()
    root = Path(__file__).resolve().parents[3]
    for target in sorted(set(targets)):
        path = root / SQL_TARGET_PATHS[target]
        hasher.update(target.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(str(path).encode("utf-8"))
        hasher.update(b"\0")
        try:
            hasher.update(path.read_bytes())
        except FileNotFoundError:
            hasher.update(b"")
        hasher.update(b"\0")
    return hasher.hexdigest()


def _normalize_json_value(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


async def _load_active_dashboard_refresh_runs(
    session: AsyncSession,
) -> dict[str, dict[str, Any]]:
    try:
        reg = await session.execute(text("SELECT to_regclass('ops.pipeline_run_log')"))
        if reg.scalar_one_or_none() is None:
            return {}
        result = await session.execute(
            text(
                """
                SELECT pipeline_name,
                       run_id,
                       status,
                       started_at,
                       completed_at,
                       context
                FROM ops.pipeline_run_log
                WHERE status = 'running'
                  AND (
                      pipeline_name LIKE 'dashboard_materialization_refresh.%'
                      OR pipeline_name LIKE 'dashboard_materialization_rebuild_core.%'
                      OR (
                          trigger_source = 'materialization_refresh'
                          AND context ? 'module_name'
                      )
                  )
                ORDER BY started_at DESC
                """
            )
        )
        runs: dict[str, dict[str, Any]] = {}
        for row in result.mappings():
            context = _normalize_json_value(row.get("context"))
            pipeline_name = str(row.get("pipeline_name") or "")
            module_name = context.get("module_name")
            if not module_name and "." in pipeline_name:
                module_name = pipeline_name.rsplit(".", 1)[-1]
            if not module_name:
                continue
            runs[module_name] = dict(row)
            runs[module_name]["context"] = context
        return runs
    except Exception:
        return {}


async def _try_advisory_lock(session: AsyncSession, key: int) -> bool:
    result = await session.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": key})
    return bool(result.scalar_one())


async def _advisory_unlock(session: AsyncSession, key: int) -> None:
    try:
        await session.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
    except Exception:
        pass


async def _advisory_lock(session: AsyncSession, key: int) -> None:
    await session.execute(text("SELECT pg_advisory_lock(:key)"), {"key": key})


async def _load_dashboard_asset_state(session: AsyncSession) -> dict[str, dict[str, Any]]:
    try:
        reg = await session.execute(text("SELECT to_regclass('ops.dashboard_asset_state')"))
        if reg.scalar_one_or_none() is None:
            return {}
        result = await session.execute(
            text(
                """
                SELECT module_name,
                       asset_fingerprint_expected,
                       asset_fingerprint_applied,
                       status,
                       run_id,
                       updated_at,
                       details_json
                FROM ops.dashboard_asset_state
                """
            )
        )
        rows = {}
        for row in result.mappings():
            rows[row["module_name"]] = dict(row)
        return rows
    except Exception:
        return {}


async def _upsert_dashboard_asset_state(
    session: AsyncSession,
    *,
    module_name: str,
    asset_fingerprint_expected: str | None,
    asset_fingerprint_applied: str | None,
    status: str,
    run_id: str | None,
    details_json: dict[str, Any] | None = None,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO ops.dashboard_asset_state (
                module_name,
                asset_fingerprint_expected,
                asset_fingerprint_applied,
                status,
                run_id,
                updated_at,
                details_json
            ) VALUES (
                :module_name,
                :asset_fingerprint_expected,
                :asset_fingerprint_applied,
                :status,
                :run_id,
                NOW(),
                CAST(:details_json AS jsonb)
            )
            ON CONFLICT (module_name) DO UPDATE
            SET asset_fingerprint_expected = EXCLUDED.asset_fingerprint_expected,
                asset_fingerprint_applied = EXCLUDED.asset_fingerprint_applied,
                status = EXCLUDED.status,
                run_id = EXCLUDED.run_id,
                updated_at = NOW(),
                details_json = EXCLUDED.details_json
            """
        ),
        {
            "module_name": module_name,
            "asset_fingerprint_expected": asset_fingerprint_expected,
            "asset_fingerprint_applied": asset_fingerprint_applied,
            "status": status,
            "run_id": run_id,
            "details_json": __import__("json").dumps(details_json or {}),
        },
    )


async def _collect_existing_assets(session: AsyncSession) -> tuple[set[str], set[str]]:
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
    return existing_schemas, existing_objects


def _build_module_report(
    *,
    module_name: str,
    module_state: dict[str, Any] | None,
    existing_objects: set[str],
    active_refresh_run: dict[str, Any] | None,
) -> dict[str, Any]:
    module = DASHBOARD_MODULE_TARGETS[module_name]
    core_targets = _module_core_plan(module_name)
    refresh_targets = _module_refresh_plan(module_name)
    core_expected = _compute_targets_fingerprint(core_targets)
    refresh_expected = _compute_targets_fingerprint(refresh_targets)

    details = _normalize_json_value((module_state or {}).get("details_json"))
    core_applied = (module_state or {}).get("asset_fingerprint_applied")
    refresh_applied = details.get("refresh_fingerprint_applied")
    core_missing = [target for target in core_targets if target not in existing_objects]
    refresh_missing = [target for target in refresh_targets if target not in existing_objects]
    stored_status = (module_state or {}).get("status")
    active_refreshing = active_refresh_run is not None

    if core_missing or (core_expected and core_applied != core_expected) or stored_status == "failed":
        status = "drift"
        ready = False
    elif refresh_targets and (
        refresh_missing
        or (refresh_expected and refresh_applied != refresh_expected)
        or active_refreshing
    ):
        status = "refreshing"
        ready = True
    else:
        status = "ready"
        ready = True

    return {
        "module_name": module_name,
        "status": status,
        "ready": ready,
        "core_targets": core_targets,
        "refresh_targets": refresh_targets,
        "core_missing_objects": core_missing,
        "refresh_missing_objects": refresh_missing,
        "assets_drift": status == "drift",
        "asset_fingerprint_expected": core_expected,
        "asset_fingerprint_applied": core_applied,
        "refresh_fingerprint_expected": refresh_expected,
        "refresh_fingerprint_applied": refresh_applied,
        "run_id": (module_state or {}).get("run_id"),
        "details": details,
        "active_refresh_run": active_refresh_run,
    }


async def inspect_dashboard_assets(session: AsyncSession) -> dict[str, Any]:
    existing_schemas, existing_objects = await _collect_existing_assets(session)
    state_rows = await _load_dashboard_asset_state(session)
    active_refresh_runs = await _load_active_dashboard_refresh_runs(session)

    modules: dict[str, dict[str, Any]] = {}
    for module_name in DASHBOARD_MODULE_TARGETS:
        modules[module_name] = _build_module_report(
            module_name=module_name,
            module_state=state_rows.get(module_name),
            existing_objects=existing_objects,
            active_refresh_run=active_refresh_runs.get(module_name),
        )

    missing_schemas = [
        schema for schema in DASHBOARD_REQUIRED_SCHEMAS if schema not in existing_schemas
    ]
    missing_objects = [
        name for name in DASHBOARD_REQUIRED_OBJECTS if name not in existing_objects
    ]
    ready = all(report["ready"] for report in modules.values())
    assets_drift = any(report["status"] == "drift" for report in modules.values())

    return {
        "ready": ready,
        "existing_schemas": sorted(existing_schemas),
        "missing_schemas": missing_schemas,
        "missing_objects": missing_objects,
        "assets_drift": assets_drift,
        "modules": modules,
    }


async def bootstrap_dashboard_assets(
    session: AsyncSession,
    *,
    module: str = "all",
) -> dict[str, Any]:
    await session.execute(text("SET LOCAL statement_timeout = 0"))
    await execute_sql_file(session, "sql/ops/create_pipeline_tables.sql")
    await execute_sql_file(session, "sql/ops/create_field_alias_rules.sql")

    selected_modules = _resolve_module_names(module)
    module_run_ids: dict[str, str | None] = {}

    for module_name in selected_modules:
        core_targets = _module_core_plan(module_name)
        refresh_targets = _module_refresh_plan(module_name)
        core_expected = _compute_targets_fingerprint(core_targets)
        refresh_expected = _compute_targets_fingerprint(refresh_targets)
        existing_state = (await _load_dashboard_asset_state(session)).get(module_name, {})
        existing_details = _normalize_json_value(existing_state.get("details_json"))

        await _upsert_dashboard_asset_state(
            session,
            module_name=module_name,
            asset_fingerprint_expected=core_expected,
            asset_fingerprint_applied=existing_state.get("asset_fingerprint_applied"),
            status="drift",
            run_id=existing_state.get("run_id"),
            details_json={
                **existing_details,
                "refresh_fingerprint_expected": refresh_expected,
                "refresh_fingerprint_applied": existing_details.get("refresh_fingerprint_applied"),
                "core_targets": core_targets,
                "refresh_targets": refresh_targets,
            },
        )

        refresh_run_id = None
        if refresh_targets:
            refresh_run_result = await execute_refresh_plan(
                session,
                targets=refresh_targets,
                pipeline_name=f"bootstrap_postgresql_dashboard_refresh.{module_name}",
                trigger_source="bootstrap",
                context={
                    "module_name": module_name,
                    "target_count": len(refresh_targets),
                    "refresh_fingerprint": refresh_expected,
                },
                preordered=True,
            )
            refresh_run_id = extract_run_id(refresh_run_result)

        run_result = await execute_refresh_plan(
            session,
            targets=core_targets,
            pipeline_name=f"bootstrap_postgresql_dashboard.{module_name}",
            trigger_source="bootstrap",
            context={
                "module_name": module_name,
                "target_count": len(core_targets),
                "asset_fingerprint": core_expected,
                "refresh_target_count": len(refresh_targets),
                "refresh_run_id": refresh_run_id,
            },
            preordered=True,
        )
        run_id = extract_run_id(run_result)
        module_run_ids[module_name] = run_id

        await _upsert_dashboard_asset_state(
            session,
            module_name=module_name,
            asset_fingerprint_expected=core_expected,
            asset_fingerprint_applied=core_expected,
            status="ready",
            run_id=run_id,
            details_json={
                "refresh_fingerprint_expected": refresh_expected,
                "refresh_fingerprint_applied": refresh_expected if refresh_targets else existing_details.get("refresh_fingerprint_applied"),
                "refresh_run_id": refresh_run_id,
                "core_targets": core_targets,
                "refresh_targets": refresh_targets,
            },
        )

    report = await inspect_dashboard_assets(session)
    report["run_ids"] = module_run_ids
    report["module"] = module
    return report


async def refresh_dashboard_materialization_assets(
    session: AsyncSession,
    *,
    module: str = "all",
) -> dict[str, Any]:
    await session.execute(text("SET LOCAL statement_timeout = 0"))
    selected_modules = _resolve_module_names(module)
    module_run_ids: dict[str, str | None] = {}

    for module_name in selected_modules:
        refresh_targets = _module_refresh_plan(module_name)
        if not refresh_targets:
            continue
        core_targets = _all_dashboard_core_plan()

        state = (await _load_dashboard_asset_state(session)).get(module_name, {})
        details = _normalize_json_value(state.get("details_json"))
        refresh_expected = _compute_targets_fingerprint(refresh_targets)

        refresh_run_result = await execute_refresh_plan(
            session,
            targets=refresh_targets,
            pipeline_name=f"dashboard_materialization_refresh.{module_name}",
            trigger_source="materialization_refresh",
            context={
                "module_name": module_name,
                "target_count": len(refresh_targets),
                "refresh_fingerprint": refresh_expected,
            },
            preordered=True,
        )
        refresh_run_id = extract_run_id(refresh_run_result)
        run_result = await execute_refresh_plan(
            session,
            targets=core_targets,
            pipeline_name=f"dashboard_materialization_rebuild_core.{module_name}",
            trigger_source="materialization_refresh",
            context={
                "module_name": module_name,
                "target_count": len(core_targets),
                "asset_fingerprint": state.get("asset_fingerprint_expected"),
                "refresh_run_id": refresh_run_id,
            },
            preordered=True,
        )
        run_id = extract_run_id(run_result)
        module_run_ids[module_name] = run_id

        await _upsert_dashboard_asset_state(
            session,
            module_name=module_name,
            asset_fingerprint_expected=state.get("asset_fingerprint_expected"),
            asset_fingerprint_applied=state.get("asset_fingerprint_applied"),
            status="ready",
            run_id=run_id,
            details_json={
                **details,
                "refresh_fingerprint_expected": refresh_expected,
                "refresh_fingerprint_applied": refresh_expected,
                "refresh_run_id": refresh_run_id,
                "refresh_targets": refresh_targets,
                "core_targets": core_targets,
            },
        )

    report = await inspect_dashboard_assets(session)
    report["run_ids"] = module_run_ids
    report["module"] = module
    return report


async def bootstrap_dashboard_assets_if_needed(
    session: AsyncSession,
    *,
    wait_for_lock: bool = False,
    module: str = "all",
) -> dict[str, Any]:
    report = await inspect_dashboard_assets(session)
    selected_modules = _resolve_module_names(module)
    if all(
        report["modules"][module_name]["status"] in {"ready", "refreshing"}
        for module_name in selected_modules
    ):
        report["bootstrapped"] = False
        return report

    acquired = False
    if wait_for_lock:
        await session.execute(text("SET LOCAL statement_timeout = 0"))
        import asyncio

        deadline_seconds = 240.0
        poll_interval = 2.0
        waited = 0.0
        while waited <= deadline_seconds:
            acquired = await _try_advisory_lock(session, _DASHBOARD_BOOTSTRAP_LOCK_KEY)
            if acquired:
                break
            await asyncio.sleep(poll_interval)
            waited += poll_interval
    else:
        acquired = await _try_advisory_lock(session, _DASHBOARD_BOOTSTRAP_LOCK_KEY)

    if not acquired:
        report["bootstrapped"] = False
        report["bootstrap_in_progress"] = True
        return report

    try:
        report = await bootstrap_dashboard_assets(session, module=module)
        report["bootstrapped"] = True
        return report
    finally:
        await _advisory_unlock(session, _DASHBOARD_BOOTSTRAP_LOCK_KEY)
