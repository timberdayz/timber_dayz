"""
通知相关的Pydantic模型 (v4.19.0)
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class NotificationType(str, Enum):
    """通知类型枚举"""
    USER_REGISTERED = "user_registered"  # 新用户注册（通知管理员）
    USER_APPROVED = "user_approved"  # 用户审批通过（通知用户）
    USER_REJECTED = "user_rejected"  # 用户审批拒绝（通知用户）
    USER_SUSPENDED = "user_suspended"  # 用户被暂停（通知用户）
    PASSWORD_RESET = "password_reset"  # 密码重置（通知用户）
    ACCOUNT_LOCKED = "account_locked"  # 账户被锁定（通知用户）v4.19.0
    ACCOUNT_UNLOCKED = "account_unlocked"  # 账户已解锁（通知用户）v4.19.0
    SYSTEM_ALERT = "system_alert"  # 系统告警


class NotificationPriority(str, Enum):
    """通知优先级枚举（v4.19.0）"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class NotificationBase(BaseModel):
    """通知基础模型"""
    notification_type: NotificationType
    title: str = Field(..., max_length=200)
    content: str
    extra_data: Optional[Dict[str, Any]] = None
    related_user_id: Optional[int] = None
    priority: str = Field(default="medium", description="优先级：high, medium, low")


class NotificationCreate(NotificationBase):
    """创建通知请求"""
    recipient_id: int


class NotificationActionType(str, Enum):
    """通知快速操作类型（v4.19.0）"""
    APPROVE_USER = "approve_user"  # 批准用户
    REJECT_USER = "reject_user"  # 拒绝用户
    VIEW_DETAILS = "view_details"  # 查看详情


class NotificationAction(BaseModel):
    """通知快速操作配置（v4.19.0）"""
    action_type: str = Field(..., description="操作类型：approve_user, reject_user, view_details")
    label: str = Field(..., description="按钮显示文本")
    icon: Optional[str] = Field(None, description="图标名称")
    style: Optional[str] = Field("default", description="按钮样式：primary, success, warning, danger, default")
    confirm: Optional[bool] = Field(False, description="是否需要确认")
    confirm_message: Optional[str] = Field(None, description="确认对话框消息")


class NotificationResponse(BaseModel):
    """通知响应"""
    notification_id: int
    recipient_id: int
    notification_type: str
    title: str
    content: str
    extra_data: Optional[Dict[str, Any]] = None
    related_user_id: Optional[int] = None
    is_read: bool
    read_at: Optional[datetime] = None
    created_at: datetime
    
    # v4.19.0: 优先级
    priority: str = Field(default="medium", description="优先级：high, medium, low")
    
    # 可选：关联用户信息
    related_username: Optional[str] = None
    
    # v4.19.0: 快速操作按钮配置
    actions: Optional[List[NotificationAction]] = Field(None, description="可用的快速操作")
    
    class Config:
        from_attributes = True


class NotificationListResponse(BaseModel):
    """通知列表响应"""
    items: List[NotificationResponse]
    total: int
    page: int
    page_size: int
    unread_count: int


class UnreadCountResponse(BaseModel):
    """未读通知数量响应"""
    unread_count: int


class MarkReadRequest(BaseModel):
    """标记已读请求"""
    notification_ids: List[int] = Field(default_factory=list, description="要标记的通知ID列表，为空则标记全部")


class MarkReadResponse(BaseModel):
    """标记已读响应"""
    marked_count: int
    message: str


class NotificationDeleteResponse(BaseModel):
    """删除通知响应"""
    deleted_count: int
    message: str


# 内部使用：批量创建通知
class NotificationBatchCreate(BaseModel):
    """批量创建通知（内部使用）"""
    recipient_ids: List[int]
    notification_type: NotificationType
    title: str
    content: str
    extra_data: Optional[Dict[str, Any]] = None
    related_user_id: Optional[int] = None


# v4.19.0: 用户通知偏好

class NotificationPreferenceResponse(BaseModel):
    """通知偏好响应"""
    preference_id: int
    user_id: int
    notification_type: str
    enabled: bool
    desktop_enabled: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class NotificationPreferenceUpdate(BaseModel):
    """更新通知偏好请求"""
    notification_type: str
    enabled: Optional[bool] = None
    desktop_enabled: Optional[bool] = None


class NotificationPreferenceBatchUpdate(BaseModel):
    """批量更新通知偏好请求"""
    preferences: List[NotificationPreferenceUpdate] = Field(..., max_items=20, description="通知偏好列表（最多20个）")


class NotificationPreferenceListResponse(BaseModel):
    """通知偏好列表响应"""
    items: List[NotificationPreferenceResponse]
    total: int


# v4.19.0: 快速操作

class NotificationActionRequest(BaseModel):
    """快速操作请求（v4.19.0）"""
    action_type: str = Field(..., description="操作类型：approve_user, reject_user")
    reason: Optional[str] = Field(None, max_length=500, description="操作原因（如拒绝原因）")


class NotificationActionResponse(BaseModel):
    """快速操作响应（v4.19.0）"""
    success: bool
    message: str
    notification_id: int
    action_type: str
    target_user_id: Optional[int] = None


# v4.19.0: 通知分组

class NotificationGroupItem(BaseModel):
    """单个分组项（v4.19.0）"""
    notification_type: str
    type_label: str  # 类型显示名称
    total_count: int
    unread_count: int
    latest_notification: Optional[NotificationResponse] = None


class NotificationGroupListResponse(BaseModel):
    """通知分组列表响应（v4.19.0）"""
    groups: List[NotificationGroupItem]
    total_count: int
    total_unread: int

