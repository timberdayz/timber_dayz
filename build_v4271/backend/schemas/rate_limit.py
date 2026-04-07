#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
限流相关 Pydantic Schemas

v4.19.2 新增:
- 限流统计响应模型
- 限流事件模型
- 限流异常告警模型
"""

from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from datetime import datetime


class RateLimitEventResponse(BaseModel):
    """限流事件响应"""
    timestamp: str = Field(..., description="事件时间戳(ISO 格式)")
    rate_limit_key: str = Field(..., description="限流键(user:xxx 或 ip:xxx)")
    path: str = Field(..., description="API 路径")
    method: str = Field(..., description="HTTP 方法")
    detail: str = Field(..., description="限流详情")
    ip_address: Optional[str] = Field(None, description="IP 地址")
    user_agent: Optional[str] = Field(None, description="User-Agent")
    
    class Config:
        from_attributes = True


class RateLimitStatsResponse(BaseModel):
    """限流统计响应"""
    date: str = Field(..., description="统计日期(YYYY-MM-DD)")
    total: int = Field(..., description="总限流次数")
    by_path: Dict[str, int] = Field(default_factory=dict, description="按 API 路径统计")
    by_key: Dict[str, int] = Field(default_factory=dict, description="按限流键统计")
    source: str = Field(..., description="数据来源(redis/local)")
    
    class Config:
        from_attributes = True


class RateLimitAnomalyResponse(BaseModel):
    """限流异常告警响应"""
    type: str = Field(..., description="异常类型")
    key: Optional[str] = Field(None, description="限流键")
    path: Optional[str] = Field(None, description="API 路径")
    count: int = Field(..., description="限流次数")
    threshold: int = Field(..., description="告警阈值")
    severity: str = Field(..., description="严重程度(warning/critical)")
    
    class Config:
        from_attributes = True


class RateLimitConfigResponse(BaseModel):
    """限流配置响应"""
    enabled: bool = Field(..., description="限流是否启用")
    default_limit: str = Field(..., description="默认限流值")
    tiers: Dict[str, Dict[str, str]] = Field(..., description="分级限流配置")
    
    class Config:
        from_attributes = True


class RateLimitInfoResponse(BaseModel):
    """当前用户限流信息响应"""
    user_id: Optional[int] = Field(None, description="用户 ID")
    tier: str = Field(..., description="限流等级")
    limits: Dict[str, str] = Field(..., description="各端点限流配置")
    
    class Config:
        from_attributes = True


# ================================================================
# 限流规则 CRUD（rate_limit_config 路由使用）
# ================================================================


class RateLimitRuleResponse(BaseModel):
    """限流规则响应模型"""
    config_id: int
    role_code: str
    endpoint_type: str
    limit_value: str
    is_active: bool
    description: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    updated_by: Optional[str] = None

    class Config:
        from_attributes = True


class RateLimitRuleCreate(BaseModel):
    """创建限流规则请求模型"""
    role_code: str = Field(
        ...,
        description="角色代码(admin/manager/finance/operator/normal/anonymous)",
    )
    endpoint_type: str = Field(
        ..., description="端点类型(default/data_sync/auth)"
    )
    limit_value: str = Field(..., description="限流值(如 '200/minute')")
    description: Optional[str] = Field(None, description="配置说明")
    is_active: bool = Field(True, description="是否启用")


class RateLimitRuleUpdate(BaseModel):
    """更新限流规则请求模型"""
    limit_value: Optional[str] = Field(
        None, description="限流值(如 '200/minute')"
    )
    is_active: Optional[bool] = Field(None, description="是否启用")
    description: Optional[str] = Field(None, description="配置说明")


class RateLimitRuleListResponse(BaseModel):
    """限流规则列表响应模型"""
    total: int
    configs: List[RateLimitRuleResponse]

