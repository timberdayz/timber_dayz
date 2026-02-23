"""
Dashboard API路由
通过Metabase Question查询提供业务概览数据
[add-dashboard-redis-cache-performance] Redis 缓存支持
"""

from fastapi import APIRouter, HTTPException, Query, Depends, Request
from fastapi.responses import JSONResponse
from typing import Optional, Dict, Any, List
from modules.core.logger import get_logger
from backend.services.metabase_question_service import get_metabase_service
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from backend.models.database import get_async_db

logger = get_logger(__name__)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _normalize_cache_params(params: Dict[str, Any]) -> Dict[str, str]:
    """规范化缓存 Key 参数，确保相同语义生成相同 Key（None→空字符串）"""
    return {k: "" if v is None else str(v) for k, v in params.items()}


def success_response(data: Any = None, message: str = "操作成功") -> Dict[str, Any]:
    """统一成功响应格式"""
    return {
        "success": True,
        "data": data,
        "message": message
    }


def error_response(message: str, error_code: str = None) -> Dict[str, Any]:
    """统一错误响应格式"""
    return {
        "success": False,
        "data": None,
        "message": message,
        "error_code": error_code
    }


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
        
        # 尝试从缓存获取
        cache_status = "BYPASS"  # Redis 不可用
        if request and hasattr(request.app.state, "cache_service"):
            cache_service = request.app.state.cache_service
            cached = await cache_service.get("dashboard_kpi", **cache_params)
            if cached is not None:
                return JSONResponse(content=cached, headers={"X-Cache": "HIT"})
            cache_status = "MISS"

        service = get_metabase_service()
        metabase_params = {k: v for k, v in params.items() if v is not None}
        logger.info(f"[KPI查询] 参数: month={month}, platform={platform}")

        result = await service.query_question("business_overview_kpi", metabase_params)
        response = success_response(data=result)

        # 仅成功时写入缓存
        if request and hasattr(request.app.state, "cache_service"):
            await request.app.state.cache_service.set("dashboard_kpi", response, **cache_params)

        return JSONResponse(content=response, headers={"X-Cache": cache_status})
        
    except ValueError as e:
        logger.error(f"业务概览KPI查询失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"业务概览KPI查询异常: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


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

        if request and hasattr(request.app.state, "cache_service"):
            cached = await request.app.state.cache_service.get("dashboard_comparison", **cache_params)
            if cached is not None:
                return cached

        service = get_metabase_service()
        metabase_params = {k: v for k, v in params.items() if v is not None}
        result = await service.query_question("business_overview_comparison", metabase_params)
        response = success_response(data=result)

        if request and hasattr(request.app.state, "cache_service"):
            await request.app.state.cache_service.set("dashboard_comparison", response, **cache_params)
        return response

    except ValueError as e:
        logger.error(f"业务概览对比查询失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"业务概览对比查询异常: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


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

        if request and hasattr(request.app.state, "cache_service"):
            cached = await request.app.state.cache_service.get("dashboard_shop_racing", **cache_params)
            if cached is not None:
                return cached

        service = get_metabase_service()
        metabase_params = {k: v for k, v in params.items() if v is not None}
        result = await service.query_question("business_overview_shop_racing", metabase_params)
        response = success_response(data=result)

        if request and hasattr(request.app.state, "cache_service"):
            await request.app.state.cache_service.set("dashboard_shop_racing", response, **cache_params)
        return response

    except ValueError as e:
        logger.error(f"店铺赛马数据查询失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"店铺赛马数据查询异常: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


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

        if request and hasattr(request.app.state, "cache_service"):
            cached = await request.app.state.cache_service.get("dashboard_traffic_ranking", **cache_params)
            if cached is not None:
                return cached

        service = get_metabase_service()
        metabase_params = {k: v for k, v in params.items() if v is not None}
        result = await service.query_question("business_overview_traffic_ranking", metabase_params)
        response = success_response(data=result)

        if request and hasattr(request.app.state, "cache_service"):
            await request.app.state.cache_service.set("dashboard_traffic_ranking", response, **cache_params)
        return response

    except ValueError as e:
        logger.error(f"流量排名数据查询失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"流量排名数据查询异常: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


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

        if request and hasattr(request.app.state, "cache_service"):
            cached = await request.app.state.cache_service.get("dashboard_inventory_backlog", **cache_params)
            if cached is not None:
                return cached

        service = get_metabase_service()
        metabase_params = {"days": str(days) if days else None, "platforms": platforms, "shops": shops}
        metabase_params = {k: v for k, v in metabase_params.items() if v is not None}
        result = await service.query_question("business_overview_inventory_backlog", metabase_params)
        response = success_response(data=result)

        if request and hasattr(request.app.state, "cache_service"):
            await request.app.state.cache_service.set("dashboard_inventory_backlog", response, **cache_params)
        return response

    except ValueError as e:
        logger.error(f"库存积压数据查询失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"库存积压数据查询异常: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


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

        if request and hasattr(request.app.state, "cache_service"):
            cached = await request.app.state.cache_service.get("dashboard_operational_metrics", **cache_params)
            if cached is not None:
                return cached

        service = get_metabase_service()
        metabase_params = {k: v for k, v in params.items() if v is not None}
        result = await service.query_question("business_overview_operational_metrics", metabase_params)
        response = success_response(data=result)

        if request and hasattr(request.app.state, "cache_service"):
            await request.app.state.cache_service.set("dashboard_operational_metrics", response, **cache_params)
        return response

    except ValueError as e:
        logger.error(f"经营指标数据查询失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"经营指标数据查询异常: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


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

        if request and hasattr(request.app.state, "cache_service"):
            cached = await request.app.state.cache_service.get("dashboard_clearance_ranking", **cache_params)
            if cached is not None:
                return cached

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
        response = success_response(data=result)

        if request and hasattr(request.app.state, "cache_service"):
            await request.app.state.cache_service.set("dashboard_clearance_ranking", response, **cache_params)
        return response

    except ValueError as e:
        logger.error(f"清仓排名数据查询失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"清仓排名数据查询异常: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.get("/annual-summary/kpi")
async def get_annual_summary_kpi(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    granularity: str = Query(..., description="粒度(monthly|yearly)"),
    period: str = Query(..., description="周期: 月度YYYY-MM 或 年度YYYY"),
):
    """
    年度数据总结 - 核心KPI（仅月度粒度数据）
    返回核心 KPI + 成本与产出（总成本 = A 类 operating_costs + B 类订单成本，口径见 docs/COST_DATA_SOURCES_AND_DEFINITIONS.md）
    """
    try:
        if granularity not in ("monthly", "yearly"):
            raise ValueError("granularity 必须为 monthly 或 yearly")
        params = {"granularity": granularity, "period": period}
        cache_params = _normalize_cache_params(params)

        cache_status = "BYPASS"
        if request and hasattr(request.app.state, "cache_service"):
            cache_service = request.app.state.cache_service
            cached = await cache_service.get("annual_summary_kpi", **cache_params)
            if cached is not None:
                return JSONResponse(content=cached, headers={"X-Cache": "HIT"})
            cache_status = "MISS"

        service = get_metabase_service()
        metabase_params = {k: v for k, v in params.items() if v}
        logger.info(f"[年度总结KPI] granularity={granularity}, period={period}")

        result = await service.query_question("annual_summary_kpi", metabase_params)
        if not isinstance(result, dict):
            result = result or {}

        # 成本与产出：后端聚合 A 类 + B 类，与成本文档一致
        from backend.services.annual_cost_aggregate import get_annual_cost_aggregate
        cost_agg = await get_annual_cost_aggregate(db, granularity, period)
        result["total_cost"] = cost_agg["total_cost"]
        result["gmv"] = result.get("gmv") if result.get("gmv") is not None else cost_agg["gmv"]
        result["cost_to_revenue_ratio"] = cost_agg["cost_to_revenue_ratio"]
        result["roi"] = cost_agg["roi"]
        result["gross_margin"] = cost_agg["gross_margin"]
        result["net_margin"] = cost_agg["net_margin"]

        response = success_response(data=result)
        if request and hasattr(request.app.state, "cache_service"):
            await request.app.state.cache_service.set("annual_summary_kpi", response, **cache_params)
        return JSONResponse(content=response, headers={"X-Cache": cache_status})
    except ValueError as e:
        logger.error(f"年度总结KPI查询失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"年度总结KPI查询异常: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.get("/annual-summary/by-shop")
async def get_annual_summary_by_shop(
    db: AsyncSession = Depends(get_async_db),
    granularity: str = Query(..., description="粒度(monthly|yearly)"),
    period: str = Query(..., description="周期: 月度YYYY-MM 或 年度YYYY"),
):
    """
    年度数据总结 - 按店铺下钻（2.3）
    返回各店铺总成本(A+B)、GMV、成本产出比、ROI、毛利率、净利率。口径见 docs/COST_DATA_SOURCES_AND_DEFINITIONS.md；
    店铺键约定：operating_costs.店铺ID = 'platform_code|shop_id' 时与订单侧一致。
    """
    try:
        if granularity not in ("monthly", "yearly"):
            raise ValueError("granularity 必须为 monthly 或 yearly")
        from backend.services.annual_cost_aggregate import get_annual_cost_aggregate_by_shop
        data = await get_annual_cost_aggregate_by_shop(db, granularity, period)
        return JSONResponse(content=success_response(data=data))
    except ValueError as e:
        logger.error(f"年度总结按店铺查询失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"年度总结按店铺查询异常: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/annual-summary/trend")
async def get_annual_summary_trend(
    granularity: str = Query(..., description="粒度(monthly|yearly)"),
    period: str = Query(..., description="周期: 月度YYYY-MM 或 年度YYYY"),
):
    """
    年度数据总结 - 月度/年度趋势
    返回按月的 GMV、总成本、利润时间序列，供折线图使用。数据来自 Metabase annual_summary_trend。
    """
    try:
        if granularity not in ("monthly", "yearly"):
            raise ValueError("granularity 必须为 monthly 或 yearly")
        service = get_metabase_service()
        result = await service.query_question("annual_summary_trend", {"granularity": granularity, "period": period})
        data = result if isinstance(result, list) else (result.get("data") if isinstance(result, dict) else []) or []
        return JSONResponse(content=success_response(data=data))
    except ValueError as e:
        if "Question ID 未找到" in str(e) or "METABASE" in str(e):
            logger.warning(f"年度总结趋势 Metabase 未配置: {e}")
            return JSONResponse(content=success_response(data=[]))
        logger.error(f"年度总结趋势查询失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"年度总结趋势查询异常: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/annual-summary/platform-share")
async def get_annual_summary_platform_share(
    granularity: str = Query(..., description="粒度(monthly|yearly)"),
    period: str = Query(..., description="周期: 月度YYYY-MM 或 年度YYYY"),
):
    """
    年度数据总结 - 平台 GMV 占比
    返回各平台（Shopee、TikTok 等）GMV 及占比，供饼图使用。数据来自 Metabase annual_summary_platform_share。
    """
    try:
        if granularity not in ("monthly", "yearly"):
            raise ValueError("granularity 必须为 monthly 或 yearly")
        service = get_metabase_service()
        result = await service.query_question("annual_summary_platform_share", {"granularity": granularity, "period": period})
        data = result if isinstance(result, list) else (result.get("data") if isinstance(result, dict) else []) or []
        return JSONResponse(content=success_response(data=data))
    except ValueError as e:
        if "Question ID 未找到" in str(e) or "METABASE" in str(e):
            logger.warning(f"年度总结平台占比 Metabase 未配置: {e}")
            return JSONResponse(content=success_response(data=[]))
        logger.error(f"年度总结平台占比查询失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"年度总结平台占比查询异常: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/annual-summary/target-completion")
async def get_annual_summary_target_completion(
    granularity: str = Query(..., description="粒度(monthly|yearly)"),
    period: str = Query(..., description="周期: 月度YYYY-MM 或 年度YYYY"),
    db: AsyncSession = Depends(get_async_db),
):
    """
    年度数据总结 - 目标完成率
    对接 a_class.sales_targets_a：按 period 汇总目标销售额，与 KPI 实际 GMV 对比得到完成率。
    利润目标暂无独立配置时，利润完成率可为 null。
    """
    try:
        if granularity not in ("monthly", "yearly"):
            raise ValueError("granularity 必须为 monthly 或 yearly")

        # 1) 汇总目标：月度用单月，年度用当年所有月
        if len(period) == 4:  # YYYY
            year_month_filter = f"year_month LIKE :period_prefix"
            params = {"period_prefix": f"{period}-%"}
        else:  # YYYY-MM
            year_month_filter = "year_month = :period"
            params = {"period": period}

        try:
            result = await db.execute(text(f"""
                SELECT COALESCE(SUM(target_sales_amount), 0) AS target_gmv,
                       COALESCE(SUM(target_quantity), 0) AS target_orders
                FROM a_class.sales_targets_a
                WHERE {year_month_filter}
            """), params)
        except Exception:
            ym_filter_cn = '"年月" LIKE :period_prefix' if len(period) == 4 else '"年月" = :period'
            result = await db.execute(text(f"""
                SELECT COALESCE(SUM("目标销售额"), 0) AS target_gmv,
                       COALESCE(SUM("目标订单数"), 0) AS target_orders
                FROM a_class.sales_targets_a
                WHERE {ym_filter_cn}
            """), params)
        row = result.fetchone()
        target_gmv = float(row[0]) if row and row[0] is not None else 0.0
        target_orders = int(row[1]) if row and row[1] is not None else 0

        # 2) 实际 GMV：调用 KPI 接口同周期数据
        achieved_gmv = None
        try:
            service = get_metabase_service()
            kpi_result = await service.query_question("annual_summary_kpi", {"granularity": granularity, "period": period})
            if isinstance(kpi_result, dict) and kpi_result.get("gmv") is not None:
                achieved_gmv = float(kpi_result["gmv"])
        except Exception as e:
            logger.warning(f"目标完成率获取实际GMV失败: {e}")

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
        return JSONResponse(content=success_response(data=data))
    except ValueError as e:
        logger.error(f"年度总结目标完成率查询失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"年度总结目标完成率查询异常: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

