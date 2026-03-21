from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.data_pipeline.refresh_registry import (
    SQL_TARGET_PATHS,
    topologically_sort_targets,
)
from backend.services.data_pipeline.sql_loader import load_sql_text, split_sql_statements


def build_refresh_plan(targets: list[str]) -> list[str]:
    return topologically_sort_targets(targets)


async def execute_sql_text(db: AsyncSession, sql_text: str) -> None:
    for statement in split_sql_statements(sql_text):
        await db.execute(text(statement))


async def execute_sql_file(db: AsyncSession, path: str | Path) -> None:
    await execute_sql_text(db, load_sql_text(path))


async def execute_sql_target(db: AsyncSession, target: str) -> None:
    if target == "ops.pipeline_run_log":
        sql_path = "sql/ops/create_pipeline_tables.sql"
    else:
        sql_path = SQL_TARGET_PATHS[target]
    await execute_sql_file(db, sql_path)
