"""
Data pipeline observability routes.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import get_async_db
from backend.utils.api_response import success_response

router = APIRouter(prefix="/api/data-pipeline", tags=["data-pipeline"])


@router.get("/status")
async def get_pipeline_status(
    db: AsyncSession = Depends(get_async_db),
):
    result = await db.execute(
        text(
            """
            SELECT run_id, pipeline_name, status, trigger_source, started_at, completed_at, error_message
            FROM ops.pipeline_run_log
            ORDER BY id DESC
            LIMIT 20
            """
        )
    )
    runs = [dict(row) for row in result.mappings().all()]
    return success_response(
        data={
            "runs": runs,
        }
    )


@router.get("/freshness")
async def get_pipeline_freshness(
    db: AsyncSession = Depends(get_async_db),
):
    result = await db.execute(
        text(
            """
            SELECT target_name, target_type, last_started_at, last_succeeded_at, status, affected_rows, data_min_date, data_max_date
            FROM ops.data_freshness_log
            ORDER BY target_name
            """
        )
    )
    targets = [dict(row) for row in result.mappings().all()]
    return success_response(
        data={
            "targets": targets,
        }
    )


@router.get("/lineage")
async def get_pipeline_lineage(
    db: AsyncSession = Depends(get_async_db),
):
    result = await db.execute(
        text(
            """
            SELECT target_name, target_type, source_name, source_type, dependency_level, active, created_at
            FROM ops.data_lineage_registry
            WHERE active = TRUE
            ORDER BY target_name, dependency_level, source_name
            """
        )
    )
    edges = [dict(row) for row in result.mappings().all()]
    return success_response(
        data={
            "edges": edges,
        }
    )
