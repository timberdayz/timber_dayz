from __future__ import annotations

from pathlib import Path
import asyncio
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.data_pipeline.refresh_registry import (
    SQL_TARGET_PATHS,
    topologically_sort_targets,
)
from backend.services.data_pipeline.sql_loader import load_sql_text, split_sql_statements


def build_refresh_plan(targets: list[str]) -> list[str]:
    return topologically_sort_targets(targets)


def _target_type(target: str) -> str:
    if "." not in target:
        return "unknown"
    return target.split(".", 1)[0]


async def _ensure_ops_tables(db: AsyncSession) -> None:
    await execute_sql_file(db, "sql/ops/create_pipeline_tables.sql")


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


async def execute_sql_target(
    db: AsyncSession,
    target: str,
    pipeline_name: str = "refresh_sql_target",
    trigger_source: str = "system",
    context: dict | None = None,
    run_id: str | None = None,
    max_attempts: int = 1,
    retry_backoff_seconds: float = 0.0,
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
    if target == "ops.pipeline_run_log":
        sql_path = "sql/ops/create_pipeline_tables.sql"
    else:
        sql_path = SQL_TARGET_PATHS[target]
    last_error: Exception | None = None
    attempts = max(1, max_attempts)
    for attempt in range(1, attempts + 1):
        try:
            async with db.begin_nested():
                await execute_sql_file(db, sql_path)
            await _sync_lineage_registry(db, target)
            await _upsert_freshness_log(db, target, "success")
            await _update_step_log(
                db,
                active_run_id,
                target,
                "success",
            )
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
                    "run_id": active_run_id,
                    "target_name": target,
                    "details": __import__("json").dumps(
                        {
                            "target_type": _target_type(target),
                            "attempts": attempt,
                        }
                    ),
                },
            )
            if run_id is None:
                await _update_run_log(db, active_run_id, "success")
            return active_run_id
        except Exception as exc:
            last_error = exc
            if attempt < attempts and retry_backoff_seconds > 0:
                await asyncio.sleep(retry_backoff_seconds * attempt)

    assert last_error is not None
    await _upsert_freshness_log(db, target, "failed")
    await _update_step_log(db, active_run_id, target, "failed", error_message=str(last_error))
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
            "run_id": active_run_id,
            "target_name": target,
            "details": __import__("json").dumps(
                {
                    "target_type": _target_type(target),
                    "attempts": attempts,
                }
            ),
        },
    )
    if run_id is None:
        await _update_run_log(db, active_run_id, "failed", error_message=str(last_error))
    raise last_error


async def execute_refresh_plan(
    db: AsyncSession,
    targets: list[str],
    pipeline_name: str = "refresh_plan",
    trigger_source: str = "system",
    context: dict | None = None,
    continue_on_error: bool = False,
    max_attempts: int = 1,
    retry_backoff_seconds: float = 0.0,
) -> str:
    run_id = f"run_{uuid.uuid4().hex}"
    ordered_targets = build_refresh_plan(targets)
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
        return run_id
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
            return run_id
        await _update_run_log(db, run_id, "failed", error_message=str(exc))
        raise
