"""
认证相关的Pydantic模型
"""

from pydantic import BaseModel, EmailStr, Field, validator
from typing import List, Optional
from datetime import datetime
import re

class LoginRequest(BaseModel):
    """登录请求"""
    username: str
    password: str
    remember_me: bool = False

class LoginResponse(BaseModel):
    """登录响应"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user_info: dict

class RefreshTokenRequest(BaseModel):
    """刷新令牌请求"""
    refresh_token: str

class RefreshTokenResponse(BaseModel):
    """刷新令牌响应"""
    access_token: str
    refresh_token: Optional[str] = None  # ⭐ v6.0.0修复：可选字段，支持 Refresh Token 轮换
    token_type: str = "bearer"
    expires_in: int

class UserCreate(BaseModel):
    """创建用户请求"""
    username: str
    email: EmailStr
    password: str
    full_name: str
    roles: List[str] = []
    is_active: bool = True

class UserUpdate(BaseModel):
    """更新用户请求"""
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    roles: Optional[List[str]] = None
    is_active: Optional[bool] = None

class UserResponse(BaseModel):
    """用户响应"""
    id: int
    username: str
    email: str
    full_name: str
    roles: List[str]
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None  # ⭐ v6.0.0修复：映射到数据库字段 last_login（Vulnerability 29）
    # 注意：数据库字段名是 last_login，但 API 响应使用 last_login_at 保持一致性

class RoleCreate(BaseModel):
    """创建角色请求"""
    name: str
    description: str
    permissions: List[str] = []

class RoleUpdate(BaseModel):
    """更新角色请求"""
    description: Optional[str] = None
    permissions: Optional[List[str]] = None

class RoleResponse(BaseModel):
    """角色响应"""
    id: int
    name: str
    description: str
    permissions: List[str]
    created_at: datetime

class PermissionResponse(BaseModel):
    """权限响应"""
    id: int
    name: str
    description: str
    resource: str
    action: str

class ChangePasswordRequest(BaseModel):
    """修改密码请求"""
    old_password: str
    new_password: str

class AuditLogResponse(BaseModel):
    """审计日志响应"""
    id: int
    user_id: int
    username: str
    action: str
    resource: str
    resource_id: Optional[str] = None
    ip_address: str
    user_agent: str
    created_at: datetime
    details: Optional[dict] = None

class RegisterRequest(BaseModel):
    """用户注册请求"""
    username: str = Field(
        ...,
        min_length=3,
        max_length=50,
        pattern="^[a-zA-Z0-9_]+$",
        description="用户名（3-50字符，字母数字下划线）"
    )
    email: EmailStr = Field(..., description="邮箱地址")
    password: str = Field(
        ...,
        min_length=8,
        description="密码（至少8位，包含字母和数字）"
    )
    full_name: Optional[str] = Field(None, max_length=200, description="姓名")
    phone: Optional[str] = Field(None, max_length=50, description="手机号")
    department: Optional[str] = Field(None, max_length=100, description="部门")

    @validator('password')
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError('密码长度至少8位')
        if not re.search(r'[A-Za-z]', v):
            raise ValueError('密码必须包含字母')
        if not re.search(r'[0-9]', v):
            raise ValueError('密码必须包含数字')
        return v

class RegisterResponse(BaseModel):
    """用户注册响应"""
    user_id: int
    username: str
    email: str
    status: str  # "pending"
    message: str

class ApproveUserRequest(BaseModel):
    """用户审批请求"""
    role_ids: List[int] = Field(
        default_factory=list,
        max_items=10,  # v4.19.0 P1安全要求：最多10个角色
        description="角色ID列表（可选，默认operator，最多10个）"
    )
    notes: Optional[str] = Field(
        None,
        max_length=500,  # v4.19.0 P1安全要求：最多500字符
        description="审批备注（最多500字符）"
    )

class RejectUserRequest(BaseModel):
    """用户拒绝请求"""
    reason: str = Field(
        ...,
        min_length=1,  # v4.19.0 P1安全要求：修改为1字符（允许简短原因）
        max_length=500,  # v4.19.0 P1安全要求：最多500字符
        description="拒绝原因（必填，1-500字符）"
    )

class PendingUserResponse(BaseModel):
    """待审批用户响应"""
    user_id: int
    username: str
    email: str
    full_name: Optional[str]
    department: Optional[str]
    status: str  # v4.19.0 P2隐私要求：添加status字段
    created_at: datetime

class ResetPasswordRequest(BaseModel):
    """重置密码请求（管理员）"""
    new_password: Optional[str] = Field(
        None,
        min_length=8,
        description="新密码（可选，如果不提供则生成临时密码）"
    )
    generate_temp_password: bool = Field(
        False,
        description="是否生成临时密码（如果为True，忽略new_password）"
    )

class ResetPasswordResponse(BaseModel):
    """重置密码响应"""
    user_id: int
    username: str
    temp_password: Optional[str] = Field(None, description="临时密码（仅生成临时密码时返回）")
    message: str

class UnlockAccountRequest(BaseModel):
    """解锁账户请求"""
    reason: Optional[str] = Field(None, max_length=200, description="解锁原因（可选）")

class UserSessionResponse(BaseModel):
    """用户会话响应"""
    session_id: str
    device_info: Optional[str]
    ip_address: Optional[str]
    location: Optional[str]
    created_at: datetime
    expires_at: datetime
    last_active_at: datetime
    is_active: bool
    is_current: bool = Field(False, description="是否为当前会话")
    
    class Config:
        from_attributes = True
