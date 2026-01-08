"""
通知配置相关的Pydantic Schemas
用于SMTP配置、通知模板、告警规则等API

v4.20.0: 系统管理模块API实现
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, field_validator, EmailStr


# ==================== SMTP配置 ====================

class SMTPConfigResponse(BaseModel):
    """SMTP配置响应模型（密码不返回）"""
    id: int
    smtp_server: str
    smtp_port: int
    use_tls: bool
    username: str
    from_email: str
    from_name: Optional[str] = None
    is_active: bool
    updated_at: datetime
    updated_by: Optional[int] = None
    
    model_config = ConfigDict(from_attributes=True)


class SMTPConfigUpdate(BaseModel):
    """SMTP配置更新请求"""
    smtp_server: Optional[str] = Field(None, max_length=256, description="SMTP服务器地址")
    smtp_port: Optional[int] = Field(None, ge=1, le=65535, description="SMTP端口（1-65535）")
    use_tls: Optional[bool] = Field(None, description="是否使用TLS")
    username: Optional[str] = Field(None, max_length=256, description="SMTP用户名")
    password: Optional[str] = Field(None, description="SMTP密码（明文，将加密存储）")
    from_email: Optional[EmailStr] = Field(None, description="发件人邮箱")
    from_name: Optional[str] = Field(None, max_length=128, description="发件人名称")
    is_active: Optional[bool] = Field(None, description="是否启用")


class TestEmailRequest(BaseModel):
    """测试邮件请求"""
    to_email: EmailStr = Field(..., description="收件人邮箱")
    subject: Optional[str] = Field("测试邮件", max_length=256, description="邮件主题")
    content: Optional[str] = Field("这是一封测试邮件", description="邮件内容")


# ==================== 通知模板 ====================

class NotificationTemplateResponse(BaseModel):
    """通知模板响应模型"""
    id: int
    template_name: str
    template_type: str
    subject: Optional[str] = None
    content: str
    variables: Optional[Dict[str, Any]] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    created_by: Optional[int] = None
    updated_by: Optional[int] = None
    
    model_config = ConfigDict(from_attributes=True)


class NotificationTemplateCreate(BaseModel):
    """通知模板创建请求"""
    template_name: str = Field(..., max_length=128, description="模板名称（唯一）")
    template_type: str = Field(..., description="模板类型（email/sms/push）")
    subject: Optional[str] = Field(None, max_length=256, description="邮件主题（email类型必填）")
    content: str = Field(..., description="模板内容（支持变量如 {{user_name}}）")
    variables: Optional[Dict[str, Any]] = Field(None, description="可用变量说明（JSON格式）")
    is_active: bool = Field(True, description="是否启用")
    
    @field_validator('template_type')
    @classmethod
    def validate_template_type(cls, v):
        if v not in ['email', 'sms', 'push']:
            raise ValueError('模板类型必须是 email、sms 或 push')
        return v


class NotificationTemplateUpdate(BaseModel):
    """通知模板更新请求"""
    template_name: Optional[str] = Field(None, max_length=128, description="模板名称")
    template_type: Optional[str] = Field(None, description="模板类型（email/sms/push）")
    subject: Optional[str] = Field(None, max_length=256, description="邮件主题")
    content: Optional[str] = Field(None, description="模板内容")
    variables: Optional[Dict[str, Any]] = Field(None, description="可用变量说明")
    is_active: Optional[bool] = Field(None, description="是否启用")
    
    @field_validator('template_type')
    @classmethod
    def validate_template_type(cls, v):
        if v and v not in ['email', 'sms', 'push']:
            raise ValueError('模板类型必须是 email、sms 或 push')
        return v


class NotificationTemplateListResponse(BaseModel):
    """通知模板列表响应（分页）"""
    data: List[NotificationTemplateResponse]
    page: int
    page_size: int
    total: int
    total_pages: int


# ==================== 告警规则 ====================

class AlertRuleResponse(BaseModel):
    """告警规则响应模型"""
    id: int
    rule_name: str
    rule_type: str
    condition: Dict[str, Any]
    template_id: Optional[int] = None
    recipients: Optional[List[Any]] = None
    enabled: bool
    priority: str
    created_at: datetime
    updated_at: datetime
    created_by: Optional[int] = None
    updated_by: Optional[int] = None
    
    model_config = ConfigDict(from_attributes=True)


class AlertRuleCreate(BaseModel):
    """告警规则创建请求"""
    rule_name: str = Field(..., max_length=128, description="规则名称（唯一）")
    rule_type: str = Field(..., description="规则类型（system/performance/security/business）")
    condition: Dict[str, Any] = Field(..., description="触发条件（JSON格式）")
    template_id: Optional[int] = Field(None, description="关联的通知模板ID")
    recipients: Optional[List[Any]] = Field(None, description="收件人列表（JSON格式）")
    enabled: bool = Field(True, description="是否启用")
    priority: str = Field("medium", description="优先级（low/medium/high/critical）")
    
    @field_validator('rule_type')
    @classmethod
    def validate_rule_type(cls, v):
        if v not in ['system', 'performance', 'security', 'business']:
            raise ValueError('规则类型必须是 system、performance、security 或 business')
        return v
    
    @field_validator('priority')
    @classmethod
    def validate_priority(cls, v):
        if v not in ['low', 'medium', 'high', 'critical']:
            raise ValueError('优先级必须是 low、medium、high 或 critical')
        return v


class AlertRuleUpdate(BaseModel):
    """告警规则更新请求"""
    rule_name: Optional[str] = Field(None, max_length=128, description="规则名称")
    rule_type: Optional[str] = Field(None, description="规则类型")
    condition: Optional[Dict[str, Any]] = Field(None, description="触发条件")
    template_id: Optional[int] = Field(None, description="关联的通知模板ID")
    recipients: Optional[List[Any]] = Field(None, description="收件人列表")
    enabled: Optional[bool] = Field(None, description="是否启用")
    priority: Optional[str] = Field(None, description="优先级")
    
    @field_validator('rule_type')
    @classmethod
    def validate_rule_type(cls, v):
        if v and v not in ['system', 'performance', 'security', 'business']:
            raise ValueError('规则类型必须是 system、performance、security 或 business')
        return v
    
    @field_validator('priority')
    @classmethod
    def validate_priority(cls, v):
        if v and v not in ['low', 'medium', 'high', 'critical']:
            raise ValueError('优先级必须是 low、medium、high 或 critical')
        return v


class AlertRuleListResponse(BaseModel):
    """告警规则列表响应（分页）"""
    data: List[AlertRuleResponse]
    page: int
    page_size: int
    total: int
    total_pages: int
