"""
认证相关 Pydantic 模型。
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class LoginRequest(BaseModel):
    username: str
    password: str
    remember_me: bool = False


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user_info: dict


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class RefreshTokenResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    full_name: Optional[str] = None
    roles: List[str] = []
    is_active: bool = True


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    roles: Optional[List[str]] = None
    is_active: Optional[bool] = None
    employee_id: Optional[int] = None


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    full_name: Optional[str] = None
    roles: List[str]
    permissions: List[str] = []
    is_admin: bool = False
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None
    employee_id: Optional[int] = None
    employee_code: Optional[str] = None
    employee_name: Optional[str] = None


class RoleCreate(BaseModel):
    name: str
    role_code: Optional[str] = None
    description: str
    permissions: List[str] = []


class RoleUpdate(BaseModel):
    role_code: Optional[str] = None
    description: Optional[str] = None
    permissions: Optional[List[str]] = None


class RoleResponse(BaseModel):
    id: int
    name: str
    role_code: Optional[str] = None
    role_name: Optional[str] = None
    description: Optional[str] = None
    permissions: List[str]
    created_at: datetime
    is_system: bool = False
    is_active: bool = True


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class AuditLogResponse(BaseModel):
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


class AuditLogFilterRequest(BaseModel):
    action: Optional[str] = Field(None, description="操作类型，支持模糊匹配")
    resource: Optional[str] = Field(None, description="资源类型，支持模糊匹配")
    user_id: Optional[int] = Field(None, description="用户 ID")
    username: Optional[str] = Field(None, description="用户名，支持模糊匹配")
    ip_address: Optional[str] = Field(None, description="IP 地址，支持模糊匹配")
    start_time: Optional[datetime] = Field(None, description="开始时间")
    end_time: Optional[datetime] = Field(None, description="结束时间")
    page: int = Field(1, ge=1, description="页码(1-based)")
    page_size: int = Field(20, ge=1, le=100, description="每页条数")


class AuditLogExportRequest(BaseModel):
    action: Optional[str] = Field(None, description="操作类型，支持模糊匹配")
    resource: Optional[str] = Field(None, description="资源类型，支持模糊匹配")
    user_id: Optional[int] = Field(None, description="用户 ID")
    username: Optional[str] = Field(None, description="用户名，支持模糊匹配")
    ip_address: Optional[str] = Field(None, description="IP 地址，支持模糊匹配")
    start_time: Optional[datetime] = Field(None, description="开始时间")
    end_time: Optional[datetime] = Field(None, description="结束时间")
    format: str = Field("excel", description="导出格式：excel 或 csv")
    max_records: int = Field(10000, ge=1, le=50000, description="最大导出记录数")

    @field_validator("format")
    @classmethod
    def validate_format(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in ["excel", "csv"]:
            raise ValueError("导出格式必须是 excel 或 csv")
        return normalized


class AuditLogDetailResponse(BaseModel):
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
    before_data: Optional[dict] = Field(None, description="变更前数据")
    after_data: Optional[dict] = Field(None, description="变更后数据")

    model_config = ConfigDict(from_attributes=True)


class RegisterRequest(BaseModel):
    username: str = Field(
        ...,
        min_length=3,
        max_length=50,
        pattern=r"^[a-zA-Z0-9_]+$",
        description="用户名，3-50 个字符，仅支持字母数字下划线",
    )
    email: EmailStr = Field(..., description="邮箱地址")
    password: str = Field(..., min_length=8, description="密码，至少 8 位")
    full_name: Optional[str] = Field(None, max_length=200, description="姓名")
    phone: Optional[str] = Field(None, max_length=50, description="手机号")
    department: Optional[str] = Field(None, max_length=100, description="部门")

    @field_validator("password")
    @classmethod
    def password_strength(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("密码长度至少 8 位")
        if not re.search(r"[A-Za-z]", value):
            raise ValueError("密码必须包含字母")
        if not re.search(r"[0-9]", value):
            raise ValueError("密码必须包含数字")
        return value


class RegisterResponse(BaseModel):
    user_id: int
    username: str
    email: str
    status: str
    message: str


class ApproveUserRequest(BaseModel):
    role_ids: List[int] = Field(default_factory=list, max_length=10, description="审批分配的角色 ID 列表")
    notes: Optional[str] = Field(None, max_length=500, description="审批备注")


class RejectUserRequest(BaseModel):
    reason: Optional[str] = Field(None, max_length=500, description="拒绝原因")


class UserIdBatchRequest(BaseModel):
    user_ids: List[int] = Field(..., min_length=1, max_length=200, description="用户 ID 列表")
    reason: Optional[str] = Field(None, max_length=500, description="原因或备注")


class BatchItemResult(BaseModel):
    user_id: int
    ok: bool
    error_message: Optional[str] = None


class BatchSummary(BaseModel):
    total: int
    success: int
    failed: int


class BatchUserActionResponse(BaseModel):
    summary: BatchSummary
    results: List[BatchItemResult]


class PendingUserResponse(BaseModel):
    user_id: int
    username: str
    email: str
    full_name: Optional[str]
    department: Optional[str]
    status: str
    created_at: datetime


class ResetPasswordRequest(BaseModel):
    new_password: Optional[str] = Field(None, min_length=8, description="新密码，留空则生成临时密码")
    generate_temp_password: bool = Field(False, description="是否生成临时密码")


class ResetPasswordResponse(BaseModel):
    user_id: int
    username: str
    temp_password: Optional[str] = Field(None, description="临时密码，仅生成临时密码时返回")
    message: str


class UnlockAccountRequest(BaseModel):
    reason: Optional[str] = Field(None, max_length=200, description="解锁原因")


class UserSessionResponse(BaseModel):
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
