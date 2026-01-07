#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
限流配置管理 API（Phase 3）

用途：
- 查询限流配置
- 更新限流配置
- 配置变更审计

v4.19.4 新增：Phase 3 数据库配置支持
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime

from backend.models.database import get_async_db
from backend.routers.auth import get_current_user
from backend.routers.users import require_admin
from modules.core.db import DimRateLimitConfig, FactRateLimitConfigAudit, DimUser
from modules.core.logger import get_logger
from backend.middleware.rate_limiter import refresh_rate_limit_config_cache

router = APIRouter(prefix="/api/rate-limit/config", tags=["限流配置管理"])
logger = get_logger(__name__)


# ==================== Pydantic 模型 ====================

class RateLimitConfigResponse(BaseModel):
    """限流配置响应模型"""
    config_id: int
    role_code: str
    endpoint_type: str
    limit_value: str
    is_active: bool
    description: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    updated_by: Optional[str] = None
    
    class Config:
        from_attributes = True


class RateLimitConfigCreate(BaseModel):
    """创建限流配置请求模型"""
    role_code: str = Field(..., description="角色代码（admin/manager/finance/operator/normal/anonymous）")
    endpoint_type: str = Field(..., description="端点类型（default/data_sync/auth）")
    limit_value: str = Field(..., description="限流值（如 '200/minute'）")
    description: Optional[str] = Field(None, description="配置说明")
    is_active: bool = Field(True, description="是否启用")


class RateLimitConfigUpdate(BaseModel):
    """更新限流配置请求模型"""
    limit_value: Optional[str] = Field(None, description="限流值（如 '200/minute'）")
    is_active: Optional[bool] = Field(None, description="是否启用")
    description: Optional[str] = Field(None, description="配置说明")


class RateLimitConfigListResponse(BaseModel):
    """限流配置列表响应模型"""
    total: int
    configs: List[RateLimitConfigResponse]


# ==================== API 端点 ====================

@router.get("/roles", response_model=RateLimitConfigListResponse)
async def list_rate_limit_configs(
    role_code: Optional[str] = None,
    endpoint_type: Optional[str] = None,
    is_active: Optional[bool] = None,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    查询限流配置列表
    
    权限：仅管理员
    """
    try:
        # 构建查询条件
        stmt = select(DimRateLimitConfig)
        conditions = []
        
        if role_code:
            conditions.append(DimRateLimitConfig.role_code == role_code)
        if endpoint_type:
            conditions.append(DimRateLimitConfig.endpoint_type == endpoint_type)
        if is_active is not None:
            conditions.append(DimRateLimitConfig.is_active == is_active)
        
        if conditions:
            for condition in conditions:
                stmt = stmt.where(condition)
        
        # 执行查询
        result = await db.execute(stmt)
        configs = result.scalars().all()
        
        return RateLimitConfigListResponse(
            total=len(configs),
            configs=[RateLimitConfigResponse.model_validate(config) for config in configs]
        )
        
    except Exception as e:
        logger.error(f"[RateLimitConfig] 查询限流配置列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.get("/roles/{role_code}", response_model=List[RateLimitConfigResponse])
async def get_rate_limit_config_by_role(
    role_code: str,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    查询指定角色的限流配置
    
    权限：仅管理员
    """
    try:
        stmt = select(DimRateLimitConfig).where(
            DimRateLimitConfig.role_code == role_code
        )
        result = await db.execute(stmt)
        configs = result.scalars().all()
        
        if not configs:
            raise HTTPException(status_code=404, detail=f"角色 {role_code} 的限流配置不存在")
        
        return [RateLimitConfigResponse.model_validate(config) for config in configs]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[RateLimitConfig] 查询角色限流配置失败: {e}")
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.post("/roles", response_model=RateLimitConfigResponse)
async def create_rate_limit_config(
    config: RateLimitConfigCreate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: DimUser = Depends(require_admin)
):
    """
    创建限流配置
    
    权限：仅管理员
    """
    try:
        # 检查是否已存在
        stmt = select(DimRateLimitConfig).where(
            DimRateLimitConfig.role_code == config.role_code,
            DimRateLimitConfig.endpoint_type == config.endpoint_type
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"角色 {config.role_code} 的 {config.endpoint_type} 端点配置已存在"
            )
        
        # 创建配置
        new_config = DimRateLimitConfig(
            role_code=config.role_code,
            endpoint_type=config.endpoint_type,
            limit_value=config.limit_value,
            description=config.description,
            is_active=config.is_active,
            created_by=current_user.username,
            updated_by=current_user.username
        )
        
        db.add(new_config)
        await db.commit()
        await db.refresh(new_config)
        
        # 记录审计日志
        await _create_audit_log(
            db=db,
            config_id=new_config.config_id,
            role_code=config.role_code,
            endpoint_type=config.endpoint_type,
            action_type="create",
            old_limit_value=None,
            new_limit_value=config.limit_value,
            old_is_active=None,
            new_is_active=config.is_active,
            operator_id=current_user.user_id,
            operator_username=current_user.username,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            is_success=True
        )
        
        # 刷新缓存
        await refresh_rate_limit_config_cache(db)
        
        logger.info(f"[RateLimitConfig] 创建限流配置: {config.role_code}/{config.endpoint_type} = {config.limit_value}")
        return RateLimitConfigResponse.model_validate(new_config)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[RateLimitConfig] 创建限流配置失败: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"创建失败: {str(e)}")


@router.put("/roles/{role_code}/{endpoint_type}", response_model=RateLimitConfigResponse)
async def update_rate_limit_config(
    role_code: str,
    endpoint_type: str,
    config_update: RateLimitConfigUpdate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: DimUser = Depends(require_admin)
):
    """
    更新限流配置
    
    权限：仅管理员
    """
    try:
        # 查询配置
        stmt = select(DimRateLimitConfig).where(
            DimRateLimitConfig.role_code == role_code,
            DimRateLimitConfig.endpoint_type == endpoint_type
        )
        result = await db.execute(stmt)
        config = result.scalar_one_or_none()
        
        if not config:
            raise HTTPException(
                status_code=404,
                detail=f"角色 {role_code} 的 {endpoint_type} 端点配置不存在"
            )
        
        # 保存旧值（用于审计）
        old_limit_value = config.limit_value
        old_is_active = config.is_active
        
        # 更新配置
        if config_update.limit_value is not None:
            config.limit_value = config_update.limit_value
        if config_update.is_active is not None:
            config.is_active = config_update.is_active
        if config_update.description is not None:
            config.description = config_update.description
        
        config.updated_by = current_user.username
        config.updated_at = datetime.utcnow()
        
        await db.commit()
        await db.refresh(config)
        
        # 记录审计日志
        await _create_audit_log(
            db=db,
            config_id=config.config_id,
            role_code=role_code,
            endpoint_type=endpoint_type,
            action_type="update",
            old_limit_value=old_limit_value,
            new_limit_value=config.limit_value,
            old_is_active=old_is_active,
            new_is_active=config.is_active,
            operator_id=current_user.user_id,
            operator_username=current_user.username,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            is_success=True
        )
        
        # 刷新缓存
        await refresh_rate_limit_config_cache(db)
        
        logger.info(f"[RateLimitConfig] 更新限流配置: {role_code}/{endpoint_type} = {config.limit_value}")
        return RateLimitConfigResponse.model_validate(config)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[RateLimitConfig] 更新限流配置失败: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"更新失败: {str(e)}")


@router.delete("/roles/{role_code}/{endpoint_type}")
async def delete_rate_limit_config(
    role_code: str,
    endpoint_type: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: DimUser = Depends(require_admin)
):
    """
    删除限流配置
    
    权限：仅管理员
    """
    try:
        # 查询配置
        stmt = select(DimRateLimitConfig).where(
            DimRateLimitConfig.role_code == role_code,
            DimRateLimitConfig.endpoint_type == endpoint_type
        )
        result = await db.execute(stmt)
        config = result.scalar_one_or_none()
        
        if not config:
            raise HTTPException(
                status_code=404,
                detail=f"角色 {role_code} 的 {endpoint_type} 端点配置不存在"
            )
        
        config_id = config.config_id
        old_limit_value = config.limit_value
        old_is_active = config.is_active
        
        # 删除配置
        await db.delete(config)
        await db.commit()
        
        # 记录审计日志
        await _create_audit_log(
            db=db,
            config_id=None,  # 已删除
            role_code=role_code,
            endpoint_type=endpoint_type,
            action_type="delete",
            old_limit_value=old_limit_value,
            new_limit_value=None,
            old_is_active=old_is_active,
            new_is_active=None,
            operator_id=current_user.user_id,
            operator_username=current_user.username,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            is_success=True
        )
        
        # 刷新缓存
        await refresh_rate_limit_config_cache(db)
        
        logger.info(f"[RateLimitConfig] 删除限流配置: {role_code}/{endpoint_type}")
        return {"message": "配置已删除"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[RateLimitConfig] 删除限流配置失败: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")


@router.post("/refresh-cache")
async def refresh_config_cache(
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    刷新限流配置缓存
    
    权限：仅管理员
    """
    try:
        await refresh_rate_limit_config_cache(db)
        return {"message": "缓存已刷新"}
    except Exception as e:
        logger.error(f"[RateLimitConfig] 刷新缓存失败: {e}")
        raise HTTPException(status_code=500, detail=f"刷新失败: {str(e)}")


# ==================== 辅助函数 ====================

async def _create_audit_log(
    db: AsyncSession,
    config_id: Optional[int],
    role_code: str,
    endpoint_type: str,
    action_type: str,
    old_limit_value: Optional[str],
    new_limit_value: Optional[str],
    old_is_active: Optional[bool],
    new_is_active: Optional[bool],
    operator_id: Optional[int],
    operator_username: str,
    ip_address: Optional[str],
    user_agent: Optional[str],
    is_success: bool,
    error_message: Optional[str] = None
):
    """
    创建审计日志
    
    Args:
        db: 数据库会话
        config_id: 配置ID（删除时为None）
        role_code: 角色代码
        endpoint_type: 端点类型
        action_type: 操作类型（create/update/delete）
        old_limit_value: 旧限流值
        new_limit_value: 新限流值
        old_is_active: 旧启用状态
        new_is_active: 新启用状态
        operator_id: 操作人ID
        operator_username: 操作人用户名
        ip_address: IP地址
        user_agent: User-Agent
        is_success: 是否成功
        error_message: 错误信息
    """
    try:
        audit_log = FactRateLimitConfigAudit(
            config_id=config_id,
            role_code=role_code,
            endpoint_type=endpoint_type,
            action_type=action_type,
            old_limit_value=old_limit_value,
            new_limit_value=new_limit_value,
            old_is_active=old_is_active,
            new_is_active=new_is_active,
            operator_id=operator_id,
            operator_username=operator_username,
            ip_address=ip_address,
            user_agent=user_agent,
            is_success=is_success,
            error_message=error_message
        )
        
        db.add(audit_log)
        await db.commit()
        
    except Exception as e:
        logger.error(f"[RateLimitConfig] 创建审计日志失败: {e}")
        # 审计日志失败不影响主操作，只记录错误

