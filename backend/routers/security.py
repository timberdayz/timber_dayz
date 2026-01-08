#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
安全设置API - v4.20.0
提供密码策略、登录限制、会话管理、2FA等安全配置功能
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from backend.models.database import get_async_db
from backend.routers.users import require_admin
from backend.schemas.security import (
    PasswordPolicyResponse,
    PasswordPolicyUpdate,
    LoginRestrictionsResponse,
    LoginRestrictionsUpdate,
    IPWhitelistResponse,
    IPWhitelistUpdate,
    SessionConfigResponse,
    SessionConfigUpdate,
    TwoFactorConfigResponse,
    TwoFactorConfigUpdate
)
from backend.services.security_config_service import get_security_config_service
from backend.utils.api_response import success_response, error_response
from backend.utils.error_codes import ErrorCode, get_error_type
from modules.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/system/security", tags=["安全设置"])

# 限流配置（如果可用）
try:
    from backend.middleware.rate_limiter import role_based_rate_limit
except ImportError:
    role_based_rate_limit = None


# ==================== 密码策略 API ====================

@router.get("/password-policy", response_model=PasswordPolicyResponse)
async def get_password_policy(
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    获取密码策略
    
    需要管理员权限
    """
    try:
        service = get_security_config_service(db)
        policy = await service.get_password_policy()
        
        # 获取配置记录以获取更新时间等信息
        config = await service.get_config("password_policy")
        
        return PasswordPolicyResponse(
            min_length=policy.get("min_length", 8),
            require_uppercase=policy.get("require_uppercase", True),
            require_lowercase=policy.get("require_lowercase", True),
            require_digits=policy.get("require_digits", True),
            require_special_chars=policy.get("require_special_chars", False),
            max_age_days=policy.get("max_age_days", 90),
            prevent_reuse_count=policy.get("prevent_reuse_count", 5),
            updated_at=config.updated_at if config else None,
            updated_by=config.updated_by if config else None
        )
    except Exception as e:
        logger.error(f"获取密码策略失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="获取密码策略失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )


@router.put("/password-policy", response_model=PasswordPolicyResponse)
async def update_password_policy(
    policy: PasswordPolicyUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    更新密码策略
    
    需要管理员权限
    """
    # 限流配置
    if role_based_rate_limit:
        @role_based_rate_limit(requests_per_minute=10, requests_per_hour=30)
        async def _update():
            pass
        await _update()
    
    try:
        service = get_security_config_service(db)
        
        # 保存配置
        config = await service.set_password_policy(
            policy=policy.model_dump(),
            updated_by=current_user.user_id
        )
        
        # 返回更新后的配置
        updated_policy = await service.get_password_policy()
        
        return PasswordPolicyResponse(
            min_length=updated_policy.get("min_length", 8),
            require_uppercase=updated_policy.get("require_uppercase", True),
            require_lowercase=updated_policy.get("require_lowercase", True),
            require_digits=updated_policy.get("require_digits", True),
            require_special_chars=updated_policy.get("require_special_chars", False),
            max_age_days=updated_policy.get("max_age_days", 90),
            prevent_reuse_count=updated_policy.get("prevent_reuse_count", 5),
            updated_at=config.updated_at,
            updated_by=config.updated_by
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"更新密码策略失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="更新密码策略失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )


# ==================== 登录限制 API ====================

@router.get("/login-restrictions", response_model=LoginRestrictionsResponse)
async def get_login_restrictions(
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    获取登录限制配置
    
    需要管理员权限
    """
    try:
        service = get_security_config_service(db)
        restrictions = await service.get_login_restrictions()
        
        # 获取配置记录
        config = await service.get_config("login_restrictions")
        
        return LoginRestrictionsResponse(
            max_failed_attempts=restrictions.get("max_failed_attempts", 5),
            lockout_duration_minutes=restrictions.get("lockout_duration_minutes", 30),
            enable_ip_whitelist=restrictions.get("enable_ip_whitelist", False),
            updated_at=config.updated_at if config else None,
            updated_by=config.updated_by if config else None
        )
    except Exception as e:
        logger.error(f"获取登录限制配置失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="获取登录限制配置失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )


@router.put("/login-restrictions", response_model=LoginRestrictionsResponse)
async def update_login_restrictions(
    restrictions: LoginRestrictionsUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    更新登录限制配置
    
    需要管理员权限
    """
    # 限流配置
    if role_based_rate_limit:
        @role_based_rate_limit(requests_per_minute=10, requests_per_hour=30)
        async def _update():
            pass
        await _update()
    
    try:
        service = get_security_config_service(db)
        
        # 保存配置
        config = await service.set_login_restrictions(
            restrictions=restrictions.model_dump(),
            updated_by=current_user.user_id
        )
        
        # 返回更新后的配置
        updated_restrictions = await service.get_login_restrictions()
        
        return LoginRestrictionsResponse(
            max_failed_attempts=updated_restrictions.get("max_failed_attempts", 5),
            lockout_duration_minutes=updated_restrictions.get("lockout_duration_minutes", 30),
            enable_ip_whitelist=updated_restrictions.get("enable_ip_whitelist", False),
            updated_at=config.updated_at,
            updated_by=config.updated_by
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"更新登录限制配置失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="更新登录限制配置失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )


@router.get("/ip-whitelist", response_model=IPWhitelistResponse)
async def get_ip_whitelist(
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    获取IP白名单
    
    需要管理员权限
    """
    try:
        service = get_security_config_service(db)
        ip_addresses = await service.get_ip_whitelist()
        
        # 获取配置记录
        config = await service.get_config("ip_whitelist")
        
        return IPWhitelistResponse(
            ip_addresses=ip_addresses,
            updated_at=config.updated_at if config else None,
            updated_by=config.updated_by if config else None
        )
    except Exception as e:
        logger.error(f"获取IP白名单失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="获取IP白名单失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )


@router.post("/ip-whitelist", response_model=IPWhitelistResponse)
async def add_ip_to_whitelist(
    request: IPWhitelistUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    添加IP到白名单
    
    需要管理员权限
    """
    try:
        service = get_security_config_service(db)
        ip_addresses = await service.get_ip_whitelist()
        
        # 检查是否已存在
        if request.ip_address in ip_addresses:
            return error_response(
                code=ErrorCode.DATA_ALREADY_EXISTS,
                message="IP地址已在白名单中",
                error_type=get_error_type(ErrorCode.DATA_ALREADY_EXISTS),
                detail=f"IP地址 {request.ip_address} 已在白名单中",
                status_code=400
            )
        
        # 添加IP
        ip_addresses.append(request.ip_address)
        config = await service.set_ip_whitelist(
            ip_addresses=ip_addresses,
            updated_by=current_user.user_id
        )
        
        return IPWhitelistResponse(
            ip_addresses=ip_addresses,
            updated_at=config.updated_at,
            updated_by=config.updated_by
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"添加IP到白名单失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="添加IP到白名单失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )


@router.delete("/ip-whitelist/{ip}")
async def remove_ip_from_whitelist(
    ip: str,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    从白名单移除IP
    
    需要管理员权限
    """
    try:
        service = get_security_config_service(db)
        ip_addresses = await service.get_ip_whitelist()
        
        # 检查是否存在
        if ip not in ip_addresses:
            return error_response(
                code=ErrorCode.DATA_NOT_FOUND,
                message="IP地址不在白名单中",
                error_type=get_error_type(ErrorCode.DATA_NOT_FOUND),
                detail=f"IP地址 {ip} 不在白名单中",
                status_code=404
            )
        
        # 移除IP
        ip_addresses.remove(ip)
        config = await service.set_ip_whitelist(
            ip_addresses=ip_addresses,
            updated_by=current_user.user_id
        )
        
        return success_response(
            data={"ip_addresses": ip_addresses},
            message=f"已从白名单移除IP: {ip}"
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"从白名单移除IP失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="从白名单移除IP失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )


# ==================== 会话管理 API ====================

@router.get("/session-config", response_model=SessionConfigResponse)
async def get_session_config(
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    获取会话配置
    
    需要管理员权限
    """
    try:
        service = get_security_config_service(db)
        session_config = await service.get_session_config()
        
        # 获取配置记录
        config = await service.get_config("session_config")
        
        return SessionConfigResponse(
            timeout_minutes=session_config.get("timeout_minutes", 15),
            max_concurrent_sessions=session_config.get("max_concurrent_sessions", 5),
            enable_session_limit=session_config.get("enable_session_limit", True),
            updated_at=config.updated_at if config else None,
            updated_by=config.updated_by if config else None
        )
    except Exception as e:
        logger.error(f"获取会话配置失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="获取会话配置失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )


@router.put("/session-config", response_model=SessionConfigResponse)
async def update_session_config(
    config: SessionConfigUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    更新会话配置
    
    需要管理员权限
    """
    # 限流配置
    if role_based_rate_limit:
        @role_based_rate_limit(requests_per_minute=10, requests_per_hour=30)
        async def _update():
            pass
        await _update()
    
    try:
        service = get_security_config_service(db)
        
        # 保存配置
        config_record = await service.set_session_config(
            session_config=config.model_dump(),
            updated_by=current_user.user_id
        )
        
        # 返回更新后的配置
        updated_config = await service.get_session_config()
        
        return SessionConfigResponse(
            timeout_minutes=updated_config.get("timeout_minutes", 15),
            max_concurrent_sessions=updated_config.get("max_concurrent_sessions", 5),
            enable_session_limit=updated_config.get("enable_session_limit", True),
            updated_at=config_record.updated_at,
            updated_by=config_record.updated_by
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"更新会话配置失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="更新会话配置失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )


# ==================== 2FA配置 API（可选） ====================

@router.get("/2fa-config", response_model=TwoFactorConfigResponse)
async def get_2fa_config(
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    获取2FA配置
    
    需要管理员权限
    """
    try:
        service = get_security_config_service(db)
        config = await service.get_config("2fa_config")
        
        if config and isinstance(config.config_value, dict):
            return TwoFactorConfigResponse(
                enabled=config.config_value.get("enabled", False),
                required_for_admin=config.config_value.get("required_for_admin", False),
                issuer_name=config.config_value.get("issuer_name", "西虹ERP系统"),
                updated_at=config.updated_at,
                updated_by=config.updated_by
            )
        
        # 返回默认值
        return TwoFactorConfigResponse(
            enabled=False,
            required_for_admin=False,
            issuer_name="西虹ERP系统",
            updated_at=None,
            updated_by=None
        )
    except Exception as e:
        logger.error(f"获取2FA配置失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="获取2FA配置失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )


@router.put("/2fa-config", response_model=TwoFactorConfigResponse)
async def update_2fa_config(
    config: TwoFactorConfigUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    更新2FA配置
    
    需要管理员权限
    """
    # 限流配置
    if role_based_rate_limit:
        @role_based_rate_limit(requests_per_minute=10, requests_per_hour=30)
        async def _update():
            pass
        await _update()
    
    try:
        service = get_security_config_service(db)
        
        # 保存配置
        config_record = await service.set_config(
            config_key="2fa_config",
            config_value=config.model_dump(),
            description="2FA配置",
            updated_by=current_user.user_id
        )
        
        return TwoFactorConfigResponse(
            enabled=config.enabled,
            required_for_admin=config.required_for_admin,
            issuer_name=config.issuer_name,
            updated_at=config_record.updated_at,
            updated_by=config_record.updated_by
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"更新2FA配置失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="更新2FA配置失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )
