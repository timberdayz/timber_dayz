#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Data governance and maintenance routes kept under the historical auto-ingest
module path.

The legacy runtime auto-ingest endpoints were retired. Only governance
statistics and development cleanup helpers remain here.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import get_async_db
from backend.schemas.auto_ingest import ClearDataRequest
from backend.services.governance_stats import get_governance_stats
from backend.utils.api_response import error_response, success_response
from backend.utils.error_codes import ErrorCode, get_error_type
from modules.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("/governance/overview")
async def get_governance_overview(
    platform: Optional[str] = Query(None, description="平台代码"),
    db: AsyncSession = Depends(get_async_db),
):
    """Return governance overview statistics for pending files and templates."""
    try:
        stats_service = get_governance_stats(db)
        overview = await stats_service.get_overview(platform)
        return success_response(data=overview)
    except Exception as exc:
        logger.error(f"[API] 获取治理概览失败: {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取治理概览失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(exc),
            status_code=500,
        )


@router.get("/governance/missing-templates")
async def get_missing_templates(
    platform: Optional[str] = Query(None, description="平台代码"),
    db: AsyncSession = Depends(get_async_db),
):
    """Return missing template combinations for the current catalog."""
    try:
        stats_service = get_governance_stats(db)
        missing = await stats_service.get_missing_templates(platform)
        return success_response(data=missing)
    except Exception as exc:
        logger.error(f"[API] 获取缺少模板清单失败: {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取缺少模板清单失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(exc),
            recovery_suggestion="请检查数据库连接和查询参数,或联系系统管理员",
            status_code=500,
        )


@router.get("/governance/pending-files")
async def get_pending_files(
    platform: Optional[str] = Query(None, description="平台代码"),
    data_domain: Optional[str] = Query(None, description="数据域"),
    granularity: Optional[str] = Query(None, description="粒度"),
    since_hours: Optional[int] = Query(None, description="最近N小时"),
    limit: int = Query(100, description="返回数量限制", ge=1, le=1000),
    group_by_batch: bool = Query(False, description="是否按数据域+粒度分组统计"),
    db: AsyncSession = Depends(get_async_db),
):
    """Return pending catalog files or grouped pending batches."""
    try:
        stats_service = get_governance_stats(db)
        files = await stats_service.get_pending_files(
            platform=platform,
            data_domain=data_domain,
            granularity=granularity,
            since_hours=since_hours,
            limit=limit,
        )

        if group_by_batch:
            batches = defaultdict(
                lambda: {"domain": "", "granularity": "", "file_count": 0, "files": []}
            )
            for file_info in files:
                domain = file_info.get("domain", "unknown")
                granularity_value = file_info.get("granularity", "unknown")
                batch_key = f"{domain}_{granularity_value}"
                batches[batch_key]["domain"] = domain
                batches[batch_key]["granularity"] = granularity_value
                batches[batch_key]["file_count"] += 1
                batches[batch_key]["files"].append(file_info)

            batch_list = list(batches.values())
            return {
                "success": True,
                "data": {
                    "batches": batch_list,
                    "total_files": len(files),
                    "batch_count": len(batch_list),
                },
            }

        return {"success": True, "data": files}
    except Exception as exc:
        logger.error(f"[API] 获取待入库文件失败: {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取待入库文件失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(exc),
            recovery_suggestion="请检查数据库连接和查询参数,或联系系统管理员",
            status_code=500,
        )


@router.post("/database/clear-all-data")
async def clear_all_data(
    request: ClearDataRequest,
    db: AsyncSession = Depends(get_async_db),
):
    """
    Development-only cleanup helper for clearing legacy business tables and
    resetting catalog file states.
    """
    if not request.confirm:
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message="必须显式确认:请传递 confirm=true 参数",
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            recovery_suggestion="请设置 confirm=true 以确认执行清理操作",
            status_code=400,
        )

    try:
        from sqlalchemy import text
        from backend.models.database import engine

        fact_tables = [
            "fact_orders",
            "fact_order_items",
            "fact_order_amounts",
            "fact_product_metrics",
            "fact_expenses_month",
            "fact_expenses_allocated_day_shop_sku",
        ]
        staging_tables = ["staging_orders", "staging_product_metrics"]
        quarantine_tables = ["data_quarantine"]

        cleared_counts: dict[str, int | str] = {}
        total_cleared = 0

        async def safe_truncate_table(table_name: str, use_cascade: bool = True) -> int:
            try:
                exists_result = await db.execute(
                    text(
                        """
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables
                            WHERE table_schema = 'public'
                              AND table_name = :table_name
                        )
                        """
                    ),
                    {"table_name": table_name},
                )
                if not exists_result.scalar():
                    logger.info(f"[DB Cleanup] 表 {table_name} 不存在,跳过")
                    cleared_counts[table_name] = 0
                    return 0

                count_result = await db.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                count_before = count_result.scalar() or 0
                if count_before > 0:
                    await db.execute(text("SAVEPOINT cleanup_table"))
                    try:
                        if use_cascade:
                            await db.execute(
                                text(f"TRUNCATE TABLE {table_name} RESTART IDENTITY CASCADE")
                            )
                        else:
                            await db.execute(text(f"TRUNCATE TABLE {table_name} RESTART IDENTITY"))
                        await db.execute(text("RELEASE SAVEPOINT cleanup_table"))
                    except Exception:
                        await db.execute(text("ROLLBACK TO SAVEPOINT cleanup_table"))
                        raise

                cleared_counts[table_name] = count_before
                return count_before
            except Exception as exc:
                logger.warning(f"[DB Cleanup] 清理表 {table_name} 失败: {exc}")
                cleared_counts[table_name] = cleared_counts.get(table_name, 0)
                return 0

        for table in fact_tables:
            total_cleared += await safe_truncate_table(table, use_cascade=True)
        for table in staging_tables:
            total_cleared += await safe_truncate_table(table, use_cascade=True)
        for table in quarantine_tables:
            total_cleared += await safe_truncate_table(table, use_cascade=False)

        try:
            result = await db.execute(
                text(
                    """
                    SELECT COUNT(*) FROM catalog_files
                    WHERE status != 'pending' OR status IS NULL
                    """
                )
            )
            reset_count = result.scalar() or 0
            cleared_counts["catalog_files_reset"] = reset_count
            if reset_count > 0:
                await db.execute(
                    text(
                        """
                        UPDATE catalog_files
                        SET status = 'pending',
                            last_processed_at = NULL
                        WHERE status != 'pending' OR status IS NULL
                        """
                    )
                )
                total_cleared += reset_count
                logger.info(f"[DB Cleanup] 重置了 {reset_count} 个 catalog_files 状态为 pending")
        except Exception as exc:
            logger.warning(f"[DB Cleanup] 重置 catalog_files 状态失败: {exc}")
            cleared_counts["catalog_files_reset"] = cleared_counts.get("catalog_files_reset", 0)

        await db.commit()

        try:
            with engine.connect() as conn:
                conn = conn.execution_options(isolation_level="AUTOCOMMIT")
                conn.execute(text("REFRESH MATERIALIZED VIEW mv_product_management"))
                conn.execute(text("REFRESH MATERIALIZED VIEW mv_product_sales_trend"))
                conn.execute(text("REFRESH MATERIALIZED VIEW mv_top_products"))
            cleared_counts["materialized_views"] = "refreshed"
        except Exception as exc:
            logger.warning(f"[DB Cleanup] 刷新物化视图失败: {exc}")
            cleared_counts["materialized_views"] = "failed"

        if total_cleared == 0:
            message = "数据库已为空,无需清理"
            logger.info("[DB Cleanup] 数据库已为空,无需清理")
        else:
            message = f"数据库清理完成,共清理 {total_cleared} 行数据"
            logger.info(f"[DB Cleanup] 数据库清理完成,共清理 {total_cleared} 行数据")

        return success_response(
            data={"rows_cleared": total_cleared, "details": cleared_counts},
            message=message,
        )
    except Exception as exc:
        await db.rollback()
        logger.error(f"[DB Cleanup] 数据库清理失败: {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="数据库清理失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(exc),
            recovery_suggestion="请检查数据库连接和权限,或联系系统管理员",
            status_code=500,
        )
