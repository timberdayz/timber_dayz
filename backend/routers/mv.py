"""
物化视图管理API - 西虹ERP系统
v4.12.0修复：添加物化视图刷新API端点
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import List, Dict, Any, Optional
import time
from datetime import datetime

from backend.models.database import get_db, get_async_db
from backend.utils.api_response import success_response, error_response
from backend.utils.error_codes import ErrorCode, get_error_type
from modules.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/mv", tags=["物化视图管理"])


@router.post("/refresh-all")
async def refresh_all_materialized_views(db: AsyncSession = Depends(get_async_db)):
    """
    刷新所有物化视图
    
    v4.12.0修复：添加物化视图刷新API端点
    前端调用：POST /api/mv/refresh-all
    
    Returns:
        {
            "success": True,
            "results": [
                {
                    "view_name": "mv_product_management",
                    "success": True,
                    "duration_seconds": 1.23,
                    "row_count": 1000,
                    "error": null
                },
                ...
            ],
            "total_duration_seconds": 5.67,
            "total_views": 27,
            "success_count": 25,
            "failed_count": 2
        }
    """
    start_time = time.time()
    results = []
    
    try:
        # 1. 获取所有物化视图列表
        logger.info("[物化视图刷新] 开始获取物化视图列表...")
        mv_query = text("""
            SELECT matviewname 
            FROM pg_matviews 
            WHERE schemaname = 'public'
            ORDER BY matviewname
        """)
        mv_result = db.execute(mv_query)
        view_names = [row[0] for row in mv_result]
        
        logger.info(f"[物化视图刷新] 找到 {len(view_names)} 个物化视图")
        
        if not view_names:
            return success_response(
                data={
                    "results": [],
                    "total_duration_seconds": 0,
                    "total_views": 0,
                    "success_count": 0,
                    "failed_count": 0
                },
                message="没有找到物化视图"
            )
        
        # 2. 定义刷新顺序（主视图优先，辅助视图后刷新）
        # 主视图（Hub视图）- 直接从事实表查询
        main_views = [
            "mv_product_management",
            "mv_order_summary",
            "mv_inventory_by_sku",
            "mv_traffic_summary",
            "mv_financial_overview"
        ]
        
        # 辅助视图（Spoke视图）- 依赖主视图
        other_views = [v for v in view_names if v not in main_views]
        
        # 按顺序刷新：先主视图，后辅助视图
        refresh_order = main_views + sorted(other_views)
        
        # 3. 逐个刷新物化视图
        for view_name in refresh_order:
            if view_name not in view_names:
                logger.warning(f"[物化视图刷新] 跳过不存在的视图: {view_name}")
                continue
            
            view_start = time.time()
            try:
                logger.info(f"[物化视图刷新] 正在刷新: {view_name}...")
                
                # 尝试使用 CONCURRENTLY（需要唯一索引）
                # ⭐ 修复：CONCURRENTLY需要唯一索引，如果失败则使用普通刷新
                refresh_method = None
                try:
                    refresh_sql = text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view_name}")
                    await db.execute(refresh_sql)
                    await db.commit()
                    refresh_method = "CONCURRENTLY"
                except Exception as concurrent_error:
                    # 如果CONCURRENTLY失败（可能没有唯一索引），使用普通刷新
                    logger.warning(f"[物化视图刷新] {view_name} CONCURRENTLY失败，使用普通刷新: {concurrent_error}")
                    try:
                        await db.rollback()
                        refresh_sql = text(f"REFRESH MATERIALIZED VIEW {view_name}")
                        await db.execute(refresh_sql)
                        await db.commit()
                        refresh_method = "NORMAL"
                    except Exception as normal_error:
                        # 普通刷新也失败，抛出异常
                        raise normal_error
                
                # 获取行数
                count_sql = text(f"SELECT COUNT(*) FROM {view_name}")
                count_result = await db.execute(count_sql)
                row_count = count_result.scalar() or 0
                
                duration = time.time() - view_start
                
                results.append({
                    "view_name": view_name,
                    "success": True,
                    "duration_seconds": round(duration, 2),
                    "row_count": row_count,
                    "refresh_method": refresh_method,
                    "error": None
                })
                
                logger.info(f"[物化视图刷新] {view_name} 刷新成功 ({duration:.2f}秒, {row_count}行)")
                
            except Exception as e:
                await db.rollback()
                duration = time.time() - view_start
                error_msg = str(e)
                
                results.append({
                    "view_name": view_name,
                    "success": False,
                    "duration_seconds": round(duration, 2),
                    "row_count": 0,
                    "refresh_method": None,
                    "error": error_msg
                })
                
                logger.error(f"[物化视图刷新] {view_name} 刷新失败: {error_msg}", exc_info=True)
        
        # 4. 汇总结果
        total_duration = time.time() - start_time
        success_count = sum(1 for r in results if r["success"])
        failed_count = len(results) - success_count
        
        logger.info(f"[物化视图刷新] 刷新完成: 成功 {success_count}/{len(results)} 个视图，耗时 {total_duration:.2f}秒")
        
        return success_response(
            data={
                "results": results,
                "total_duration_seconds": round(total_duration, 2),
                "total_views": len(results),
                "success_count": success_count,
                "failed_count": failed_count
            },
            message=f"物化视图刷新完成：成功 {success_count}/{len(results)} 个视图"
        )
        
    except Exception as e:
        logger.error(f"[物化视图刷新] 刷新过程失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="物化视图刷新失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和物化视图定义，或联系系统管理员",
            status_code=500
        )


@router.get("/status")
async def get_all_mv_status(db: AsyncSession = Depends(get_async_db)):
    """
    获取所有物化视图状态
    
    Returns:
        {
            "success": True,
            "views": [
                {
                    "view_name": "mv_product_management",
                    "row_count": 1000,
                    "last_refresh": "2025-12-02T10:30:00Z",
                    "duration_seconds": 1.23,
                    "age_minutes": 5,
                    "is_stale": false
                },
                ...
            ]
        }
    """
    try:
        # 查询所有物化视图及其状态
        status_query = text("""
            SELECT 
                matviewname as view_name,
                pg_size_pretty(pg_total_relation_size('public.' || matviewname)) as size
            FROM pg_matviews 
            WHERE schemaname = 'public'
            ORDER BY matviewname
        """)
        status_result = db.execute(status_query)
        
        views = []
        for row in status_result:
            view_name = row[0]
            size = row[1]
            
            # 获取行数
            try:
                count_sql = text(f"SELECT COUNT(*) FROM {view_name}")
                count_result = db.execute(count_sql)
                row_count = count_result.scalar() or 0
            except:
                row_count = 0
            
            # 获取最后刷新时间（从刷新日志表）
            try:
                from modules.core.db import MaterializedViewRefreshLog
                result = await db.execute(
                    select(MaterializedViewRefreshLog).where(
                        MaterializedViewRefreshLog.view_name == view_name
                    ).order_by(MaterializedViewRefreshLog.refresh_completed_at.desc())
                )
                last_refresh_log = result.scalar_one_or_none()
                
                if last_refresh_log:
                    last_refresh = last_refresh_log.refresh_completed_at
                    duration_seconds = last_refresh_log.duration_seconds
                    age_minutes = (datetime.now() - last_refresh).total_seconds() / 60 if last_refresh else None
                else:
                    last_refresh = None
                    duration_seconds = None
                    age_minutes = None
            except:
                last_refresh = None
                duration_seconds = None
                age_minutes = None
            
            views.append({
                "view_name": view_name,
                "row_count": row_count,
                "size": size,
                "last_refresh": last_refresh.isoformat() if last_refresh else None,
                "duration_seconds": duration_seconds,
                "age_minutes": round(age_minutes, 2) if age_minutes else None,
                "is_stale": age_minutes > 60 if age_minutes else True  # 超过1小时认为过期
            })
        
        return success_response(
            data={"views": views},
            message=f"获取到 {len(views)} 个物化视图状态"
        )
        
    except Exception as e:
        logger.error(f"[物化视图状态] 获取状态失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取物化视图状态失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接，或联系系统管理员",
            status_code=500
        )

