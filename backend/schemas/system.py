"""
系统管理相关的Pydantic Schemas
用于系统日志、系统配置等API

v4.20.0: 系统管理模块API实现
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, field_validator


# ==================== 系统日志 ====================

class SystemLogResponse(BaseModel):
    """系统日志响应模型"""
    id: int
    level: str = Field(description="日志级别（ERROR, WARN, INFO, DEBUG）")
    module: str = Field(description="模块名称")
    message: str = Field(description="日志消息")
    user_id: Optional[int] = Field(None, description="用户ID（如果关联）")
    ip_address: Optional[str] = Field(None, description="IP地址")
    user_agent: Optional[str] = Field(None, description="用户代理")
    details: Optional[Dict[str, Any]] = Field(None, description="详细信息（JSON格式）")
    created_at: datetime = Field(description="创建时间")
    
    model_config = ConfigDict(from_attributes=True)


class SystemLogFilterRequest(BaseModel):
    """系统日志筛选请求"""
    level: Optional[str] = Field(None, description="日志级别（ERROR, WARN, INFO, DEBUG）")
    module: Optional[str] = Field(None, description="模块名称（支持模糊匹配）")
    user_id: Optional[int] = Field(None, description="用户ID")
    start_time: Optional[datetime] = Field(None, description="开始时间")
    end_time: Optional[datetime] = Field(None, description="结束时间")
    page: int = Field(1, ge=1, description="页码（1-based）")
    page_size: int = Field(20, ge=1, le=100, description="每页条数（最大100）")
    
    @field_validator('level')
    @classmethod
    def validate_level(cls, v):
        if v is not None and v.upper() not in ['ERROR', 'WARN', 'INFO', 'DEBUG']:
            raise ValueError('日志级别必须是 ERROR, WARN, INFO 或 DEBUG')
        return v.upper() if v else None


class SystemLogListResponse(BaseModel):
    """系统日志列表响应（分页）"""
    success: bool = Field(default=True, description="请求是否成功")
    data: List[SystemLogResponse] = Field(description="日志列表")
    pagination: Dict[str, Any] = Field(description="分页信息")
    timestamp: datetime = Field(default_factory=datetime.now, description="响应时间")


class SystemLogExportRequest(BaseModel):
    """系统日志导出请求"""
    level: Optional[str] = Field(None, description="日志级别（ERROR, WARN, INFO, DEBUG）")
    module: Optional[str] = Field(None, description="模块名称（支持模糊匹配）")
    user_id: Optional[int] = Field(None, description="用户ID")
    start_time: Optional[datetime] = Field(None, description="开始时间")
    end_time: Optional[datetime] = Field(None, description="结束时间")
    format: str = Field("excel", description="导出格式（excel 或 csv）")
    max_records: int = Field(10000, ge=1, le=50000, description="最大导出记录数（防止导出过多数据）")
    
    @field_validator('level')
    @classmethod
    def validate_level(cls, v):
        if v is not None and v.upper() not in ['ERROR', 'WARN', 'INFO', 'DEBUG']:
            raise ValueError('日志级别必须是 ERROR, WARN, INFO 或 DEBUG')
        return v.upper() if v else None
    
    @field_validator('format')
    @classmethod
    def validate_format(cls, v):
        if v.lower() not in ['excel', 'csv']:
            raise ValueError('导出格式必须是 excel 或 csv')
        return v.lower()


# ==================== 系统基础配置 ====================

class SystemConfigResponse(BaseModel):
    """系统基础配置响应模型"""
    system_name: str = Field(description="系统名称")
    version: str = Field(description="系统版本")
    timezone: str = Field(description="时区（如：Asia/Shanghai）")
    language: str = Field(description="语言（如：zh-CN, en-US）")
    currency: str = Field(description="货币（如：CNY, USD）")
    updated_at: Optional[datetime] = Field(None, description="更新时间")
    updated_by: Optional[int] = Field(None, description="更新人ID")


class SystemConfigUpdate(BaseModel):
    """系统基础配置更新请求"""
    system_name: Optional[str] = Field(None, max_length=128, description="系统名称")
    version: Optional[str] = Field(None, max_length=32, description="系统版本")
    timezone: Optional[str] = Field(None, max_length=64, description="时区（如：Asia/Shanghai）")
    language: Optional[str] = Field(None, max_length=16, description="语言（如：zh-CN, en-US）")
    currency: Optional[str] = Field(None, max_length=8, description="货币（如：CNY, USD）")


# ==================== 数据库配置 ====================

class DatabaseConfigResponse(BaseModel):
    """数据库配置响应模型（敏感字段加密）"""
    host: str = Field(description="数据库主机")
    port: int = Field(description="数据库端口")
    database: str = Field(description="数据库名称")
    username: str = Field(description="数据库用户名")
    password: str = Field(description="数据库密码（已加密，显示为***）")
    connection_url: str = Field(description="数据库连接URL（密码已隐藏）")
    updated_at: Optional[datetime] = Field(None, description="更新时间")
    updated_by: Optional[int] = Field(None, description="更新人ID")


class DatabaseConfigUpdate(BaseModel):
    """数据库配置更新请求（仅用于预览，不直接应用）"""
    host: Optional[str] = Field(None, max_length=256, description="数据库主机")
    port: Optional[int] = Field(None, ge=1, le=65535, description="数据库端口")
    database: Optional[str] = Field(None, max_length=128, description="数据库名称")
    username: Optional[str] = Field(None, max_length=128, description="数据库用户名")
    password: Optional[str] = Field(None, description="数据库密码（明文，将加密存储）")


class DatabaseConnectionTestRequest(BaseModel):
    """数据库连接测试请求"""
    host: str = Field(..., max_length=256, description="数据库主机")
    port: int = Field(..., ge=1, le=65535, description="数据库端口")
    database: str = Field(..., max_length=128, description="数据库名称")
    username: str = Field(..., max_length=128, description="数据库用户名")
    password: str = Field(..., description="数据库密码（明文）")


class DatabaseConnectionTestResponse(BaseModel):
    """数据库连接测试响应模型"""
    success: bool = Field(description="连接是否成功")
    message: str = Field(description="连接结果消息")
    response_time_ms: Optional[int] = Field(None, description="响应时间（毫秒）")
