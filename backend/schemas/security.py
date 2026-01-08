"""
安全设置相关的Pydantic Schemas
用于密码策略、登录限制、会话管理、2FA等API

v4.20.0: 系统管理模块API实现
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, field_validator


# ==================== 密码策略 ====================

class PasswordPolicyResponse(BaseModel):
    """密码策略响应模型"""
    min_length: int = Field(description="最小长度")
    require_uppercase: bool = Field(description="需要大写字母")
    require_lowercase: bool = Field(description="需要小写字母")
    require_digits: bool = Field(description="需要数字")
    require_special_chars: bool = Field(description="需要特殊字符")
    max_age_days: int = Field(description="最大有效期（天）")
    prevent_reuse_count: int = Field(description="防止重复使用最近N个密码")
    updated_at: Optional[datetime] = Field(None, description="更新时间")
    updated_by: Optional[int] = Field(None, description="更新人ID")


class PasswordPolicyUpdate(BaseModel):
    """密码策略更新请求"""
    min_length: int = Field(8, ge=6, le=32, description="最小长度（6-32）")
    require_uppercase: bool = Field(True, description="需要大写字母")
    require_lowercase: bool = Field(True, description="需要小写字母")
    require_digits: bool = Field(True, description="需要数字")
    require_special_chars: bool = Field(False, description="需要特殊字符")
    max_age_days: int = Field(90, ge=30, le=365, description="最大有效期（天，30-365）")
    prevent_reuse_count: int = Field(5, ge=0, le=20, description="防止重复使用最近N个密码（0-20）")


# ==================== 登录限制 ====================

class LoginRestrictionsResponse(BaseModel):
    """登录限制响应模型"""
    max_failed_attempts: int = Field(description="最大失败次数")
    lockout_duration_minutes: int = Field(description="锁定时长（分钟）")
    enable_ip_whitelist: bool = Field(description="是否启用IP白名单")
    updated_at: Optional[datetime] = Field(None, description="更新时间")
    updated_by: Optional[int] = Field(None, description="更新人ID")


class LoginRestrictionsUpdate(BaseModel):
    """登录限制更新请求"""
    max_failed_attempts: int = Field(5, ge=3, le=10, description="最大失败次数（3-10）")
    lockout_duration_minutes: int = Field(30, ge=5, le=1440, description="锁定时长（分钟，5-1440）")
    enable_ip_whitelist: bool = Field(False, description="是否启用IP白名单")


class IPWhitelistResponse(BaseModel):
    """IP白名单响应模型"""
    ip_addresses: List[str] = Field(description="IP地址列表")
    updated_at: Optional[datetime] = Field(None, description="更新时间")
    updated_by: Optional[int] = Field(None, description="更新人ID")


class IPWhitelistUpdate(BaseModel):
    """IP白名单更新请求"""
    ip_address: str = Field(..., description="IP地址（IPv4或IPv6）")
    
    @field_validator('ip_address')
    @classmethod
    def validate_ip(cls, v):
        import ipaddress
        try:
            ipaddress.ip_address(v)
            return v
        except ValueError:
            raise ValueError('无效的IP地址格式')


# ==================== 会话管理 ====================

class SessionConfigResponse(BaseModel):
    """会话配置响应模型"""
    timeout_minutes: int = Field(description="会话超时时间（分钟）")
    max_concurrent_sessions: int = Field(description="最大并发会话数")
    enable_session_limit: bool = Field(description="是否启用会话限制")
    updated_at: Optional[datetime] = Field(None, description="更新时间")
    updated_by: Optional[int] = Field(None, description="更新人ID")


class SessionConfigUpdate(BaseModel):
    """会话配置更新请求"""
    timeout_minutes: int = Field(15, ge=5, le=1440, description="会话超时时间（分钟，5-1440）")
    max_concurrent_sessions: int = Field(5, ge=1, le=20, description="最大并发会话数（1-20）")
    enable_session_limit: bool = Field(True, description="是否启用会话限制")


# ==================== 2FA配置（可选） ====================

class TwoFactorConfigResponse(BaseModel):
    """2FA配置响应模型"""
    enabled: bool = Field(description="是否启用2FA")
    required_for_admin: bool = Field(description="管理员是否必须启用2FA")
    issuer_name: str = Field(description="发行者名称")
    updated_at: Optional[datetime] = Field(None, description="更新时间")
    updated_by: Optional[int] = Field(None, description="更新人ID")


class TwoFactorConfigUpdate(BaseModel):
    """2FA配置更新请求"""
    enabled: bool = Field(False, description="是否启用2FA")
    required_for_admin: bool = Field(False, description="管理员是否必须启用2FA")
    issuer_name: str = Field("西虹ERP系统", max_length=64, description="发行者名称（最多64字符）")
