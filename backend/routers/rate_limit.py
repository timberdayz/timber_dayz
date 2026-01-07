#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
限流管理 API 路由

v4.19.2 新增:
- 限流统计查询
- 限流配置查询
- 限流异常检测
- 当前用户限流信息

访问控制：
- 统计和配置 API 需要管理员权限
- 当前用户限流信息 API 需要登录
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from typing import List, Optional
from datetime import datetime
import os

from backend.routers.auth import get_current_user
from backend.services.rate_limit_stats import get_rate_limit_stats_service
from backend.middleware.rate_limiter import (
    RATE_LIMIT_TIERS,
    get_user_rate_limit_tier,
    get_rate_limit_for_endpoint
)
from backend.schemas.rate_limit import (
    RateLimitStatsResponse,
    RateLimitEventResponse,
    RateLimitAnomalyResponse,
    RateLimitConfigResponse,
    RateLimitInfoResponse
)
from backend.utils.api_response import success_response, error_response
from backend.utils.error_codes import ErrorCode, get_error_type
from modules.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/rate-limit", tags=["限流管理"])


def require_admin(current_user = Depends(get_current_user)):
    """要求管理员权限"""
    # 检查用户角色
    roles = getattr(current_user, "roles", [])
    role_names = []
    for role in roles:
        if hasattr(role, "role_name"):
            role_names.append(role.role_name.lower())
        elif hasattr(role, "name"):
            role_names.append(role.name.lower())
        elif isinstance(role, str):
            role_names.append(role.lower())
    
    if "admin" in role_names or "administrator" in role_names:
        return current_user
    
    # 回退机制：检查用户名是否为 admin（用于没有分配角色的情况）
    username = getattr(current_user, "username", None)
    if username and username.lower() == "admin":
        return current_user
    
    raise HTTPException(
        status_code=403,
        detail="需要管理员权限"
    )


@router.get("/config", response_model=RateLimitConfigResponse)
async def get_rate_limit_config(
    current_user = Depends(require_admin)
):
    """
    获取限流配置（需要管理员权限）
    
    返回当前系统的限流配置，包括：
    - 限流是否启用
    - 默认限流值
    - 分级限流配置
    """
    enabled = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
    
    # 转换 Pydantic 模型为字典
    response_data = RateLimitConfigResponse(
        enabled=enabled,
        default_limit="100/minute",
        tiers=RATE_LIMIT_TIERS
    ).model_dump()
    
    return success_response(
        data=response_data,
        message="获取限流配置成功"
    )


@router.get("/stats", response_model=RateLimitStatsResponse)
async def get_rate_limit_stats(
    date: Optional[str] = Query(None, description="日期（YYYY-MM-DD 格式），默认为今天"),
    current_user = Depends(require_admin)
):
    """
    获取限流统计（需要管理员权限）
    
    返回指定日期的限流统计数据，包括：
    - 总限流次数
    - 按 API 路径统计
    - 按限流键统计
    """
    stats_service = get_rate_limit_stats_service()
    stats = await stats_service.get_stats(date)
    
    # 转换 Pydantic 模型为字典
    response_data = RateLimitStatsResponse(**stats).model_dump()
    
    return success_response(
        data=response_data,
        message="获取限流统计成功"
    )


@router.get("/events", response_model=List[RateLimitEventResponse])
async def get_rate_limit_events(
    date: Optional[str] = Query(None, description="日期（YYYY-MM-DD 格式），默认为今天"),
    limit: int = Query(100, description="返回数量限制", ge=1, le=1000),
    current_user = Depends(require_admin)
):
    """
    获取限流事件列表（需要管理员权限）
    
    返回最近的限流触发事件，用于分析和调试。
    """
    stats_service = get_rate_limit_stats_service()
    events = await stats_service.get_recent_events(date, limit)
    
    # 转换 Pydantic 模型为字典列表
    response_data = [RateLimitEventResponse(**e).model_dump() for e in events]
    
    return success_response(
        data=response_data,
        message=f"获取到 {len(events)} 条限流事件"
    )


@router.get("/anomalies", response_model=List[RateLimitAnomalyResponse])
async def check_rate_limit_anomalies(
    threshold: int = Query(100, description="告警阈值", ge=10),
    current_user = Depends(require_admin)
):
    """
    检查限流异常（需要管理员权限）
    
    检测异常流量模式，如：
    - 单个用户/IP 频繁触发限流
    - 单个 API 频繁触发限流
    """
    stats_service = get_rate_limit_stats_service()
    anomalies = await stats_service.check_anomalies(threshold)
    
    # 转换 Pydantic 模型为字典列表
    response_data = [RateLimitAnomalyResponse(**a).model_dump() for a in anomalies]
    
    return success_response(
        data=response_data,
        message=f"发现 {len(anomalies)} 个异常"
    )


@router.get("/my-info", response_model=RateLimitInfoResponse)
async def get_my_rate_limit_info(
    current_user = Depends(get_current_user)
):
    """
    获取当前用户的限流信息（需要登录）
    
    返回当前用户的限流等级和各端点的限流配置。
    """
    tier = get_user_rate_limit_tier(current_user)
    limits = RATE_LIMIT_TIERS.get(tier, RATE_LIMIT_TIERS["normal"])
    
    user_id = getattr(current_user, "user_id", None) or getattr(current_user, "id", None)
    
    # 转换 Pydantic 模型为字典
    response_data = RateLimitInfoResponse(
        user_id=user_id,
        tier=tier,
        limits=limits
    ).model_dump()
    
    return success_response(
        data=response_data,
        message="获取限流信息成功"
    )


@router.delete("/stats", status_code=204)
async def clear_rate_limit_stats(
    date: Optional[str] = Query(None, description="日期（YYYY-MM-DD 格式），默认为今天"),
    current_user = Depends(require_admin)
):
    """
    清除限流统计（需要管理员权限）
    
    清除指定日期的限流统计数据。
    """
    stats_service = get_rate_limit_stats_service()
    await stats_service.clear_stats(date)
    
    logger.info(f"[RateLimit] 管理员 {current_user.username} 清除了 {date or 'today'} 的限流统计")
    
    return None

