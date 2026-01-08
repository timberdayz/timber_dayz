#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
系统配置API - v4.3.5 + v4.20.0
提供系统级配置和常量
v4.20.0新增：系统基础配置、数据库配置API
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models.database import get_async_db
from backend.routers.users import require_admin
from backend.utils.api_response import success_response, error_response
from backend.utils.error_codes import ErrorCode, get_error_type
from backend.schemas.system import (
    SystemConfigResponse,
    SystemConfigUpdate,
    DatabaseConfigResponse,
    DatabaseConfigUpdate,
    DatabaseConnectionTestRequest,
    DatabaseConnectionTestResponse
)
from backend.services.system_config_service import get_system_config_service
from modules.core.validators import VALID_PLATFORMS, VALID_DATA_DOMAINS, VALID_GRANULARITIES
from modules.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/system", tags=["系统配置"])

# 限流配置（如果可用）
try:
    from backend.middleware.rate_limiter import role_based_rate_limit
except ImportError:
    role_based_rate_limit = None


@router.get("/platforms")
async def get_platforms():
    """
    获取支持的平台列表（白名单）
    
    Returns:
        list: 平台列表
    """
    return success_response(data={"platforms": sorted(list(VALID_PLATFORMS))})


@router.get("/data-domains")
async def get_data_domains():
    """
    获取支持的数据域列表（白名单）
    
    Returns:
        list: 数据域列表
    """
    return success_response(data={"data_domains": sorted(list(VALID_DATA_DOMAINS))})


@router.get("/granularities")
async def get_granularities():
    """
    获取支持的粒度列表（白名单）
    
    Returns:
        list: 粒度列表
    """
    return success_response(data={"granularities": sorted(list(VALID_GRANULARITIES))})


@router.get("/constants")
async def get_all_constants():
    """
    获取所有系统常量（一次性获取）
    
    Returns:
        dict: 所有常量
    """
    data = {
        "platforms": sorted(list(VALID_PLATFORMS)),
        "data_domains": sorted(list(VALID_DATA_DOMAINS)),
        "granularities": sorted(list(VALID_GRANULARITIES))
    }
    
    return success_response(data=data)


# ==================== 系统基础配置 API ====================

@router.get("/config", response_model=SystemConfigResponse)
async def get_system_config(
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    获取系统基础配置
    
    需要管理员权限
    """
    try:
        service = get_system_config_service(db)
        config = await service.get_system_config()
        
        return SystemConfigResponse(
            system_name=config.get("system_name", "西虹ERP系统"),
            version=config.get("version", "v4.20.0"),
            timezone=config.get("timezone", "Asia/Shanghai"),
            language=config.get("language", "zh-CN"),
            currency=config.get("currency", "CNY"),
            updated_at=config.get("updated_at"),
            updated_by=config.get("updated_by")
        )
    except Exception as e:
        logger.error(f"获取系统配置失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="获取系统配置失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )


@router.put("/config", response_model=SystemConfigResponse)
async def update_system_config(
    config_update: SystemConfigUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    更新系统基础配置
    
    需要管理员权限
    """
    try:
        service = get_system_config_service(db)
        updated_config = await service.update_system_config(
            config_update.model_dump(exclude_unset=True),
            updated_by_user_id=current_user.user_id if hasattr(current_user, 'user_id') else None
        )
        
        return SystemConfigResponse(
            system_name=updated_config.get("system_name", "西虹ERP系统"),
            version=updated_config.get("version", "v4.20.0"),
            timezone=updated_config.get("timezone", "Asia/Shanghai"),
            language=updated_config.get("language", "zh-CN"),
            currency=updated_config.get("currency", "CNY"),
            updated_at=updated_config.get("updated_at"),
            updated_by=updated_config.get("updated_by")
        )
    except Exception as e:
        logger.error(f"更新系统配置失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="更新系统配置失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )


# ==================== 数据库配置 API ====================

@router.get("/database/config", response_model=DatabaseConfigResponse)
async def get_database_config(
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    获取数据库配置
    
    需要管理员权限
    """
    try:
        service = get_system_config_service(db)
        config = await service.get_database_config()
        
        return DatabaseConfigResponse(
            host=config.get("host", ""),
            port=config.get("port", 5432),
            database=config.get("database", ""),
            username=config.get("username", ""),
            password=config.get("password", "***"),  # 密码已隐藏
            connection_url=config.get("connection_url", ""),  # 修复：添加缺失的 connection_url 字段
            updated_at=config.get("updated_at"),
            updated_by=config.get("updated_by")
        )
    except Exception as e:
        logger.error(f"获取数据库配置失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="获取数据库配置失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )


@router.put("/database/config", response_model=DatabaseConfigResponse)
async def update_database_config(
    config_update: DatabaseConfigUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    更新数据库配置（保存为pending状态，需要手动应用）
    
    需要管理员权限
    """
    try:
        service = get_system_config_service(db)
        updated_config = await service.update_database_config(
            config_update.model_dump(exclude_unset=True),
            updated_by_user_id=current_user.user_id if hasattr(current_user, 'user_id') else None
        )
        
        return DatabaseConfigResponse(
            host=updated_config.get("host", ""),
            port=updated_config.get("port", 5432),
            database=updated_config.get("database", ""),
            username=updated_config.get("username", ""),
            password="***",  # 密码已隐藏
            connection_url=updated_config.get("connection_url", ""),  # 修复：添加缺失的 connection_url 字段
            updated_at=updated_config.get("updated_at"),
            updated_by=updated_config.get("updated_by")
        )
    except Exception as e:
        logger.error(f"更新数据库配置失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="更新数据库配置失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )


@router.post("/database/test-connection", response_model=DatabaseConnectionTestResponse)
async def test_database_connection(
    request: DatabaseConnectionTestRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    测试数据库连接
    
    需要管理员权限
    """
    try:
        service = get_system_config_service(db)
        is_success, error_message, response_time_ms = await service.test_database_connection(
            host=request.host,
            port=request.port,
            database=request.database,
            username=request.username,
            password=request.password
        )
        
        return DatabaseConnectionTestResponse(
            success=is_success,
            message=error_message or "连接成功",
            response_time_ms=response_time_ms
        )
    except Exception as e:
        logger.error(f"测试数据库连接失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="测试数据库连接失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )

