"""
用户管理API路由
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Request as FastAPIRequest
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from backend.models.database import get_db, get_async_db
from modules.core.db import DimUser, DimRole, UserApprovalLog, UserSession, UserNotificationPreference  # v4.12.0 SSOT迁移, v4.19.0用户审批和会话管理, v4.19.0通知偏好
from backend.schemas.auth import (
    UserCreate, UserUpdate, UserResponse, RoleCreate, RoleUpdate, RoleResponse,
    ApproveUserRequest, RejectUserRequest, PendingUserResponse,  # v4.19.0: 用户审批
    ResetPasswordRequest, ResetPasswordResponse, UnlockAccountRequest,  # v4.19.0: 密码管理
    UserSessionResponse  # v4.19.0: 会话管理
)
from backend.schemas.notification import (  # v4.19.0: 通知偏好
    NotificationPreferenceResponse,
    NotificationPreferenceUpdate,
    NotificationPreferenceBatchUpdate,
    NotificationPreferenceListResponse,
    NotificationType
)
from backend.routers.auth import get_current_user
from backend.services.audit_service import audit_service
from backend.utils.api_response import success_response, error_response, pagination_response
from backend.utils.error_codes import ErrorCode, get_error_type
from typing import List, Optional
from datetime import datetime
from functools import wraps
from modules.core.logger import get_logger

# v4.19.0新增：导入限流器
# [*] v4.19.4更新：使用基于角色的动态限流
try:
    from backend.middleware.rate_limiter import limiter, role_based_rate_limit
except ImportError:
    limiter = None
    role_based_rate_limit = None

router = APIRouter(prefix="/users", tags=["用户管理"])
logger = get_logger(__name__)

async def require_admin(current_user: DimUser = Depends(get_current_user)):
    """要求管理员权限"""
    # 优先检查 is_superuser 标志
    if current_user.is_superuser:
        return current_user
    
    # 检查角色（使用 role_code 或 role_name）
    is_admin = any(
        (hasattr(role, "role_code") and role.role_code == "admin") or
        (hasattr(role, "role_name") and role.role_name == "admin")
        for role in current_user.roles
    )
    
    if not is_admin:
        raise HTTPException(
            status_code=403,
            detail="Insufficient permissions"
        )
    return current_user

@router.post("/", response_model=UserResponse)
async def create_user(
    user_data: UserCreate,
    current_user: DimUser = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db)
):
    """创建用户"""
    # 检查用户名是否已存在
    result = await db.execute(select(DimUser).where(DimUser.username == user_data.username))
    existing_user = result.scalar_one_or_none()
    if existing_user:
        return error_response(
            code=ErrorCode.DATA_UNIQUE_CONSTRAINT_VIOLATION,
            message="Username already exists",
            error_type=get_error_type(ErrorCode.DATA_UNIQUE_CONSTRAINT_VIOLATION),
            recovery_suggestion="请使用不同的用户名",
            status_code=400
        )
    
    # 检查邮箱是否已存在
    result = await db.execute(select(DimUser).where(DimUser.email == user_data.email))
    existing_email = result.scalar_one_or_none()
    if existing_email:
        return error_response(
            code=ErrorCode.DATA_UNIQUE_CONSTRAINT_VIOLATION,
            message="Email already exists",
            error_type=get_error_type(ErrorCode.DATA_UNIQUE_CONSTRAINT_VIOLATION),
            recovery_suggestion="请使用不同的邮箱地址",
            status_code=400
        )
    
    # 创建用户
    from backend.services.auth_service import auth_service
    user = DimUser(
        username=user_data.username,
        email=user_data.email,
        password_hash=auth_service.hash_password(user_data.password),
        full_name=user_data.full_name,
        is_active=user_data.is_active
    )
    
    db.add(user)
    await db.flush()  # 获取用户ID
    
    # 分配角色
    for role_name in user_data.roles:
        result = await db.execute(select(DimRole).where(DimRole.role_name == role_name))
        role = result.scalar_one_or_none()
        if role:
            user.roles.append(role)
    
    await db.commit()
    # [FIX] AsyncSession 下访问 user.roles 可能触发懒加载（MissingGreenlet），这里显式加载关系
    await db.refresh(user, ["roles"])
    
    # 记录操作
    await audit_service.log_action(
        user_id=current_user.user_id,  # [*] v6.0.0修复：使用 user.user_id 而不是 user.id（Vulnerability 28）
        action="create_user",
        resource="user",
        resource_id=str(user.user_id),  # [*] v6.0.0修复：使用 user.user_id 而不是 user.id（Vulnerability 28）
        ip_address="127.0.0.1",
        user_agent="Unknown",
        details={"username": user.username, "email": user.email}
    )
    
    return UserResponse(
        id=user.user_id,  # [*] v6.0.0修复：使用 user.user_id 而不是 user.id（Vulnerability 28）
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        roles=[role.role_name for role in user.roles],
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login  # [*] v6.0.0修复：使用正确的字段名 last_login（Vulnerability 29）
    )

@router.get("/")
async def get_users(
    page: int = 1,
    page_size: int = 20,
    current_user: DimUser = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db)
):
    """获取用户列表（分页）"""
    from sqlalchemy import func
    
    offset = (page - 1) * page_size
    
    # 查询总数（排除已删除用户）
    count_result = await db.execute(
        select(func.count(DimUser.user_id))
        .where(DimUser.status != "deleted")
    )
    total = count_result.scalar() or 0
    
    # [FIX] 预加载 roles，避免返回时访问 user.roles 触发懒加载（MissingGreenlet）
    # [*] 软删除：过滤已删除用户
    result = await db.execute(
        select(DimUser)
        .options(selectinload(DimUser.roles))
        .where(DimUser.status != "deleted")  # 过滤已删除用户
        .offset(offset)
        .limit(page_size)
        .order_by(DimUser.created_at.desc())
    )
    users = result.scalars().all()
    
    # 转换为响应模型
    user_responses = [
        UserResponse(
            id=user.user_id,  # [*] v6.0.0修复：使用 user.user_id 而不是 user.id（Vulnerability 28）
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            roles=[role.role_name for role in user.roles],
            is_active=user.is_active,
            created_at=user.created_at,
            last_login_at=user.last_login  # [*] v6.0.0修复：使用正确的字段名 last_login（Vulnerability 29）
        )
        for user in users
    ]
    
    # 使用分页响应格式
    return pagination_response(
        data=[user.dict() for user in user_responses],
        page=page,
        page_size=page_size,
        total=total
    )

@router.get("/deleted")
async def get_deleted_users(
    page: int = 1,
    page_size: int = 20,
    current_user: DimUser = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db)
):
    """获取已删除用户列表（软删除）"""
    from sqlalchemy import func
    
    offset = (page - 1) * page_size
    
    # 查询总数（仅已删除用户）
    count_result = await db.execute(
        select(func.count(DimUser.user_id))
        .where(DimUser.status == "deleted")
    )
    total = count_result.scalar() or 0
    
    # 查询已删除用户列表
    result = await db.execute(
        select(DimUser)
        .options(selectinload(DimUser.roles))
        .where(DimUser.status == "deleted")
        .offset(offset)
        .limit(page_size)
        .order_by(DimUser.updated_at.desc())  # 按删除时间倒序
    )
    users = result.scalars().all()
    
    # 转换为响应模型
    user_responses = [
        UserResponse(
            id=user.user_id,
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            roles=[role.role_name for role in user.roles],
            is_active=user.is_active,
            created_at=user.created_at,
            last_login_at=user.last_login
        )
        for user in users
    ]
    
    # 使用分页响应格式
    return pagination_response(
        data=[user.dict() for user in user_responses],
        page=page,
        page_size=page_size,
        total=total
    )

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    current_user: DimUser = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db)
):
    """获取用户详情"""
    # [FIX] 预加载 roles，避免返回时访问 user.roles 触发懒加载（MissingGreenlet）
    result = await db.execute(
        select(DimUser)
        .options(selectinload(DimUser.roles))
        .where(DimUser.user_id == user_id)  # v4.12.0修复：使用user_id字段
    )
    user = result.scalar_one_or_none()
    if not user:
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message="User not found",
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            recovery_suggestion="请检查用户ID是否正确，或确认该用户已创建",
            status_code=404
        )
    
    return UserResponse(
        id=user.user_id,  # [*] v6.0.0修复：使用 user.user_id 而不是 user.id（Vulnerability 28）
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        roles=[role.role_name for role in user.roles],
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login  # [*] v6.0.0修复：使用正确的字段名 last_login（Vulnerability 29）
    )

@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_update: UserUpdate,
    current_user: DimUser = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db)
):
    """更新用户信息"""
    # [FIX] 预加载 roles 关系，避免更新角色时触发懒加载（MissingGreenlet）
    result = await db.execute(
        select(DimUser)
        .options(selectinload(DimUser.roles))
        .where(DimUser.user_id == user_id)  # v4.12.0修复：使用user_id字段
    )
    user = result.scalar_one_or_none()
    if not user:
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message="User not found",
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            recovery_suggestion="请检查用户ID是否正确，或确认该用户已创建",
            status_code=404
        )
    
    # 更新用户信息
    if user_update.email is not None:
        # 检查邮箱是否被其他用户使用
        result = await db.execute(
            select(DimUser).where(
                DimUser.email == user_update.email,
                DimUser.user_id != user_id  # v4.12.0修复：使用user_id字段
            )
        )
        existing_email = result.scalar_one_or_none()
        if existing_email:
            return error_response(
                code=ErrorCode.DATA_UNIQUE_CONSTRAINT_VIOLATION,
                message="Email already exists",
                error_type=get_error_type(ErrorCode.DATA_UNIQUE_CONSTRAINT_VIOLATION),
                recovery_suggestion="请使用不同的邮箱地址",
                status_code=400
            )
        user.email = user_update.email
    
    if user_update.full_name is not None:
        user.full_name = user_update.full_name
    
    # v4.19.0 P0/P1安全要求：用户暂停处理
    was_active = user.is_active
    if user_update.is_active is not None:
        user.is_active = user_update.is_active
        
        # v4.19.0 P1：同步设置 status 字段（数据一致性）
        if user_update.is_active is False and was_active:
            # 用户被暂停：同步设置 status="suspended"
            user.status = "suspended"
            
            # v4.19.0 P0安全要求：强制撤销用户所有活跃会话
            from backend.routers.notifications import revoke_all_user_sessions, notify_user_suspended
            revoked_count = await revoke_all_user_sessions(
                db=db,
                user_id=user.user_id,
                reason="Account suspended by administrator, forced logout"
            )
            
            # v4.19.0 P1：发送用户暂停通知
            await notify_user_suspended(
                db=db,
                user_id=user.user_id,
                suspended_by=current_user.username,
                reason="Account suspended by administrator"
            )
        elif user_update.is_active is True and not was_active:
            # [*] 修复：用户被恢复时，同步设置 status="active"
            # 处理所有非 deleted 状态（suspended、pending、rejected）
            # 注意：deleted 状态应该通过 restore_user 接口恢复，这里不处理
            if user.status != "deleted":
                user.status = "active"
    
    # 更新角色
    if user_update.roles is not None:
        user.roles.clear()
        for role_name in user_update.roles:
            result = await db.execute(select(DimRole).where(DimRole.role_name == role_name))
            role = result.scalar_one_or_none()
            if role:
                user.roles.append(role)
    
    await db.commit()
    # [FIX] AsyncSession 下访问 user.roles 可能触发懒加载（MissingGreenlet），这里显式加载关系
    await db.refresh(user, ["roles"])
    
    # 记录操作
    await audit_service.log_action(
        user_id=current_user.user_id,  # [*] v6.0.0修复：使用 user.user_id 而不是 user.id（Vulnerability 28）
        action="update_user",
        resource="user",
        resource_id=str(user.user_id),  # [*] v6.0.0修复：使用 user.user_id 而不是 user.id（Vulnerability 28）
        ip_address="127.0.0.1",
        user_agent="Unknown",
        details=user_update.dict(exclude_unset=True)
    )
    
    return UserResponse(
        id=user.user_id,  # [*] v6.0.0修复：使用 user.user_id 而不是 user.id（Vulnerability 28）
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        roles=[role.role_name for role in user.roles],
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login  # [*] v6.0.0修复：使用正确的字段名 last_login（Vulnerability 29）
    )

@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    current_user: DimUser = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
    reason: Optional[str] = None
):
    """
    删除用户（软删除 - 业界标准）
    
    流程：
    1. 验证用户存在且未删除
    2. 撤销所有活跃会话（安全要求）
    3. 软删除用户（status="deleted", is_active=False）
    4. 记录删除操作（审计）
    5. 保留数据用于合规和追溯
    """
    try:
        # 1. 查询用户
        result = await db.execute(
            select(DimUser).where(DimUser.user_id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="用户不存在",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="请检查用户ID是否正确，或确认该用户已创建",
                status_code=404
            )
        
        # 检查用户是否已被删除
        if user.status == "deleted":
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="用户已被删除",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="该用户已被删除，如需恢复请使用恢复接口",
                status_code=400
            )
        
        # 2. 不能删除自己
        if user.user_id == current_user.user_id:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="不能删除自己的账户",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="不能删除自己的账户",
                status_code=400
            )
        
        # 3. 撤销所有活跃会话（安全要求）
        await db.execute(
            update(UserSession)
            .where(
                UserSession.user_id == user_id,
                UserSession.is_active == True
            )
            .values(
                is_active=False,
                revoked_at=datetime.utcnow(),
                revoked_reason="用户已删除"
            )
        )
        
        # 4. 软删除用户
        user.is_active = False
        user.status = "deleted"
        # 注意：如果需要 deleted_at 和 deleted_by 字段，需要先添加数据库迁移
        
        # 5. 记录审计日志（在删除前记录）
        await audit_service.log_action(
            user_id=current_user.user_id,
            action="delete_user",
            resource="user",
            resource_id=str(user.user_id),
            ip_address="127.0.0.1",
            user_agent="Unknown",
            details={
                "username": user.username,
                "email": user.email,
                "reason": reason
            }
        )
        
        await db.commit()
        
        logger.info(f"用户已软删除: user_id={user_id}, username={user.username}, deleted_by={current_user.user_id}")
        
        return success_response(
            data={"user_id": user_id},
            message="用户已删除（软删除，数据已保留用于审计）"
        )
    
    except Exception as e:
        await db.rollback()
        logger.error(f"删除用户失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="删除用户失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限，或联系系统管理员",
            status_code=500
        )

@router.post("/{user_id}/restore")
async def restore_user(
    user_id: int,
    current_user: DimUser = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db)
):
    """
    恢复已删除的用户（软删除恢复）
    
    注意：建议设置恢复期限（如30天），超过期限的用户需要管理员特殊权限才能恢复
    """
    try:
        result = await db.execute(
            select(DimUser).where(DimUser.user_id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="用户不存在",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="请检查用户ID是否正确",
                status_code=404
            )
        
        if user.status != "deleted":
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="用户未被删除",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="该用户未被删除，无需恢复",
                status_code=400
            )
        
        # 恢复用户
        user.status = "active"
        user.is_active = True
        
        # 记录恢复操作
        await audit_service.log_action(
            user_id=current_user.user_id,
            action="restore_user",
            resource="user",
            resource_id=str(user.user_id),
            ip_address="127.0.0.1",
            user_agent="Unknown",
            details={
                "username": user.username,
                "email": user.email
            }
        )
        
        await db.commit()
        
        logger.info(f"用户已恢复: user_id={user_id}, username={user.username}, restored_by={current_user.user_id}")
        
        return success_response(
            data={"user_id": user_id},
            message="用户已恢复"
        )
    
    except Exception as e:
        await db.rollback()
        logger.error(f"恢复用户失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="恢复用户失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限，或联系系统管理员",
            status_code=500
        )

@router.post("/{user_id}/reset-password", response_model=ResetPasswordResponse)
async def reset_user_password(
    user_id: int,
    request_body: ResetPasswordRequest,
    request: Request,
    current_user: DimUser = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db)
):
    """
    重置用户密码（管理员）
    
    v4.19.0新增：支持生成临时密码或指定新密码
    """
    result = await db.execute(select(DimUser).where(DimUser.user_id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message="用户不存在",
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            recovery_suggestion="请检查用户ID是否正确",
            status_code=404
        )
    
    from backend.services.auth_service import auth_service
    import secrets
    import string
    
    # 生成新密码或临时密码
    if request_body.generate_temp_password or not request_body.new_password:
        # 生成临时密码（12位，包含大小写字母、数字和特殊字符）
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        temp_password = ''.join(secrets.choice(alphabet) for i in range(12))
        new_password = temp_password
    else:
        # 使用指定的新密码
        temp_password = None
        new_password = request_body.new_password
        # 验证密码强度
        if len(new_password) < 8:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="密码长度至少8位",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="请使用至少8位的密码",
                status_code=400
            )
    
    # 重置密码
    user.password_hash = auth_service.hash_password(new_password)
    # 重置失败登录计数和锁定状态
    user.failed_login_attempts = 0
    user.locked_until = None
    
    # v4.19.0 P0安全要求：强制撤销用户所有活跃会话
    from backend.routers.notifications import revoke_all_user_sessions, notify_password_reset
    revoked_count = await revoke_all_user_sessions(
        db=db,
        user_id=user.user_id,
        reason="Password reset by administrator, forced logout"
    )
    
    await db.commit()
    
    # 获取真实IP和User-Agent
    ip_address = request.client.host if request.client else "127.0.0.1"
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        ip_address = forwarded_for.split(",")[0].strip()
    user_agent = request.headers.get("User-Agent", "Unknown")
    
    # 记录操作
    await audit_service.log_action(
        user_id=current_user.user_id,
        action="reset_password",
        resource="user",
        resource_id=str(user.user_id),
        ip_address=ip_address,
        user_agent=user_agent,
        details={
            "username": user.username,
            "generated_temp": request_body.generate_temp_password or not request_body.new_password,
            "sessions_revoked": revoked_count
        }
    )
    
    # v4.19.0 P1：发送密码重置通知
    await notify_password_reset(
        db=db,
        user_id=user.user_id,
        reset_by=current_user.username
    )
    await db.commit()
    
    response_data = ResetPasswordResponse(
        user_id=user.user_id,
        username=user.username,
        temp_password=temp_password,
        message="密码重置成功" + ("，临时密码已生成" if temp_password else "")
    )
    
    return success_response(
        data=response_data.dict(),
        message="密码重置成功"
    )

@router.post("/{user_id}/unlock")
async def unlock_user_account(
    user_id: int,
    request_body: UnlockAccountRequest,
    request: Request,
    current_user: DimUser = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db)
):
    """
    解锁用户账户（管理员）
    
    v4.19.0新增：账户锁定机制
    """
    result = await db.execute(select(DimUser).where(DimUser.user_id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message="用户不存在",
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            recovery_suggestion="请检查用户ID是否正确",
            status_code=404
        )
    
    # 检查账户是否被锁定
    from datetime import datetime
    if not user.locked_until or user.locked_until <= datetime.utcnow():
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message="账户未被锁定",
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            recovery_suggestion="该账户当前未被锁定，无需解锁",
            status_code=400
        )
    
    # 解锁账户
    user.locked_until = None
    user.failed_login_attempts = 0
    await db.commit()
    
    # 获取真实IP和User-Agent
    ip_address = request.client.host if request.client else "127.0.0.1"
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        ip_address = forwarded_for.split(",")[0].strip()
    user_agent = request.headers.get("User-Agent", "Unknown")
    
    # 记录操作
    await audit_service.log_action(
        user_id=current_user.user_id,
        action="unlock_account",
        resource="user",
        resource_id=str(user.user_id),
        ip_address=ip_address,
        user_agent=user_agent,
        details={
            "username": user.username,
            "reason": request_body.reason or "Administrator manual unlock"
        }
    )
    
    # v4.19.0 P1：发送账户解锁通知
    from backend.routers.notifications import notify_account_unlocked
    await notify_account_unlocked(
        db=db,
        user_id=user.user_id,
        unlocked_by=current_user.username
    )
    await db.commit()
    
    return success_response(
        data={"user_id": user.user_id, "username": user.username},
        message="账户解锁成功"
    )

# [*] v4.19.4更新：使用基于角色的动态限流（替换硬编码限流）
@router.post("/{user_id}/approve")
@role_based_rate_limit(endpoint_type="default")  # [*] v4.19.4: 基于角色的动态限流
async def approve_user(
    user_id: int,
    request_body: ApproveUserRequest,
    request: Request,  # [*] v4.19.4新增：添加 request 参数用于限流
    current_user: DimUser = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db)
):
    """
    审批用户（将pending状态改为active）
    
    v4.19.0新增：用户审批流程
    """
    # 查找用户（预加载 roles 关系，避免访问时触发懒加载）
    result = await db.execute(
        select(DimUser)
        .where(DimUser.user_id == user_id)
        .options(selectinload(DimUser.roles))
    )
    user = result.scalar_one_or_none()
    if not user:
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message="用户不存在",
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            recovery_suggestion="请检查用户ID是否正确",
            status_code=404
        )
    
    # 检查用户状态（必须是pending）
    if user.status != "pending":
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message=f"只能审批pending状态的用户，当前状态：{user.status}",
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            recovery_suggestion="只能审批待审批状态的用户",
            status_code=400
        )
    
    # 更新用户状态
    from datetime import datetime
    user.status = "active"
    user.is_active = True
    user.approved_at = datetime.utcnow()
    user.approved_by = current_user.user_id
    
    # 分配角色
    if request_body.role_ids:
        # v4.19.0 P1安全要求：验证所有role_ids是否都存在（不能静默忽略）
        result = await db.execute(select(DimRole).where(DimRole.role_id.in_(request_body.role_ids)))
        roles = result.scalars().all()
        found_role_ids = {role.role_id for role in roles}
        requested_role_ids = set(request_body.role_ids)
        
        if found_role_ids != requested_role_ids:
            missing_role_ids = requested_role_ids - found_role_ids
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message=f"以下角色ID不存在: {sorted(missing_role_ids)}",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="请检查角色ID是否正确",
                status_code=400
            )
        
        user.roles.clear()
        user.roles.extend(roles)
    else:
        # 分配默认operator角色
        result = await db.execute(select(DimRole).where(DimRole.role_code == "operator"))
        operator_role = result.scalar_one_or_none()
        if not operator_role:
            return error_response(
                code=ErrorCode.INTERNAL_SERVER_ERROR,
                message="默认operator角色不存在",
                error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
                recovery_suggestion="请联系系统管理员创建operator角色",
                status_code=500
            )
        user.roles.clear()
        user.roles.append(operator_role)
    
    await db.flush()
    # [FIX] AsyncSession 下修改关系后，刷新以确保关系已加载
    await db.refresh(user, ["roles"])
    
    # 记录审批日志（UserApprovalLog）
    approval_log = UserApprovalLog(
        user_id=user.user_id,
        action="approve",
        approved_by=current_user.user_id,
        reason=request_body.notes
    )
    db.add(approval_log)
    
    # 记录审计日志
    ip_address = "127.0.0.1"
    user_agent = "Unknown"
    await audit_service.log_action(
        user_id=current_user.user_id,
        action="user_approved",
        resource="user",
        resource_id=str(user.user_id),
        ip_address=ip_address,
        user_agent=user_agent,
        details={
            "approved_user_id": user.user_id,
            "approved_username": user.username,
            "role_ids": request_body.role_ids if request_body.role_ids else ["operator"],
            "notes": request_body.notes
        }
    )
    
    # v4.19.0: 通知用户审批通过
    from backend.routers.notifications import notify_user_approved
    await notify_user_approved(
        db=db,
        user_id=user.user_id,
        approved_by=current_user.username
    )
    
    await db.commit()
    await db.refresh(user)
    
    return success_response(
        data={
            "user_id": user.user_id,
            "username": user.username,
            "status": user.status
        },
        message="用户审批成功"
    )

# [*] v4.19.4更新：使用基于角色的动态限流（替换硬编码限流）
@router.post("/{user_id}/reject")
@role_based_rate_limit(endpoint_type="default")  # [*] v4.19.4: 基于角色的动态限流
async def reject_user(
    user_id: int,
    request_body: RejectUserRequest,
    request: Request,  # [*] v4.19.4新增：添加 request 参数用于限流
    current_user: DimUser = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db)
):
    """
    拒绝用户（将pending状态改为rejected）
    
    v4.19.0新增：用户审批流程
    """
    # 查找用户
    result = await db.execute(select(DimUser).where(DimUser.user_id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message="用户不存在",
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            recovery_suggestion="请检查用户ID是否正确",
            status_code=404
        )
    
    # 检查用户状态（必须是pending）
    if user.status != "pending":
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message=f"只能拒绝pending状态的用户，当前状态：{user.status}",
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            recovery_suggestion="只能拒绝待审批状态的用户",
            status_code=400
        )
    
    # 更新用户状态
    user.status = "rejected"
    user.is_active = False
    user.rejection_reason = request_body.reason
    user.approved_by = current_user.user_id
    
    await db.flush()
    
    # 记录审批日志（UserApprovalLog）
    approval_log = UserApprovalLog(
        user_id=user.user_id,
        action="reject",
        approved_by=current_user.user_id,
        reason=request_body.reason
    )
    db.add(approval_log)
    
    # 记录审计日志
    ip_address = "127.0.0.1"
    user_agent = "Unknown"
    await audit_service.log_action(
        user_id=current_user.user_id,
        action="user_rejected",
        resource="user",
        resource_id=str(user.user_id),
        ip_address=ip_address,
        user_agent=user_agent,
        details={
            "rejected_user_id": user.user_id,
            "rejected_username": user.username,
            "reason": request_body.reason
        }
    )
    
    # v4.19.0: 通知用户审批被拒绝
    from backend.routers.notifications import notify_user_rejected
    await notify_user_rejected(
        db=db,
        user_id=user.user_id,
        rejected_by=current_user.username,
        reason=request_body.reason
    )
    
    await db.commit()
    
    return success_response(
        data={
            "user_id": user.user_id,
            "username": user.username,
            "status": user.status
        },
        message="用户已拒绝"
    )

# v4.19.0 P1安全要求：待审批用户列表API限流装饰器（条件应用）
# [*] v4.19.4更新：使用基于角色的动态限流（替换硬编码限流）
@router.get("/pending", response_model=List[PendingUserResponse])
@role_based_rate_limit(endpoint_type="default")  # [*] v4.19.4: 基于角色的动态限流
async def get_pending_users(
    request: Request,  # [*] v4.19.4新增：添加 request 参数用于限流（必须放在有默认值参数之前）
    page: int = 1,
    page_size: int = 20,
    current_user: DimUser = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db)
):
    """
    获取待审批用户列表
    
    v4.19.0新增：用户审批流程
    """
    from sqlalchemy import func
    
    # 分页查询
    offset = (page - 1) * page_size
    result = await db.execute(
        select(DimUser)
        .where(DimUser.status == "pending")
        .order_by(DimUser.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    users = result.scalars().all()
    
    return [
        PendingUserResponse(
            user_id=user.user_id,
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            department=user.department,
            status=user.status,  # v4.19.0 P2隐私要求：添加status字段
            created_at=user.created_at
        )
        for user in users
    ]

# ========== Phase 7: 会话管理 API (v4.19.0) ==========

@router.get("/me/sessions", response_model=List[UserSessionResponse])
async def get_my_sessions(
    request: Request,
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    获取当前用户的所有活跃会话
    
    v4.19.0新增：会话管理功能
    """
    from datetime import datetime
    import hashlib
    
    # 获取当前会话ID（从token计算）
    token = None
    if "access_token" in request.cookies:
        token = request.cookies.get("access_token")
    elif request.headers.get("Authorization", "").startswith("Bearer "):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
    
    current_session_id = None
    if token:
        current_session_id = hashlib.sha256(token.encode()).hexdigest()
    
    # 查询所有活跃会话（未过期且未撤销）
    result = await db.execute(
        select(UserSession)
        .where(
            UserSession.user_id == current_user.user_id,
            UserSession.is_active == True,
            UserSession.expires_at > datetime.utcnow()
        )
        .order_by(UserSession.last_active_at.desc())
    )
    sessions = result.scalars().all()
    
    # 转换为响应格式
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
    """
    撤销指定会话（强制登出其他设备）
    
    v4.19.0新增：会话管理功能
    """
    from datetime import datetime
    
    # 查找会话
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
    
    if not session.is_active or session.expires_at <= datetime.utcnow():
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message="会话已失效",
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            recovery_suggestion="该会话已过期或已被撤销",
            status_code=400
        )
    
    # 撤销会话
    session.is_active = False
    session.revoked_at = datetime.utcnow()
    session.revoked_reason = "用户手动撤销"
    await db.commit()
    
    # 获取真实IP和User-Agent
    ip_address = request.client.host if request.client else "127.0.0.1"
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        ip_address = forwarded_for.split(",")[0].strip()
    user_agent = request.headers.get("User-Agent", "Unknown")
    
    # 记录操作
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
    """
    撤销除当前会话外的所有会话
    
    v4.19.0新增：会话管理功能
    """
    from datetime import datetime
    import hashlib
    
    # 获取当前会话ID
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
    
    # 撤销除当前会话外的所有活跃会话
    result = await db.execute(
        select(UserSession)
        .where(
            UserSession.user_id == current_user.user_id,
            UserSession.session_id != current_session_id,
            UserSession.is_active == True,
            UserSession.expires_at > datetime.utcnow()
        )
    )
    sessions = result.scalars().all()
    
    revoked_count = 0
    for session in sessions:
        session.is_active = False
        session.revoked_at = datetime.utcnow()
        session.revoked_reason = "用户撤销所有其他会话"
        revoked_count += 1
    
    await db.commit()
    
    # 获取真实IP和User-Agent
    ip_address = request.client.host if request.client else "127.0.0.1"
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        ip_address = forwarded_for.split(",")[0].strip()
    user_agent = request.headers.get("User-Agent", "Unknown")
    
    # 记录操作
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


# v4.19.0: 用户通知偏好 API

# [*] v4.19.4更新：使用基于角色的动态限流（替换硬编码限流）
@router.get("/me/notification-preferences", response_model=NotificationPreferenceListResponse)
@role_based_rate_limit(endpoint_type="default")  # [*] v4.19.4: 基于角色的动态限流
async def get_notification_preferences(
    request: Request,  # [*] v4.19.4新增：添加 request 参数用于限流
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    获取当前用户所有通知偏好
    
    v4.19.0 P1安全要求：仅允许用户访问自己的偏好（自动通过 current_user 验证）
    """
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
@role_based_rate_limit(endpoint_type="default")  # [*] v4.19.4: 基于角色的动态限流
async def update_notification_preferences(
    batch_update: NotificationPreferenceBatchUpdate,
    request: Request,  # [*] v4.19.4新增：添加 request 参数用于限流
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    批量更新通知偏好
    
    v4.19.0 P1安全要求：
    - 验证所有偏好记录的 user_id 必须等于 current_user.user_id
    - 禁止从请求中获取 user_id，必须使用 current_user.user_id
    """
    updated_preferences = []
    
    for update_data in batch_update.preferences:
        # 查询或创建偏好记录
        result = await db.execute(
            select(UserNotificationPreference)
            .where(
                UserNotificationPreference.user_id == current_user.user_id,
                UserNotificationPreference.notification_type == update_data.notification_type
            )
        )
        preference = result.scalar_one_or_none()
        
        if preference:
            # 更新现有记录
            if update_data.enabled is not None:
                preference.enabled = update_data.enabled
            if update_data.desktop_enabled is not None:
                preference.desktop_enabled = update_data.desktop_enabled
        else:
            # 创建新记录
            preference = UserNotificationPreference(
                user_id=current_user.user_id,  # v4.19.0 P1安全要求：使用 current_user.user_id
                notification_type=update_data.notification_type,
                enabled=update_data.enabled if update_data.enabled is not None else True,
                desktop_enabled=update_data.desktop_enabled if update_data.desktop_enabled is not None else False
            )
            db.add(preference)
        
        updated_preferences.append(preference)
    
    await db.commit()
    
    # 刷新所有更新的记录
    for pref in updated_preferences:
        await db.refresh(pref)
    
    items = [NotificationPreferenceResponse.model_validate(p) for p in updated_preferences]
    
    return NotificationPreferenceListResponse(
        items=items,
        total=len(items)
    )


@router.get("/me/notification-preferences/{notification_type}", response_model=NotificationPreferenceResponse)
@role_based_rate_limit(endpoint_type="default")  # [*] v4.19.4: 基于角色的动态限流
async def get_notification_preference(
    notification_type: str,
    request: Request,  # [*] v4.19.4新增：添加 request 参数用于限流
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    获取特定类型通知偏好
    
    v4.19.0 P1安全要求：查询时验证 user_id == current_user.user_id
    """
    result = await db.execute(
        select(UserNotificationPreference)
        .where(
            UserNotificationPreference.user_id == current_user.user_id,
            UserNotificationPreference.notification_type == notification_type
        )
    )
    preference = result.scalar_one_or_none()
    
    if not preference:
        # 返回默认偏好
        return NotificationPreferenceResponse(
            preference_id=0,
            user_id=current_user.user_id,
            notification_type=notification_type,
            enabled=True,
            desktop_enabled=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
    
    return NotificationPreferenceResponse.model_validate(preference)


@router.put("/me/notification-preferences/{notification_type}", response_model=NotificationPreferenceResponse)
@role_based_rate_limit(endpoint_type="default")  # [*] v4.19.4: 基于角色的动态限流
async def update_notification_preference(
    notification_type: str,
    update_data: NotificationPreferenceUpdate,
    request: Request,  # [*] v4.19.4新增：添加 request 参数用于限流
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    更新特定类型通知偏好
    
    v4.19.0 P1安全要求：
    - 查询偏好时验证 user_id == current_user.user_id
    - 创建新偏好时使用 current_user.user_id，不能从请求中获取
    """
    result = await db.execute(
        select(UserNotificationPreference)
        .where(
            UserNotificationPreference.user_id == current_user.user_id,
            UserNotificationPreference.notification_type == notification_type
        )
    )
    preference = result.scalar_one_or_none()
    
    if preference:
        # 更新现有记录
        if update_data.enabled is not None:
            preference.enabled = update_data.enabled
        if update_data.desktop_enabled is not None:
            preference.desktop_enabled = update_data.desktop_enabled
        await db.commit()
        await db.refresh(preference)
    else:
        # 创建新记录
        preference = UserNotificationPreference(
            user_id=current_user.user_id,  # v4.19.0 P1安全要求：使用 current_user.user_id
            notification_type=notification_type,
            enabled=update_data.enabled if update_data.enabled is not None else True,
            desktop_enabled=update_data.desktop_enabled if update_data.desktop_enabled is not None else False
        )
        db.add(preference)
        await db.commit()
        await db.refresh(preference)
    
    return NotificationPreferenceResponse.model_validate(preference)
