from __future__ import annotations

from pathlib import Path
import asyncio
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.data_pipeline.refresh_registry import (
    SQL_TARGET_PATHS,
    topologically_sort_targets,
)
from backend.services.data_pipeline.sql_loader import load_sql_text, split_sql_statements
from modules.core.logger import get_logger


_OPS_TABLES_LOCK = asyncio.Lock()
_OPS_REQUIRED_TABLES = {
    "pipeline_run_log",
    "pipeline_step_log",
    "data_freshness_log",
    "data_lineage_registry",
}
_OPS_TABLES_READY_SIGNATURE: tuple[str, str] | None = None
logger = get_logger(__name__)


def extract_run_id(refresh_result: str | dict[str, Any]) -> str:
    if isinstance(refresh_result, dict):
        return str(refresh_result.get("run_id", ""))
    return str(refresh_result)


def extract_refresh_status(refresh_result: str | dict[str, Any]) -> str:
    if isinstance(refresh_result, dict):
        return str(refresh_result.get("status", "failed"))
    return "success"


def extract_failed_targets(refresh_result: str | dict[str, Any]) -> list[str]:
    if isinstance(refresh_result, dict):
        return [str(target) for target in (refresh_result.get("failed_targets", []) or [])]
    return []


def build_refresh_plan(targets: list[str]) -> list[str]:
    return topologically_sort_targets(targets)


def _target_type(target: str) -> str:
    if "." not in target:
        return "unknown"
    return target.split(".", 1)[0]


async def _ensure_ops_tables(db: AsyncSession) -> None:
    global _OPS_TABLES_READY_SIGNATURE
    try:
        bind = getattr(db, "get_bind", None)
        if callable(bind):
            engine = db.get_bind()
            db_url = str(getattr(engine, "url", "")) if engine is not None else ""
        else:
            engine = getattr(db, "bind", None)
            db_url = str(getattr(engine, "url", "")) if engine is not None else ""
    except Exception:
        db_url = ""

    signature = (db_url, "ops_tables_ready_v1")
    if _OPS_TABLES_READY_SIGNATURE == signature:
        return
    async with _OPS_TABLES_LOCK:
        if _OPS_TABLES_READY_SIGNATURE == signature:
            return
        existing_tables_result = await db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema = 'ops'
                  AND table_name IN (
                      'pipeline_run_log',
                      'pipeline_step_log',
                      'data_freshness_log',
                      'data_lineage_registry'
                  )
                """
            )
        )
        existing_tables_count = existing_tables_result.scalar() or 0
        if existing_tables_count >= len(_OPS_REQUIRED_TABLES):
            _OPS_TABLES_READY_SIGNATURE = signature
            return

        await execute_sql_file(db, "sql/ops/create_pipeline_tables.sql")
        _OPS_TABLES_READY_SIGNATURE = signature


async def _insert_run_log(
    db: AsyncSession,
    run_id: str,
    pipeline_name: str,
    trigger_source: str,
    context: dict | None = None,
) -> None:
    await db.execute(
        text(
            """
            INSERT INTO ops.pipeline_run_log (
                run_id, pipeline_name, status, trigger_source, context
            ) VALUES (
                :run_id, :pipeline_name, 'running', :trigger_source, CAST(:context AS jsonb)
            )
            """
        ),
        {
            "run_id": run_id,
            "pipeline_name": pipeline_name,
            "trigger_source": trigger_source,
            "context": "{}" if context is None else __import__("json").dumps(context),
        },
    )


async def _update_run_log(
    db: AsyncSession,
    run_id: str,
    status: str,
    error_message: str | None = None,
) -> None:
    await db.execute(
        text(
            """
            UPDATE ops.pipeline_run_log
            SET status = :status,
                completed_at = NOW(),
                error_message = :error_message
            WHERE run_id = :run_id
            """
        ),
        {
            "run_id": run_id,
            "status": status,
            "error_message": error_message,
        },
    )


async def _insert_step_log(
    db: AsyncSession,
    run_id: str,
    step_name: str,
    target_name: str,
    status: str,
    details: dict | None = None,
) -> None:
    await db.execute(
        text(
            """
            INSERT INTO ops.pipeline_step_log (
                run_id, step_name, target_name, status, details
            ) VALUES (
                :run_id, :step_name, :target_name, :status, CAST(:details AS jsonb)
            )
            """
        ),
        {
            "run_id": run_id,
            "step_name": step_name,
            "target_name": target_name,
            "status": status,
            "details": "{}" if details is None else __import__("json").dumps(details),
        },
    )


async def _insert_skipped_step_log(
    db: AsyncSession,
    run_id: str,
    target_name: str,
    reason: str,
) -> None:
    await _insert_step_log(
        db,
        run_id=run_id,
        step_name="execute_sql_target",
        target_name=target_name,
        status="skipped",
        details={"reason": reason},
    )
    await _update_step_log(
        db,
        run_id=run_id,
        target_name=target_name,
        status="skipped",
        error_message=reason,
    )


async def _update_step_log(
    db: AsyncSession,
    run_id: str,
    target_name: str,
    status: str,
    affected_rows: int | None = None,
    error_message: str | None = None,
) -> None:
    await db.execute(
        text(
            """
            UPDATE ops.pipeline_step_log
            SET status = :status,
                completed_at = NOW(),
                affected_rows = :affected_rows,
                error_message = :error_message
            WHERE id = (
                SELECT id
                FROM ops.pipeline_step_log
                WHERE run_id = :run_id
                  AND target_name = :target_name
                ORDER BY id DESC
                LIMIT 1
            )
            """
        ),
        {
            "run_id": run_id,
            "target_name": target_name,
            "status": status,
            "affected_rows": affected_rows,
            "error_message": error_message,
        },
    )


async def _upsert_freshness_log(
    db: AsyncSession,
    target: str,
    status: str,
) -> None:
    await db.execute(
        text(
            """
            INSERT INTO ops.data_freshness_log (
                target_name, target_type, last_started_at, last_succeeded_at, status
            ) VALUES (
                :target_name, :target_type, NOW(),
                CASE WHEN :status = 'success' THEN NOW() ELSE NULL END,
                :status
            )
            ON CONFLICT (target_name) DO UPDATE
            SET target_type = EXCLUDED.target_type,
                last_started_at = NOW(),
                last_succeeded_at = CASE WHEN EXCLUDED.status = 'success' THEN NOW() ELSE ops.data_freshness_log.last_succeeded_at END,
                status = EXCLUDED.status
            """
        ),
        {
            "target_name": target,
            "target_type": _target_type(target),
            "status": status,
        },
    )


async def _sync_lineage_registry(db: AsyncSession, target: str) -> None:
    from backend.services.data_pipeline.refresh_registry import PIPELINE_DEPENDENCIES

    for dependency in PIPELINE_DEPENDENCIES.get(target, []):
        await db.execute(
            text(
                """
                INSERT INTO ops.data_lineage_registry (
                    target_name, target_type, source_name, source_type, dependency_level, active
                ) VALUES (
                    :target_name, :target_type, :source_name, :source_type, 1, TRUE
                )
                ON CONFLICT (target_name, source_name) DO UPDATE
                SET target_type = EXCLUDED.target_type,
                    source_type = EXCLUDED.source_type,
                    dependency_level = EXCLUDED.dependency_level,
                    active = TRUE
                """
            ),
            {
                "target_name": target,
                "target_type": _target_type(target),
                "source_name": dependency,
                "source_type": _target_type(dependency),
            },
        )


async def execute_sql_text(db: AsyncSession, sql_text: str) -> None:
    for statement in split_sql_statements(sql_text):
        await db.execute(text(statement))


async def execute_sql_file(db: AsyncSession, path: str | Path) -> None:
    await execute_sql_text(db, load_sql_text(path))


async def _replace_step_details(
    db: AsyncSession,
    *,
    run_id: str,
    target_name: str,
    details: dict,
) -> None:
    await db.execute(
        text(
            """
            UPDATE ops.pipeline_step_log
            SET details = CAST(:details AS jsonb)
            WHERE id = (
                SELECT id
                FROM ops.pipeline_step_log
                WHERE run_id = :run_id
                  AND target_name = :target_name
                ORDER BY id DESC
                LIMIT 1
            )
            """
        ),
        {
            "run_id": run_id,
            "target_name": target_name,
            "details": __import__("json").dumps(details),
        },
    )


async def execute_sql_target(
    db: AsyncSession,
    target: str,
    pipeline_name: str = "refresh_sql_target",
    trigger_source: str = "system",
    context: dict | None = None,
    run_id: str | None = None,
    max_attempts: int = 1,
    retry_backoff_seconds: float = 0.0,
    resolve_dependencies: bool = False,
) -> str:
    active_run_id = run_id or f"run_{uuid.uuid4().hex}"
    await _ensure_ops_tables(db)
    if run_id is None:
        await _insert_run_log(
            db,
            run_id=active_run_id,
            pipeline_name=pipeline_name,
            trigger_source=trigger_source,
            context={"target": target, **(context or {})},
        )
    await _insert_step_log(
        db,
        run_id=active_run_id,
        step_name="execute_sql_target",
        target_name=target,
        status="running",
        details={"target_type": _target_type(target)},
    )
    if resolve_dependencies:
        ordered_targets = build_refresh_plan([target])
    else:
        ordered_targets = [target]
    last_error: Exception | None = None
    last_sql_path: str | None = None
    last_attempt = 0
    last_success_target: str | None = None
    try:
        for planned_target in ordered_targets:
            if planned_target == "ops.pipeline_run_log":
                sql_path = "sql/ops/create_pipeline_tables.sql"
            else:
                sql_path = SQL_TARGET_PATHS[planned_target]
            last_sql_path = str(sql_path)
            attempts = max(1, max_attempts)
            for attempt in range(1, attempts + 1):
                last_attempt = attempt
                logger.info(
                    "[refresh_runner] run_id=%s target=%s sql=%s attempt=%s/%s",
                    active_run_id,
                    planned_target,
                    sql_path,
                    attempt,
                    attempts,
                )
                try:
                    async with db.begin_nested():
                        await execute_sql_file(db, sql_path)
                    await _sync_lineage_registry(db, planned_target)
                    await _upsert_freshness_log(db, planned_target, "success")
                    last_success_target = planned_target
                    break
                except Exception as exc:
                    last_error = exc
                    logger.error(
                        "[refresh_runner] target failed run_id=%s target=%s sql=%s attempt=%s/%s error=%s",
                        active_run_id,
                        planned_target,
                        sql_path,
                        attempt,
                        attempts,
                        exc,
                    )
                    if attempt < attempts and retry_backoff_seconds > 0:
                        await asyncio.sleep(retry_backoff_seconds * attempt)
            else:
                assert last_error is not None
                raise last_error

        await _update_step_log(
            db,
            active_run_id,
            target,
            "success",
        )
        await _replace_step_details(
            db,
            run_id=active_run_id,
            target_name=target,
            details={
                "target_type": _target_type(target),
                "attempts": str(last_attempt or max(1, max_attempts)),
                "ordered_targets": ordered_targets,
                "sql_path": last_sql_path,
                "last_success_target": last_success_target,
            },
        )
        if run_id is None:
            await _update_run_log(db, active_run_id, "success")
        return active_run_id
    except Exception as exc:
        last_error = exc
        await _upsert_freshness_log(db, target, "failed")
        await _update_step_log(db, active_run_id, target, "failed", error_message=str(last_error))
        await _replace_step_details(
            db,
            run_id=active_run_id,
            target_name=target,
            details={
                "target_type": _target_type(target),
                "attempts": str(last_attempt or max(1, max_attempts)),
                "ordered_targets": ordered_targets,
                "sql_path": last_sql_path,
                "last_success_target": last_success_target,
                "error_summary": str(last_error),
            },
        )
        if run_id is None:
            await _update_run_log(db, active_run_id, "failed", error_message=str(last_error))
        raise


async def execute_refresh_plan(
    db: AsyncSession,
    targets: list[str],
    pipeline_name: str = "refresh_plan",
    trigger_source: str = "system",
    context: dict | None = None,
    continue_on_error: bool = False,
    max_attempts: int = 1,
    retry_backoff_seconds: float = 0.0,
    preordered: bool = False,
) -> dict[str, Any]:
    run_id = f"run_{uuid.uuid4().hex}"
    ordered_targets = list(targets) if preordered else build_refresh_plan(targets)
    await _ensure_ops_tables(db)
    await _insert_run_log(
        db,
        run_id=run_id,
        pipeline_name=pipeline_name,
        trigger_source=trigger_source,
        context={
            "targets": targets,
            "ordered_targets": ordered_targets,
            **(context or {}),
        },
    )
    failed_targets: set[str] = set()
    try:
        for target in ordered_targets:
            from backend.services.data_pipeline.refresh_registry import PIPELINE_DEPENDENCIES

            failed_dependencies = [
                dependency
                for dependency in PIPELINE_DEPENDENCIES.get(target, [])
                if dependency in failed_targets
            ]
            if failed_dependencies:
                await _insert_skipped_step_log(
                    db,
                    run_id=run_id,
                    target_name=target,
                    reason=f"dependency_failed:{','.join(failed_dependencies)}",
                )
                continue
            await execute_sql_target(
                db,
                target,
                pipeline_name=pipeline_name,
                trigger_source=trigger_source,
                context=context,
                run_id=run_id,
                max_attempts=max_attempts,
                retry_backoff_seconds=retry_backoff_seconds,
            )
        if failed_targets:
            await _update_run_log(db, run_id, "partial_failed")
        else:
            await _update_run_log(db, run_id, "success")
        return {
            "run_id": run_id,
            "status": "partial_failed" if failed_targets else "success",
            "failed_targets": sorted(failed_targets),
        }
    except Exception as exc:
        if continue_on_error:
            failed_targets.add(target)
            for remaining_target in ordered_targets[ordered_targets.index(target) + 1 :]:
                from backend.services.data_pipeline.refresh_registry import PIPELINE_DEPENDENCIES

                failed_dependencies = [
                    dependency
                    for dependency in PIPELINE_DEPENDENCIES.get(remaining_target, [])
                    if dependency in failed_targets
                ]
                if failed_dependencies:
                    await _insert_skipped_step_log(
                        db,
                        run_id=run_id,
                        target_name=remaining_target,
                        reason=f"dependency_failed:{','.join(failed_dependencies)}",
                    )
                else:
                    try:
                        await execute_sql_target(
                            db,
                            remaining_target,
                            pipeline_name=pipeline_name,
                            trigger_source=trigger_source,
                            context=context,
                            run_id=run_id,
                            max_attempts=max_attempts,
                            retry_backoff_seconds=retry_backoff_seconds,
                        )
                    except Exception:
                        failed_targets.add(remaining_target)
            await _update_run_log(db, run_id, "partial_failed", error_message=str(exc))
            return {
                "run_id": run_id,
                "status": "partial_failed",
                "failed_targets": sorted(failed_targets),
            }
        await _update_run_log(db, run_id, "failed", error_message=str(exc))
        raise
