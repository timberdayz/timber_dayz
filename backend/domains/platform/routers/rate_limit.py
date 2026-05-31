#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
限流管理 API 路由。
"""

from __future__ import annotations

import os
from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from backend.dependencies.auth import get_current_user, require_admin
from backend.middleware.rate_limiter import (
    RATE_LIMIT_TIERS,
    get_rate_limit_for_endpoint,
    get_user_rate_limit_tier,
)
from backend.schemas.rate_limit import (
    RateLimitAnomalyResponse,
    RateLimitConfigResponse,
    RateLimitEventResponse,
    RateLimitInfoResponse,
    RateLimitStatsResponse,
)
from backend.services.rate_limit_stats import get_rate_limit_stats_service
from backend.utils.api_response import success_response
from modules.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/rate-limit", tags=["限流管理"])


@router.get("/config", response_model=RateLimitConfigResponse)
async def get_rate_limit_config(current_user=Depends(require_admin)):
    enabled = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
    response_data = RateLimitConfigResponse(
        enabled=enabled,
        default_limit=get_rate_limit_for_endpoint("default", "normal"),
        tiers=RATE_LIMIT_TIERS,
    ).model_dump()
    return success_response(data=response_data, message="获取限流配置成功")


@router.get("/stats", response_model=RateLimitStatsResponse)
async def get_rate_limit_stats(
    date: Optional[str] = Query(None, description="日期(YYYY-MM-DD)"),
    current_user=Depends(require_admin),
):
    stats_service = get_rate_limit_stats_service()
    stats = await stats_service.get_stats(date)
    return success_response(data=RateLimitStatsResponse(**stats).model_dump(), message="获取限流统计成功")


@router.get("/events", response_model=List[RateLimitEventResponse])
async def get_rate_limit_events(
    date: Optional[str] = Query(None, description="日期(YYYY-MM-DD)"),
    limit: int = Query(100, description="返回数量限制", ge=1, le=1000),
    current_user=Depends(require_admin),
):
    stats_service = get_rate_limit_stats_service()
    events = await stats_service.get_recent_events(date, limit)
    response_data = [RateLimitEventResponse(**event).model_dump() for event in events]
    return success_response(data=response_data, message=f"获取到 {len(events)} 条限流事件")


@router.get("/anomalies", response_model=List[RateLimitAnomalyResponse])
async def check_rate_limit_anomalies(
    threshold: int = Query(100, description="告警阈值", ge=10),
    current_user=Depends(require_admin),
):
    stats_service = get_rate_limit_stats_service()
    anomalies = await stats_service.check_anomalies(threshold)
    response_data = [RateLimitAnomalyResponse(**item).model_dump() for item in anomalies]
    return success_response(data=response_data, message=f"发现 {len(anomalies)} 个异常")


@router.get("/my-info", response_model=RateLimitInfoResponse)
async def get_my_rate_limit_info(current_user=Depends(get_current_user)):
    tier = get_user_rate_limit_tier(current_user)
    limits = RATE_LIMIT_TIERS.get(tier, RATE_LIMIT_TIERS["normal"])
    user_id = getattr(current_user, "user_id", None) or getattr(current_user, "id", None)
    response_data = RateLimitInfoResponse(user_id=user_id, tier=tier, limits=limits).model_dump()
    return success_response(data=response_data, message="获取限流信息成功")


@router.delete("/stats", status_code=204)
async def clear_rate_limit_stats(
    date: Optional[str] = Query(None, description="日期(YYYY-MM-DD)"),
    current_user=Depends(require_admin),
):
    stats_service = get_rate_limit_stats_service()
    await stats_service.clear_stats(date)
    logger.info("[RateLimit] admin %s cleared stats for %s", current_user.username, date or "today")
    return None
