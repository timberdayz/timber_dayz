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

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import get_async_db
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
    month: Optional[str] = Query(None, description="month in YYYY-MM-DD (first day of month)"),
    platform: Optional[str] = Query(None, description="single platform code"),
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
    granularity: str = Query(..., description="daily/weekly/monthly"),
    date: str = Query(..., description="date in YYYY-MM-DD or YYYY-MM"),
    platform: Optional[str] = Query(None, description="single platform code"),
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
    granularity: str = Query(..., description="monthly|yearly"),
    period: str = Query(..., description="YYYY-MM or YYYY"),
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


@router.get("/business-overview/shop-racing")
async def get_business_overview_shop_racing_postgresql(
    request: Request,
    granularity: str = Query(..., description="granularity"),
    date: str = Query(..., description="date"),
    group_by: str = Query("shop", description="grouping dimension"),
    platform: Optional[str] = Query(None, description="single platform code"),
    platforms: Optional[str] = Query(None, description="legacy comma-separated platform list"),
):
    try:
        effective_platform = platform or (platforms.split(",")[0].strip() if platforms else None)
        params = {
            "granularity": granularity,
            "date": date,
            "group_by": group_by,
            "platform": effective_platform,
        }
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            service = get_postgresql_dashboard_service()
            result = await service.get_business_overview_shop_racing(
                granularity=granularity,
                target_date=date,
                group_by=group_by,
                platform=effective_platform,
            )
            return json.loads(success_response(data=result).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "dashboard_shop_racing",
            cache_params,
            _produce_payload,
        )
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except ValueError as e:
        return error_response(ErrorCode.PARAMETER_INVALID, str(e), status_code=400)
    except Exception as e:
        logger.error(f"PostgreSQL compatibility shop racing query failed: {e}", exc_info=True)
        return error_response(ErrorCode.DATABASE_QUERY_ERROR, f"查询失败: {str(e)}", status_code=500)


@router.get("/business-overview/traffic-ranking")
async def get_business_overview_traffic_ranking_postgresql(
    request: Request,
    granularity: str = Query(..., description="granularity"),
    dimension: str = Query("visitor", description="ranking dimension"),
    date: Optional[str] = Query(None, description="date"),
    date_value: Optional[str] = Query(None, description="legacy date alias"),
    platform: Optional[str] = Query(None, description="single platform code"),
    platforms: Optional[str] = Query(None, description="legacy comma-separated platform list"),
    shops: Optional[str] = Query(None, description="legacy shop filter (currently unused)"),
):
    try:
        target_date = date or date_value
        if not target_date:
            raise ValueError("date is required")
        effective_platform = platform or (platforms.split(",")[0].strip() if platforms else None)
        params = {
            "granularity": granularity,
            "dimension": dimension,
            "date": target_date,
            "platform": effective_platform,
        }
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            service = get_postgresql_dashboard_service()
            result = await service.get_business_overview_traffic_ranking(
                granularity=granularity,
                target_date=target_date,
                dimension=dimension,
                platform=effective_platform,
            )
            return json.loads(success_response(data=result).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "dashboard_traffic_ranking",
            cache_params,
            _produce_payload,
        )
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except ValueError as e:
        return error_response(ErrorCode.PARAMETER_INVALID, str(e), status_code=400)
    except Exception as e:
        logger.error(f"PostgreSQL compatibility traffic ranking query failed: {e}", exc_info=True)
        return error_response(ErrorCode.DATABASE_QUERY_ERROR, f"查询失败: {str(e)}", status_code=500)


@router.get("/business-overview/inventory-backlog")
async def get_business_overview_inventory_backlog_postgresql(
    request: Request,
    days: Optional[int] = Query(30, description="minimum turnover days"),
):
    try:
        params = {"days": days}
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            service = get_postgresql_dashboard_service()
            result = await service.get_business_overview_inventory_backlog(min_days=days or 30)
            return json.loads(success_response(data=result).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "dashboard_inventory_backlog",
            cache_params,
            _produce_payload,
        )
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except ValueError as e:
        return error_response(ErrorCode.PARAMETER_INVALID, str(e), status_code=400)
    except Exception as e:
        logger.error(f"PostgreSQL inventory backlog query failed: {e}", exc_info=True)
        return error_response(ErrorCode.DATABASE_QUERY_ERROR, f"查询失败: {str(e)}", status_code=500)


@router.get("/business-overview/operational-metrics")
async def get_business_overview_operational_metrics_postgresql(
    request: Request,
    month: Optional[str] = Query(None, description="month in YYYY-MM-DD"),
    platform: Optional[str] = Query(None, description="single platform code"),
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
            result = await service.get_business_overview_operational_metrics(
                month=month,
                platform=platform,
            )
            return json.loads(success_response(data=result).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "dashboard_operational_metrics",
            cache_params,
            _produce_payload,
        )
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except ValueError as e:
        return error_response(ErrorCode.PARAMETER_INVALID, str(e), status_code=400)
    except Exception as e:
        logger.error(f"PostgreSQL compatibility operational metrics query failed: {e}", exc_info=True)
        return error_response(ErrorCode.DATABASE_QUERY_ERROR, f"查询失败: {str(e)}", status_code=500)


@router.get("/clearance-ranking")
async def get_clearance_ranking_postgresql(
    request: Request,
    limit: int = Query(100, description="row limit"),
):
    try:
        params = {"limit": limit}
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            service = get_postgresql_dashboard_service()
            result = await service.get_clearance_ranking(limit=limit)
            return json.loads(success_response(data=result).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "dashboard_clearance_ranking",
            cache_params,
            _produce_payload,
        )
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except ValueError as e:
        return error_response(ErrorCode.PARAMETER_INVALID, str(e), status_code=400)
    except Exception as e:
        logger.error(f"PostgreSQL clearance ranking query failed: {e}", exc_info=True)
        return error_response(ErrorCode.DATABASE_QUERY_ERROR, f"查询失败: {str(e)}", status_code=500)


@router.get("/annual-summary/trend")
async def get_annual_summary_trend_postgresql(
    request: Request,
    granularity: str = Query(..., description="monthly|yearly"),
    period: str = Query(..., description="YYYY-MM or YYYY"),
):
    try:
        params = {"granularity": granularity, "period": period}
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            service = get_postgresql_dashboard_service()
            result = await service.get_annual_summary_trend(granularity=granularity, period=period)
            return json.loads(success_response(data=result).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "annual_summary_trend",
            cache_params,
            _produce_payload,
        )
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except ValueError as e:
        return error_response(ErrorCode.PARAMETER_INVALID, str(e), status_code=400)
    except Exception as e:
        logger.error(f"PostgreSQL annual summary trend query failed: {e}", exc_info=True)
        return error_response(ErrorCode.DATABASE_QUERY_ERROR, f"查询失败: {str(e)}", status_code=500)


@router.get("/annual-summary/platform-share")
async def get_annual_summary_platform_share_postgresql(
    request: Request,
    granularity: str = Query(..., description="monthly|yearly"),
    period: str = Query(..., description="YYYY-MM or YYYY"),
):
    try:
        params = {"granularity": granularity, "period": period}
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            service = get_postgresql_dashboard_service()
            result = await service.get_annual_summary_platform_share(granularity=granularity, period=period)
            return json.loads(success_response(data=result).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "annual_summary_platform_share",
            cache_params,
            _produce_payload,
        )
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except ValueError as e:
        return error_response(ErrorCode.PARAMETER_INVALID, str(e), status_code=400)
    except Exception as e:
        logger.error(f"PostgreSQL annual summary platform share query failed: {e}", exc_info=True)
        return error_response(ErrorCode.DATABASE_QUERY_ERROR, f"查询失败: {str(e)}", status_code=500)


@router.get("/annual-summary/by-shop")
async def get_annual_summary_by_shop_postgresql(
    request: Request,
    granularity: str = Query(..., description="monthly|yearly"),
    period: str = Query(..., description="YYYY-MM or YYYY"),
):
    try:
        params = {"granularity": granularity, "period": period}
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            service = get_postgresql_dashboard_service()
            result = await service.get_annual_summary_by_shop(granularity=granularity, period=period)
            return json.loads(success_response(data=result).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "annual_summary_by_shop",
            cache_params,
            _produce_payload,
        )
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except ValueError as e:
        return error_response(ErrorCode.PARAMETER_INVALID, str(e), status_code=400)
    except Exception as e:
        logger.error(f"PostgreSQL annual summary by shop query failed: {e}", exc_info=True)
        return error_response(ErrorCode.DATABASE_QUERY_ERROR, f"查询失败: {str(e)}", status_code=500)


@router.get("/annual-summary/target-completion")
async def get_annual_summary_target_completion_postgresql(
    request: Request,
    granularity: str = Query(..., description="monthly|yearly"),
    period: str = Query(..., description="YYYY-MM or YYYY"),
    db: AsyncSession = Depends(get_async_db),
):
    try:
        params = {"granularity": granularity, "period": period}
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            service = get_postgresql_dashboard_service()
            result = await service.get_annual_summary_target_completion(
                db=db,
                granularity=granularity,
                period=period,
            )
            return json.loads(success_response(data=result).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "annual_summary_target_completion",
            cache_params,
            _produce_payload,
        )
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except ValueError as e:
        return error_response(ErrorCode.PARAMETER_INVALID, str(e), status_code=400)
    except Exception as e:
        logger.error(f"PostgreSQL annual summary target completion query failed: {e}", exc_info=True)
        return error_response(ErrorCode.DATABASE_QUERY_ERROR, f"查询失败: {str(e)}", status_code=500)
