"""
用户管理API路由 - 当前用户端点

包含: 会话管理、通知偏好
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.models.database import get_async_db
from modules.core.db import DimUser, UserSession, UserNotificationPreference
from backend.schemas.auth import UserSessionResponse
from backend.schemas.notification import (
    NotificationPreferenceResponse,
    NotificationPreferenceUpdate,
    NotificationPreferenceBatchUpdate,
    NotificationPreferenceListResponse,
)
from backend.dependencies.auth import get_current_user
from backend.services.audit_service import audit_service
from backend.utils.api_response import success_response, error_response
from backend.utils.error_codes import ErrorCode, get_error_type
from typing import List
from datetime import datetime, timezone
from modules.core.logger import get_logger

try:
    from backend.middleware.rate_limiter import limiter, role_based_rate_limit
except ImportError:
    limiter = None
    role_based_rate_limit = None

router = APIRouter(prefix="/users", tags=["用户管理"])
logger = get_logger(__name__)


# ========== 会话管理 API ==========

@router.get("/me/sessions", response_model=List[UserSessionResponse])
async def get_my_sessions(
    request: Request,
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """获取当前用户的所有活跃会话"""
    import hashlib
    
    token = None
    if "access_token" in request.cookies:
        token = request.cookies.get("access_token")
    elif request.headers.get("Authorization", "").startswith("Bearer "):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
    
    current_session_id = None
    if token:
        current_session_id = hashlib.sha256(token.encode()).hexdigest()
    
    result = await db.execute(
        select(UserSession)
        .where(
            UserSession.user_id == current_user.user_id,
            UserSession.is_active == True,
            UserSession.expires_at > datetime.now(timezone.utc)
        )
        .order_by(UserSession.last_active_at.desc())
    )
    sessions = result.scalars().all()
    
    session_list = []
    for session in sessions:
        session_list.append(UserSessionResponse(
            session_id=session.session_id,
            device_info=session.device_info,
            ip_address=session.ip_address,
            location=session.location,
            created_at=session.created_at,
            expires_at=session.expires_at,
            last_active_at=session.last_active_at,
            is_active=session.is_active,
            is_current=(session.session_id == current_session_id) if current_session_id else False
        ))
    
    return success_response(
        data=session_list,
        message="获取会话列表成功"
    )

@router.delete("/me/sessions/{session_id}")
async def revoke_session(
    session_id: str,
    request: Request,
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """撤销指定会话(强制登出其他设备)"""
    result = await db.execute(
        select(UserSession)
        .where(
            UserSession.session_id == session_id,
            UserSession.user_id == current_user.user_id
        )
    )
    session = result.scalar_one_or_none()
    
    if not session:
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message="会话不存在",
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            recovery_suggestion="请检查会话ID是否正确",
            status_code=404
        )
    
    if not session.is_active or session.expires_at <= datetime.now(timezone.utc):
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message="会话已失效",
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            recovery_suggestion="该会话已过期或已被撤销",
            status_code=400
        )
    
    session.is_active = False
    session.revoked_at = datetime.now(timezone.utc)
    session.revoked_reason = "用户手动撤销"
    await db.commit()
    
    ip_address = request.client.host if request.client else "127.0.0.1"
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        ip_address = forwarded_for.split(",")[0].strip()
    user_agent = request.headers.get("User-Agent", "Unknown")
    
    await audit_service.log_action(
        user_id=current_user.user_id,
        action="revoke_session",
        resource="session",
        resource_id=session_id,
        ip_address=ip_address,
        user_agent=user_agent,
        details={"device_info": session.device_info, "ip_address": session.ip_address}
    )
    
    return success_response(
        data={"session_id": session_id},
        message="会话撤销成功"
    )

@router.delete("/me/sessions")
async def revoke_other_sessions(
    request: Request,
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """撤销除当前会话外的所有会话"""
    import hashlib
    
    token = None
    if "access_token" in request.cookies:
        token = request.cookies.get("access_token")
    elif request.headers.get("Authorization", "").startswith("Bearer "):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
    
    if not token:
        return error_response(
            code=ErrorCode.AUTH_REQUIRED,
            message="无法识别当前会话",
            error_type=get_error_type(ErrorCode.AUTH_REQUIRED),
            recovery_suggestion="请重新登录",
            status_code=401
        )
    
    current_session_id = hashlib.sha256(token.encode()).hexdigest()
    
    result = await db.execute(
        select(UserSession)
        .where(
            UserSession.user_id == current_user.user_id,
            UserSession.session_id != current_session_id,
            UserSession.is_active == True,
            UserSession.expires_at > datetime.now(timezone.utc)
        )
    )
    sessions = result.scalars().all()
    
    revoked_count = 0
    for session in sessions:
        session.is_active = False
        session.revoked_at = datetime.now(timezone.utc)
        session.revoked_reason = "用户撤销所有其他会话"
        revoked_count += 1
    
    await db.commit()
    
    ip_address = request.client.host if request.client else "127.0.0.1"
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        ip_address = forwarded_for.split(",")[0].strip()
    user_agent = request.headers.get("User-Agent", "Unknown")
    
    await audit_service.log_action(
        user_id=current_user.user_id,
        action="revoke_other_sessions",
        resource="session",
        ip_address=ip_address,
        user_agent=user_agent,
        details={"revoked_count": revoked_count}
    )
    
    return success_response(
        data={"revoked_count": revoked_count},
        message=f"已撤销 {revoked_count} 个其他会话"
    )


# ========== 通知偏好 API ==========

@router.get("/me/notification-preferences", response_model=NotificationPreferenceListResponse)
@role_based_rate_limit(endpoint_type="default")
async def get_notification_preferences(
    request: Request,
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """获取当前用户所有通知偏好"""
    result = await db.execute(
        select(UserNotificationPreference)
        .where(UserNotificationPreference.user_id == current_user.user_id)
        .order_by(UserNotificationPreference.notification_type)
    )
    preferences = result.scalars().all()
    
    items = [NotificationPreferenceResponse.model_validate(p) for p in preferences]
    
    return NotificationPreferenceListResponse(
        items=items,
        total=len(items)
    )


@router.put("/me/notification-preferences", response_model=NotificationPreferenceListResponse)
@role_based_rate_limit(endpoint_type="default")
async def update_notification_preferences(
    batch_update: NotificationPreferenceBatchUpdate,
    request: Request,
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """批量更新通知偏好"""
    updated_preferences = []
    
    for update_data in batch_update.preferences:
        result = await db.execute(
            select(UserNotificationPreference)
            .where(
                UserNotificationPreference.user_id == current_user.user_id,
                UserNotificationPreference.notification_type == update_data.notification_type
            )
        )
        preference = result.scalar_one_or_none()
        
        if preference:
            if update_data.enabled is not None:
                preference.enabled = update_data.enabled
            if update_data.desktop_enabled is not None:
                preference.desktop_enabled = update_data.desktop_enabled
        else:
            preference = UserNotificationPreference(
                user_id=current_user.user_id,
                notification_type=update_data.notification_type,
                enabled=update_data.enabled if update_data.enabled is not None else True,
                desktop_enabled=update_data.desktop_enabled if update_data.desktop_enabled is not None else False
            )
            db.add(preference)
        
        updated_preferences.append(preference)
    
    await db.commit()
    
    for pref in updated_preferences:
        await db.refresh(pref)
    
    items = [NotificationPreferenceResponse.model_validate(p) for p in updated_preferences]
    
    return NotificationPreferenceListResponse(
        items=items,
        total=len(items)
    )


@router.get("/me/notification-preferences/{notification_type}", response_model=NotificationPreferenceResponse)
@role_based_rate_limit(endpoint_type="default")
async def get_notification_preference(
    notification_type: str,
    request: Request,
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """获取特定类型通知偏好"""
    result = await db.execute(
        select(UserNotificationPreference)
        .where(
            UserNotificationPreference.user_id == current_user.user_id,
            UserNotificationPreference.notification_type == notification_type
        )
    )
    preference = result.scalar_one_or_none()
    
    if not preference:
        return NotificationPreferenceResponse(
            preference_id=0,
            user_id=current_user.user_id,
            notification_type=notification_type,
            enabled=True,
            desktop_enabled=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
    
    return NotificationPreferenceResponse.model_validate(preference)


@router.put("/me/notification-preferences/{notification_type}", response_model=NotificationPreferenceResponse)
@role_based_rate_limit(endpoint_type="default")
async def update_notification_preference(
    notification_type: str,
    update_data: NotificationPreferenceUpdate,
    request: Request,
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """更新特定类型通知偏好"""
    result = await db.execute(
        select(UserNotificationPreference)
        .where(
            UserNotificationPreference.user_id == current_user.user_id,
            UserNotificationPreference.notification_type == notification_type
        )
    )
    preference = result.scalar_one_or_none()
    
    if preference:
        if update_data.enabled is not None:
            preference.enabled = update_data.enabled
        if update_data.desktop_enabled is not None:
            preference.desktop_enabled = update_data.desktop_enabled
        await db.commit()
        await db.refresh(preference)
    else:
        preference = UserNotificationPreference(
            user_id=current_user.user_id,
            notification_type=notification_type,
            enabled=update_data.enabled if update_data.enabled is not None else True,
            desktop_enabled=update_data.desktop_enabled if update_data.desktop_enabled is not None else False
        )
        db.add(preference)
        await db.commit()
        await db.refresh(preference)
    
    return NotificationPreferenceResponse.model_validate(preference)
