"""
Clean PostgreSQL-backed dashboard router.

This module exists to avoid coupling the new PostgreSQL cutover work to the
legacy `dashboard_api.py`, which currently contains historical encoding noise.
Once PostgreSQL coverage is sufficient, `main.py` can switch router binding via
feature flag.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from backend.services.postgresql_dashboard_service import get_postgresql_dashboard_service
from backend.utils.api_response import error_response, success_response
from backend.utils.error_codes import ErrorCode
from modules.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard-postgresql"])


def _normalize_cache_params(params: Dict[str, Any]) -> Dict[str, str]:
    return {k: "" if v is None else str(v) for k, v in params.items()}


async def _resolve_cached_payload(
    request: Request,
    cache_type: str,
    cache_params: Dict[str, Any],
    producer,
):
    if request and hasattr(request.app.state, "cache_service"):
        cache_service = request.app.state.cache_service
        cached = await cache_service.get(cache_type, **cache_params)
        if cached is not None:
            return cached, "HIT"
        payload = await cache_service.get_or_set_singleflight(cache_type, producer, **cache_params)
        return payload, "MISS"
    payload = await producer()
    return payload, "BYPASS"


@router.get("/business-overview/kpi")
async def get_business_overview_kpi_postgresql(
    request: Request,
    month: Optional[str] = Query(None, description="月份(格式:YYYY-MM-DD,传入月初日期)"),
    platform: Optional[str] = Query(None, description="平台代码(可选)"),
):
    from datetime import datetime

    try:
        if not month:
            today = datetime.now()
            month = f"{today.year}-{today.month:02d}-01"
        params = {"month": month, "platform": platform}
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            service = get_postgresql_dashboard_service()
            result = await service.get_business_overview_kpi(month=month, platform=platform)
            return json.loads(success_response(data=result).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "dashboard_kpi",
            cache_params,
            _produce_payload,
        )
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except ValueError as e:
        return error_response(ErrorCode.PARAMETER_INVALID, str(e), status_code=400)
    except Exception as e:
        logger.error(f"PostgreSQL KPI query failed: {e}", exc_info=True)
        return error_response(ErrorCode.DATABASE_QUERY_ERROR, f"查询失败: {str(e)}", status_code=500)


@router.get("/business-overview/comparison")
async def get_business_overview_comparison_postgresql(
    request: Request,
    granularity: str = Query(..., description="时间粒度(daily/weekly/monthly)"),
    date: str = Query(..., description="日期(YYYY-MM-DD 或 YYYY-MM)"),
    platform: Optional[str] = Query(None, description="平台代码"),
):
    try:
        params = {"granularity": granularity, "date": date, "platform": platform}
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            service = get_postgresql_dashboard_service()
            result = await service.get_business_overview_comparison(
                granularity=granularity,
                target_date=date,
                platform=platform,
            )
            return json.loads(success_response(data=result).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "dashboard_comparison",
            cache_params,
            _produce_payload,
        )
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except ValueError as e:
        return error_response(ErrorCode.PARAMETER_INVALID, str(e), status_code=400)
    except Exception as e:
        logger.error(f"PostgreSQL comparison query failed: {e}", exc_info=True)
        return error_response(ErrorCode.DATABASE_QUERY_ERROR, f"查询失败: {str(e)}", status_code=500)


@router.get("/annual-summary/kpi")
async def get_annual_summary_kpi_postgresql(
    request: Request,
    granularity: str = Query(..., description="粒度(monthly|yearly)"),
    period: str = Query(..., description="周期: 月度YYYY-MM 或 年度YYYY"),
):
    try:
        params = {"granularity": granularity, "period": period}
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            service = get_postgresql_dashboard_service()
            result = await service.get_annual_summary_kpi(granularity=granularity, period=period)
            return json.loads(success_response(data=result).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "annual_summary_kpi",
            cache_params,
            _produce_payload,
        )
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except ValueError as e:
        return error_response(ErrorCode.PARAMETER_INVALID, str(e), status_code=400)
    except Exception as e:
        logger.error(f"PostgreSQL annual summary KPI query failed: {e}", exc_info=True)
        return error_response(ErrorCode.DATABASE_QUERY_ERROR, f"查询失败: {str(e)}", status_code=500)
