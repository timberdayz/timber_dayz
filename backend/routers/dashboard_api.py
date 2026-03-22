"""
Legacy Dashboard API router.

This file keeps the Metabase compatibility path alive for fallback only.
The PostgreSQL-first dashboard path lives in dashboard_api_postgresql.py.
"""

import json
from fastapi import APIRouter, Query, Depends, Request
from fastapi.responses import JSONResponse
from typing import Optional, Dict, Any, List
from modules.core.logger import get_logger
from backend.utils.api_response import success_response, error_response
from backend.utils.error_codes import ErrorCode
from backend.services.metabase_question_service import (
    get_metabase_service,
    MetabaseUnavailableError,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from backend.models.database import get_async_db

logger = get_logger(__name__)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

DASHBOARD_DATA_SOURCE_MAP = {
    "business_overview_kpi": {
        "route": "/business-overview/kpi",
        "source": "metabase_question",
        "query_key": "business_overview_kpi",
    },
    "business_overview_comparison": {
        "route": "/business-overview/comparison",
        "source": "metabase_question",
        "query_key": "business_overview_comparison",
    },
    "business_overview_shop_racing": {
        "route": "/business-overview/shop-racing",
        "source": "metabase_question",
        "query_key": "business_overview_shop_racing",
    },
    "business_overview_traffic_ranking": {
        "route": "/business-overview/traffic-ranking",
        "source": "metabase_question",
        "query_key": "business_overview_traffic_ranking",
    },
    "business_overview_inventory_backlog": {
        "route": "/business-overview/inventory-backlog",
        "source": "metabase_question",
        "query_key": "business_overview_inventory_backlog",
    },
    "business_overview_operational_metrics": {
        "route": "/business-overview/operational-metrics",
        "source": "metabase_question",
        "query_key": "business_overview_operational_metrics",
    },
    "clearance_ranking": {
        "route": "/clearance-ranking",
        "source": "metabase_question",
        "query_key": "clearance_ranking",
    },
    "annual_summary_kpi": {
        "route": "/annual-summary/kpi",
        "source": "hybrid_metabase_postgresql",
        "query_key": "annual_summary_kpi",
    },
    "annual_summary_by_shop": {
        "route": "/annual-summary/by-shop",
        "source": "postgresql_service",
        "query_key": "annual_cost_aggregate_by_shop",
    },
    "annual_summary_trend": {
        "route": "/annual-summary/trend",
        "source": "metabase_question",
        "query_key": "annual_summary_trend",
    },
    "annual_summary_platform_share": {
        "route": "/annual-summary/platform-share",
        "source": "metabase_question",
        "query_key": "annual_summary_platform_share",
    },
    "annual_summary_target_completion": {
        "route": "/annual-summary/target-completion",
        "source": "postgresql_sql",
        "query_key": "annual_summary_target_completion",
    },
}


def _normalize_cache_params(params: Dict[str, Any]) -> Dict[str, str]:
    """规范化缓存 Key 参数，确保相同语义生成相同 Key（None→空字符串）"""
    return {k: "" if v is None else str(v) for k, v in params.items()}


METABASE_UNAVAILABLE_ERROR_CODE = "METABASE_UNAVAILABLE"


def metabase_unavailable_response(message: str = "Metabase服务暂时不可用，请稍后重试") -> JSONResponse:
    """Metabase 不可用时的统一响应（保留 error_code 字符串供前端区分）"""
    return JSONResponse(
        status_code=503,
        content={
            "success": False,
            "data": None,
            "message": message,
            "error": {"code": METABASE_UNAVAILABLE_ERROR_CODE},
            "error_code": METABASE_UNAVAILABLE_ERROR_CODE,
        },
    )




def _is_metabase_question_missing_error(exc: Exception) -> bool:
    message = str(exc)
    return "Question ID" in message or "METABASE" in message


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
        payload = await cache_service.get_or_set_singleflight(
            cache_type,
            producer,
            **cache_params,
        )
        return payload, "MISS"

    payload = await producer()
    return payload, "BYPASS"


@router.get("/business-overview/kpi")
async def get_business_overview_kpi(
    request: Request,
    month: Optional[str] = Query(None, description="月份(格式:YYYY-MM-DD,传入月初日期)"),
    platform: Optional[str] = Query(None, description="平台代码(可选,为空则选择全部平台)"),
    # 保留旧参数用于兼容
    start_date: Optional[str] = Query(None, description="[已弃用] 开始日期"),
    end_date: Optional[str] = Query(None, description="[已弃用] 结束日期"),
    platforms: Optional[str] = Query(None, description="[已弃用] 平台代码(逗号分隔)"),
    shops: Optional[str] = Query(None, description="[已弃用] 店铺ID(逗号分隔)")
):
    """
    获取业务概览KPI数据
    
    通过Metabase Question查询关键业务指标
    
    参数说明:
    - month: 月份选择,格式为 YYYY-MM-DD(月初日期),如 2025-09-01
    - platform: 平台筛选,可选值: shopee, tiktok, miaoshou;为空则选择全部平台
    
    返回值:
    - GMV(元): 总成交金额
    - 订单数: 去重订单数量
    - 访客数: 总访客数
    - 转化率(%): 订单数/访客数*100
    - 客单价(元): GMV/订单数
    """
    from datetime import datetime
    
    try:
        # 如果没有传入 month,使用当前月份
        if not month:
            today = datetime.now()
            month = f"{today.year}-{today.month:02d}-01"
        
        params = {"month": month, "platform": platform}
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            service = get_metabase_service()
            metabase_params = {k: v for k, v in params.items() if v is not None}
            logger.info(f"[KPI鏌ヨ] 鍙傛暟: month={month}, platform={platform}")
            result = await service.query_question("business_overview_kpi", metabase_params)
            return json.loads(success_response(data=result).body.decode())

        if request and hasattr(request.app.state, "cache_service"):
            cache_service = request.app.state.cache_service
            cached = await cache_service.get("dashboard_kpi", **cache_params)
            if cached is not None:
                return JSONResponse(content=cached, headers={"X-Cache": "HIT"})
            payload = await cache_service.get_or_set_singleflight(
                "dashboard_kpi",
                _produce_payload,
                **cache_params,
            )
            return JSONResponse(content=payload, headers={"X-Cache": "MISS"})

        payload = await _produce_payload()
        return JSONResponse(content=payload, headers={"X-Cache": "BYPASS"})
    except MetabaseUnavailableError as e:
        logger.warning(f"业务概览KPI查询失败（Metabase不可用）: {e}")
        return metabase_unavailable_response(str(e) or "Metabase服务暂时不可用，请稍后重试")
    except ValueError as e:
        logger.error(f"业务概览KPI查询失败: {e}")
        return error_response(
            ErrorCode.PARAMETER_INVALID,
            str(e),
            status_code=400,
            recovery_suggestion="请检查请求参数",
        )
    except Exception as e:
        logger.error(f"业务概览KPI查询异常: {e}", exc_info=True)
        return error_response(
            ErrorCode.DATABASE_QUERY_ERROR,
            f"查询失败: {str(e)}",
            status_code=500,
            detail=str(e),
            recovery_suggestion="请稍后重试",
        )


def _normalize_comparison_date(date_str: str) -> str:
    """规范化对比日期为 YYYY-MM-DD，支持 YYYY-MM 自动补 01。"""
    if not date_str or not isinstance(date_str, str):
        raise ValueError("日期不能为空")
    s = date_str.strip()
    if len(s) == 7 and s[4] == "-":
        return f"{s}-01"
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    raise ValueError("日期格式应为 YYYY-MM-DD 或 YYYY-MM")


@router.get("/business-overview/comparison")
async def get_business_overview_comparison(
    request: Request,
    granularity: str = Query(..., description="时间粒度(daily/weekly/monthly)"),
    date: str = Query(..., description="日期(YYYY-MM-DD 或 YYYY-MM)"),
    platforms: Optional[str] = Query(None, description="平台代码(逗号分隔，传第一个)"),
    shops: Optional[str] = Query(None, description="店铺ID(逗号分隔)")
):
    """
    获取业务概览数据对比(日/周/月度)
    """
    try:
        if granularity not in ("daily", "weekly", "monthly"):
            raise ValueError("粒度必须为 daily、weekly 或 monthly")
        date_normalized = _normalize_comparison_date(date)
        params = {"granularity": granularity, "date": date_normalized, "platforms": platforms, "shops": shops}
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            service = get_metabase_service()
            metabase_params = {k: v for k, v in params.items() if v is not None}
            result = await service.query_question("business_overview_comparison", metabase_params)
            return json.loads(success_response(data=result).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "dashboard_comparison",
            cache_params,
            _produce_payload,
        )
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except MetabaseUnavailableError as e:
        logger.warning(f"业务概览对比查询失败（Metabase不可用）: {e}")
        return metabase_unavailable_response(str(e) or "Metabase服务暂时不可用，请稍后重试")
    except ValueError as e:
        logger.error(f"业务概览对比查询失败: {e}")
        return error_response(
            ErrorCode.PARAMETER_INVALID,
            str(e),
            status_code=400,
            recovery_suggestion="请检查请求参数",
        )
    except Exception as e:
        logger.error(f"业务概览对比查询异常: {e}", exc_info=True)
        return error_response(
            ErrorCode.DATABASE_QUERY_ERROR,
            f"查询失败: {str(e)}",
            status_code=500,
            detail=str(e),
            recovery_suggestion="请稍后重试",
        )


@router.get("/business-overview/shop-racing")
async def get_business_overview_shop_racing(
    request: Request,
    granularity: str = Query(..., description="时间粒度"),
    date: str = Query(..., description="日期"),
    group_by: str = Query("shop", description="分组维度"),
    platforms: Optional[str] = Query(None, description="平台代码(逗号分隔)")
):
    """
    获取店铺赛马数据
    """
    try:
        params = {"granularity": granularity, "date": date, "group_by": group_by, "platforms": platforms}
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            service = get_metabase_service()
            metabase_params = {k: v for k, v in params.items() if v is not None}
            result = await service.query_question("business_overview_shop_racing", metabase_params)
            return json.loads(success_response(data=result).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "dashboard_shop_racing",
            cache_params,
            _produce_payload,
        )
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except MetabaseUnavailableError as e:
        logger.warning(f"店铺赛马数据查询失败（Metabase不可用）: {e}")
        return metabase_unavailable_response(str(e) or "Metabase服务暂时不可用，请稍后重试")
    except ValueError as e:
        logger.error(f"店铺赛马数据查询失败: {e}")
        return error_response(
            ErrorCode.PARAMETER_INVALID,
            str(e),
            status_code=400,
            recovery_suggestion="请检查请求参数",
        )
    except Exception as e:
        logger.error(f"店铺赛马数据查询异常: {e}", exc_info=True)
        return error_response(
            ErrorCode.DATABASE_QUERY_ERROR,
            f"查询失败: {str(e)}",
            status_code=500,
            detail=str(e),
            recovery_suggestion="请稍后重试",
        )


@router.get("/business-overview/traffic-ranking")
async def get_business_overview_traffic_ranking(
    request: Request,
    granularity: Optional[str] = Query(None, description="时间粒度"),
    dimension: Optional[str] = Query(None, description="维度"),
    date_value: Optional[str] = Query(None, description="日期值"),
    platforms: Optional[str] = Query(None, description="平台代码(逗号分隔)"),
    shops: Optional[str] = Query(None, description="店铺ID(逗号分隔)")
):
    """
    获取流量排名数据
    """
    try:
        # 前端 dimension：shop/account → Question 排序维度：visitor/pv
        question_dimension = "pv" if dimension == "account" else "visitor"
        params = {"granularity": granularity, "dimension": question_dimension, "date": date_value, "platforms": platforms, "shops": shops}
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            service = get_metabase_service()
            metabase_params = {k: v for k, v in params.items() if v is not None}
            result = await service.query_question("business_overview_traffic_ranking", metabase_params)
            return json.loads(success_response(data=result).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "dashboard_traffic_ranking",
            cache_params,
            _produce_payload,
        )
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except MetabaseUnavailableError as e:
        logger.warning(f"流量排名数据查询失败（Metabase不可用）: {e}")
        return metabase_unavailable_response(str(e) or "Metabase服务暂时不可用，请稍后重试")
    except ValueError as e:
        logger.error(f"流量排名数据查询失败: {e}")
        return error_response(
            ErrorCode.PARAMETER_INVALID,
            str(e),
            status_code=400,
            recovery_suggestion="请检查请求参数",
        )
    except Exception as e:
        logger.error(f"流量排名数据查询异常: {e}", exc_info=True)
        return error_response(
            ErrorCode.DATABASE_QUERY_ERROR,
            f"查询失败: {str(e)}",
            status_code=500,
            detail=str(e),
            recovery_suggestion="请稍后重试",
        )


@router.get("/business-overview/inventory-backlog")
async def get_business_overview_inventory_backlog(
    request: Request,
    days: Optional[int] = Query(None, description="天数"),
    platforms: Optional[str] = Query(None, description="平台代码(逗号分隔)"),
    shops: Optional[str] = Query(None, description="店铺ID(逗号分隔)")
):
    """
    获取库存积压数据
    """
    try:
        params = {"days": str(days) if days is not None else "", "platforms": platforms, "shops": shops}
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            service = get_metabase_service()
            metabase_params = {"days": str(days) if days else None, "platforms": platforms, "shops": shops}
            metabase_params = {k: v for k, v in metabase_params.items() if v is not None}
            result = await service.query_question("business_overview_inventory_backlog", metabase_params)
            return json.loads(success_response(data=result).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "dashboard_inventory_backlog",
            cache_params,
            _produce_payload,
        )
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except MetabaseUnavailableError as e:
        logger.warning(f"库存积压数据查询失败（Metabase不可用）: {e}")
        return metabase_unavailable_response(str(e) or "Metabase服务暂时不可用，请稍后重试")
    except ValueError as e:
        logger.error(f"库存积压数据查询失败: {e}")
        return error_response(
            ErrorCode.PARAMETER_INVALID,
            str(e),
            status_code=400,
            recovery_suggestion="请检查请求参数",
        )
    except Exception as e:
        logger.error(f"库存积压数据查询异常: {e}", exc_info=True)
        return error_response(
            ErrorCode.DATABASE_QUERY_ERROR,
            f"查询失败: {str(e)}",
            status_code=500,
            detail=str(e),
            recovery_suggestion="请稍后重试",
        )


@router.get("/business-overview/operational-metrics")
async def get_business_overview_operational_metrics(
    request: Request,
    month: Optional[str] = Query(None, description="月份,格式 YYYY-MM-DD 月初,默认当月"),
    platform: Optional[str] = Query(None, description="平台代码,与核心KPI一致")
):
    """
    获取经营指标数据(与核心KPI同参数:月份、平台)
    """
    try:
        from datetime import date
        if not month:
            today = date.today()
            month = today.replace(day=1).isoformat()
        params = {"month": month, "platform": platform}
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            service = get_metabase_service()
            metabase_params = {k: v for k, v in params.items() if v is not None}
            result = await service.query_question("business_overview_operational_metrics", metabase_params)
            return json.loads(success_response(data=result).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "dashboard_operational_metrics",
            cache_params,
            _produce_payload,
        )
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except MetabaseUnavailableError as e:
        logger.warning(f"经营指标数据查询失败（Metabase不可用）: {e}")
        return metabase_unavailable_response(str(e) or "Metabase服务暂时不可用，请稍后重试")
    except ValueError as e:
        logger.error(f"经营指标数据查询失败: {e}")
        return error_response(
            ErrorCode.PARAMETER_INVALID,
            str(e),
            status_code=400,
            recovery_suggestion="请检查请求参数",
        )
    except Exception as e:
        logger.error(f"经营指标数据查询异常: {e}", exc_info=True)
        return error_response(
            ErrorCode.DATABASE_QUERY_ERROR,
            f"查询失败: {str(e)}",
            status_code=500,
            detail=str(e),
            recovery_suggestion="请稍后重试",
        )


@router.get("/clearance-ranking")
async def get_clearance_ranking(
    request: Request,
    start_date: Optional[str] = Query(None, description="开始日期"),
    end_date: Optional[str] = Query(None, description="结束日期"),
    platforms: Optional[str] = Query(None, description="平台代码(逗号分隔)"),
    shops: Optional[str] = Query(None, description="店铺ID(逗号分隔)"),
    limit: Optional[int] = Query(10, description="返回数量")
):
    """
    获取清仓排名数据
    """
    try:
        params = {
            "start_date": start_date,
            "end_date": end_date,
            "platforms": platforms,
            "shops": shops,
            "limit": str(limit) if limit is not None else ""
        }
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            service = get_metabase_service()
            metabase_params = {
                "start_date": start_date,
                "end_date": end_date,
                "platforms": platforms,
                "shops": shops,
                "limit": str(limit) if limit else None
            }
            metabase_params = {k: v for k, v in metabase_params.items() if v is not None}
            result = await service.query_question("clearance_ranking", metabase_params)
            return json.loads(success_response(data=result).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "dashboard_clearance_ranking",
            cache_params,
            _produce_payload,
        )
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except MetabaseUnavailableError as e:
        logger.warning(f"清仓排名数据查询失败（Metabase不可用）: {e}")
        return metabase_unavailable_response(str(e) or "Metabase服务暂时不可用，请稍后重试")
    except ValueError as e:
        logger.error(f"清仓排名数据查询失败: {e}")
        return error_response(
            ErrorCode.PARAMETER_INVALID,
            str(e),
            status_code=400,
            recovery_suggestion="请检查请求参数",
        )
    except Exception as e:
        logger.error(f"清仓排名数据查询异常: {e}", exc_info=True)
        return error_response(
            ErrorCode.DATABASE_QUERY_ERROR,
            f"查询失败: {str(e)}",
            status_code=500,
            detail=str(e),
            recovery_suggestion="请稍后重试",
        )


@router.get("/annual-summary/kpi")
async def get_annual_summary_kpi(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    granularity: str = Query(..., description="\u7c92\u5ea6(monthly|yearly)"),
    period: str = Query(..., description="\u5468\u671f: \u6708\u5ea6YYYY-MM \u6216 \u5e74\u5ea6YYYY"),
):
    """\u5e74\u5ea6\u6570\u636e\u603b\u7ed3\u6838\u5fc3 KPI\uff0c\u8865\u5145\u6210\u672c\u805a\u5408\u7ed3\u679c\u3002"""
    try:
        if granularity not in ("monthly", "yearly"):
            raise ValueError("granularity \u5fc5\u987b\u4e3a monthly \u6216 yearly")
        params = {"granularity": granularity, "period": period}
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            service = get_metabase_service()
            metabase_params = {k: v for k, v in params.items() if v}
            logger.info(f"[annual-summary-kpi] granularity={granularity}, period={period}")

            result = await service.query_question("annual_summary_kpi", metabase_params)
            if not isinstance(result, dict):
                result = result or {}

            from backend.services.annual_cost_aggregate import get_annual_cost_aggregate

            cost_agg = await get_annual_cost_aggregate(db, granularity, period)
            result["total_cost"] = cost_agg["total_cost"]
            result["gmv"] = result.get("gmv") if result.get("gmv") is not None else cost_agg["gmv"]
            result["cost_to_revenue_ratio"] = cost_agg["cost_to_revenue_ratio"]
            result["roi"] = cost_agg["roi"]
            result["gross_margin"] = cost_agg["gross_margin"]
            result["net_margin"] = cost_agg["net_margin"]
            return json.loads(success_response(data=result).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "annual_summary_kpi",
            cache_params,
            _produce_payload,
        )
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except MetabaseUnavailableError as e:
        logger.warning(f"\u5e74\u5ea6\u603b\u7ed3 KPI \u67e5\u8be2\u5931\u8d25\uff08Metabase\u4e0d\u53ef\u7528\uff09: {e}")
        return metabase_unavailable_response(str(e) or "Metabase\u670d\u52a1\u6682\u65f6\u4e0d\u53ef\u7528\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5")
    except ValueError as e:
        logger.error(f"\u5e74\u5ea6\u603b\u7ed3 KPI \u53c2\u6570\u6821\u9a8c\u5931\u8d25: {e}")
        return error_response(
            ErrorCode.PARAMETER_INVALID,
            str(e),
            status_code=400,
            recovery_suggestion="\u8bf7\u68c0\u67e5\u8bf7\u6c42\u53c2\u6570",
        )
    except Exception as e:
        logger.error(f"\u5e74\u5ea6\u603b\u7ed3 KPI \u67e5\u8be2\u5f02\u5e38: {e}", exc_info=True)
        return error_response(
            ErrorCode.DATABASE_QUERY_ERROR,
            f"\u67e5\u8be2\u5931\u8d25: {str(e)}",
            status_code=500,
            detail=str(e),
            recovery_suggestion="\u8bf7\u7a0d\u540e\u91cd\u8bd5",
        )


@router.get("/annual-summary/by-shop")
async def get_annual_summary_by_shop(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    granularity: str = Query(..., description="\u7c92\u5ea6(monthly|yearly)"),
    period: str = Query(..., description="\u5468\u671f: \u6708\u5ea6YYYY-MM \u6216 \u5e74\u5ea6YYYY"),
):
    """\u5e74\u5ea6\u6570\u636e\u603b\u7ed3\u6309\u5e97\u94fa\u4e0b\u94bb\u3002"""
    try:
        if granularity not in ("monthly", "yearly"):
            raise ValueError("granularity \u5fc5\u987b\u4e3a monthly \u6216 yearly")
        params = {"granularity": granularity, "period": period}
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            from backend.services.annual_cost_aggregate import get_annual_cost_aggregate_by_shop

            data = await get_annual_cost_aggregate_by_shop(db, granularity, period)
            return json.loads(success_response(data=data).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "annual_summary_by_shop",
            cache_params,
            _produce_payload,
        )
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except ValueError as e:
        logger.error(f"\u5e74\u5ea6\u603b\u7ed3\u6309\u5e97\u94fa\u67e5\u8be2\u53c2\u6570\u6821\u9a8c\u5931\u8d25: {e}")
        return error_response(
            ErrorCode.PARAMETER_INVALID,
            str(e),
            status_code=400,
            recovery_suggestion="\u8bf7\u68c0\u67e5\u8bf7\u6c42\u53c2\u6570",
        )
    except Exception as e:
        logger.error(f"\u5e74\u5ea6\u603b\u7ed3\u6309\u5e97\u94fa\u67e5\u8be2\u5f02\u5e38: {e}", exc_info=True)
        return error_response(
            ErrorCode.DATABASE_QUERY_ERROR,
            f"\u67e5\u8be2\u5931\u8d25: {str(e)}",
            status_code=500,
            detail=str(e),
            recovery_suggestion="\u8bf7\u7a0d\u540e\u91cd\u8bd5",
        )


@router.get("/annual-summary/trend")
async def get_annual_summary_trend(
    request: Request,
    granularity: str = Query(..., description="\u7c92\u5ea6(monthly|yearly)"),
    period: str = Query(..., description="\u5468\u671f: \u6708\u5ea6YYYY-MM \u6216 \u5e74\u5ea6YYYY"),
):
    """\u5e74\u5ea6\u6570\u636e\u603b\u7ed3\u8d8b\u52bf\u5e8f\u5217\u3002"""
    try:
        if granularity not in ("monthly", "yearly"):
            raise ValueError("granularity \u5fc5\u987b\u4e3a monthly \u6216 yearly")
        params = {"granularity": granularity, "period": period}
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            service = get_metabase_service()
            result = await service.query_question(
                "annual_summary_trend",
                {"granularity": granularity, "period": period},
            )
            data = result if isinstance(result, list) else (result.get("data") if isinstance(result, dict) else []) or []
            return json.loads(success_response(data=data).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "annual_summary_trend",
            cache_params,
            _produce_payload,
        )
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except ValueError as e:
        if _is_metabase_question_missing_error(e):
            logger.warning(f"\u5e74\u5ea6\u603b\u7ed3\u8d8b\u52bf Metabase \u95ee\u9898\u672a\u914d\u7f6e: {e}")
            return success_response(data=[])
        logger.error(f"\u5e74\u5ea6\u603b\u7ed3\u8d8b\u52bf\u53c2\u6570\u6821\u9a8c\u5931\u8d25: {e}")
        return error_response(
            ErrorCode.PARAMETER_INVALID,
            str(e),
            status_code=400,
            recovery_suggestion="\u8bf7\u68c0\u67e5\u8bf7\u6c42\u53c2\u6570",
        )
    except Exception as e:
        logger.error(f"\u5e74\u5ea6\u603b\u7ed3\u8d8b\u52bf\u67e5\u8be2\u5f02\u5e38: {e}", exc_info=True)
        return error_response(
            ErrorCode.DATABASE_QUERY_ERROR,
            f"\u67e5\u8be2\u5931\u8d25: {str(e)}",
            status_code=500,
            detail=str(e),
            recovery_suggestion="\u8bf7\u7a0d\u540e\u91cd\u8bd5",
        )


@router.get("/annual-summary/platform-share")
async def get_annual_summary_platform_share(
    request: Request,
    granularity: str = Query(..., description="\u7c92\u5ea6(monthly|yearly)"),
    period: str = Query(..., description="\u5468\u671f: \u6708\u5ea6YYYY-MM \u6216 \u5e74\u5ea6YYYY"),
):
    """\u5e74\u5ea6\u6570\u636e\u603b\u7ed3\u5e73\u53f0\u5360\u6bd4\u3002"""
    try:
        if granularity not in ("monthly", "yearly"):
            raise ValueError("granularity \u5fc5\u987b\u4e3a monthly \u6216 yearly")
        params = {"granularity": granularity, "period": period}
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            service = get_metabase_service()
            result = await service.query_question(
                "annual_summary_platform_share",
                {"granularity": granularity, "period": period},
            )
            data = result if isinstance(result, list) else (result.get("data") if isinstance(result, dict) else []) or []
            return json.loads(success_response(data=data).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "annual_summary_platform_share",
            cache_params,
            _produce_payload,
        )
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except ValueError as e:
        if _is_metabase_question_missing_error(e):
            logger.warning(f"\u5e74\u5ea6\u603b\u7ed3\u5e73\u53f0\u5360\u6bd4 Metabase \u95ee\u9898\u672a\u914d\u7f6e: {e}")
            return success_response(data=[])
        logger.error(f"\u5e74\u5ea6\u603b\u7ed3\u5e73\u53f0\u5360\u6bd4\u53c2\u6570\u6821\u9a8c\u5931\u8d25: {e}")
        return error_response(
            ErrorCode.PARAMETER_INVALID,
            str(e),
            status_code=400,
            recovery_suggestion="\u8bf7\u68c0\u67e5\u8bf7\u6c42\u53c2\u6570",
        )
    except Exception as e:
        logger.error(f"\u5e74\u5ea6\u603b\u7ed3\u5e73\u53f0\u5360\u6bd4\u67e5\u8be2\u5f02\u5e38: {e}", exc_info=True)
        return error_response(
            ErrorCode.DATABASE_QUERY_ERROR,
            f"\u67e5\u8be2\u5931\u8d25: {str(e)}",
            status_code=500,
            detail=str(e),
            recovery_suggestion="\u8bf7\u7a0d\u540e\u91cd\u8bd5",
        )


@router.get("/annual-summary/target-completion")
async def get_annual_summary_target_completion(
    request: Request,
    granularity: str = Query(..., description="\u7c92\u5ea6(monthly|yearly)"),
    period: str = Query(..., description="\u5468\u671f: \u6708\u5ea6YYYY-MM \u6216 \u5e74\u5ea6YYYY"),
    db: AsyncSession = Depends(get_async_db),
):
    """\u5e74\u5ea6\u6570\u636e\u603b\u7ed3\u76ee\u6807\u5b8c\u6210\u7387\u3002"""
    try:
        if granularity not in ("monthly", "yearly"):
            raise ValueError("granularity \u5fc5\u987b\u4e3a monthly \u6216 yearly")
        params = {"granularity": granularity, "period": period}
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            if len(period) == 4:
                year_month_filter = "year_month LIKE :period_prefix"
                db_params: dict = {"period_prefix": f"{period}-%"}
                year_month_filter_cn = '"\u5e74\u6708" LIKE :period_prefix'
            else:
                year_month_filter = "year_month = :period"
                db_params = {"period": period}
                year_month_filter_cn = '"\u5e74\u6708" = :period'

            try:
                result = await db.execute(text(f"""
                    SELECT COALESCE(SUM(target_sales_amount), 0) AS target_gmv,
                           COALESCE(SUM(target_quantity), 0) AS target_orders
                    FROM a_class.sales_targets_a
                    WHERE {year_month_filter}
                """), db_params)
            except Exception:
                await db.rollback()
                result = await db.execute(text(f"""
                    SELECT COALESCE(SUM("\u76ee\u6807\u9500\u552e\u989d"), 0) AS target_gmv,
                           COALESCE(SUM("\u76ee\u6807\u8ba2\u5355\u6570"), 0) AS target_orders
                    FROM a_class.sales_targets_a
                    WHERE {year_month_filter_cn}
                """), db_params)

            row = result.fetchone()
            target_gmv = float(row[0]) if row and row[0] is not None else 0.0
            target_orders = int(row[1]) if row and row[1] is not None else 0

            achieved_gmv = None
            try:
                service = get_metabase_service()
                kpi_result = await service.query_question(
                    "annual_summary_kpi",
                    {"granularity": granularity, "period": period},
                )
                if isinstance(kpi_result, dict) and kpi_result.get("gmv") is not None:
                    achieved_gmv = float(kpi_result["gmv"])
            except Exception as e:
                logger.warning(f"\u76ee\u6807\u5b8c\u6210\u7387\u67e5\u8be2\u5b9e\u9645 GMV \u5931\u8d25: {e}")

            achievement_rate_gmv = None
            if target_gmv and achieved_gmv is not None:
                achievement_rate_gmv = round(achieved_gmv / target_gmv * 100, 2)

            data = {
                "target_gmv": target_gmv,
                "achieved_gmv": achieved_gmv,
                "achievement_rate_gmv": achievement_rate_gmv,
                "target_orders": target_orders,
                "target_profit": None,
                "achieved_profit": None,
                "achievement_rate_profit": None,
            }
            return json.loads(success_response(data=data).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "annual_summary_target_completion",
            cache_params,
            _produce_payload,
        )
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except ValueError as e:
        logger.error(f"\u5e74\u5ea6\u603b\u7ed3\u76ee\u6807\u5b8c\u6210\u7387\u53c2\u6570\u6821\u9a8c\u5931\u8d25: {e}")
        return error_response(
            ErrorCode.PARAMETER_INVALID,
            str(e),
            status_code=400,
            recovery_suggestion="\u8bf7\u68c0\u67e5\u8bf7\u6c42\u53c2\u6570",
        )
    except Exception as e:
        logger.error(f"\u5e74\u5ea6\u603b\u7ed3\u76ee\u6807\u5b8c\u6210\u7387\u67e5\u8be2\u5f02\u5e38: {e}", exc_info=True)
        return error_response(
            ErrorCode.DATABASE_QUERY_ERROR,
            f"\u67e5\u8be2\u5931\u8d25: {str(e)}",
            status_code=500,
            detail=str(e),
            recovery_suggestion="\u8bf7\u7a0d\u540e\u91cd\u8bd5",
        )
