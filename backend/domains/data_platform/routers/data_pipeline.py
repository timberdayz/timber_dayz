"""
Data pipeline observability routes.
"""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import get_async_db
from backend.services.data_pipeline.refresh_validation import find_missing_targets
from backend.services.data_pipeline.source_freshness_service import (
    collect_source_freshness,
)
from backend.utils.api_response import success_response

router = APIRouter(prefix="/api/data-pipeline", tags=["data-pipeline"])


def _object_exists_flag(name: Any, missing_names: set[str]) -> bool | None:
    """带 schema 前缀的名字是数据库对象，可核对存在性；其余返回 None（无法核对）。"""
    if not name or "." not in str(name):
        return None
    return str(name) not in missing_names


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

    # 存在性校验：freshness 只记录「上一次刷新当时的结果」，对象后来被删除/改名时
    # 状态仍是 success，监控因此「假绿」。这里实时核对对象是否还在，
    # 把「已注册但对象已不存在」的目标标成 missing。
    missing_targets = await find_missing_targets(
        db, [row.get("target_name") for row in targets]
    )
    for row in targets:
        target_name = row.get("target_name")
        if target_name in missing_targets:
            row["object_exists"] = False
            row["recorded_status"] = row.get("status")
            row["status"] = "missing"
        else:
            row["object_exists"] = _object_exists_flag(target_name, missing_targets)

    return success_response(
        data={
            "targets": targets,
            "missing_targets": sorted(missing_targets),
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

    # 注册表里 active = TRUE 只说明「登记过」，不代表对象还在。
    # 这里实时核对目标与来源对象，暴露「注册还在、对象已删」的情况。
    missing_objects = await find_missing_targets(
        db,
        [row.get("target_name") for row in edges]
        + [row.get("source_name") for row in edges],
    )
    for row in edges:
        row["target_object_exists"] = _object_exists_flag(
            row.get("target_name"), missing_objects
        )
        row["source_object_exists"] = _object_exists_flag(
            row.get("source_name"), missing_objects
        )

    return success_response(
        data={
            "edges": edges,
            "missing_objects": sorted(missing_objects),
        }
    )


@router.get("/source-freshness")
async def get_source_freshness(
    db: AsyncSession = Depends(get_async_db),
):
    """源数据（业务事实表）新鲜度。

    与 ``/freshness`` 的分工：``/freshness`` 看的是「视图/接口上次刷新有没有成功」，
    这里看的是「业务数据本身有多旧」。断流的第一现场在后者——
    刷新链路可以全绿，而底下的业务数据已经几个月没更新过。
    """
    report = await collect_source_freshness(db)
    return success_response(
        data={
            "summary": report.to_summary(),
            "chains": [row.to_dict() for row in report.rows],
        }
    )
