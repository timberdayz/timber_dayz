#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
系统日志API - v4.20.0
提供系统日志查看、筛选、导出功能
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, delete
from sqlalchemy.orm import selectinload
from typing import Optional, List
from datetime import datetime
from pathlib import Path
import io
import csv

from backend.models.database import get_async_db
from backend.routers.users import require_admin
from backend.schemas.system import (
    SystemLogResponse,
    SystemLogListResponse,
    SystemLogFilterRequest,
    SystemLogExportRequest
)
from modules.core.db import SystemLog, DimUser
from backend.utils.api_response import success_response, pagination_response, error_response
from backend.utils.error_codes import ErrorCode, get_error_type
from modules.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/system/logs", tags=["系统日志"])

# 限流配置（如果可用）
try:
    from backend.middleware.rate_limiter import role_based_rate_limit
except ImportError:
    role_based_rate_limit = None


@router.get("", response_model=SystemLogListResponse)
async def get_system_logs(
    level: Optional[str] = Query(None, description="日志级别（ERROR, WARN, INFO, DEBUG）"),
    module: Optional[str] = Query(None, description="模块名称（支持模糊匹配）"),
    user_id: Optional[int] = Query(None, description="用户ID"),
    start_time: Optional[datetime] = Query(None, description="开始时间"),
    end_time: Optional[datetime] = Query(None, description="结束时间"),
    page: int = Query(1, ge=1, description="页码（1-based）"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数（最大100）"),
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    获取系统日志列表（分页、筛选）
    
    需要管理员权限
    """
    try:
        # 构建查询条件
        conditions = []
        
        if level:
            conditions.append(SystemLog.level == level.upper())
        
        if module:
            conditions.append(SystemLog.module.ilike(f"%{module}%"))
        
        if user_id:
            conditions.append(SystemLog.user_id == user_id)
        
        if start_time:
            conditions.append(SystemLog.created_at >= start_time)
        
        if end_time:
            conditions.append(SystemLog.created_at <= end_time)
        
        # 查询总数
        count_query = select(func.count(SystemLog.id))
        if conditions:
            count_query = count_query.where(and_(*conditions))
        
        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0
        
        # 查询数据
        query = select(SystemLog).order_by(SystemLog.created_at.desc())
        if conditions:
            query = query.where(and_(*conditions))
        
        # 分页
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)
        
        result = await db.execute(query)
        logs = result.scalars().all()
        
        # 转换为响应模型
        log_responses = [SystemLogResponse.model_validate(log) for log in logs]
        
        # 计算分页信息
        total_pages = (total + page_size - 1) // page_size
        
        pagination = {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "has_previous": page > 1,
            "has_next": page < total_pages
        }
        
        return SystemLogListResponse(
            success=True,
            data=log_responses,
            pagination=pagination,
            timestamp=datetime.now()
        )
        
    except Exception as e:
        logger.error(f"获取系统日志列表失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="获取系统日志列表失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )


@router.get("/{log_id}", response_model=SystemLogResponse)
async def get_system_log_detail(
    log_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    获取系统日志详情
    
    需要管理员权限
    """
    try:
        result = await db.execute(
            select(SystemLog).where(SystemLog.id == log_id)
        )
        log = result.scalar_one_or_none()
        
        if not log:
            return error_response(
                code=ErrorCode.DATA_NOT_FOUND,
                message="日志不存在",
                error_type=get_error_type(ErrorCode.DATA_NOT_FOUND),
                detail=f"日志ID {log_id} 不存在",
                status_code=404
            )
        
        return SystemLogResponse.model_validate(log)
        
    except Exception as e:
        logger.error(f"获取系统日志详情失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="获取系统日志详情失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )


@router.post("/export")
async def export_system_logs(
    request: SystemLogExportRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    导出系统日志（Excel/CSV格式）
    
    需要管理员权限
    限流：防止大量导出导致性能问题
    """
    # 限流配置
    if role_based_rate_limit:
        @role_based_rate_limit(requests_per_minute=5, requests_per_hour=20)
        async def _export():
            pass
        await _export()
    
    try:
        # 构建查询条件
        conditions = []
        
        if request.level:
            conditions.append(SystemLog.level == request.level.upper())
        
        if request.module:
            conditions.append(SystemLog.module.ilike(f"%{request.module}%"))
        
        if request.user_id:
            conditions.append(SystemLog.user_id == request.user_id)
        
        if request.start_time:
            conditions.append(SystemLog.created_at >= request.start_time)
        
        if request.end_time:
            conditions.append(SystemLog.created_at <= request.end_time)
        
        # 查询数据（限制最大记录数）
        query = select(SystemLog).order_by(SystemLog.created_at.desc())
        if conditions:
            query = query.where(and_(*conditions))
        
        query = query.limit(request.max_records)
        
        result = await db.execute(query)
        logs = result.scalars().all()
        
        if not logs:
            return error_response(
                code=ErrorCode.DATA_NOT_FOUND,
                message="没有可导出的日志",
                error_type=get_error_type(ErrorCode.DATA_NOT_FOUND),
                detail="根据筛选条件未找到任何日志",
                status_code=404
            )
        
        # 导出为CSV或Excel
        if request.format == "csv":
            # CSV导出
            output = io.StringIO()
            writer = csv.writer(output)
            
            # 写入表头
            writer.writerow(["ID", "级别", "模块", "消息", "用户ID", "IP地址", "用户代理", "创建时间"])
            
            # 写入数据
            for log in logs:
                writer.writerow([
                    log.id,
                    log.level,
                    log.module,
                    log.message,
                    log.user_id or "",
                    log.ip_address or "",
                    log.user_agent or "",
                    log.created_at.isoformat() if log.created_at else ""
                ])
            
            from fastapi.responses import Response
            return Response(
                content=output.getvalue(),
                media_type="text/csv",
                headers={
                    "Content-Disposition": f"attachment; filename=system_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                }
            )
        else:
            # Excel导出（需要openpyxl）
            try:
                from openpyxl import Workbook
                from openpyxl.styles import Font, Alignment
                
                wb = Workbook()
                ws = wb.active
                ws.title = "系统日志"
                
                # 写入表头
                headers = ["ID", "级别", "模块", "消息", "用户ID", "IP地址", "用户代理", "创建时间"]
                ws.append(headers)
                
                # 设置表头样式
                for cell in ws[1]:
                    cell.font = Font(bold=True)
                    cell.alignment = Alignment(horizontal="center")
                
                # 写入数据
                for log in logs:
                    ws.append([
                        log.id,
                        log.level,
                        log.module,
                        log.message,
                        log.user_id or "",
                        log.ip_address or "",
                        log.user_agent or "",
                        log.created_at.isoformat() if log.created_at else ""
                    ])
                
                # 保存到内存
                output = io.BytesIO()
                wb.save(output)
                output.seek(0)
                
                from fastapi.responses import Response
                return Response(
                    content=output.getvalue(),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={
                        "Content-Disposition": f"attachment; filename=system_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                    }
                )
            except ImportError:
                # 如果没有openpyxl，降级为CSV
                logger.warning("openpyxl未安装，降级为CSV格式导出")
                return await export_system_logs(
                    SystemLogExportRequest(
                        **request.model_dump(),
                        format="csv"
                    ),
                    db,
                    current_user
                )
        
    except Exception as e:
        logger.error(f"导出系统日志失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="导出系统日志失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )


@router.delete("")
async def clear_system_logs(
    days: int = Query(30, ge=1, le=365, description="保留最近N天的日志（默认30天）"),
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    清空系统日志（可选，谨慎使用）
    
    只删除指定天数之前的日志，保留最近的日志
    需要管理员权限
    """
    try:
        from datetime import timedelta
        
        # 计算截止时间
        cutoff_time = datetime.utcnow() - timedelta(days=days)
        
        # 查询要删除的日志数量
        count_query = select(func.count(SystemLog.id)).where(
            SystemLog.created_at < cutoff_time
        )
        count_result = await db.execute(count_query)
        deleted_count = count_result.scalar() or 0
        
        if deleted_count == 0:
            return success_response(
                data={"deleted_count": 0},
                message=f"没有需要删除的日志（保留最近{days}天）"
            )
        
        # 删除日志（使用delete语句）
        delete_stmt = delete(SystemLog).where(
            SystemLog.created_at < cutoff_time
        )
        result = await db.execute(delete_stmt)
        await db.commit()
        
        logger.warning(f"管理员 {current_user.user_id} 清空了 {deleted_count} 条系统日志（保留最近{days}天）")
        
        return success_response(
            data={"deleted_count": deleted_count},
            message=f"已删除 {deleted_count} 条日志（保留最近{days}天）"
        )
        
    except Exception as e:
        await db.rollback()
        logger.error(f"清空系统日志失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="清空系统日志失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )
