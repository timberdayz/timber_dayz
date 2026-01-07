"""
Dashboard API路由
通过Metabase Question查询提供业务概览数据
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional, Dict, Any
from modules.core.logger import get_logger
from backend.services.metabase_question_service import get_metabase_service

logger = get_logger(__name__)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


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
    start_date: Optional[str] = Query(None, description="开始日期"),
    end_date: Optional[str] = Query(None, description="结束日期"),
    platforms: Optional[str] = Query(None, description="平台代码（逗号分隔）"),
    shops: Optional[str] = Query(None, description="店铺ID（逗号分隔）")
):
    """
    获取业务概览KPI数据
    
    通过Metabase Question查询关键业务指标
    """
    try:
        service = get_metabase_service()
        
        params = {
            "start_date": start_date,
            "end_date": end_date,
            "platforms": platforms,
            "shops": shops
        }
        
        # 移除None值
        params = {k: v for k, v in params.items() if v is not None}
        
        result = await service.query_question("business_overview_kpi", params)
        return success_response(data=result)
        
    except ValueError as e:
        logger.error(f"业务概览KPI查询失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"业务概览KPI查询异常: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.get("/business-overview/comparison")
async def get_business_overview_comparison(
    granularity: str = Query(..., description="时间粒度（daily/weekly/monthly）"),
    date: str = Query(..., description="日期"),
    platforms: Optional[str] = Query(None, description="平台代码（逗号分隔）"),
    shops: Optional[str] = Query(None, description="店铺ID（逗号分隔）")
):
    """
    获取业务概览数据对比（日/周/月度）
    """
    try:
        service = get_metabase_service()
        
        params = {
            "granularity": granularity,
            "date": date,
            "platforms": platforms,
            "shops": shops
        }
        
        params = {k: v for k, v in params.items() if v is not None}
        
        result = await service.query_question("business_overview_comparison", params)
        return success_response(data=result)
        
    except ValueError as e:
        logger.error(f"业务概览对比查询失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"业务概览对比查询异常: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.get("/business-overview/shop-racing")
async def get_business_overview_shop_racing(
    granularity: str = Query(..., description="时间粒度"),
    date: str = Query(..., description="日期"),
    group_by: str = Query("shop", description="分组维度"),
    platforms: Optional[str] = Query(None, description="平台代码（逗号分隔）")
):
    """
    获取店铺赛马数据
    """
    try:
        service = get_metabase_service()
        
        params = {
            "granularity": granularity,
            "date": date,
            "group_by": group_by,
            "platforms": platforms
        }
        
        params = {k: v for k, v in params.items() if v is not None}
        
        result = await service.query_question("business_overview_shop_racing", params)
        return success_response(data=result)
        
    except ValueError as e:
        logger.error(f"店铺赛马数据查询失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"店铺赛马数据查询异常: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.get("/business-overview/traffic-ranking")
async def get_business_overview_traffic_ranking(
    granularity: Optional[str] = Query(None, description="时间粒度"),
    dimension: Optional[str] = Query(None, description="维度"),
    date_value: Optional[str] = Query(None, description="日期值"),
    platforms: Optional[str] = Query(None, description="平台代码（逗号分隔）"),
    shops: Optional[str] = Query(None, description="店铺ID（逗号分隔）")
):
    """
    获取流量排名数据
    """
    try:
        service = get_metabase_service()
        
        params = {
            "granularity": granularity,
            "dimension": dimension,
            "date": date_value,  # 前端传date_value，转换为date
            "platforms": platforms,
            "shops": shops
        }
        
        params = {k: v for k, v in params.items() if v is not None}
        
        result = await service.query_question("business_overview_traffic_ranking", params)
        return success_response(data=result)
        
    except ValueError as e:
        logger.error(f"流量排名数据查询失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"流量排名数据查询异常: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.get("/business-overview/inventory-backlog")
async def get_business_overview_inventory_backlog(
    days: Optional[int] = Query(None, description="天数"),
    platforms: Optional[str] = Query(None, description="平台代码（逗号分隔）"),
    shops: Optional[str] = Query(None, description="店铺ID（逗号分隔）")
):
    """
    获取库存积压数据
    """
    try:
        service = get_metabase_service()
        
        params = {
            "days": str(days) if days else None,
            "platforms": platforms,
            "shops": shops
        }
        
        params = {k: v for k, v in params.items() if v is not None}
        
        result = await service.query_question("business_overview_inventory_backlog", params)
        return success_response(data=result)
        
    except ValueError as e:
        logger.error(f"库存积压数据查询失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"库存积压数据查询异常: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.get("/business-overview/operational-metrics")
async def get_business_overview_operational_metrics(
    date: Optional[str] = Query(None, description="日期"),
    platforms: Optional[str] = Query(None, description="平台代码（逗号分隔）"),
    shops: Optional[str] = Query(None, description="店铺ID（逗号分隔）")
):
    """
    获取经营指标数据（门店经营表格）
    """
    try:
        service = get_metabase_service()
        
        params = {
            "date": date,
            "platforms": platforms,
            "shops": shops
        }
        
        params = {k: v for k, v in params.items() if v is not None}
        
        result = await service.query_question("business_overview_operational_metrics", params)
        return success_response(data=result)
        
    except ValueError as e:
        logger.error(f"经营指标数据查询失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"经营指标数据查询异常: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.get("/clearance-ranking")
async def get_clearance_ranking(
    start_date: Optional[str] = Query(None, description="开始日期"),
    end_date: Optional[str] = Query(None, description="结束日期"),
    platforms: Optional[str] = Query(None, description="平台代码（逗号分隔）"),
    shops: Optional[str] = Query(None, description="店铺ID（逗号分隔）"),
    limit: Optional[int] = Query(10, description="返回数量")
):
    """
    获取清仓排名数据
    """
    try:
        service = get_metabase_service()
        
        params = {
            "start_date": start_date,
            "end_date": end_date,
            "platforms": platforms,
            "shops": shops,
            "limit": str(limit) if limit else None
        }
        
        params = {k: v for k, v in params.items() if v is not None}
        
        result = await service.query_question("clearance_ranking", params)
        return success_response(data=result)
        
    except ValueError as e:
        logger.error(f"清仓排名数据查询失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"清仓排名数据查询异常: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")

