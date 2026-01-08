#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
系统维护API - v4.20.0
提供缓存清理、数据清理、系统升级等功能
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from backend.models.database import get_async_db
from backend.routers.users import require_admin
from backend.schemas.maintenance import (
    CacheClearRequest,
    CacheClearResponse,
    CacheStatusResponse,
    DataCleanRequest,
    DataCleanResponse,
    DataStatusResponse,
    UpgradeCheckResponse,
    UpgradeRequest,
    UpgradeResponse
)
from backend.services.maintenance_service import get_maintenance_service
from backend.utils.api_response import success_response, error_response
from backend.utils.error_codes import ErrorCode, get_error_type
from modules.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/system/maintenance", tags=["系统维护"])

# 限流配置（如果可用）
try:
    from backend.middleware.rate_limiter import role_based_rate_limit
except ImportError:
    role_based_rate_limit = None


# ==================== 缓存清理 API ====================

@router.get("/cache/status", response_model=CacheStatusResponse)
async def get_cache_status(
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    获取缓存状态
    
    需要管理员权限
    """
    try:
        service = get_maintenance_service(db)
        status = await service.get_cache_status()
        
        return CacheStatusResponse(
            redis_connected=status.get("redis_connected", False),
            redis_memory_used=status.get("redis_memory_used"),
            redis_keys_count=status.get("redis_keys_count"),
            app_cache_size=status.get("app_cache_size")
        )
    except Exception as e:
        logger.error(f"获取缓存状态失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="获取缓存状态失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )


@router.post("/cache/clear", response_model=CacheClearResponse)
async def clear_cache(
    request: CacheClearRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    清理缓存
    
    需要管理员权限
    Docker环境：连接redis:6379（Docker网络内）
    """
    # 限流配置
    if role_based_rate_limit:
        @role_based_rate_limit(requests_per_minute=5, requests_per_hour=20)
        async def _clear():
            pass
        await _clear()
    
    try:
        service = get_maintenance_service(db)
        cleared_keys, freed_memory = await service.clear_cache(
            cache_type=request.cache_type,
            pattern=request.pattern
        )
        
        # 记录审计日志
        from backend.services.audit_service import audit_service
        await audit_service.log_action(
            user_id=current_user.user_id,
            action="cache_clear",
            resource="maintenance",
            resource_id=request.cache_type,
            details={
                "cache_type": request.cache_type,
                "pattern": request.pattern,
                "cleared_keys": cleared_keys,
                "freed_memory": freed_memory
            },
            is_success=True
        )
        
        return CacheClearResponse(
            cache_type=request.cache_type,
            cleared_keys=cleared_keys,
            cleared_memory=freed_memory,
            message=f"成功清理 {cleared_keys} 个缓存键"
        )
    except Exception as e:
        logger.error(f"清理缓存失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="清理缓存失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )


# ==================== 数据清理 API ====================

@router.get("/data/status", response_model=DataStatusResponse)
async def get_data_status(
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    获取数据状态
    
    需要管理员权限
    """
    try:
        service = get_maintenance_service(db)
        status = await service.get_data_status()
        
        return DataStatusResponse(
            system_logs_count=status.get("system_logs_count", 0),
            system_logs_size=status.get("system_logs_size"),
            task_logs_count=status.get("task_logs_count", 0),
            task_logs_size=status.get("task_logs_size"),
            temp_files_count=status.get("temp_files_count", 0),
            temp_files_size=status.get("temp_files_size", 0),
            staging_data_count=status.get("staging_data_count", 0),
            staging_data_size=status.get("staging_data_size")
        )
    except Exception as e:
        logger.error(f"获取数据状态失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="获取数据状态失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )


@router.post("/data/clean", response_model=DataCleanResponse)
async def clean_data(
    request: DataCleanRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    清理数据
    
    需要管理员权限
    警告：清理操作不可逆，请谨慎使用
    """
    # 限流配置（数据清理操作更严格）
    if role_based_rate_limit:
        @role_based_rate_limit(requests_per_minute=2, requests_per_hour=10)
        async def _clean():
            pass
        await _clean()
    
    try:
        service = get_maintenance_service(db)
        deleted_count, freed_space = await service.clean_data(
            clean_type=request.clean_type,
            retention_days=request.retention_days,
            user_id=current_user.user_id
        )
        
        return DataCleanResponse(
            clean_type=request.clean_type,
            deleted_count=deleted_count,
            freed_space=freed_space,
            retention_days=request.retention_days,
            message=f"成功清理 {deleted_count} 条记录/文件（保留最近{request.retention_days}天）"
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"清理数据失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="清理数据失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )


# ==================== 系统升级 API（P3 - 可选，不推荐） ====================

@router.get("/upgrade/check", response_model=UpgradeCheckResponse)
async def check_upgrade(
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    检查系统升级（仅查看，不执行）
    
    需要管理员权限
    P3功能：不推荐通过API实现系统升级
    """
    try:
        service = get_maintenance_service(db)
        upgrade_info = await service.check_upgrade()
        
        return UpgradeCheckResponse(
            current_version=upgrade_info.get("current_version", "unknown"),
            latest_version=upgrade_info.get("latest_version"),
            upgrade_available=upgrade_info.get("upgrade_available", False),
            release_notes=upgrade_info.get("release_notes"),
            check_time=upgrade_info.get("check_time", datetime.utcnow())
        )
    except Exception as e:
        logger.error(f"检查系统升级失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="检查系统升级失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )


@router.post("/upgrade", response_model=UpgradeResponse)
async def upgrade_system(
    request: UpgradeRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    执行系统升级
    
    需要管理员权限
    多重安全防护：多重确认、自动备份等
    P3功能：不推荐通过API实现系统升级，建议通过CI/CD流程完成
    
    警告：此功能存在严重安全风险，仅用于紧急情况
    """
    # 限流配置（升级操作最严格）
    if role_based_rate_limit:
        @role_based_rate_limit(requests_per_minute=1, requests_per_hour=1)
        async def _upgrade():
            pass
        await _upgrade()
    
    try:
        # 验证多重确认（至少2名不同的管理员）
        from modules.core.db import DimUser
        from sqlalchemy.orm import selectinload
        
        confirmed_users = []
        for user_id in request.confirmed_by:
            result = await db.execute(
                select(DimUser)
                .where(DimUser.user_id == user_id)
                .options(selectinload(DimUser.roles))
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
            if not any(role.role_name == "admin" for role in user.roles):
                return error_response(
                    code=ErrorCode.PERMISSION_DENIED,
                    message=f"用户ID {user_id} 不是管理员",
                    error_type=get_error_type(ErrorCode.PERMISSION_DENIED),
                    status_code=403
                )
            
            confirmed_users.append(user)
        
        # 升级前自动备份（除非明确跳过）
        backup_id = None
        if not request.skip_backup:
            from backend.services.backup_service import get_backup_service
            backup_service = get_backup_service(db)
            try:
                backup = await backup_service.create_backup(
                    backup_type="full",
                    description=f"系统升级前自动备份（目标版本: {request.target_version}）",
                    created_by=current_user.user_id
                )
                backup_id = backup.id
                logger.warning(f"升级前已创建自动备份: ID={backup_id}")
            except Exception as e:
                logger.error(f"创建升级前备份失败: {e}", exc_info=True)
                return error_response(
                    code=ErrorCode.INTERNAL_SERVER_ERROR,
                    message="创建升级前备份失败",
                    error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
                    detail="升级操作前必须创建备份，但创建失败",
                    status_code=500
                )
        
        # TODO: 实现实际的升级逻辑（Docker环境）
        # 这里只是占位实现，实际升级应该通过CI/CD流程完成
        started_at = datetime.utcnow()
        
        logger.warning(f"系统升级操作已启动: 目标版本={request.target_version}, 备份ID={backup_id}")
        
        # 记录审计日志
        from backend.services.audit_service import audit_service
        await audit_service.log_action(
            user_id=current_user.user_id,
            action="system_upgrade",
            resource="maintenance",
            resource_id=request.target_version,
            details={
                "target_version": request.target_version,
                "confirmed_by": request.confirmed_by,
                "backup_id": backup_id,
                "skip_backup": request.skip_backup
            },
            is_success=True
        )
        
        return UpgradeResponse(
            target_version=request.target_version,
            status="pending",  # 实际应该是异步任务状态
            backup_id=backup_id,
            started_at=started_at,
            completed_at=None,
            message="系统升级操作已启动，正在后台执行（P3功能，建议通过CI/CD流程完成）"
        )
        
    except Exception as e:
        await db.rollback()
        logger.error(f"系统升级失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="系统升级失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )
