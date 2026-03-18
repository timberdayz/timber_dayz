"""
Legacy materialized view management API.

The preferred query architecture is DSS/Metabase. These endpoints remain
available only as compatibility tooling for environments that still maintain
materialized views.
"""

from datetime import datetime
import time
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import get_async_db
from backend.utils.api_response import error_response, success_response
from backend.utils.error_codes import ErrorCode, get_error_type
from modules.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/mv", tags=["legacy-materialized-views"])


def _preferred_refresh_order(view_names: list[str]) -> list[str]:
    preferred = [
        "mv_product_management",
        "mv_order_summary",
        "mv_inventory_by_sku",
        "mv_traffic_summary",
        "mv_financial_overview",
    ]
    remainder = sorted(name for name in view_names if name not in preferred)
    ordered = [name for name in preferred if name in view_names]
    return ordered + remainder


async def _fetch_view_names(db: AsyncSession) -> list[str]:
    result = await db.execute(
        text(
            """
            SELECT matviewname
            FROM pg_matviews
            WHERE schemaname = 'public'
            ORDER BY matviewname
            """
        )
    )
    return [row[0] for row in result]


async def _count_rows(db: AsyncSession, view_name: str) -> int:
    result = await db.execute(text(f"SELECT COUNT(*) FROM {view_name}"))
    return int(result.scalar() or 0)


async def _fetch_refresh_log(
    db: AsyncSession, view_name: str
) -> tuple[str | None, float | None, float | None]:
    try:
        from modules.core.db import MaterializedViewRefreshLog

        result = await db.execute(
            select(MaterializedViewRefreshLog)
            .where(MaterializedViewRefreshLog.view_name == view_name)
            .order_by(MaterializedViewRefreshLog.refresh_completed_at.desc())
        )
        refresh_log = result.scalar_one_or_none()
    except Exception:
        return None, None, None

    if not refresh_log or not refresh_log.refresh_completed_at:
        return None, None, None

    refresh_time = refresh_log.refresh_completed_at
    age_minutes = (datetime.now() - refresh_time).total_seconds() / 60
    return (
        refresh_time.isoformat(),
        refresh_log.duration_seconds,
        round(age_minutes, 2),
    )


@router.post("/refresh-all", deprecated=True)
async def refresh_all_materialized_views(
    db: AsyncSession = Depends(get_async_db),
):
    logger.warning("[LegacyMV] /api/mv/refresh-all is deprecated and kept for compatibility only")
    start_time = time.time()
    results: list[dict[str, Any]] = []

    try:
        view_names = await _fetch_view_names(db)
        if not view_names:
            return success_response(
                data={
                    "results": [],
                    "total_duration_seconds": 0,
                    "total_views": 0,
                    "success_count": 0,
                    "failed_count": 0,
                },
                message="没有找到物化视图",
            )

        for view_name in _preferred_refresh_order(view_names):
            view_start = time.time()
            try:
                refresh_method = "CONCURRENTLY"
                try:
                    await db.execute(
                        text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view_name}")
                    )
                    await db.commit()
                except Exception:
                    await db.rollback()
                    refresh_method = "NORMAL"
                    await db.execute(text(f"REFRESH MATERIALIZED VIEW {view_name}"))
                    await db.commit()

                row_count = await _count_rows(db, view_name)
                results.append(
                    {
                        "view_name": view_name,
                        "success": True,
                        "duration_seconds": round(time.time() - view_start, 2),
                        "row_count": row_count,
                        "refresh_method": refresh_method,
                        "error": None,
                    }
                )
            except Exception as exc:
                await db.rollback()
                results.append(
                    {
                        "view_name": view_name,
                        "success": False,
                        "duration_seconds": round(time.time() - view_start, 2),
                        "row_count": 0,
                        "refresh_method": None,
                        "error": str(exc),
                    }
                )
                logger.error(
                    f"[LegacyMV] Failed to refresh {view_name}: {exc}",
                    exc_info=True,
                )

        success_count = sum(1 for item in results if item["success"])
        failed_count = len(results) - success_count
        return success_response(
            data={
                "results": results,
                "total_duration_seconds": round(time.time() - start_time, 2),
                "total_views": len(results),
                "success_count": success_count,
                "failed_count": failed_count,
            },
            message=(
                f"物化视图刷新完成: 成功 {success_count}/{len(results)} 个视图"
            ),
        )
    except Exception as exc:
        logger.error("[LegacyMV] Refresh flow failed", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="物化视图刷新失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(exc),
            recovery_suggestion="请检查数据库连接和物化视图定义",
            status_code=500,
        )


@router.get("/status", deprecated=True)
async def get_all_mv_status(db: AsyncSession = Depends(get_async_db)):
    logger.warning("[LegacyMV] /api/mv/status is deprecated and kept for compatibility only")
    try:
        result = await db.execute(
            text(
                """
                SELECT
                    matviewname AS view_name,
                    pg_size_pretty(pg_total_relation_size('public.' || matviewname)) AS size
                FROM pg_matviews
                WHERE schemaname = 'public'
                ORDER BY matviewname
                """
            )
        )

        views: list[dict[str, Any]] = []
        for row in result:
            view_name = row[0]
            size = row[1]

            try:
                row_count = await _count_rows(db, view_name)
            except Exception:
                row_count = 0

            last_refresh, duration_seconds, age_minutes = await _fetch_refresh_log(
                db, view_name
            )

            views.append(
                {
                    "view_name": view_name,
                    "row_count": row_count,
                    "size": size,
                    "last_refresh": last_refresh,
                    "duration_seconds": duration_seconds,
                    "age_minutes": age_minutes,
                    "is_stale": age_minutes is None or age_minutes > 60,
                }
            )

        return success_response(
            data={"views": views},
            message=f"获取到 {len(views)} 个物化视图状态",
        )
    except Exception as exc:
        logger.error("[LegacyMV] Failed to query view status", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取物化视图状态失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(exc),
            recovery_suggestion="请检查数据库连接",
            status_code=500,
        )
