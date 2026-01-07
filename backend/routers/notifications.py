"""
通知管理API路由 (v4.19.0)

提供通知的CRUD操作和状态管理
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, delete, and_, Integer
from sqlalchemy.orm import selectinload
from typing import List, Optional
from datetime import datetime

from backend.models.database import get_async_db
from modules.core.db import DimUser, Notification, DimRole, user_roles
from backend.schemas.notification import (
    NotificationType,
    NotificationPriority,
    NotificationCreate,
    NotificationResponse,
    NotificationListResponse,
    UnreadCountResponse,
    MarkReadRequest,
    MarkReadResponse,
    NotificationDeleteResponse,
    NotificationBatchCreate,
    NotificationAction,
    NotificationActionRequest,
    NotificationActionResponse,
    NotificationGroupItem,
    NotificationGroupListResponse,
)
from backend.routers.auth import get_current_user
from backend.utils.api_response import success_response, error_response
from backend.utils.error_codes import ErrorCode, get_error_type
from modules.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/notifications", tags=["通知管理"])


# v4.19.0: 快速操作配置生成
def generate_notification_actions(notification_type: str, related_user_id: Optional[int], current_user: DimUser) -> Optional[List[NotificationAction]]:
    """
    根据通知类型生成快速操作按钮配置
    
    v4.19.0 P0安全要求：只有管理员才能看到审批操作
    """
    # 检查用户是否是管理员
    is_admin = current_user.is_superuser or any(
        (hasattr(role, "role_code") and role.role_code == "admin") or
        (hasattr(role, "role_name") and role.role_name == "admin")
        for role in current_user.roles
    )
    
    if notification_type == "user_registered" and related_user_id and is_admin:
        # 新用户注册通知 - 管理员可以快速批准/拒绝
        return [
            NotificationAction(
                action_type="approve_user",
                label="Approve",
                icon="CircleCheck",
                style="success",
                confirm=True,
                confirm_message="Are you sure you want to approve this user?"
            ),
            NotificationAction(
                action_type="reject_user",
                label="Reject",
                icon="CircleClose",
                style="danger",
                confirm=True,
                confirm_message="Are you sure you want to reject this user? Please provide a reason."
            )
        ]
    
    # 其他通知类型暂不支持快速操作
    return None


@router.get("", response_model=NotificationListResponse)
async def get_notifications(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    is_read: Optional[bool] = Query(None, description="过滤已读/未读"),
    notification_type: Optional[str] = Query(None, description="过滤通知类型"),
    priority: Optional[str] = Query(None, description="过滤优先级：high, medium, low"),
    sort_by: Optional[str] = Query("created_at", description="排序字段：created_at, priority"),
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    获取当前用户的通知列表
    
    支持分页、过滤和排序
    v4.19.0: 新增优先级过滤和排序
    """
    # 构建查询
    query = select(Notification).where(
        Notification.recipient_id == current_user.user_id
    )
    
    # 应用过滤条件
    if is_read is not None:
        query = query.where(Notification.is_read == is_read)
    
    if notification_type:
        query = query.where(Notification.notification_type == notification_type)
    
    # v4.19.0: 优先级过滤（带验证）
    if priority:
        valid_priorities = ["high", "medium", "low"]
        if priority.lower() in valid_priorities:
            query = query.where(Notification.priority == priority.lower())
        # 无效优先级值静默忽略（不报错）
    
    # 计算总数
    count_query = select(func.count()).select_from(query.subquery())
    result = await db.execute(count_query)
    total = result.scalar() or 0
    
    # 获取未读数量
    unread_query = select(func.count()).where(
        and_(
            Notification.recipient_id == current_user.user_id,
            Notification.is_read == False
        )
    )
    result = await db.execute(unread_query)
    unread_count = result.scalar() or 0
    
    # v4.19.0: 排序逻辑
    # 优先级排序：high > medium > low
    from sqlalchemy import case
    priority_order = case(
        (Notification.priority == "high", 1),
        (Notification.priority == "medium", 2),
        (Notification.priority == "low", 3),
        else_=2  # 默认 medium
    )
    
    if sort_by == "priority":
        query = query.order_by(priority_order, Notification.created_at.desc())
    else:
        # 默认按时间排序，但高优先级置顶
        query = query.order_by(priority_order, Notification.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    notifications = result.scalars().all()
    
    # 转换为响应模型
    items = []
    for n in notifications:
        # 获取关联用户名（如果有）
        related_username = None
        if n.related_user_id:
            user_result = await db.execute(
                select(DimUser.username).where(DimUser.user_id == n.related_user_id)
            )
            related_username = user_result.scalar_one_or_none()
        
        # v4.19.0: 生成快速操作按钮
        actions = generate_notification_actions(n.notification_type, n.related_user_id, current_user)
        
        items.append(NotificationResponse(
            notification_id=n.notification_id,
            recipient_id=n.recipient_id,
            notification_type=n.notification_type,
            title=n.title,
            content=n.content,
            extra_data=n.extra_data,
            related_user_id=n.related_user_id,
            is_read=n.is_read,
            read_at=n.read_at,
            created_at=n.created_at,
            priority=getattr(n, 'priority', 'medium'),  # v4.19.0
            related_username=related_username,
            actions=actions
        ))
    
    return NotificationListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        unread_count=unread_count
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    获取当前用户的未读通知数量
    
    用于前端轮询更新通知图标
    """
    query = select(func.count()).where(
        and_(
            Notification.recipient_id == current_user.user_id,
            Notification.is_read == False
        )
    )
    result = await db.execute(query)
    unread_count = result.scalar() or 0
    
    return UnreadCountResponse(unread_count=unread_count)


# v4.19.0: 通知类型显示名称映射
NOTIFICATION_TYPE_LABELS = {
    "user_registered": "New User Registration",
    "user_approved": "Account Approved",
    "user_rejected": "Account Rejected",
    "user_suspended": "Account Suspended",
    "password_reset": "Password Reset",
    "account_locked": "Account Locked",
    "account_unlocked": "Account Unlocked",
    "system_alert": "System Alert"
}


@router.get("/grouped", response_model=NotificationGroupListResponse)
async def get_notifications_grouped(
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    获取按类型分组的通知列表
    
    v4.19.0: 返回每个类型的统计信息和最新通知
    """
    # 按类型分组统计
    group_query = select(
        Notification.notification_type,
        func.count(Notification.notification_id).label('total_count'),
        func.sum(func.cast(~Notification.is_read, Integer)).label('unread_count')
    ).where(
        Notification.recipient_id == current_user.user_id
    ).group_by(
        Notification.notification_type
    )
    
    result = await db.execute(group_query)
    group_stats = result.all()
    
    groups = []
    total_count = 0
    total_unread = 0
    
    for notification_type, count, unread in group_stats:
        total_count += count
        total_unread += unread or 0
        
        # 获取该类型的最新通知
        latest_query = select(Notification).where(
            and_(
                Notification.recipient_id == current_user.user_id,
                Notification.notification_type == notification_type
            )
        ).order_by(Notification.created_at.desc()).limit(1)
        
        result = await db.execute(latest_query)
        latest = result.scalar_one_or_none()
        
        latest_response = None
        if latest:
            # 获取关联用户名
            related_username = None
            if latest.related_user_id:
                user_result = await db.execute(
                    select(DimUser.username).where(DimUser.user_id == latest.related_user_id)
                )
                related_username = user_result.scalar_one_or_none()
            
            # 生成快速操作
            actions = generate_notification_actions(latest.notification_type, latest.related_user_id, current_user)
            
            latest_response = NotificationResponse(
                notification_id=latest.notification_id,
                recipient_id=latest.recipient_id,
                notification_type=latest.notification_type,
                title=latest.title,
                content=latest.content,
                extra_data=latest.extra_data,
                related_user_id=latest.related_user_id,
                is_read=latest.is_read,
                read_at=latest.read_at,
                created_at=latest.created_at,
                related_username=related_username,
                actions=actions
            )
        
        groups.append(NotificationGroupItem(
            notification_type=notification_type,
            type_label=NOTIFICATION_TYPE_LABELS.get(notification_type, notification_type),
            total_count=count,
            unread_count=unread or 0,
            latest_notification=latest_response
        ))
    
    # 按未读数量降序排列
    groups.sort(key=lambda x: (-x.unread_count, -x.total_count))
    
    return NotificationGroupListResponse(
        groups=groups,
        total_count=total_count,
        total_unread=total_unread
    )


@router.get("/{notification_id}", response_model=NotificationResponse)
async def get_notification(
    notification_id: int,
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """获取单个通知详情"""
    query = select(Notification).where(
        and_(
            Notification.notification_id == notification_id,
            Notification.recipient_id == current_user.user_id
        )
    )
    result = await db.execute(query)
    notification = result.scalar_one_or_none()
    
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    # 获取关联用户名
    related_username = None
    if notification.related_user_id:
        user_result = await db.execute(
            select(DimUser.username).where(DimUser.user_id == notification.related_user_id)
        )
        related_username = user_result.scalar_one_or_none()
    
    return NotificationResponse(
        notification_id=notification.notification_id,
        recipient_id=notification.recipient_id,
        notification_type=notification.notification_type,
        title=notification.title,
        content=notification.content,
        extra_data=notification.extra_data,
        related_user_id=notification.related_user_id,
        is_read=notification.is_read,
        read_at=notification.read_at,
        created_at=notification.created_at,
        related_username=related_username
    )


@router.put("/{notification_id}/read", response_model=MarkReadResponse)
async def mark_notification_read(
    notification_id: int,
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """标记单个通知为已读"""
    # 检查通知是否存在且属于当前用户
    query = select(Notification).where(
        and_(
            Notification.notification_id == notification_id,
            Notification.recipient_id == current_user.user_id
        )
    )
    result = await db.execute(query)
    notification = result.scalar_one_or_none()
    
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    if notification.is_read:
        return MarkReadResponse(
            marked_count=0,
            message="Notification already read"
        )
    
    # 更新为已读
    notification.is_read = True
    notification.read_at = datetime.utcnow()
    await db.commit()
    
    return MarkReadResponse(
        marked_count=1,
        message="Notification marked as read"
    )


@router.put("/read-all", response_model=MarkReadResponse)
async def mark_all_read(
    request: MarkReadRequest = None,
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    标记通知为已读
    
    - 如果提供 notification_ids，则标记指定通知
    - 如果不提供或为空，则标记所有未读通知
    """
    now = datetime.utcnow()
    
    if request and request.notification_ids:
        # 标记指定通知
        stmt = (
            update(Notification)
            .where(
                and_(
                    Notification.notification_id.in_(request.notification_ids),
                    Notification.recipient_id == current_user.user_id,
                    Notification.is_read == False
                )
            )
            .values(is_read=True, read_at=now)
        )
    else:
        # 标记所有未读通知
        stmt = (
            update(Notification)
            .where(
                and_(
                    Notification.recipient_id == current_user.user_id,
                    Notification.is_read == False
                )
            )
            .values(is_read=True, read_at=now)
        )
    
    result = await db.execute(stmt)
    await db.commit()
    
    marked_count = result.rowcount
    
    return MarkReadResponse(
        marked_count=marked_count,
        message=f"Marked {marked_count} notifications as read"
    )


@router.delete("/{notification_id}", response_model=NotificationDeleteResponse)
async def delete_notification(
    notification_id: int,
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """删除单个通知"""
    # 检查通知是否存在且属于当前用户
    stmt = delete(Notification).where(
        and_(
            Notification.notification_id == notification_id,
            Notification.recipient_id == current_user.user_id
        )
    )
    result = await db.execute(stmt)
    await db.commit()
    
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    return NotificationDeleteResponse(
        deleted_count=1,
        message="Notification deleted"
    )


@router.delete("", response_model=NotificationDeleteResponse)
async def delete_all_read_notifications(
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """删除所有已读通知"""
    stmt = delete(Notification).where(
        and_(
            Notification.recipient_id == current_user.user_id,
            Notification.is_read == True
        )
    )
    result = await db.execute(stmt)
    await db.commit()
    
    return NotificationDeleteResponse(
        deleted_count=result.rowcount,
        message=f"Deleted {result.rowcount} read notifications"
    )


# ==================== v4.19.0: 快速操作 API ====================

from backend.services.audit_service import audit_service
from fastapi import Request

@router.post("/{notification_id}/action", response_model=NotificationActionResponse)
async def execute_notification_action(
    notification_id: int,
    action_request: NotificationActionRequest,
    request: Request,
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    执行通知快速操作
    
    v4.19.0 P0安全要求：
    - 验证用户权限
    - 验证目标资源状态
    - 记录审计日志
    - 防止权限绕过
    """
    # 1. 获取通知
    result = await db.execute(
        select(Notification).where(Notification.notification_id == notification_id)
    )
    notification = result.scalar_one_or_none()
    
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    # 2. 验证通知属于当前用户
    if notification.recipient_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # 3. 验证操作类型
    action_type = action_request.action_type
    if action_type not in ["approve_user", "reject_user"]:
        raise HTTPException(status_code=400, detail=f"Unsupported action type: {action_type}")
    
    # 4. 验证权限 - 只有管理员可以执行审批操作
    is_admin = current_user.is_superuser or any(
        (hasattr(role, "role_code") and role.role_code == "admin") or
        (hasattr(role, "role_name") and role.role_name == "admin")
        for role in current_user.roles
    )
    
    if action_type in ["approve_user", "reject_user"] and not is_admin:
        raise HTTPException(status_code=403, detail="Admin permission required")
    
    # 5. 验证目标用户存在且状态正确
    target_user_id = notification.related_user_id
    if not target_user_id:
        raise HTTPException(status_code=400, detail="No target user associated with this notification")
    
    result = await db.execute(
        select(DimUser).where(DimUser.user_id == target_user_id)
    )
    target_user = result.scalar_one_or_none()
    
    if not target_user:
        raise HTTPException(status_code=404, detail="Target user not found")
    
    if target_user.status != "pending":
        raise HTTPException(
            status_code=400, 
            detail=f"User status is '{target_user.status}', can only operate on 'pending' users"
        )
    
    # 6. 获取请求信息（用于审计日志）
    ip_address = request.client.host if request.client else "127.0.0.1"
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        ip_address = forwarded_for.split(",")[0].strip()
    user_agent = request.headers.get("User-Agent", "Unknown")
    
    # 7. 执行操作
    if action_type == "approve_user":
        # 批准用户
        target_user.status = "active"
        target_user.is_active = True
        target_user.approved_at = datetime.utcnow()
        target_user.approved_by = current_user.user_id
        
        await db.commit()
        
        # 记录审计日志
        await audit_service.log_action(
            user_id=current_user.user_id,
            action="approve_user_quick",
            resource="user",
            resource_id=str(target_user_id),
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                "notification_id": notification_id,
                "target_user_id": target_user_id,
                "target_username": target_user.username
            }
        )
        
        # 发送通知给用户
        await create_notification(
            db=db,
            recipient_id=target_user_id,
            notification_type=NotificationType.USER_APPROVED,
            title="Account Approved",
            content="Your account has been approved. You can now log in.",
            related_user_id=current_user.user_id
        )
        
        # 标记当前通知为已读
        notification.is_read = True
        notification.read_at = datetime.utcnow()
        await db.commit()
        
        return NotificationActionResponse(
            success=True,
            message=f"User '{target_user.username}' has been approved",
            notification_id=notification_id,
            action_type=action_type,
            target_user_id=target_user_id
        )
    
    elif action_type == "reject_user":
        # 拒绝用户
        reason = action_request.reason or "Rejected by administrator"
        
        target_user.status = "rejected"
        target_user.is_active = False
        target_user.rejection_reason = reason
        target_user.approved_by = current_user.user_id
        
        await db.commit()
        
        # 记录审计日志
        await audit_service.log_action(
            user_id=current_user.user_id,
            action="reject_user_quick",
            resource="user",
            resource_id=str(target_user_id),
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                "notification_id": notification_id,
                "target_user_id": target_user_id,
                "target_username": target_user.username,
                "reason": reason
            }
        )
        
        # 发送通知给用户
        await create_notification(
            db=db,
            recipient_id=target_user_id,
            notification_type=NotificationType.USER_REJECTED,
            title="Account Rejected",
            content=f"Your account registration has been rejected. Reason: {reason}",
            related_user_id=current_user.user_id
        )
        
        # 标记当前通知为已读
        notification.is_read = True
        notification.read_at = datetime.utcnow()
        await db.commit()
        
        return NotificationActionResponse(
            success=True,
            message=f"User '{target_user.username}' has been rejected",
            notification_id=notification_id,
            action_type=action_type,
            target_user_id=target_user_id
        )


# ==================== 通知服务函数（内部使用）====================

async def create_notification(
    db: AsyncSession,
    recipient_id: int,
    notification_type: NotificationType,
    title: str,
    content: str,
    extra_data: dict = None,
    related_user_id: int = None,
    priority: str = "medium"
) -> Notification:
    """
    创建单个通知（内部使用）
    
    Args:
        db: 数据库会话
        recipient_id: 接收者用户ID
        notification_type: 通知类型
        title: 通知标题
        content: 通知内容
        extra_data: 扩展数据
        related_user_id: 关联用户ID
        priority: 优先级（high, medium, low），v4.19.0新增
    
    Returns:
        创建的通知对象
    """
    # v4.19.0: 验证优先级
    valid_priorities = ["high", "medium", "low"]
    if priority.lower() not in valid_priorities:
        priority = "medium"  # 无效值使用默认
    
    notification = Notification(
        recipient_id=recipient_id,
        notification_type=notification_type.value if isinstance(notification_type, NotificationType) else notification_type,
        title=title,
        content=content,
        extra_data=extra_data,
        related_user_id=related_user_id,
        priority=priority.lower()
    )
    db.add(notification)
    await db.flush()
    return notification


async def create_notifications_for_admins(
    db: AsyncSession,
    notification_type: NotificationType,
    title: str,
    content: str,
    extra_data: dict = None,
    related_user_id: int = None,
    priority: str = "medium"
) -> List[Notification]:
    """
    为所有管理员创建通知（内部使用）
    
    Args:
        db: 数据库会话
        notification_type: 通知类型
        title: 通知标题
        content: 通知内容
        extra_data: 扩展数据
        related_user_id: 关联用户ID
        priority: 优先级（high, medium, low），v4.19.0新增
    
    Returns:
        创建的通知列表
    """
    # 查询所有管理员（is_superuser=True 或角色为 admin）
    from modules.core.db import DimRole, user_roles
    
    # 方法1：查询 is_superuser=True 的用户
    superuser_query = select(DimUser.user_id).where(DimUser.is_superuser == True)
    result = await db.execute(superuser_query)
    admin_ids = set(result.scalars().all())
    
    # 方法2：查询角色为 admin 的用户
    admin_role_query = (
        select(user_roles.c.user_id)
        .join(DimRole, user_roles.c.role_id == DimRole.role_id)
        .where(DimRole.role_code == "admin")
    )
    result = await db.execute(admin_role_query)
    admin_ids.update(result.scalars().all())
    
    if not admin_ids:
        logger.warning("[WARN] No admin users found for notification")
        return []
    
    # 为每个管理员创建通知
    notifications = []
    for admin_id in admin_ids:
        notification = await create_notification(
            db=db,
            recipient_id=admin_id,
            notification_type=notification_type,
            title=title,
            content=content,
            extra_data=extra_data,
            related_user_id=related_user_id,
            priority=priority
        )
        notifications.append(notification)
    
    logger.info(f"[OK] Created {len(notifications)} notifications for admins")
    return notifications


async def notify_user_registered(
    db: AsyncSession,
    user_id: int,
    username: str,
    email: str
) -> List[Notification]:
    """
    新用户注册时通知管理员
    
    Args:
        db: 数据库会话
        user_id: 新注册用户的ID
        username: 用户名
        email: 邮箱
    
    Returns:
        创建的通知列表
    """
    # v4.19.0: 新用户注册使用高优先级
    notifications = await create_notifications_for_admins(
        db=db,
        notification_type=NotificationType.USER_REGISTERED,
        title="New User Registration",
        content=f"User '{username}' ({email}) has registered and is waiting for approval.",
        extra_data={
            "user_id": user_id,
            "username": username,
            "email": email,
            "registered_at": datetime.utcnow().isoformat()
        },
        related_user_id=user_id,
        priority="high"
    )
    
    # v4.19.0: WebSocket 实时推送
    try:
        from backend.routers.notification_websocket import connection_manager, NotificationMessage
        
        # 获取所有管理员ID
        admin_ids = set()
        
        # 查询 is_superuser=True 的用户
        superuser_query = select(DimUser.user_id).where(DimUser.is_superuser == True)
        result = await db.execute(superuser_query)
        admin_ids.update(result.scalars().all())
        
        # 查询角色为 admin 的用户
        admin_role_query = (
            select(user_roles.c.user_id)
            .join(DimRole, user_roles.c.role_id == DimRole.role_id)
            .where(DimRole.role_code == "admin")
        )
        result = await db.execute(admin_role_query)
        admin_ids.update(result.scalars().all())
        
        # 批量推送通知
        if admin_ids and notifications:
            for notification in notifications:
                notification_msg = NotificationMessage(
                    notification_id=notification.notification_id,
                    recipient_id=notification.recipient_id,
                    notification_type=notification.notification_type,
                    title=notification.title,
                    content=notification.content,
                    extra_data=notification.extra_data,
                    related_user_id=notification.related_user_id,
                    created_at=notification.created_at.isoformat()
                )
                await connection_manager.send_notification(notification.recipient_id, notification_msg)
    except Exception as e:
        logger.warning(f"[WS] Failed to push notification via WebSocket: {e}")
    
    return notifications


async def notify_user_approved(
    db: AsyncSession,
    user_id: int,
    approved_by: str
) -> Notification:
    """
    用户审批通过时通知用户
    
    Args:
        db: 数据库会话
        user_id: 被批准用户的ID
        approved_by: 批准者用户名
    
    Returns:
        创建的通知
    """
    notification = await create_notification(
        db=db,
        recipient_id=user_id,
        notification_type=NotificationType.USER_APPROVED,
        title="Account Approved",
        content="Your account has been approved. You can now log in to the system.",
        extra_data={
            "approved_by": approved_by,
            "approved_at": datetime.utcnow().isoformat()
        }
    )
    
    # v4.19.0: WebSocket 实时推送
    try:
        from backend.routers.notification_websocket import connection_manager, NotificationMessage
        
        # v4.19.0 P0安全要求：推送前验证 recipient_id 与连接用户 ID 匹配
        notification_msg = NotificationMessage(
            notification_id=notification.notification_id,
            recipient_id=notification.recipient_id,
            notification_type=notification.notification_type,
            title=notification.title,
            content=notification.content,
            extra_data=notification.extra_data,
            related_user_id=notification.related_user_id,
            created_at=notification.created_at.isoformat()
        )
        await connection_manager.send_notification(user_id, notification_msg)
    except Exception as e:
        logger.warning(f"[WS] Failed to push notification via WebSocket: {e}")
    
    return notification


async def notify_user_rejected(
    db: AsyncSession,
    user_id: int,
    rejected_by: str,
    reason: str = None
) -> Notification:
    """
    用户审批拒绝时通知用户
    
    Args:
        db: 数据库会话
        user_id: 被拒绝用户的ID
        rejected_by: 拒绝者用户名
        reason: 拒绝原因
    
    Returns:
        创建的通知
    """
    content = "Your account registration has been rejected."
    if reason:
        content += f" Reason: {reason}"
    
    notification = await create_notification(
        db=db,
        recipient_id=user_id,
        notification_type=NotificationType.USER_REJECTED,
        title="Account Rejected",
        content=content,
        extra_data={
            "rejected_by": rejected_by,
            "rejected_at": datetime.utcnow().isoformat(),
            "reason": reason
        }
    )
    
    # v4.19.0: WebSocket 实时推送
    try:
        from backend.routers.notification_websocket import connection_manager, NotificationMessage
        
        # v4.19.0 P0安全要求：推送前验证 recipient_id 与连接用户 ID 匹配
        notification_msg = NotificationMessage(
            notification_id=notification.notification_id,
            recipient_id=notification.recipient_id,
            notification_type=notification.notification_type,
            title=notification.title,
            content=notification.content,
            extra_data=notification.extra_data,
            related_user_id=notification.related_user_id,
            created_at=notification.created_at.isoformat()
        )
        await connection_manager.send_notification(user_id, notification_msg)
    except Exception as e:
        logger.warning(f"[WS] Failed to push notification via WebSocket: {e}")
    
    return notification


async def notify_password_reset(
    db: AsyncSession,
    user_id: int,
    reset_by: str
) -> Notification:
    """
    密码重置时通知用户
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        reset_by: 重置者用户名
    
    Returns:
        创建的通知
    """
    notification = await create_notification(
        db=db,
        recipient_id=user_id,
        notification_type=NotificationType.PASSWORD_RESET,
        title="Password Reset",
        content="Your password has been reset by an administrator. Please change it after logging in.",
        extra_data={
            "reset_by": reset_by,
            "reset_at": datetime.utcnow().isoformat()
        }
    )
    
    # v4.19.0: WebSocket 实时推送
    try:
        from backend.routers.notification_websocket import connection_manager, NotificationMessage
        
        notification_msg = NotificationMessage(
            notification_id=notification.notification_id,
            recipient_id=notification.recipient_id,
            notification_type=notification.notification_type,
            title=notification.title,
            content=notification.content,
            extra_data=notification.extra_data,
            related_user_id=notification.related_user_id,
            created_at=notification.created_at.isoformat()
        )
        await connection_manager.send_notification(user_id, notification_msg)
    except Exception as e:
        logger.warning(f"[WS] Failed to push notification via WebSocket: {e}")
    
    return notification


async def notify_account_locked(
    db: AsyncSession,
    user_id: int,
    locked_minutes: int,
    failed_attempts: int
) -> Notification:
    """
    账户被锁定时通知用户 (v4.19.0)
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        locked_minutes: 锁定时长（分钟）
        failed_attempts: 失败登录次数
    
    Returns:
        创建的通知
    """
    notification = await create_notification(
        db=db,
        recipient_id=user_id,
        notification_type=NotificationType.ACCOUNT_LOCKED,
        title="Account Locked",
        content=f"Your account has been locked for {locked_minutes} minutes due to {failed_attempts} failed login attempts.",
        extra_data={
            "locked_minutes": locked_minutes,
            "failed_attempts": failed_attempts,
            "locked_at": datetime.utcnow().isoformat()
        }
    )
    
    # v4.19.0: WebSocket 实时推送
    try:
        from backend.routers.notification_websocket import connection_manager, NotificationMessage
        
        notification_msg = NotificationMessage(
            notification_id=notification.notification_id,
            recipient_id=notification.recipient_id,
            notification_type=notification.notification_type,
            title=notification.title,
            content=notification.content,
            extra_data=notification.extra_data,
            related_user_id=notification.related_user_id,
            created_at=notification.created_at.isoformat()
        )
        await connection_manager.send_notification(user_id, notification_msg)
    except Exception as e:
        logger.warning(f"[WS] Failed to push notification via WebSocket: {e}")
    
    return notification


async def notify_account_unlocked(
    db: AsyncSession,
    user_id: int,
    unlocked_by: str = None,
    auto_unlock: bool = False
) -> Notification:
    """
    账户解锁时通知用户 (v4.19.0)
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        unlocked_by: 解锁者用户名（管理员解锁时）
        auto_unlock: 是否为自动解锁（锁定期满）
    
    Returns:
        创建的通知
    """
    if auto_unlock:
        content = "Your account has been automatically unlocked. You can now log in."
    else:
        content = f"Your account has been unlocked by an administrator ({unlocked_by}). You can now log in."
    
    notification = await create_notification(
        db=db,
        recipient_id=user_id,
        notification_type=NotificationType.ACCOUNT_UNLOCKED,
        title="Account Unlocked",
        content=content,
        extra_data={
            "unlocked_by": unlocked_by,
            "auto_unlock": auto_unlock,
            "unlocked_at": datetime.utcnow().isoformat()
        }
    )
    
    # v4.19.0: WebSocket 实时推送
    try:
        from backend.routers.notification_websocket import connection_manager, NotificationMessage
        
        notification_msg = NotificationMessage(
            notification_id=notification.notification_id,
            recipient_id=notification.recipient_id,
            notification_type=notification.notification_type,
            title=notification.title,
            content=notification.content,
            extra_data=notification.extra_data,
            related_user_id=notification.related_user_id,
            created_at=notification.created_at.isoformat()
        )
        await connection_manager.send_notification(user_id, notification_msg)
    except Exception as e:
        logger.warning(f"[WS] Failed to push notification via WebSocket: {e}")
    
    return notification


async def notify_user_suspended(
    db: AsyncSession,
    user_id: int,
    suspended_by: str,
    reason: str = None
) -> Notification:
    """
    用户被暂停时通知用户 (v4.19.0)
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        suspended_by: 暂停者用户名
        reason: 暂停原因
    
    Returns:
        创建的通知
    """
    content = "Your account has been suspended by an administrator."
    if reason:
        content += f" Reason: {reason}"
    content += " Please contact the administrator for more information."
    
    notification = await create_notification(
        db=db,
        recipient_id=user_id,
        notification_type=NotificationType.USER_SUSPENDED,
        title="Account Suspended",
        content=content,
        extra_data={
            "suspended_by": suspended_by,
            "reason": reason,
            "suspended_at": datetime.utcnow().isoformat()
        }
    )
    
    # v4.19.0: WebSocket 实时推送
    try:
        from backend.routers.notification_websocket import connection_manager, NotificationMessage
        
        notification_msg = NotificationMessage(
            notification_id=notification.notification_id,
            recipient_id=notification.recipient_id,
            notification_type=notification.notification_type,
            title=notification.title,
            content=notification.content,
            extra_data=notification.extra_data,
            related_user_id=notification.related_user_id,
            created_at=notification.created_at.isoformat()
        )
        await connection_manager.send_notification(user_id, notification_msg)
    except Exception as e:
        logger.warning(f"[WS] Failed to push notification via WebSocket: {e}")
    
    return notification


# ==================== 会话撤销服务函数（内部使用）====================

async def revoke_all_user_sessions(
    db: AsyncSession,
    user_id: int,
    reason: str
) -> int:
    """
    撤销用户所有活跃会话 (v4.19.0 P0 安全要求)
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        reason: 撤销原因
    
    Returns:
        撤销的会话数量
    """
    from modules.core.db import UserSession
    
    # 查询所有活跃会话
    result = await db.execute(
        select(UserSession).where(
            UserSession.user_id == user_id,
            UserSession.is_active == True
        )
    )
    sessions = result.scalars().all()
    
    revoked_count = 0
    now = datetime.utcnow()
    for session in sessions:
        session.is_active = False
        session.revoked_at = now
        session.revoked_reason = reason
        revoked_count += 1
    
    if revoked_count > 0:
        await db.flush()
        logger.info(f"[OK] Revoked {revoked_count} sessions for user {user_id}: {reason}")
    
    return revoked_count

