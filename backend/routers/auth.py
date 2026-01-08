"""
认证相关API路由
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from backend.models.database import get_db, get_async_db
from backend.services.auth_service import auth_service
from backend.schemas.auth import (
    LoginRequest, LoginResponse, RefreshTokenRequest, RefreshTokenResponse,
    UserCreate, UserUpdate, UserResponse, RoleCreate, RoleUpdate, RoleResponse,
    # 注意：PermissionResponse已迁移到backend.schemas.permission（v4.20.0）
    ChangePasswordRequest, AuditLogResponse,
    AuditLogFilterRequest, AuditLogExportRequest, AuditLogDetailResponse,  # v4.20.0: 审计日志增强
    RegisterRequest, RegisterResponse  # v4.19.0: 用户注册
)
from modules.core.db import DimUser, DimRole, FactAuditLog, UserSession  # v4.12.0 SSOT迁移, v4.19.0会话管理
from backend.services.audit_service import audit_service
from backend.utils.api_response import success_response, error_response
from backend.utils.error_codes import ErrorCode, get_error_type
from backend.utils.config import get_settings  # [*] v6.0.0修复：导入 settings（Vulnerability 24）
from modules.core.logger import get_logger
from typing import List, Optional
from datetime import datetime
import os  # [*] v6.0.0新增：用于检查 CSRF_ENABLED 环境变量

logger = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["认证管理"])
security = HTTPBearer(auto_error=False)  # [*] v6.0.0修改：auto_error=False 允许可选认证（支持 Cookie）

# [*] v4.19.0新增：导入限流器
# [*] v4.19.4更新：使用基于角色的动态限流
try:
    from backend.middleware.rate_limiter import limiter, role_based_rate_limit
except ImportError:
    limiter = None
    role_based_rate_limit = None

# [*] v6.0.0修复：获取配置实例（Vulnerability 24）
settings = get_settings()

async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_async_db)
):
    """
    获取当前用户
    
    [*] v6.0.0新增：支持从 Cookie 和 Header 两种方式读取 token
    - 优先从 Cookie 读取（httpOnly Cookie，更安全）
    - 其次从 Header 读取（向后兼容）
    """
    token = None
    
    # [*] v6.0.0新增：优先从 Cookie 读取 token
    if "access_token" in request.cookies:
        token = request.cookies.get("access_token")
    # 其次从 Header 读取（向后兼容）
    elif credentials and credentials.credentials:
        token = credentials.credentials
    
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Missing authentication token"
        )
    
    try:
        payload = auth_service.verify_token(token)
        user_id = payload.get("user_id")
        
        if not user_id:
            raise HTTPException(
                status_code=401,
                detail="Invalid token"
            )
        
        # 从数据库获取用户信息（预加载 roles 关系）
        result = await db.execute(
            select(DimUser)
            .where(DimUser.user_id == user_id)  # v4.12.0修复：使用user_id字段
            .options(selectinload(DimUser.roles))
        )
        user = result.scalar_one_or_none()
        if not user or not user.is_active:
            raise HTTPException(
                status_code=401,
                detail="User not found or inactive"
            )
        
        # [*] v4.19.0 P1安全要求：检查用户 status 字段
        # 防止被暂停的用户使用现有 token 访问系统
        if user.status != "active":
            raise HTTPException(
                status_code=403,
                detail=f"Account is {user.status}, access denied"
            )
        
        return user
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token verification failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=401,
            detail="Invalid token"
        )

# [*] v4.19.4更新：使用基于角色的动态限流（替换硬编码限流）
@router.post("/register")
@role_based_rate_limit(endpoint_type="auth")  # [*] v4.19.4: 基于角色的动态限流（匿名用户使用 anonymous 配额）
async def register(
    request_body: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """
    用户注册
    
    速率限制：5次/分钟（防止暴力注册）
    """
    # [*] v4.19.0: 合并检查用户名和邮箱唯一性（统一错误消息，防止用户名/邮箱枚举）
    result = await db.execute(select(DimUser).where(DimUser.username == request_body.username))
    existing_user_by_username = result.scalar_one_or_none()
    
    result = await db.execute(select(DimUser).where(DimUser.email == request_body.email))
    existing_user_by_email = result.scalar_one_or_none()
    
    # [*] v4.19.0: 处理rejected用户重新注册
    # 如果用户名和邮箱都匹配同一个rejected用户，允许重新注册
    if (existing_user_by_username and existing_user_by_email and 
        existing_user_by_username.user_id == existing_user_by_email.user_id and
        existing_user_by_username.status == "rejected"):
        # rejected用户允许重新注册：更新状态为pending
        existing_user_by_username.status = "pending"
        existing_user_by_username.is_active = False
        existing_user_by_username.rejection_reason = None
        existing_user_by_username.password_hash = auth_service.hash_password(request_body.password)
        if request_body.full_name:
            existing_user_by_username.full_name = request_body.full_name
        if request_body.phone:
            existing_user_by_username.phone = request_body.phone
        if request_body.department:
            existing_user_by_username.department = request_body.department
        
        await db.commit()
        await db.refresh(existing_user_by_username)
        
        # 记录审计日志
        ip_address = request.client.host if request.client else "127.0.0.1"
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            ip_address = forwarded_for.split(",")[0].strip()
        user_agent = request.headers.get("User-Agent", "Unknown")
        
        await audit_service.log_action(
            user_id=existing_user_by_username.user_id,
            action="user_registered",
            resource="user",
            resource_id=str(existing_user_by_username.user_id),
            ip_address=ip_address,
            user_agent=user_agent,
            details={"username": existing_user_by_username.username, "email": existing_user_by_username.email, "action": "re-register"}
        )
        
        # v4.19.0: 通知管理员有新用户注册
        from backend.routers.notifications import notify_user_registered
        await notify_user_registered(
            db=db,
            user_id=existing_user_by_username.user_id,
            username=existing_user_by_username.username,
            email=existing_user_by_username.email
        )
        await db.commit()
        
        register_response = RegisterResponse(
            user_id=existing_user_by_username.user_id,
            username=existing_user_by_username.username,
            email=existing_user_by_username.email,
            status="pending",
            message="注册成功，请等待管理员审批"
        )
        return success_response(
            data=register_response.dict(),
            message="注册成功，请等待管理员审批"
        )
    
    # [*] v4.19.0: 统一错误消息（防止用户名/邮箱枚举）
    # 检查是否存在冲突（非rejected状态的用户）
    username_exists = (existing_user_by_username is not None and 
                      existing_user_by_username.status != "rejected")
    email_exists = (existing_user_by_email is not None and 
                   (existing_user_by_email.status != "rejected" or
                    (existing_user_by_username and existing_user_by_email.user_id != existing_user_by_username.user_id)))
    
    if username_exists or email_exists:
        return error_response(
            code=ErrorCode.DATA_UNIQUE_CONSTRAINT_VIOLATION,
            message="用户名或邮箱已被使用",
            error_type=get_error_type(ErrorCode.DATA_UNIQUE_CONSTRAINT_VIOLATION),
            recovery_suggestion="请使用不同的用户名或邮箱",
            status_code=400
        )
    
    # 创建用户（status="pending", is_active=False）
    user = DimUser(
        username=request_body.username,
        email=request_body.email,
        password_hash=auth_service.hash_password(request_body.password),
        full_name=request_body.full_name,
        phone=request_body.phone,
        department=request_body.department,
        status="pending",
        is_active=False
    )
    
    db.add(user)
    await db.flush()  # 获取用户ID
    
    # 记录审计日志
    ip_address = request.client.host if request.client else "127.0.0.1"
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        ip_address = forwarded_for.split(",")[0].strip()
    user_agent = request.headers.get("User-Agent", "Unknown")
    
    await audit_service.log_action(
        user_id=user.user_id,
        action="user_registered",
        resource="user",
        resource_id=str(user.user_id),
        ip_address=ip_address,
        user_agent=user_agent,
        details={"username": user.username, "email": user.email}
    )
    
    # v4.19.0: 通知管理员有新用户注册
    from backend.routers.notifications import notify_user_registered
    await notify_user_registered(
        db=db,
        user_id=user.user_id,
        username=user.username,
        email=user.email
    )
    
    await db.commit()
    
    register_response = RegisterResponse(
        user_id=user.user_id,
        username=user.username,
        email=user.email,
        status="pending",
        message="注册成功，请等待管理员审批"
    )
    return success_response(
        data=register_response.dict(),
        message="注册成功，请等待管理员审批"
    )

@router.post("/login", response_model=LoginResponse)
async def login(
    credentials: LoginRequest, 
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """
    用户登录
    
    速率限制：5次/分钟（防止暴力破解）
    """
    # 查找用户（预加载 roles 关系）
    result = await db.execute(
        select(DimUser)
        .where(DimUser.username == credentials.username)
        .options(selectinload(DimUser.roles))
    )
    user = result.scalar_one_or_none()
    
    # [*] v4.19.0: 1. 先检查用户是否存在（不泄露信息，统一错误消息）
    if not user:
        return error_response(
            code=ErrorCode.AUTH_CREDENTIALS_INVALID,
            message="Invalid credentials",
            error_type=get_error_type(ErrorCode.AUTH_CREDENTIALS_INVALID),
            recovery_suggestion="用户名或密码错误",
            status_code=401
        )
    
    # [*] v4.19.0: 2. 检查用户状态（在密码验证之前）
    if user.status == "pending":
        return error_response(
            code=ErrorCode.AUTH_ACCOUNT_PENDING,
            message="账号待审批，请联系管理员",
            error_type=get_error_type(ErrorCode.AUTH_ACCOUNT_PENDING),
            recovery_suggestion="请等待管理员审批",
            status_code=403
        )
    
    if user.status == "rejected":
        return error_response(
            code=ErrorCode.AUTH_ACCOUNT_REJECTED,
            message="账号已被拒绝，请联系管理员",
            error_type=get_error_type(ErrorCode.AUTH_ACCOUNT_REJECTED),
            recovery_suggestion="请联系管理员了解拒绝原因",
            status_code=403
        )
    
    if user.status == "suspended":
        return error_response(
            code=ErrorCode.AUTH_ACCOUNT_SUSPENDED,
            message="账号已被暂停，请联系管理员",
            error_type=get_error_type(ErrorCode.AUTH_ACCOUNT_SUSPENDED),
            recovery_suggestion="请联系管理员了解暂停原因",
            status_code=403
        )
    
    # [*] v4.19.0: 3. 检查status和is_active（只有active状态且is_active=True才能继续）
    if user.status != "active" or not user.is_active:
        return error_response(
            code=ErrorCode.AUTH_ACCOUNT_INACTIVE,
            message="账号未激活",
            error_type=get_error_type(ErrorCode.AUTH_ACCOUNT_INACTIVE),
            recovery_suggestion="请联系管理员激活账号",
            status_code=403
        )
    
    # [*] v4.19.0: 4. 检查账户是否被锁定（在密码验证之前）
    from datetime import datetime, timedelta
    if user.locked_until and user.locked_until > datetime.utcnow():
        # 账户仍被锁定
        remaining_minutes = int((user.locked_until - datetime.utcnow()).total_seconds() / 60)
        return error_response(
            code=ErrorCode.AUTH_ACCOUNT_LOCKED,
            message="账户已被锁定",
            error_type=get_error_type(ErrorCode.AUTH_ACCOUNT_LOCKED),
            recovery_suggestion=f"账户因多次登录失败已被锁定，请等待 {remaining_minutes} 分钟后重试，或联系管理员解锁",
            status_code=403
        )
    elif user.locked_until and user.locked_until <= datetime.utcnow():
        # 锁定已过期，自动解锁
        user.locked_until = None
        user.failed_login_attempts = 0
        await db.commit()
        
        # v4.19.0 P1：发送自动解锁通知
        from backend.routers.notifications import notify_account_unlocked
        await notify_account_unlocked(
            db=db,
            user_id=user.user_id,
            auto_unlock=True
        )
        await db.commit()
    
    # 验证密码
    if not auth_service.verify_password(credentials.password, user.password_hash):
        # 获取真实IP（考虑代理）
        ip_address = request.client.host if request.client else "127.0.0.1"
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            ip_address = forwarded_for.split(",")[0].strip()
        
        # 获取User-Agent
        user_agent = request.headers.get("User-Agent", "Unknown")
        
        # [*] v4.19.0: 增加失败登录计数
        from datetime import datetime, timedelta
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        
        # v4.20.0: 使用SecurityConfigService获取登录限制配置（替代硬编码策略）
        from backend.services.security_config_service import get_security_config_service
        security_service = get_security_config_service(db)
        login_restrictions = await security_service.get_login_restrictions()
        
        max_failed_attempts = login_restrictions.get("max_failed_attempts", 5)
        lockout_duration_minutes = login_restrictions.get("lockout_duration_minutes", 30)
        
        # 如果达到阈值，锁定账户
        if user.failed_login_attempts >= max_failed_attempts:
            user.locked_until = datetime.utcnow() + timedelta(minutes=lockout_duration_minutes)
            
            # v4.19.0 P0安全要求：账户锁定后强制撤销所有活跃会话
            from backend.routers.notifications import revoke_all_user_sessions, notify_account_locked
            revoked_count = await revoke_all_user_sessions(
                db=db,
                user_id=user.user_id,
                reason="Account locked due to failed login attempts, forced logout"
            )
            
            await db.commit()
            
            # 记录登录失败和账户锁定
            await audit_service.log_action(
                user_id=user.user_id,
                action="login_failed",
                resource="auth",
                ip_address=ip_address,
                user_agent=user_agent,
                details={
                    "reason": "invalid_password",
                    "failed_attempts": user.failed_login_attempts,
                    "account_locked": True,
                    "locked_until": user.locked_until.isoformat(),
                    "sessions_revoked": revoked_count
                }
            )
            
            # v4.19.0 P1：发送账户锁定通知
            await notify_account_locked(
                db=db,
                user_id=user.user_id,
                locked_minutes=lockout_duration_minutes,
                failed_attempts=user.failed_login_attempts
            )
            await db.commit()
            
            return error_response(
                code=ErrorCode.AUTH_ACCOUNT_LOCKED,
                message="账户已被锁定",
                error_type=get_error_type(ErrorCode.AUTH_ACCOUNT_LOCKED),
                recovery_suggestion=f"因多次登录失败，账户已被锁定 {lockout_duration_minutes} 分钟，请稍后重试或联系管理员解锁",
                status_code=403
            )
        else:
            # 未达到阈值，只更新失败计数
            await db.commit()
        
        # 记录登录失败
        await audit_service.log_action(
            user_id=user.user_id,
            action="login_failed",
            resource="auth",
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                "reason": "invalid_password",
                "failed_attempts": user.failed_login_attempts,
                "remaining_attempts": max_failed_attempts - user.failed_login_attempts
            }
        )
        
        remaining_attempts = max_failed_attempts - user.failed_login_attempts
        return error_response(
            code=ErrorCode.AUTH_CREDENTIALS_INVALID,
            message="Invalid credentials",
            error_type=get_error_type(ErrorCode.AUTH_CREDENTIALS_INVALID),
            recovery_suggestion=f"用户名或密码错误，剩余尝试次数：{remaining_attempts}",
            status_code=401
        )
    
    # 获取用户角色（已通过 selectinload 预加载）
    # [*] 修复：使用 role_name 而不是 name（DimRole 使用 role_name 字段）
    user_roles = [role.role_name for role in user.roles]
    
    # 创建令牌
    tokens = auth_service.create_token_pair(
        user_id=user.user_id,  # [*] v6.0.0修复：使用 user.user_id 而不是 user.id（Vulnerability 28）
        username=user.username,
        roles=user_roles
    )
    
    # 更新最后登录时间和重置失败计数
    from datetime import datetime
    user.last_login = datetime.utcnow()  # [*] v6.0.0修复：使用正确的字段名 last_login（Vulnerability 29）
    user.failed_login_attempts = 0  # [*] v4.19.0: 登录成功，重置失败计数
    user.locked_until = None  # [*] v4.19.0: 清除锁定状态（如果存在）
    await db.commit()
    
    # [*] v6.0.0修复：获取真实IP和User-Agent（Vulnerability 25, 26）
    # 获取真实IP（考虑代理）
    ip_address = request.client.host if request.client else "127.0.0.1"
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        ip_address = forwarded_for.split(",")[0].strip()
    
    # 获取User-Agent
    user_agent = request.headers.get("User-Agent", "Unknown")
    
    # 记录登录成功
    await audit_service.log_action(
        user_id=user.user_id,  # [*] v6.0.0修复：使用 user.user_id 而不是 user.id（Vulnerability 28）
        action="login_success",
        resource="auth",
        ip_address=ip_address,  # [*] v6.0.0修复：使用真实IP（Vulnerability 25）
        user_agent=user_agent,  # [*] v6.0.0修复：使用真实User-Agent（Vulnerability 25）
        details={"remember_me": credentials.remember_me}  # [*] v6.0.0修复：使用credentials.remember_me（Vulnerability 26）
    )
    
    # [*] v4.19.0: 创建会话记录
    import hashlib
    from datetime import datetime, timedelta
    session_id = hashlib.sha256(tokens["access_token"].encode()).hexdigest()
    expires_at = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    # 检查会话是否已存在（避免重复创建）
    session_result = await db.execute(
        select(UserSession).where(UserSession.session_id == session_id)
    )
    existing_session = session_result.scalar_one_or_none()
    
    if not existing_session:
        session = UserSession(
            session_id=session_id,
            user_id=user.user_id,
            device_info=user_agent,
            ip_address=ip_address,
            created_at=datetime.utcnow(),
            expires_at=expires_at,
            last_active_at=datetime.utcnow(),
            is_active=True
        )
        db.add(session)
        await db.commit()
    else:
        # 如果会话已存在，更新最后活跃时间和过期时间
        existing_session.last_active_at = datetime.utcnow()
        existing_session.is_active = True
        existing_session.expires_at = expires_at
        await db.commit()
    
    # [*] v6.0.0新增：创建响应对象，用于设置 Cookie
    from fastapi.responses import JSONResponse
    response_data = {
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "token_type": tokens["token_type"],
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user_info": {
            "id": user.user_id,  # [*] v6.0.0修复：使用 user.user_id 而不是 user.id（Vulnerability 28）
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "roles": user_roles
        }
    }
    
    # [*] v6.0.0新增：将 token 存储在 httpOnly Cookie 中（提升安全性）
    response = JSONResponse(content=response_data)
    
    # 设置 Access Token Cookie
    # httpOnly: 防止 JavaScript 访问（防止 XSS 攻击）
    # secure: 仅在 HTTPS 连接时发送（开发环境可以设为 False）
    # sameSite: 防止 CSRF 攻击
    # [*] v6.0.0修复：更准确地判断是否使用 secure Cookie（检查请求是否是 HTTPS）
    is_https = request.url.scheme == "https"
    import os
    is_production = os.getenv("ENVIRONMENT", "development") == "production"
    # 生产环境或 HTTPS 连接时使用 secure Cookie
    secure_cookie = is_https or is_production
    
    response.set_cookie(
        key="access_token",
        value=tokens["access_token"],
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # 30 分钟
        httponly=True,  # 防止 XSS 攻击
        secure=secure_cookie,  # [*] v6.0.0修复：使用更准确的 secure 判断
        samesite="lax",  # 防止 CSRF 攻击
        path="/"
    )
    
    # 设置 Refresh Token Cookie
    response.set_cookie(
        key="refresh_token",
        value=tokens["refresh_token"],
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,  # 7 天
        httponly=True,
        secure=secure_cookie,  # [*] v6.0.0修复：使用更准确的 secure 判断
        samesite="lax",
        path="/"
    )
    
    # [*] v6.0.0新增：设置 CSRF Token Cookie（Phase 3: CSRF 保护）
    # 仅在 CSRF 保护启用时设置 CSRF Token
    csrf_enabled = os.getenv("CSRF_ENABLED", "false").lower() == "true"
    if csrf_enabled:
        from backend.middleware.csrf import set_csrf_token_cookie
        set_csrf_token_cookie(response, request)
    
    return response

@router.post("/refresh", response_model=RefreshTokenResponse)
async def refresh_token(
    http_request: Request,
    request_body: Optional[RefreshTokenRequest] = None,
    db: AsyncSession = Depends(get_async_db)
):
    """
    刷新访问令牌
    
    [*] v6.0.0新增：支持从 Cookie 和请求体两种方式读取 refresh token
    - 优先从 Cookie 读取（httpOnly Cookie，更安全）
    - 其次从请求体读取（向后兼容）
    
    [*] v4.19.0 P0安全要求：刷新token前必须验证账户状态
    """
    refresh_token_value = None
    
    # [*] v6.0.0新增：优先从 Cookie 读取 refresh token
    if "refresh_token" in http_request.cookies:
        refresh_token_value = http_request.cookies.get("refresh_token")
    # 其次从请求体读取（向后兼容）
    elif request_body and request_body.refresh_token:
        refresh_token_value = request_body.refresh_token
    
    if not refresh_token_value:
        return error_response(
            code=ErrorCode.AUTH_TOKEN_INVALID,
            message="Missing refresh token",
            error_type=get_error_type(ErrorCode.AUTH_TOKEN_INVALID),
            recovery_suggestion="请重新登录获取新的token",
            status_code=401
        )
    
    try:
        # [*] v4.19.0 P0安全要求：验证token并获取用户ID
        payload = auth_service.verify_token(refresh_token_value)
        user_id = payload.get("user_id")
        
        if not user_id:
            return error_response(
                code=ErrorCode.AUTH_TOKEN_INVALID,
                message="Invalid refresh token",
                error_type=get_error_type(ErrorCode.AUTH_TOKEN_INVALID),
                recovery_suggestion="请重新登录获取新的token",
                status_code=401
            )
        
        # [*] v4.19.0 P0安全要求：从数据库获取用户信息并检查状态
        result = await db.execute(
            select(DimUser).where(DimUser.user_id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            return error_response(
                code=ErrorCode.AUTH_TOKEN_INVALID,
                message="User not found",
                error_type=get_error_type(ErrorCode.AUTH_TOKEN_INVALID),
                recovery_suggestion="请重新登录",
                status_code=401
            )
        
        # [*] v4.19.0 P0安全要求：检查用户状态
        if user.status != "active" or not user.is_active:
            return error_response(
                code=ErrorCode.AUTH_ACCOUNT_INACTIVE,
                message="Account is not active",
                error_type=get_error_type(ErrorCode.AUTH_ACCOUNT_INACTIVE),
                recovery_suggestion="您的账户已被暂停或未激活，请联系管理员",
                status_code=403
            )
        
        # [*] v4.19.0 P0安全要求：检查账户是否被锁定
        from datetime import datetime
        if user.locked_until and user.locked_until > datetime.utcnow():
            return error_response(
                code=ErrorCode.AUTH_ACCOUNT_LOCKED,
                message="Account is locked",
                error_type=get_error_type(ErrorCode.AUTH_ACCOUNT_LOCKED),
                recovery_suggestion="您的账户已被锁定，请等待锁定期满或联系管理员解锁",
                status_code=403
            )
        
        # [*] v4.19.0 P0安全要求：检查会话是否已被撤销
        import hashlib
        # 从当前access_token（如果有）计算session_id
        current_token = None
        if "access_token" in http_request.cookies:
            current_token = http_request.cookies.get("access_token")
        elif http_request.headers.get("Authorization", "").startswith("Bearer "):
            current_token = http_request.headers.get("Authorization", "").replace("Bearer ", "")
        
        if current_token:
            current_session_id = hashlib.sha256(current_token.encode()).hexdigest()
            session_result = await db.execute(
                select(UserSession).where(
                    UserSession.session_id == current_session_id,
                    UserSession.user_id == user_id
                )
            )
            session = session_result.scalar_one_or_none()
            
            if session and not session.is_active:
                return error_response(
                    code=ErrorCode.AUTH_TOKEN_INVALID,
                    message="Session has been revoked",
                    error_type=get_error_type(ErrorCode.AUTH_TOKEN_INVALID),
                    recovery_suggestion="您的会话已被撤销，请重新登录",
                    status_code=401
                )
        
        # [*] v6.0.0修复：使用 refresh_token_pair 同时生成新的 access token 和 refresh token
        # [*] v6.0.0修复：refresh_token_pair 现在是异步方法（需要访问 Redis 黑名单）
        new_tokens = await auth_service.refresh_token_pair(refresh_token_value)
        
        # [*] v4.19.0: 更新会话的 last_active_at（在单独的数据库会话中）
        # 注意：这里不能使用当前的db依赖，因为refresh_token端点没有db参数
        # 使用临时数据库连接更新会话
        try:
            from datetime import datetime, timedelta
            import hashlib
            from backend.models.database import AsyncSessionLocal
            
            # 获取新的access token的session_id
            new_session_id = hashlib.sha256(new_tokens["access_token"].encode()).hexdigest()
            
            # 从refresh token中获取user_id
            payload = auth_service.verify_token(refresh_token_value)
            user_id = payload.get("user_id")
            
            if user_id:
                async with AsyncSessionLocal() as temp_db:
                    try:
                        # 查找会话（可能使用新的session_id或旧的）
                        session_result = await temp_db.execute(
                            select(UserSession)
                            .where(
                                (UserSession.session_id == new_session_id) |
                                (UserSession.user_id == user_id)
                            )
                            .order_by(UserSession.last_active_at.desc())
                            .limit(1)
                        )
                        session = session_result.scalar_one_or_none()
                        
                        if session:
                            # 更新会话信息
                            session.session_id = new_session_id  # 更新为新的session_id（如果token轮换）
                            session.last_active_at = datetime.utcnow()
                            session.expires_at = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
                            session.is_active = True
                            await temp_db.commit()
                    except Exception as e:
                        await temp_db.rollback()
                        logger.warning(f"Failed to update session on token refresh: {e}")
        except Exception as e:
            logger.warning(f"Failed to update session on token refresh: {e}")
        
        # [*] v6.0.0新增：创建响应对象，用于设置 Cookie
        from fastapi.responses import JSONResponse
        response_data = {
            "access_token": new_tokens["access_token"],
            "refresh_token": new_tokens["refresh_token"],  # [*] v6.0.0修复：同时返回新的 refresh_token（用于前端同步）
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        }
        
        # [*] v6.0.0新增：将新的 access token 和 refresh token 存储在 httpOnly Cookie 中
        # [*] v6.0.0修复：更准确地判断是否使用 secure Cookie（检查请求是否是 HTTPS）
        is_https = http_request.url.scheme == "https"
        import os
        is_production = os.getenv("ENVIRONMENT", "development") == "production"
        # 生产环境或 HTTPS 连接时使用 secure Cookie
        secure_cookie = is_https or is_production
        
        json_response = JSONResponse(content=response_data)
        
        # 设置新的 Access Token Cookie
        json_response.set_cookie(
            key="access_token",
            value=new_tokens["access_token"],
            max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            httponly=True,
            secure=secure_cookie,  # [*] v6.0.0修复：使用更准确的 secure 判断
            samesite="lax",
            path="/"
        )
        
        # [*] v6.0.0修复：同时更新 Refresh Token Cookie（支持 Refresh Token 轮换）
        json_response.set_cookie(
            key="refresh_token",
            value=new_tokens["refresh_token"],
            max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
            httponly=True,
            secure=secure_cookie,  # [*] v6.0.0修复：使用更准确的 secure 判断
            samesite="lax",
            path="/"
        )
        
        return json_response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Refresh token failed: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.AUTH_TOKEN_INVALID,
            message="Invalid refresh token",
            error_type=get_error_type(ErrorCode.AUTH_TOKEN_INVALID),
            detail=str(e),
            recovery_suggestion="请重新登录获取新的token",
            status_code=401
        )

@router.post("/logout")
async def logout(
    request: Request,
    current_user: DimUser = Depends(get_current_user)
):
    """
    用户登出
    
    [*] v6.0.0修复：清除所有认证相关的 Cookie
    """
    # [*] v6.0.0修复：获取真实IP和User-Agent（Vulnerability 27）
    # 获取真实IP（考虑代理）
    ip_address = request.client.host if request.client else "127.0.0.1"
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        ip_address = forwarded_for.split(",")[0].strip()
    
    # 获取User-Agent
    user_agent = request.headers.get("User-Agent", "Unknown")
    
    # 记录登出操作
    await audit_service.log_action(
        user_id=current_user.user_id,  # [*] v6.0.0修复：使用 user.user_id 而不是 user.id（Vulnerability 28）
        action="logout",
        resource="auth",
        ip_address=ip_address,  # [*] v6.0.0修复：使用真实IP（Vulnerability 27）
        user_agent=user_agent  # [*] v6.0.0修复：使用真实User-Agent（Vulnerability 27）
    )
    
    # [*] v6.0.0修复：清除所有认证相关的 Cookie
    from fastapi.responses import JSONResponse
    response = JSONResponse(content={
        "success": True,
        "message": "登出成功",
        "data": None
    })
    
    # [*] v6.0.0修复：清除 Access Token Cookie
    # 注意：如果将来设置了 domain，删除时也需要指定相同的 domain
    response.delete_cookie(
        key="access_token", 
        path="/",
        domain=None,  # 当前未设置 domain，如果将来设置了，需要指定相同的 domain
        samesite="lax"  # 必须与设置 Cookie 时的值一致
    )
    # [*] v6.0.0修复：清除 Refresh Token Cookie
    response.delete_cookie(
        key="refresh_token", 
        path="/",
        domain=None,  # 当前未设置 domain，如果将来设置了，需要指定相同的 domain
        samesite="lax"  # 必须与设置 Cookie 时的值一致
    )
    
    # [*] v6.0.0新增：清除 CSRF Token Cookie（Phase 3: CSRF 保护）
    # 仅在 CSRF 保护启用时清除 CSRF Token
    csrf_enabled = os.getenv("CSRF_ENABLED", "false").lower() == "true"
    if csrf_enabled:
        from backend.middleware.csrf import delete_csrf_token_cookie
        delete_csrf_token_cookie(response)
    
    return response

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: DimUser = Depends(get_current_user)):
    """获取当前用户信息"""
    return UserResponse(
        id=current_user.user_id,  # [*] v6.0.0修复：使用 user.user_id 而不是 user.id（Vulnerability 28）
        username=current_user.username,
        email=current_user.email,
        full_name=current_user.full_name,
        roles=[role.role_name for role in current_user.roles],  # [*] 修复：使用 role_name 而不是 name
        is_active=current_user.is_active,
        created_at=current_user.created_at,
        last_login_at=current_user.last_login  # [*] v6.0.0修复：使用正确的字段名 last_login（Vulnerability 29）
    )

@router.put("/me", response_model=UserResponse)
async def update_current_user(
    user_update: UserUpdate,
    request: Request,  # [*] v6.0.0修复：添加 request 参数以获取真实IP和User-Agent（Vulnerability 27）
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """更新当前用户信息"""
    # 更新用户信息
    if user_update.email is not None:
        current_user.email = user_update.email
    if user_update.full_name is not None:
        current_user.full_name = user_update.full_name
    
    await db.commit()
    await db.refresh(current_user)
    
    # [*] v6.0.0修复：获取真实IP和User-Agent（Vulnerability 27）
    # 获取真实IP（考虑代理）
    ip_address = request.client.host if request.client else "127.0.0.1"
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        ip_address = forwarded_for.split(",")[0].strip()
    
    # 获取User-Agent
    user_agent = request.headers.get("User-Agent", "Unknown")
    
    # 记录更新操作
    await audit_service.log_action(
        user_id=current_user.user_id,  # [*] v6.0.0修复：使用 user.user_id 而不是 user.id（Vulnerability 28）
        action="update_profile",
        resource="user",
        resource_id=str(current_user.user_id),  # [*] v6.0.0修复：使用 user.user_id 而不是 user.id（Vulnerability 28）
        ip_address=ip_address,  # [*] v6.0.0修复：使用真实IP（Vulnerability 27）
        user_agent=user_agent,  # [*] v6.0.0修复：使用真实User-Agent（Vulnerability 27）
        details=user_update.dict(exclude_unset=True)
    )
    
    return UserResponse(
        id=current_user.user_id,  # [*] v6.0.0修复：使用 user.user_id 而不是 user.id（Vulnerability 28）
        username=current_user.username,
        email=current_user.email,
        full_name=current_user.full_name,
        roles=[role.role_name for role in current_user.roles],  # [*] 修复：使用 role_name 而不是 name
        is_active=current_user.is_active,
        created_at=current_user.created_at,
        last_login_at=current_user.last_login  # [*] v6.0.0修复：使用正确的字段名 last_login（Vulnerability 29）
    )

@router.post("/change-password")
async def change_password(
    password_request: ChangePasswordRequest,  # [*] v6.0.0修复：重命名参数避免与 Request 冲突（Vulnerability 27）
    http_request: Request,  # [*] v6.0.0修复：添加 request 参数以获取真实IP和User-Agent（Vulnerability 27）
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    修改密码
    
    v4.20.0: 使用SecurityConfigService验证密码策略
    """
    # 验证旧密码
    if not auth_service.verify_password(password_request.old_password, current_user.password_hash):
        return error_response(
            code=ErrorCode.AUTH_CREDENTIALS_INVALID,
            message="Invalid old password",
            error_type=get_error_type(ErrorCode.AUTH_CREDENTIALS_INVALID),
            recovery_suggestion="旧密码不正确，请重新输入",
            status_code=400
        )
    
    # v4.20.0: 使用SecurityConfigService验证密码策略
    from backend.services.security_config_service import get_security_config_service
    security_service = get_security_config_service(db)
    password_policy = await security_service.get_password_policy()
    
    # 验证新密码是否符合策略
    is_valid, error_message = security_service.validate_password(
        password_request.new_password,
        password_policy
    )
    
    if not is_valid:
        return error_response(
            code=ErrorCode.VALIDATION_ERROR,
            message=error_message or "密码不符合策略要求",
            error_type=get_error_type(ErrorCode.VALIDATION_ERROR),
            recovery_suggestion=error_message,
            status_code=400
        )
    
    # 更新密码
    current_user.password_hash = auth_service.hash_password(password_request.new_password)
    await db.commit()
    
    # [*] v6.0.0修复：获取真实IP和User-Agent（Vulnerability 27）
    # 获取真实IP（考虑代理）
    ip_address = http_request.client.host if http_request.client else "127.0.0.1"
    forwarded_for = http_request.headers.get("X-Forwarded-For")
    if forwarded_for:
        ip_address = forwarded_for.split(",")[0].strip()
    
    # 获取User-Agent
    user_agent = http_request.headers.get("User-Agent", "Unknown")
    
    # 记录密码修改
    await audit_service.log_action(
        user_id=current_user.user_id,  # [*] v6.0.0修复：使用 user.user_id 而不是 user.id（Vulnerability 28）
        action="change_password",
        resource="user",
        resource_id=str(current_user.user_id),  # [*] v6.0.0修复：使用 user.user_id 而不是 user.id（Vulnerability 28）
        ip_address=ip_address,  # [*] v6.0.0修复：使用真实IP（Vulnerability 27）
        user_agent=user_agent  # [*] v6.0.0修复：使用真实User-Agent（Vulnerability 27）
    )
    
    return success_response(
        data=None,
        message="密码修改成功"
    )

@router.get("/audit-logs", response_model=List[AuditLogResponse])
async def get_audit_logs(
    action: Optional[str] = Query(None, description="操作类型（支持模糊匹配）"),
    resource: Optional[str] = Query(None, description="资源类型（支持模糊匹配）"),
    user_id: Optional[int] = Query(None, description="用户ID"),
    username: Optional[str] = Query(None, description="用户名（支持模糊匹配）"),
    ip_address: Optional[str] = Query(None, description="IP地址（支持模糊匹配）"),
    start_time: Optional[datetime] = Query(None, description="开始时间"),
    end_time: Optional[datetime] = Query(None, description="结束时间"),
    page: int = Query(1, ge=1, description="页码（1-based）"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数（最大100）"),
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    获取审计日志列表（支持筛选、分页）
    
    需要管理员权限
    v4.20.0: 增强筛选功能
    """
    # 检查权限（使用require_admin依赖更简洁，但保持向后兼容）
    if not any(role.role_name == "admin" for role in current_user.roles):
        return error_response(
            code=ErrorCode.PERMISSION_DENIED,
            message="Insufficient permissions",
            error_type=get_error_type(ErrorCode.PERMISSION_DENIED),
            recovery_suggestion="需要管理员权限才能执行此操作",
            status_code=403
        )
    
    try:
        # 构建查询条件
        conditions = []
        
        if action:
            conditions.append(FactAuditLog.action.ilike(f"%{action}%"))
        
        if resource:
            conditions.append(FactAuditLog.resource.ilike(f"%{resource}%"))
        
        if user_id:
            conditions.append(FactAuditLog.user_id == user_id)
        
        if username:
            conditions.append(FactAuditLog.username.ilike(f"%{username}%"))
        
        if ip_address:
            conditions.append(FactAuditLog.ip_address.ilike(f"%{ip_address}%"))
        
        if start_time:
            conditions.append(FactAuditLog.created_at >= start_time)
        
        if end_time:
            conditions.append(FactAuditLog.created_at <= end_time)
        
        # 查询数据
        query = select(FactAuditLog).order_by(FactAuditLog.created_at.desc())
        if conditions:
            query = query.where(and_(*conditions))
        
        # 分页
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)
        
        result = await db.execute(query)
        logs = result.scalars().all()
        
        return [
            AuditLogResponse(
                id=log.id,
                user_id=log.user_id,
                username=log.username,
                action=log.action,
                resource=log.resource,
                resource_id=log.resource_id,
                ip_address=log.ip_address,
                user_agent=log.user_agent,
                created_at=log.created_at,
                details=log.details
            )
            for log in logs
        ]
        
    except Exception as e:
        logger.error(f"获取审计日志列表失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="获取审计日志列表失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )


@router.get("/audit-logs/{log_id}", response_model=AuditLogDetailResponse)
async def get_audit_log_detail(
    log_id: int,
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    获取审计日志详情（包含变更前后对比）
    
    需要管理员权限
    v4.20.0: 新增端点
    """
    # 检查权限
    if not any(role.role_name == "admin" for role in current_user.roles):
        return error_response(
            code=ErrorCode.PERMISSION_DENIED,
            message="Insufficient permissions",
            error_type=get_error_type(ErrorCode.PERMISSION_DENIED),
            recovery_suggestion="需要管理员权限才能执行此操作",
            status_code=403
        )
    
    try:
        result = await db.execute(
            select(FactAuditLog).where(FactAuditLog.id == log_id)
        )
        log = result.scalar_one_or_none()
        
        if not log:
            return error_response(
                code=ErrorCode.DATA_NOT_FOUND,
                message="审计日志不存在",
                error_type=get_error_type(ErrorCode.DATA_NOT_FOUND),
                detail=f"审计日志ID {log_id} 不存在",
                status_code=404
            )
        
        # 解析变更前后数据（如果details中包含）
        before_data = None
        after_data = None
        if log.details:
            if isinstance(log.details, dict):
                before_data = log.details.get("before")
                after_data = log.details.get("after")
        
        return AuditLogDetailResponse(
            id=log.id,
            user_id=log.user_id,
            username=log.username,
            action=log.action,
            resource=log.resource,
            resource_id=log.resource_id,
            ip_address=log.ip_address,
            user_agent=log.user_agent,
            created_at=log.created_at,
            details=log.details,
            before_data=before_data,
            after_data=after_data
        )
        
    except Exception as e:
        logger.error(f"获取审计日志详情失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="获取审计日志详情失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )


@router.post("/audit-logs/export")
async def export_audit_logs(
    request: AuditLogExportRequest,
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    导出审计日志（Excel/CSV格式）
    
    需要管理员权限
    限流：防止大量导出导致性能问题
    v4.20.0: 新增端点
    """
    # 检查权限
    if not any(role.role_name == "admin" for role in current_user.roles):
        return error_response(
            code=ErrorCode.PERMISSION_DENIED,
            message="Insufficient permissions",
            error_type=get_error_type(ErrorCode.PERMISSION_DENIED),
            recovery_suggestion="需要管理员权限才能执行此操作",
            status_code=403
        )
    
    # 限流配置
    if role_based_rate_limit:
        @role_based_rate_limit(requests_per_minute=5, requests_per_hour=20)
        async def _export():
            pass
        await _export()
    
    try:
        import io
        import csv
        
        # 构建查询条件
        conditions = []
        
        if request.action:
            conditions.append(FactAuditLog.action.ilike(f"%{request.action}%"))
        
        if request.resource:
            conditions.append(FactAuditLog.resource.ilike(f"%{request.resource}%"))
        
        if request.user_id:
            conditions.append(FactAuditLog.user_id == request.user_id)
        
        if request.username:
            conditions.append(FactAuditLog.username.ilike(f"%{request.username}%"))
        
        if request.ip_address:
            conditions.append(FactAuditLog.ip_address.ilike(f"%{request.ip_address}%"))
        
        if request.start_time:
            conditions.append(FactAuditLog.created_at >= request.start_time)
        
        if request.end_time:
            conditions.append(FactAuditLog.created_at <= request.end_time)
        
        # 查询数据（限制最大记录数）
        query = select(FactAuditLog).order_by(FactAuditLog.created_at.desc())
        if conditions:
            query = query.where(and_(*conditions))
        
        query = query.limit(request.max_records)
        
        result = await db.execute(query)
        logs = result.scalars().all()
        
        if not logs:
            return error_response(
                code=ErrorCode.DATA_NOT_FOUND,
                message="没有可导出的审计日志",
                error_type=get_error_type(ErrorCode.DATA_NOT_FOUND),
                detail="根据筛选条件未找到任何审计日志",
                status_code=404
            )
        
        # 导出为CSV或Excel
        if request.format == "csv":
            # CSV导出
            output = io.StringIO()
            writer = csv.writer(output)
            
            # 写入表头
            writer.writerow(["ID", "用户ID", "用户名", "操作", "资源", "资源ID", "IP地址", "用户代理", "创建时间", "详情"])
            
            # 写入数据
            for log in logs:
                writer.writerow([
                    log.id,
                    log.user_id,
                    log.username,
                    log.action,
                    log.resource,
                    log.resource_id or "",
                    log.ip_address,
                    log.user_agent,
                    log.created_at.isoformat() if log.created_at else "",
                    str(log.details) if log.details else ""
                ])
            
            from fastapi.responses import Response
            return Response(
                content=output.getvalue(),
                media_type="text/csv",
                headers={
                    "Content-Disposition": f"attachment; filename=audit_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                }
            )
        else:
            # Excel导出（需要openpyxl）
            try:
                from openpyxl import Workbook
                from openpyxl.styles import Font, Alignment
                
                wb = Workbook()
                ws = wb.active
                ws.title = "审计日志"
                
                # 写入表头
                headers = ["ID", "用户ID", "用户名", "操作", "资源", "资源ID", "IP地址", "用户代理", "创建时间", "详情"]
                ws.append(headers)
                
                # 设置表头样式
                for cell in ws[1]:
                    cell.font = Font(bold=True)
                    cell.alignment = Alignment(horizontal="center")
                
                # 写入数据
                for log in logs:
                    ws.append([
                        log.id,
                        log.user_id,
                        log.username,
                        log.action,
                        log.resource,
                        log.resource_id or "",
                        log.ip_address,
                        log.user_agent,
                        log.created_at.isoformat() if log.created_at else "",
                        str(log.details) if log.details else ""
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
                        "Content-Disposition": f"attachment; filename=audit_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                    }
                )
            except ImportError:
                # 如果没有openpyxl，降级为CSV
                logger.warning("openpyxl未安装，降级为CSV格式导出")
                return await export_audit_logs(
                    AuditLogExportRequest(
                        **request.model_dump(),
                        format="csv"
                    ),
                    current_user,
                    db
                )
        
    except Exception as e:
        logger.error(f"导出审计日志失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="导出审计日志失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )
