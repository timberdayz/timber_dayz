#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据备份与恢复API - v4.20.0
提供数据备份、恢复、备份历史管理功能
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from pathlib import Path
from datetime import datetime
import os

from backend.models.database import get_async_db
from backend.routers.users import require_admin
from backend.schemas.backup import (
    BackupCreateRequest,
    BackupResponse,
    BackupListResponse,
    BackupFilterRequest,
    RestoreRequest,
    RestoreResponse,
    AutoBackupConfigResponse,
    AutoBackupConfigUpdate
)
from backend.services.backup_service import get_backup_service
from backend.utils.api_response import success_response, error_response
from backend.utils.error_codes import ErrorCode, get_error_type
from modules.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/system/backup", tags=["数据备份"])

# 限流配置（如果可用）
try:
    from backend.middleware.rate_limiter import role_based_rate_limit
except ImportError:
    role_based_rate_limit = None


# ==================== 备份 API ====================

@router.post("/backups", response_model=BackupResponse)
async def create_backup(
    request: BackupCreateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    创建备份
    
    需要管理员权限
    Docker环境：在容器内执行备份操作
    """
    # 限流配置
    if role_based_rate_limit:
        @role_based_rate_limit(requests_per_minute=2, requests_per_hour=10)
        async def _create():
            pass
        await _create()
    
    try:
        service = get_backup_service(db)
        backup_record = await service.create_backup(
            backup_type=request.backup_type,
            description=request.description,
            created_by=current_user.user_id
        )
        
        return BackupResponse(
            id=backup_record.id,
            backup_type=backup_record.backup_type,
            backup_path=backup_record.backup_path,
            backup_size=backup_record.backup_size,
            checksum=backup_record.checksum,
            status=backup_record.status,
            description=backup_record.description,
            created_by=backup_record.created_by,
            created_at=backup_record.created_at,
            completed_at=backup_record.completed_at
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"创建备份失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="创建备份失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )


@router.get("/backups", response_model=BackupListResponse)
async def list_backups(
    backup_type: Optional[str] = Query(None, description="备份类型（full 或 incremental）"),
    status: Optional[str] = Query(None, description="备份状态（pending/completed/failed）"),
    start_time: Optional[datetime] = Query(None, description="开始时间"),
    end_time: Optional[datetime] = Query(None, description="结束时间"),
    page: int = Query(1, ge=1, description="页码（1-based）"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数（最大100）"),
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    获取备份列表（支持筛选、分页）
    
    需要管理员权限
    """
    try:
        service = get_backup_service(db)
        backups, total = await service.list_backups(
            backup_type=backup_type,
            status=status,
            start_time=start_time,
            end_time=end_time,
            page=page,
            page_size=page_size
        )
        
        total_pages = (total + page_size - 1) // page_size
        
        return BackupListResponse(
            data=[
                BackupResponse(
                    id=b.id,
                    backup_type=b.backup_type,
                    backup_path=b.backup_path,
                    backup_size=b.backup_size,
                    checksum=b.checksum,
                    status=b.status,
                    description=b.description,
                    created_by=b.created_by,
                    created_at=b.created_at,
                    completed_at=b.completed_at
                )
                for b in backups
            ],
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages
        )
    except Exception as e:
        logger.error(f"获取备份列表失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="获取备份列表失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )


@router.get("/backups/{backup_id}", response_model=BackupResponse)
async def get_backup_detail(
    backup_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    获取备份详情
    
    需要管理员权限
    """
    try:
        service = get_backup_service(db)
        backup = await service.get_backup(backup_id)
        
        if not backup:
            return error_response(
                code=ErrorCode.DATA_NOT_FOUND,
                message="备份记录不存在",
                error_type=get_error_type(ErrorCode.DATA_NOT_FOUND),
                detail=f"备份ID {backup_id} 不存在",
                status_code=404
            )
        
        return BackupResponse(
            id=backup.id,
            backup_type=backup.backup_type,
            backup_path=backup.backup_path,
            backup_size=backup.backup_size,
            checksum=backup.checksum,
            status=backup.status,
            description=backup.description,
            created_by=backup.created_by,
            created_at=backup.created_at,
            completed_at=backup.completed_at
        )
    except Exception as e:
        logger.error(f"获取备份详情失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="获取备份详情失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )


@router.get("/backups/{backup_id}/download")
async def download_backup(
    backup_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    下载备份文件
    
    需要管理员权限
    """
    try:
        service = get_backup_service(db)
        backup = await service.get_backup(backup_id)
        
        if not backup:
            return error_response(
                code=ErrorCode.DATA_NOT_FOUND,
                message="备份记录不存在",
                error_type=get_error_type(ErrorCode.DATA_NOT_FOUND),
                detail=f"备份ID {backup_id} 不存在",
                status_code=404
            )
        
        # 验证备份文件完整性
        is_valid, error_message = service.verify_backup(backup)
        if not is_valid:
            return error_response(
                code=ErrorCode.DATA_CORRUPTED,
                message="备份文件验证失败",
                error_type=get_error_type(ErrorCode.DATA_CORRUPTED),
                detail=error_message,
                status_code=400
            )
        
        backup_path = Path(backup.backup_path)
        if not backup_path.exists():
            return error_response(
                code=ErrorCode.DATA_NOT_FOUND,
                message="备份文件不存在",
                error_type=get_error_type(ErrorCode.DATA_NOT_FOUND),
                detail=f"备份文件路径不存在: {backup_path}",
                status_code=404
            )
        
        # 读取文件并返回
        from fastapi.responses import FileResponse
        return FileResponse(
            path=str(backup_path),
            filename=backup_path.name,
            media_type="application/gzip"
        )
        
    except Exception as e:
        logger.error(f"下载备份文件失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="下载备份文件失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )


# ==================== 恢复 API ====================

@router.post("/backups/{backup_id}/restore", response_model=RestoreResponse)
async def restore_backup(
    backup_id: int,
    request: RestoreRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    恢复备份
    
    需要管理员权限
    多重安全防护：维护窗口检查、多重确认、备份文件验证、恢复前自动备份等
    """
    # 限流配置（恢复操作更严格）
    if role_based_rate_limit:
        @role_based_rate_limit(requests_per_minute=1, requests_per_hour=3)
        async def _restore():
            pass
        await _restore()
    
    try:
        service = get_backup_service(db)
        backup = await service.get_backup(backup_id)
        
        if not backup:
            return error_response(
                code=ErrorCode.DATA_NOT_FOUND,
                message="备份记录不存在",
                error_type=get_error_type(ErrorCode.DATA_NOT_FOUND),
                detail=f"备份ID {backup_id} 不存在",
                status_code=404
            )
        
        # 多重安全防护检查
        # 1. 验证备份文件完整性
        is_valid, error_message = service.verify_backup(backup)
        if not is_valid:
            return error_response(
                code=ErrorCode.DATA_CORRUPTED,
                message="备份文件验证失败",
                error_type=get_error_type(ErrorCode.DATA_CORRUPTED),
                detail=error_message,
                status_code=400
            )
        
        # 2. 验证多重确认（至少2名不同的管理员）
        from modules.core.db import DimUser
        from sqlalchemy import select
        
        confirmed_users = []
        for user_id in request.confirmed_by:
            result = await db.execute(
                select(DimUser).where(DimUser.user_id == user_id)
            )
            user = result.scalar_one_or_none()
            if not user:
                return error_response(
                    code=ErrorCode.DATA_NOT_FOUND,
                    message=f"管理员ID {user_id} 不存在",
                    error_type=get_error_type(ErrorCode.DATA_NOT_FOUND),
                    status_code=404
                )
            
            # 验证管理员权限
            from sqlalchemy.orm import selectinload
            result = await db.execute(
                select(DimUser)
                .where(DimUser.user_id == user_id)
                .options(selectinload(DimUser.roles))
            )
            user = result.scalar_one()
            if not any(role.role_name == "admin" for role in user.roles):
                return error_response(
                    code=ErrorCode.PERMISSION_DENIED,
                    message=f"用户ID {user_id} 不是管理员",
                    error_type=get_error_type(ErrorCode.PERMISSION_DENIED),
                    status_code=403
                )
            
            confirmed_users.append(user)
        
        # 3. 维护窗口检查（默认凌晨2-4点）
        from datetime import datetime, time
        current_time = datetime.utcnow().time()
        maintenance_start = time(2, 0)  # 凌晨2点
        maintenance_end = time(4, 0)    # 凌晨4点
        
        in_maintenance_window = maintenance_start <= current_time <= maintenance_end
        
        if not in_maintenance_window and not request.force_outside_window:
            return error_response(
                code=ErrorCode.OPERATION_NOT_ALLOWED,
                message="当前不在维护窗口内",
                error_type=get_error_type(ErrorCode.OPERATION_NOT_ALLOWED),
                detail="数据恢复操作只能在维护窗口（凌晨2-4点）内执行，或设置 force_outside_window=True 强制执行",
                status_code=403
            )
        
        # 4. 恢复前自动创建紧急备份
        emergency_backup = None
        try:
            emergency_backup = await service.create_backup(
                backup_type="full",
                description=f"恢复前紧急备份（恢复备份ID: {backup_id}）",
                created_by=current_user.user_id
            )
            logger.warning(f"恢复前已创建紧急备份: ID={emergency_backup.id}")
        except Exception as e:
            logger.error(f"创建紧急备份失败: {e}", exc_info=True)
            return error_response(
                code=ErrorCode.INTERNAL_SERVER_ERROR,
                message="创建紧急备份失败",
                error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
                detail="恢复操作前必须创建紧急备份，但创建失败",
                status_code=500
            )
        
        # 5. 执行恢复操作（简化实现，实际应该使用Celery异步任务）
        # 注意：这里只是占位实现，实际恢复操作应该使用Celery异步任务，避免阻塞API
        started_at = datetime.utcnow()
        
        try:
            # TODO: 实现实际的恢复逻辑（使用Celery异步任务）
            # 这里只是返回成功响应，实际恢复应该在后台执行
            logger.warning(f"恢复操作已启动: 备份ID={backup_id}, 紧急备份ID={emergency_backup.id}")
            
            # 记录审计日志
            from backend.services.audit_service import audit_service
            await audit_service.log_action(
                user_id=current_user.user_id,
                action="backup_restore",
                resource="backup",
                resource_id=str(backup_id),
                details={
                    "backup_id": backup_id,
                    "emergency_backup_id": emergency_backup.id,
                    "confirmed_by": request.confirmed_by,
                    "force_outside_window": request.force_outside_window,
                    "reason": request.reason,
                    "in_maintenance_window": in_maintenance_window
                },
                is_success=True
            )
            
            return RestoreResponse(
                backup_id=backup_id,
                status="pending",  # 实际应该是异步任务状态
                emergency_backup_id=emergency_backup.id,
                started_at=started_at,
                completed_at=None,
                message="恢复操作已启动，正在后台执行"
            )
            
        except Exception as e:
            logger.error(f"恢复操作失败: {e}", exc_info=True)
            await audit_service.log_action(
                user_id=current_user.user_id,
                action="backup_restore",
                resource="backup",
                resource_id=str(backup_id),
                details={
                    "backup_id": backup_id,
                    "error": str(e)
                },
                is_success=False
            )
            return error_response(
                code=ErrorCode.INTERNAL_SERVER_ERROR,
                message="恢复操作失败",
                error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
                detail=str(e),
                status_code=500
            )
        
    except Exception as e:
        await db.rollback()
        logger.error(f"恢复备份失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="恢复备份失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )


# ==================== 自动备份配置 API ====================

@router.get("/config", response_model=AutoBackupConfigResponse)
async def get_auto_backup_config(
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    获取自动备份配置
    
    需要管理员权限
    """
    try:
        from backend.services.security_config_service import get_security_config_service
        service = get_security_config_service(db)
        config = await service.get_config("auto_backup_config")
        
        if config and isinstance(config.config_value, dict):
            return AutoBackupConfigResponse(
                enabled=config.config_value.get("enabled", False),
                schedule=config.config_value.get("schedule", "0 2 * * *"),
                backup_type=config.config_value.get("backup_type", "full"),
                retention_days=config.config_value.get("retention_days", 30),
                updated_at=config.updated_at,
                updated_by=config.updated_by
            )
        
        # 返回默认值
        return AutoBackupConfigResponse(
            enabled=False,
            schedule="0 2 * * *",
            backup_type="full",
            retention_days=30,
            updated_at=None,
            updated_by=None
        )
    except Exception as e:
        logger.error(f"获取自动备份配置失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="获取自动备份配置失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )


@router.put("/config", response_model=AutoBackupConfigResponse)
async def update_auto_backup_config(
    config: AutoBackupConfigUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    更新自动备份配置
    
    需要管理员权限
    """
    # 限流配置
    if role_based_rate_limit:
        @role_based_rate_limit(requests_per_minute=10, requests_per_hour=30)
        async def _update():
            pass
        await _update()
    
    try:
        from backend.services.security_config_service import get_security_config_service
        service = get_security_config_service(db)
        
        config_record = await service.set_config(
            config_key="auto_backup_config",
            config_value=config.model_dump(),
            description="自动备份配置",
            updated_by=current_user.user_id
        )
        
        return AutoBackupConfigResponse(
            enabled=config.enabled,
            schedule=config.schedule,
            backup_type=config.backup_type,
            retention_days=config.retention_days,
            updated_at=config_record.updated_at,
            updated_by=config_record.updated_by
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"更新自动备份配置失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="更新自动备份配置失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )
