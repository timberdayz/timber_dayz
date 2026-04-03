#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
绩效管理API(v4.11.0新增)

功能:
1. 绩效权重配置CRUD
2. 绩效评分查询(自动计算)
3. 绩效排名查询

路由:
- GET /api/performance/config - 查询绩效配置列表
- GET /api/performance/config/{config_id} - 查询绩效配置详情
- POST /api/performance/config - 创建绩效配置
- PUT /api/performance/config/{config_id} - 更新绩效配置
- DELETE /api/performance/config/{config_id} - 删除绩效配置
- GET /api/performance/scores - 查询绩效评分列表
- GET /api/performance/scores/{shop_id} - 查询店铺绩效详情
- POST /api/performance/scores/calculate - 计算绩效评分
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, text
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import date, datetime, timedelta, timezone

from backend.models.database import get_db, get_async_db
from backend.utils.api_response import success_response, error_response, pagination_response
from backend.utils.error_codes import ErrorCode, get_error_type
from modules.core.db import (
    PerformanceConfig,
    PerformanceScore,
    SalesTarget,
    TargetBreakdown,
    Employee,
    EmployeePerformance,
    # [DELETED] v4.19.0: FactOrder 已删除
    FactProductMetric,
    DimShop,
    ShopAccount,
)
from modules.core.logger import get_logger
from backend.schemas.performance import (
    PerformanceConfigCreateRequest,
    PerformanceConfigUpdateRequest,
    PerformanceConfigResponse,
    PerformanceScoreResponse,
)
from backend.services.hr_income_calculation_service import HRIncomeCalculationService
from backend.services.payroll_generation_service import PayrollGenerationService
from backend.services.postgresql_shop_metrics_service import (
    load_shop_monthly_metrics,
    load_shop_monthly_target_achievement,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/performance", tags=["绩效管理"])


# ==================== Request/Response Models ====================

# ==================== API Endpoints ====================

@router.get("/config", response_model=Dict[str, Any])
async def list_performance_configs(
    is_active: Optional[bool] = Query(None, description="是否启用筛选"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    查询绩效配置列表
    """
    try:
        query = select(PerformanceConfig)
        
        if is_active is not None:
            query = query.where(PerformanceConfig.is_active == is_active)
        
        # 总数查询
        total_query = select(func.count()).select_from(query.subquery())
        total = (await db.execute(total_query)).scalar() or 0
        
        # 分页查询
        query = query.order_by(PerformanceConfig.effective_from.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        
        configs = (await db.execute(query)).scalars().all()
        
        return pagination_response(
            data=[PerformanceConfigResponse.model_validate(c).model_dump() for c in configs],
            page=page,
            page_size=page_size,
            total=total
        )
    except Exception as e:
        logger.error(f"查询绩效配置列表失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="查询失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )


@router.get("/config/{config_id}", response_model=Dict[str, Any])
async def get_performance_config(
    config_id: int,
    db: AsyncSession = Depends(get_async_db)
):
    """
    查询绩效配置详情
    """
    try:
        result = await db.execute(
            select(PerformanceConfig).where(PerformanceConfig.id == config_id)
        )
        config = result.scalar_one_or_none()
        
        if not config:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="配置不存在",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="请检查配置ID是否正确,或确认该配置已创建",
                status_code=404
            )
        
        return {
            "success": True,
            "data": PerformanceConfigResponse.model_validate(config).model_dump()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询绩效配置详情失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="查询绩效配置详情失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和查询参数,或联系系统管理员",
            status_code=500
        )


@router.post("/config", response_model=Dict[str, Any])
async def create_performance_config(
    request: PerformanceConfigCreateRequest,
    db: AsyncSession = Depends(get_async_db),
    created_by: str = "admin"  # TODO: 从认证中获取当前用户
):
    """
    创建绩效配置
    
    验证权重总和必须为100
    """
    try:
        # 验证权重总和
        total_weight = request.sales_weight + request.profit_weight + request.key_product_weight + request.operation_weight
        if total_weight != 100:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message=f"权重总和必须为100,当前为{total_weight}",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="请调整权重值,确保总和为100",
                status_code=400
            )
        
        # 创建配置
        config = PerformanceConfig(
            config_name=request.config_name,
            sales_weight=request.sales_weight,
            profit_weight=request.profit_weight,
            key_product_weight=request.key_product_weight,
            operation_weight=request.operation_weight,
            sales_max_score=request.sales_max_score,
            profit_max_score=request.profit_max_score,
            key_product_max_score=request.key_product_max_score,
            operation_max_score=request.operation_max_score,
            effective_from=request.effective_from,
            effective_to=request.effective_to,
            created_by=created_by,
            is_active=True
        )
        
        db.add(config)
        await db.commit()
        await db.refresh(config)
        
        # 触发A_CLASS_UPDATED事件(数据流转流程自动化)
        try:
            from backend.utils.events import AClassUpdatedEvent
            from backend.services.event_listeners import event_listener
            
            # 绩效配置影响所有店铺,不需要指定具体店铺
            event = AClassUpdatedEvent(
                data_type="performance_config",
                record_id=config.id,
                action="create",
                affected_shops=None,  # 影响所有店铺
                affected_platforms=None  # 影响所有平台
            )
            event_listener.handle_a_class_updated(event)
            logger.info(f"[PerformanceManagement] 已触发A_CLASS_UPDATED事件: config_id={config.id}, action=create")
        except Exception as event_err:
            # 事件触发失败不影响主流程
            logger.warning(f"[PerformanceManagement] 触发A_CLASS_UPDATED事件失败: {event_err}")
        
        return success_response(
            data=PerformanceConfigResponse.model_validate(config).model_dump(),
            message="绩效配置创建成功"
        )
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"创建绩效配置失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="创建失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )


@router.put("/config/{config_id}", response_model=Dict[str, Any])
async def update_performance_config(
    config_id: int,
    request: PerformanceConfigUpdateRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """
    更新绩效配置
    
    如果更新权重,需要验证总和为100
    """
    try:
        result = await db.execute(
            select(PerformanceConfig).where(PerformanceConfig.id == config_id)
        )
        config = result.scalar_one_or_none()
        
        if not config:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="配置不存在",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="请检查配置ID是否正确,或确认该配置已创建",
                status_code=404
            )
        
        # 更新字段
        update_data = request.dict(exclude_unset=True)
        
        # 如果更新权重,验证总和
        if any(k in update_data for k in ["sales_weight", "profit_weight", "key_product_weight", "operation_weight"]):
            sales_weight = update_data.get("sales_weight", config.sales_weight)
            profit_weight = update_data.get("profit_weight", config.profit_weight)
            key_product_weight = update_data.get("key_product_weight", config.key_product_weight)
            operation_weight = update_data.get("operation_weight", config.operation_weight)
            
            total_weight = sales_weight + profit_weight + key_product_weight + operation_weight
            if total_weight != 100:
                return error_response(
                    code=ErrorCode.DATA_VALIDATION_FAILED,
                    message=f"权重总和必须为100,当前为{total_weight}",
                    error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                    recovery_suggestion="请调整权重值,确保总和为100",
                    status_code=400
                )
        
        for key, value in update_data.items():
            setattr(config, key, value)
        
        config.updated_at = datetime.now(timezone.utc)
        
        await db.commit()
        await db.refresh(config)
        
        # 触发A_CLASS_UPDATED事件(数据流转流程自动化)
        try:
            from backend.utils.events import AClassUpdatedEvent
            from backend.services.event_listeners import event_listener
            
            # 绩效配置影响所有店铺,不需要指定具体店铺
            event = AClassUpdatedEvent(
                data_type="performance_config",
                record_id=config_id,
                action="update",
                affected_shops=None,  # 影响所有店铺
                affected_platforms=None  # 影响所有平台
            )
            event_listener.handle_a_class_updated(event)
            logger.info(f"[PerformanceManagement] 已触发A_CLASS_UPDATED事件: config_id={config_id}, action=update")
        except Exception as event_err:
            # 事件触发失败不影响主流程
            logger.warning(f"[PerformanceManagement] 触发A_CLASS_UPDATED事件失败: {event_err}")
        
        return success_response(
            data=PerformanceConfigResponse.model_validate(config).model_dump(),
            message="绩效配置更新成功"
        )
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"更新绩效配置失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="更新失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )


@router.delete("/config/{config_id}", response_model=Dict[str, Any])
async def delete_performance_config(
    config_id: int,
    db: AsyncSession = Depends(get_async_db)
):
    """
    删除绩效配置
    """
    try:
        result = await db.execute(
            select(PerformanceConfig).where(PerformanceConfig.id == config_id)
        )
        config = result.scalar_one_or_none()
        
        if not config:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="配置不存在",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="请检查配置ID是否正确,或确认该配置已创建",
                status_code=404
            )
        
        await db.delete(config)
        await db.commit()
        
        return {
            "success": True,
            "message": "绩效配置删除成功"
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"删除绩效配置失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="删除绩效配置失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限,或联系系统管理员",
            status_code=500
        )


def _score_details_field(details: Optional[dict], *keys) -> Optional[Any]:
    """从 score_details JSON 取嵌套字段，如 sales.target, profit.achieved"""
    if not details or not isinstance(details, dict):
        return None
    for key in keys:
        details = details.get(key) if isinstance(details, dict) else None
        if details is None:
            return None
    return details


def _normalize_cache_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """规范化缓存 key 参数（None→空字符串），与 dashboard_api 一致"""
    return {k: ("" if v is None else str(v)) for k, v in params.items()}


def _normalize_rate_percent(raw_rate: Optional[Any]) -> Optional[float]:
    if raw_rate is None:
        return None
    rate = float(raw_rate)
    if 0 <= rate <= 1:
        rate *= 100.0
    return round(rate, 4)


def _rate_percent_to_fraction(raw_rate: Optional[Any]) -> float:
    if raw_rate is None:
        return 0.0
    rate = float(raw_rate)
    if rate > 1:
        rate /= 100.0
    return max(0.0, rate)


def _metric_status(details: Dict[str, Any], metric: str) -> Optional[str]:
    return _score_details_field(details, metric, "status")


def _metric_is_calculated(details: Dict[str, Any], metric: str) -> bool:
    return _metric_status(details, metric) == "calculated"


def _summary_is_complete(details: Dict[str, Any]) -> bool:
    return _score_details_field(details, "summary", "status") == "complete"


def _public_metric_score(score_value: Optional[float], details: Dict[str, Any], metric: str) -> Optional[float]:
    return score_value if _metric_is_calculated(details, metric) else None


def _public_total_score(total_score: Optional[float], details: Dict[str, Any]) -> Optional[float]:
    return total_score if _summary_is_complete(details) else None


def _public_rank(rank: Optional[int], details: Dict[str, Any]) -> Optional[int]:
    return rank if _summary_is_complete(details) else None


def _public_coefficient(coefficient: Optional[float], details: Dict[str, Any]) -> Optional[float]:
    return coefficient if _summary_is_complete(details) else None


def _build_metric_detail(details: Dict[str, Any], metric: str, score_value: Optional[float]) -> Dict[str, Any]:
    metric_details = _score_details_field(details, metric) or {}
    return {
        "status": metric_details.get("status", "missing"),
        "source": metric_details.get("source"),
        "message": metric_details.get("message"),
        "score": _public_metric_score(score_value, details, metric),
        "target": metric_details.get("target"),
        "achieved": metric_details.get("achieved"),
        "rate": metric_details.get("rate"),
        "calculation": metric_details.get("calculation"),
    }


async def _load_shop_monthly_product_metrics(
    db: AsyncSession,
    year_month: str,
) -> Dict[str, Dict[str, float]]:
    period_start = datetime.strptime(f"{year_month}-01", "%Y-%m-%d").date()
    if period_start.month == 12:
        period_end = period_start.replace(year=period_start.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        period_end = period_start.replace(month=period_start.month + 1, day=1) - timedelta(days=1)

    result = await db.execute(
        text(
            """
            select
              lower(platform_code) as platform_code,
              shop_id,
              platform_sku,
              product_id,
              coalesce(sum(sales_amount), 0) as sales_amount,
              coalesce(sum(order_count), 0) as order_count
            from mart.product_day_kpi
            where period_date >= :period_start
              and period_date <= :period_end
            group by lower(platform_code), shop_id, platform_sku, product_id
            """
        ),
        {"period_start": period_start, "period_end": period_end},
    )

    metrics: Dict[str, Dict[str, float]] = {}
    for row in result.mappings().all():
        platform_code = row.get("platform_code") or ""
        shop_id = row.get("shop_id") or ""
        sales_amount = float(row.get("sales_amount") or 0.0)
        order_count = float(row.get("order_count") or 0.0)
        platform_sku = row.get("platform_sku")
        product_id = row.get("product_id")
        if platform_sku:
            metrics[f"{platform_code}|{shop_id}|sku:{platform_sku}"] = {
                "sales_amount": sales_amount,
                "order_count": order_count,
            }
        if product_id is not None:
            metrics[f"{platform_code}|{shop_id}|pid:{product_id}"] = {
                "sales_amount": sales_amount,
                "order_count": order_count,
            }
    return metrics


def _calculate_operation_metric_score(target: Any) -> tuple[float, Dict[str, Any]]:
    direction = getattr(target, "metric_direction", None)
    target_value = getattr(target, "target_value", None)
    achieved_value = getattr(target, "achieved_value", None)
    max_score = float(getattr(target, "max_score", 0) or 0)
    penalty_enabled = bool(getattr(target, "penalty_enabled", False))
    penalty_threshold = getattr(target, "penalty_threshold", None)
    penalty_per_unit = float(getattr(target, "penalty_per_unit", 0) or 0)
    penalty_max = float(getattr(target, "penalty_max", 0) or 0)
    manual_score_enabled = bool(getattr(target, "manual_score_enabled", False))
    manual_score_value = getattr(target, "manual_score_value", None)

    if direction == "manual_score" or manual_score_enabled:
        score = max(0.0, min(float(manual_score_value or 0), max_score))
        return score, {
            "status": "calculated",
            "source": "target_management_manual_score",
            "target": target_value,
            "achieved": achieved_value,
            "rate": None,
            "calculation": f"manual_score={score:.2f}",
            "message": None,
        }

    if target_value in (None, 0) or achieved_value is None:
        return 0.0, {
            "status": "pending_design",
            "source": "target_management",
            "target": target_value,
            "achieved": achieved_value,
            "rate": None,
            "calculation": None,
            "message": "运营目标缺少目标值或实际值，当前不参与绩效得分。",
        }

    target_float = float(target_value)
    achieved_float = float(achieved_value)

    if direction == "higher_better":
        ratio = min(max(achieved_float / target_float, 0.0), 1.0)
        score = max_score * ratio
        calc_text = f"min({achieved_float:.2f}/{target_float:.2f}, 1) * {max_score:.2f}"
        return round(score, 4), {
            "status": "calculated",
            "source": "target_management",
            "target": target_float,
            "achieved": achieved_float,
            "rate": round(ratio * 100, 4),
            "calculation": calc_text,
            "message": None,
        }

    if direction == "lower_better":
        ratio = 1.0 if achieved_float <= target_float else min(max(target_float / achieved_float, 0.0), 1.0)
        score = max_score * ratio
        penalty = 0.0
        if penalty_enabled and penalty_threshold is not None and achieved_float > float(penalty_threshold):
            penalty = min((achieved_float - float(penalty_threshold)) * penalty_per_unit, penalty_max)
        score = max(score - penalty, -max_score)
        calc_text = f"base=min({target_float:.2f}/{max(achieved_float, 1e-9):.2f}, 1) * {max_score:.2f}; penalty={penalty:.2f}"
        return round(score, 4), {
            "status": "calculated",
            "source": "target_management",
            "target": target_float,
            "achieved": achieved_float,
            "rate": round(ratio * 100, 4),
            "calculation": calc_text,
            "message": None,
        }

    return 0.0, {
        "status": "pending_design",
        "source": "target_management",
        "target": target_value,
        "achieved": achieved_value,
        "rate": None,
        "calculation": None,
        "message": "运营目标方向未配置，当前不参与绩效得分。",
    }


async def invalidate_performance_related_caches(cache_service) -> None:
    await cache_service.invalidate("performance_scores")
    await cache_service.invalidate("performance_scores_shop")
    await cache_service.invalidate("hr_shop_profit_statistics")
    await cache_service.invalidate("hr_annual_profit_statistics")


@router.get("/scores", response_model=Dict[str, Any])
async def list_performance_scores(
    request: Request,
    period: Optional[str] = Query(None, description="考核周期,如'2025-01'"),
    platform_code: Optional[str] = Query(None, description="平台筛选"),
    shop_id: Optional[str] = Query(None, description="店铺筛选"),
    group_by: Optional[str] = Query("shop", description="维度: shop 按店铺 | person 按人员"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    查询绩效评分列表
    
    group_by=shop: 按店铺展示，数据来自 performance_scores
    group_by=person: 按人员展示，数据来自 employee_performance
    """
    try:
        params = {
            "period": period,
            "platform_code": platform_code,
            "shop_id": shop_id,
            "group_by": group_by or "shop",
            "page": page,
            "page_size": page_size,
        }
        cache_params = _normalize_cache_params(params)
        cache_status = "BYPASS"
        if request and hasattr(request.app.state, "cache_service"):
            cache_service = request.app.state.cache_service
            cached = await cache_service.get("performance_scores", **cache_params)
            if cached is not None:
                return JSONResponse(content=cached, headers={"X-Cache": "HIT"})
            cache_status = "MISS"

        if group_by == "person":
            # 按人员：从 employee_performance 取数据（兼容英/中文列）
            use_cn_fallback = False
            ep_list = []
            all_ep = []
            total = 0
            try:
                query = select(EmployeePerformance)
                if period:
                    query = query.where(EmployeePerformance.year_month == period)
                total_query = select(func.count()).select_from(query.subquery())
                total = (await db.execute(total_query)).scalar() or 0
                query = query.order_by(EmployeePerformance.performance_score.desc())
                query = query.offset((page - 1) * page_size).limit(page_size)
                rows = (await db.execute(query)).scalars().all()
                ep_list = [r[0] if hasattr(r, "__getitem__") and len(r) == 1 else r for r in rows]

                all_query = select(EmployeePerformance)
                if period:
                    all_query = all_query.where(EmployeePerformance.year_month == period)
                all_rows = (await db.execute(all_query)).scalars().all()
                all_ep = [r[0] if hasattr(r, "__getitem__") and len(r) == 1 else r for r in all_rows]
            except Exception:
                await db.rollback()
                use_cn_fallback = True
                logger.warning("employee_performance ORM query failed, fallback to CN column SQL")

                if period:
                    total_sql = text(
                        """
                        select count(1)
                        from c_class.employee_performance
                        where "年月" = :period
                        """
                    )
                    total = int((await db.execute(total_sql, {"period": period})).scalar() or 0)
                    page_sql = text(
                        """
                        select
                          "员工编号" as employee_code,
                          "实际销售额" as actual_sales,
                          "达成率" as achievement_rate,
                          "绩效得分" as performance_score
                        from c_class.employee_performance
                        where "年月" = :period
                        order by "绩效得分" desc
                        limit :limit offset :offset
                        """
                    )
                    page_rows = (
                        await db.execute(
                            page_sql,
                            {"period": period, "limit": page_size, "offset": (page - 1) * page_size},
                        )
                    ).mappings().all()
                    all_sql = text(
                        """
                        select
                          "员工编号" as employee_code,
                          "绩效得分" as performance_score
                        from c_class.employee_performance
                        where "年月" = :period
                        """
                    )
                    all_rows = (await db.execute(all_sql, {"period": period})).mappings().all()
                else:
                    total_sql = text(
                        """
                        select count(1)
                        from c_class.employee_performance
                        """
                    )
                    total = int((await db.execute(total_sql)).scalar() or 0)
                    page_sql = text(
                        """
                        select
                          "员工编号" as employee_code,
                          "实际销售额" as actual_sales,
                          "达成率" as achievement_rate,
                          "绩效得分" as performance_score
                        from c_class.employee_performance
                        order by "绩效得分" desc
                        limit :limit offset :offset
                        """
                    )
                    page_rows = (
                        await db.execute(
                            page_sql,
                            {"limit": page_size, "offset": (page - 1) * page_size},
                        )
                    ).mappings().all()
                    all_sql = text(
                        """
                        select
                          "员工编号" as employee_code,
                          "绩效得分" as performance_score
                        from c_class.employee_performance
                        """
                    )
                    all_rows = (await db.execute(all_sql)).mappings().all()
                ep_list = [dict(r) for r in page_rows]
                all_ep = [dict(r) for r in all_rows]

            # 取员工姓名
            codes = []
            for e in ep_list:
                if use_cn_fallback:
                    ec = e.get("employee_code")
                else:
                    ec = getattr(e, "employee_code", None)
                if ec:
                    codes.append(ec)
            codes = list(set(codes))

            name_map = {}
            if codes:
                emp_query = select(Employee.employee_code, Employee.name).where(Employee.employee_code.in_(codes))
                emp_rows = (await db.execute(emp_query)).all()
                for r in emp_rows:
                    ec = r[0] if hasattr(r, "__getitem__") else getattr(r, "employee_code", "")
                    nm = r[1] if hasattr(r, "__getitem__") and len(r) > 1 else getattr(r, "name", "")
                    name_map[ec] = nm or ec

            # 计算排名
            sorted_ep = sorted(
                all_ep,
                key=lambda x: float(
                    (x.get("performance_score") if use_cn_fallback else getattr(x, "performance_score", 0))
                    or 0
                ),
                reverse=True,
            )
            rank_by_code = {}
            for i, e in enumerate(sorted_ep, 1):
                ec = e.get("employee_code") if use_cn_fallback else getattr(e, "employee_code", None)
                if ec:
                    rank_by_code[ec] = i

            score_responses = []
            for ep in ep_list:
                if use_cn_fallback:
                    ec = ep.get("employee_code", "")
                    scr = float(ep.get("performance_score", 0) or 0)
                    ach = float(ep.get("achievement_rate", 0) or 0) * 100
                    sales_achieved_raw = ep.get("actual_sales")
                    sales_achieved = (
                        float(sales_achieved_raw) if sales_achieved_raw is not None else None
                    )
                else:
                    ec = getattr(ep, "employee_code", "")
                    scr = float(getattr(ep, "performance_score", 0) or 0)
                    ach = float(getattr(ep, "achievement_rate", 0) or 0) * 100
                    sales_achieved = getattr(ep, "actual_sales", None)
                score_responses.append({
                    "employee_code": ec,
                    "employee_name": name_map.get(ec, ec),
                    "sales_target": None,
                    "sales_achieved": sales_achieved,
                    "sales_rate": ach if ach else None,
                    "profit_target": None,
                    "profit_achieved": None,
                    "profit_rate": None,
                    "key_product_target": None,
                    "key_product_achieved": None,
                    "key_product_rate": None,
                    "operation_score": None,
                    "total_score": scr,
                    "rank": rank_by_code.get(ec),
                    "performance_coefficient": 1.0 + (scr - 80) / 100 if scr else 1.0,
                })
            result = {
                "success": True,
                "data": score_responses,
                "total": total,
                "page": page,
                "page_size": page_size,
                "has_more": (page * page_size) < total,
            }
            if request and hasattr(request.app.state, "cache_service"):
                await request.app.state.cache_service.set("performance_scores", result, **cache_params)
            return JSONResponse(content=result, headers={"X-Cache": cache_status})

        # 按店铺：以 shop_accounts（正在经营店铺）为主，合并 performance_scores
        shop_query = (
            select(ShopAccount)
            .where(ShopAccount.enabled == True)
            .order_by(ShopAccount.platform, ShopAccount.store_name)
        )
        shop_rows = (await db.execute(shop_query)).scalars().all()
        all_shops = [
            {
                "platform_code": (r.platform or "").lower() if r.platform else "",
                "shop_id": getattr(r, "platform_shop_id", None) or getattr(r, "shop_account_id", None) or getattr(r, "shop_id", None) or getattr(r, "account_id", None) or str(r.id),
                "shop_name": getattr(r, "store_name", None) or getattr(r, "shop_account_id", None) or getattr(r, "account_id", None) or "",
            }
            for r in shop_rows
        ]
        if platform_code:
            pc_lower = (platform_code or "").lower()
            all_shops = [s for s in all_shops if (s["platform_code"] or "").lower() == pc_lower]
        if shop_id:
            all_shops = [s for s in all_shops if s["shop_id"] == shop_id]
        total = len(all_shops)
        start = (page - 1) * page_size
        paged_shops = all_shops[start : start + page_size]
        perf_map = {}
        if period and paged_shops:
            platform_codes = list({s["platform_code"] for s in paged_shops})
            shop_ids = list({s["shop_id"] for s in paged_shops})
            perf_query = select(PerformanceScore).where(
                PerformanceScore.period == period,
                PerformanceScore.platform_code.in_(platform_codes),
                PerformanceScore.shop_id.in_(shop_ids),
            )
            perf_rows = (await db.execute(perf_query)).all()
            for pr in perf_rows:
                s = pr[0] if hasattr(pr, "__getitem__") and len(pr) == 1 else pr
                key = f"{(getattr(s, 'platform_code') or '').lower()}|{getattr(s, 'shop_id') or ''}"
                details = getattr(s, "score_details", None) or {}
                perf_map[key] = {
                    "sales_target": _score_details_field(details, "sales", "target"),
                    "sales_achieved": _score_details_field(details, "sales", "achieved"),
                    "sales_rate": _score_details_field(details, "sales", "rate"),
                    "sales_score": _public_metric_score(getattr(s, "sales_score", None), details, "sales"),
                    "profit_target": _score_details_field(details, "profit", "target"),
                    "profit_achieved": _score_details_field(details, "profit", "achieved"),
                    "profit_rate": _score_details_field(details, "profit", "rate"),
                    "profit_score": _public_metric_score(getattr(s, "profit_score", None), details, "profit"),
                    "key_product_target": _score_details_field(details, "key_product", "target"),
                    "key_product_achieved": _score_details_field(details, "key_product", "achieved"),
                    "key_product_rate": _score_details_field(details, "key_product", "rate"),
                    "key_product_score": _public_metric_score(getattr(s, "key_product_score", None), details, "key_product"),
                    "operation_score": _public_metric_score(getattr(s, "operation_score", None), details, "operation"),
                    "total_score": _public_total_score(getattr(s, "total_score", None), details),
                    "rank": _public_rank(getattr(s, "rank", None), details),
                    "performance_coefficient": _public_coefficient(getattr(s, "performance_coefficient", None), details),
                    "score_details": details,
                }
        score_responses = []
        for s in paged_shops:
            key = f"{s['platform_code']}|{s['shop_id']}"
            p = perf_map.get(key)
            row = {
                "platform_code": s["platform_code"],
                "shop_id": s["shop_id"],
                "shop_name": s["shop_name"],
                "sales_target": p["sales_target"] if p else None,
                "sales_achieved": p["sales_achieved"] if p else None,
                "sales_rate": p["sales_rate"] if p else None,
                "sales_score": p["sales_score"] if p else None,
                "profit_target": p["profit_target"] if p else None,
                "profit_achieved": p["profit_achieved"] if p else None,
                "profit_rate": p["profit_rate"] if p else None,
                "profit_score": p["profit_score"] if p else None,
                "key_product_target": p["key_product_target"] if p else None,
                "key_product_achieved": p["key_product_achieved"] if p else None,
                "key_product_rate": p["key_product_rate"] if p else None,
                "key_product_score": p["key_product_score"] if p else None,
                "operation_score": p["operation_score"] if p else None,
                "total_score": p["total_score"] if p else None,
                "rank": p["rank"] if p else None,
                "performance_coefficient": p["performance_coefficient"] if p else None,
                "score_details": p["score_details"] if p else None,
            }
            score_responses.append(row)

        result = {
            "success": True,
            "data": score_responses,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_more": (page * page_size) < total
        }
        if request and hasattr(request.app.state, "cache_service"):
            await request.app.state.cache_service.set("performance_scores", result, **cache_params)
        return JSONResponse(content=result, headers={"X-Cache": cache_status})
    except Exception as e:
        logger.error(f"查询绩效评分列表失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="查询绩效评分列表失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和查询参数,或联系系统管理员",
            status_code=500
        )


@router.get("/scores/{shop_id}", response_model=Dict[str, Any])
async def get_shop_performance(
    request: Request,
    shop_id: str,
    platform_code: str = Query(..., description="平台代码"),
    period: Optional[str] = Query(None, description="考核周期,如'2025-01'"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    查询店铺绩效详情
    
    如果未指定period,返回最新周期的绩效
    """
    try:
        params = {"shop_id": shop_id, "platform_code": platform_code, "period": period or ""}
        cache_params = _normalize_cache_params(params)
        cache_status = "BYPASS"
        if request and hasattr(request.app.state, "cache_service"):
            cache_service = request.app.state.cache_service
            cached = await cache_service.get("performance_scores_shop", **cache_params)
            if cached is not None:
                return JSONResponse(content=cached, headers={"X-Cache": "HIT"})
            cache_status = "MISS"

        query = select(PerformanceScore).where(
            PerformanceScore.platform_code == platform_code,
            PerformanceScore.shop_id == shop_id
        )
        
        if period:
            query = query.where(PerformanceScore.period == period)
        else:
            # 获取最新周期
            query = query.order_by(PerformanceScore.period.desc()).limit(1)
        
        score = (await db.execute(query)).scalar_one_or_none()
        
        if not score:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="绩效数据不存在",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="请检查店铺ID和日期,或确认该绩效数据已计算",
                status_code=404
            )
        
        # 获取店铺名称
        shop = (await db.execute(
            select(DimShop).where(
                DimShop.platform_code == platform_code,
                DimShop.shop_id == shop_id
            )
        )).scalar_one_or_none()
        
        details = getattr(score, "score_details", None) or {}
        score_data = {
            "id": score.id,
            "platform_code": score.platform_code,
            "shop_id": score.shop_id,
            "shop_name": shop.shop_name if shop else None,
            "period": score.period,
            "total_score": _public_total_score(score.total_score, details),
            "rank": _public_rank(score.rank, details),
            "performance_coefficient": _public_coefficient(score.performance_coefficient, details),
            "sales_score": _build_metric_detail(details, "sales", score.sales_score),
            "profit_score": _build_metric_detail(details, "profit", score.profit_score),
            "key_product_score": _build_metric_detail(details, "key_product", score.key_product_score),
            "operation_score": _build_metric_detail(details, "operation", score.operation_score),
            "score_details": details,
        }

        result = {"success": True, "data": score_data}
        if request and hasattr(request.app.state, "cache_service"):
            await request.app.state.cache_service.set("performance_scores_shop", result, **cache_params)
        return JSONResponse(content=result, headers={"X-Cache": cache_status})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询店铺绩效详情失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="查询店铺绩效详情失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和查询参数,或联系系统管理员",
            status_code=500
        )


@router.post("/scores/calculate", response_model=Dict[str, Any])
async def calculate_performance_scores(
    period: str = Query(..., description="考核周期,如'2025-01'"),
    config_id: Optional[int] = Query(None, description="绩效配置ID(默认使用当前生效的配置)"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    计算绩效评分(C类数据:系统自动计算)

    绩效计算最小闭环：
    - 优先使用 a_class.target_breakdown（月度店铺目标/达成）聚合
    - 缺失时回退使用 PostgreSQL 店铺赛马模块估算达成率
    - 写入 c_class.performance_scores（按 platform_code+shop_id+period upsert）
    """
    try:
        # 按考核周期校验配置是否存在(契约: 无配置时返回 404 + PERF_CONFIG_NOT_FOUND)
        period_start = datetime.strptime(period, "%Y-%m").date().replace(day=1)
        if period_start.month == 12:
            period_end = period_start.replace(year=period_start.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            period_end = period_start.replace(month=period_start.month + 1, day=1) - timedelta(days=1)

        if config_id:
            result = await db.execute(
                select(PerformanceConfig).where(PerformanceConfig.id == config_id)
            )
            config = result.scalar_one_or_none()
        else:
            result = await db.execute(
                select(PerformanceConfig).where(
                    PerformanceConfig.is_active == True,
                    PerformanceConfig.effective_from <= period_end,
                    or_(
                        PerformanceConfig.effective_to.is_(None),
                        PerformanceConfig.effective_to >= period_start
                    )
                ).order_by(PerformanceConfig.effective_from.desc())
            )
            config = result.scalar_one_or_none()

        if not config:
            return error_response(
                code=ErrorCode.PERF_CONFIG_NOT_FOUND,
                message="考核周期内无可用绩效配置",
                error_type=get_error_type(ErrorCode.PERF_CONFIG_NOT_FOUND),
                recovery_suggestion="请先创建并启用该周期内的绩效配置",
                status_code=404,
                data={"error_code": "PERF_CONFIG_NOT_FOUND"}
            )

        def _score_by_rate(max_score: float, rate: float) -> float:
            safe_rate = max(0.0, min(1.0, float(rate or 0.0)))
            return round(float(max_score) * safe_rate, 4)

        # 1) 优先从 target_breakdown 聚合店铺维度达成
        source_rows = {}
        tb_query = select(TargetBreakdown).where(
            TargetBreakdown.breakdown_type.in_(["shop", "shop_time"]),
            TargetBreakdown.platform_code.is_not(None),
            TargetBreakdown.shop_id.is_not(None),
            or_(
                and_(
                    TargetBreakdown.period_start.is_not(None),
                    TargetBreakdown.period_end.is_not(None),
                    TargetBreakdown.period_start <= period_end,
                    TargetBreakdown.period_end >= period_start,
                ),
                TargetBreakdown.period_label == period,
            ),
        )
        tb_rows = (await db.execute(tb_query)).scalars().all()
        for row in tb_rows:
            key = f"{(row.platform_code or '').lower()}|{row.shop_id or ''}"
            rec = source_rows.setdefault(
                key,
                {
                    "platform_code": (row.platform_code or "").lower(),
                    "shop_id": row.shop_id,
                    "target": 0.0,
                    "achieved": 0.0,
                    "target_profit_amount": 0.0,
                    "achieved_profit_amount": 0.0,
                },
            )
            rec["target"] += float(row.target_amount or 0)
            rec["achieved"] += float(row.achieved_amount or 0)
            rec["target_profit_amount"] += float(getattr(row, "target_profit_amount", 0) or 0)
            rec["achieved_profit_amount"] += float(getattr(row, "achieved_profit_amount", 0) or 0)

        # 2) 若目标分解为空，回退 PostgreSQL 店铺赛马模块
        if not source_rows:
            try:
                source_rows = await load_shop_monthly_target_achievement(db, period)
            except Exception as e:
                logger.warning("绩效计算 PostgreSQL 店铺赛马回退数据加载失败: %s", e)

        if not source_rows:
            return error_response(
                code=ErrorCode.PERF_CALC_NOT_READY,
                message="绩效计算能力未就绪（无可用源数据）",
                error_type=get_error_type(ErrorCode.PERF_CALC_NOT_READY),
                recovery_suggestion="请先配置目标分解或确认 PostgreSQL 店铺赛马数据可用",
                status_code=503,
                data={"error_code": "PERF_CALC_NOT_READY"},
            )

        # 3) 计算分数并排名
        metrics_by_shop = {}
        try:
            metrics_by_shop = await load_shop_monthly_metrics(db, period)
        except Exception as e:
            logger.warning("缁╂晥璁＄畻 PostgreSQL 搴楅摵鏈堝害鎸囨爣鍔犺浇澶辫触: %s", e)

        operation_target_query = (
            select(SalesTarget)
            .where(SalesTarget.target_type == "operation")
            .where(SalesTarget.period_start <= period_end)
            .where(SalesTarget.period_end >= period_start)
            .order_by(SalesTarget.created_at.desc())
            .limit(1)
        )
        operation_target = (await db.execute(operation_target_query)).scalar_one_or_none()
        product_target_query = (
            select(SalesTarget)
            .where(SalesTarget.target_type == "product")
            .where(SalesTarget.period_start <= period_end)
            .where(SalesTarget.period_end >= period_start)
            .order_by(SalesTarget.created_at.desc())
        )
        product_targets = (await db.execute(product_target_query)).scalars().all()
        product_metrics_by_shop = {}
        try:
            product_metrics_by_shop = await _load_shop_monthly_product_metrics(db, period)
        except Exception as e:
            logger.warning("Product monthly metrics load failed: %s", e)

        product_target_by_shop: Dict[str, Dict[str, Any]] = {}
        for product_target in product_targets:
            if not getattr(product_target, "platform_sku", None) and getattr(product_target, "product_id", None) is None:
                continue
            breakdown_rows = (
                await db.execute(
                    select(TargetBreakdown).where(
                        TargetBreakdown.target_id == product_target.id,
                        TargetBreakdown.breakdown_type.in_(["shop", "shop_time"]),
                    )
                )
            ).scalars().all()
            for breakdown_row in breakdown_rows:
                shop_key = f"{(breakdown_row.platform_code or '').lower()}|{breakdown_row.shop_id or ''}"
                product_key = None
                if getattr(product_target, "platform_sku", None):
                    product_key = f"{shop_key}|sku:{product_target.platform_sku}"
                elif getattr(product_target, "product_id", None) is not None:
                    product_key = f"{shop_key}|pid:{product_target.product_id}"
                metrics = product_metrics_by_shop.get(product_key or "", {})
                rec = product_target_by_shop.setdefault(
                    shop_key,
                    {"target_amount": 0.0, "achieved_amount": 0.0, "products": []},
                )
                target_amount = float(getattr(breakdown_row, "target_amount", 0) or 0)
                achieved_amount = float(metrics.get("sales_amount", 0.0))
                rec["target_amount"] += target_amount
                rec["achieved_amount"] += achieved_amount
                rec["products"].append(
                    {
                        "product_id": getattr(product_target, "product_id", None),
                        "platform_sku": getattr(product_target, "platform_sku", None),
                        "company_sku": getattr(product_target, "company_sku", None),
                        "target_amount": target_amount,
                        "achieved_amount": achieved_amount,
                    }
                )

        calc_list = []
        for rec in source_rows.values():
            platform_code = rec["platform_code"]
            current_shop_id = rec["shop_id"]
            key = f"{platform_code}|{current_shop_id}"
            target = float(rec["target"] or 0)
            achieved = float(rec["achieved"] or 0)
            target_profit = float(rec.get("target_profit_amount") or 0)
            rate = (achieved / target) if target > 0 else _rate_percent_to_fraction(rec.get("achievement_rate"))
            sales_rate = _normalize_rate_percent(rate)
            sales_score = _score_by_rate(config.sales_max_score, rate)
            profit_achieved = float(
                rec.get("achieved_profit_amount")
                or metrics_by_shop.get(key, {}).get("monthly_profit")
                or 0.0
            )
            profit_rate_fraction = (profit_achieved / target_profit) if target_profit > 0 else None
            profit_rate = _normalize_rate_percent(profit_rate_fraction)
            profit_score = _score_by_rate(config.profit_max_score, profit_rate_fraction) if target_profit > 0 else 0.0
            key_product_target = float(product_target_by_shop.get(key, {}).get("target_amount", 0.0))
            key_product_achieved = float(product_target_by_shop.get(key, {}).get("achieved_amount", 0.0))
            key_product_rate_fraction = (key_product_achieved / key_product_target) if key_product_target > 0 else None
            key_product_rate = _normalize_rate_percent(key_product_rate_fraction)
            key_product_score = _score_by_rate(config.key_product_max_score, key_product_rate_fraction) if key_product_target > 0 else 0.0
            operation_score, operation_details = _calculate_operation_metric_score(operation_target) if operation_target else (
                0.0,
                {
                    "status": "pending_design",
                    "source": None,
                    "target": None,
                    "achieved": None,
                    "rate": None,
                    "calculation": None,
                    "message": "Operation target pipeline is not ready.",
                },
            )

            calc_list.append(
                {
                    "platform_code": platform_code,
                    "shop_id": current_shop_id,
                    "sales_score": sales_score,
                    "profit_score": profit_score,
                    "key_product_score": key_product_score,
                    "operation_score": operation_score,
                    "total_score": round(sales_score + profit_score + key_product_score + operation_score, 4),
                    "rank": None,
                    "performance_coefficient": 1.0,
                    "score_details": {
                        "sales": {
                            "status": "calculated",
                            "source": "target_breakdown" if tb_rows else "api.business_overview_shop_racing_module",
                            "target": target,
                            "achieved": achieved,
                            "rate": sales_rate,
                            "calculation": f"min(rate {sales_rate or 0:.2f}%, 100%) * sales max {config.sales_max_score}",
                        },
                        "profit": {
                            "status": "calculated" if target_profit > 0 else "pending_design",
                            "source": "target_breakdown + api.business_overview_shop_racing_module" if target_profit > 0 else "api.business_overview_shop_racing_module",
                            "target": target_profit if target_profit > 0 else None,
                            "achieved": profit_achieved,
                            "rate": profit_rate,
                            "calculation": f"min(rate {profit_rate or 0:.2f}%, 100%) * profit max {config.profit_max_score}" if target_profit > 0 else None,
                            "message": None if target_profit > 0 else "Profit target pipeline is not ready.",
                        },
                        "key_product": {
                            "status": "calculated" if key_product_target > 0 else "pending_design",
                            "source": "target_management + mart.product_day_kpi" if key_product_target > 0 else None,
                            "target": key_product_target if key_product_target > 0 else None,
                            "achieved": key_product_achieved if key_product_target > 0 else None,
                            "rate": key_product_rate if key_product_target > 0 else None,
                            "calculation": f"min(rate {key_product_rate or 0:.2f}%, 100%) * key product max {config.key_product_max_score}" if key_product_target > 0 else None,
                            "message": None if key_product_target > 0 else "Key product target pipeline is not ready.",
                        },
                        "operation": {
                            "status": operation_details["status"],
                            "source": operation_details["source"],
                            "target": operation_details["target"],
                            "achieved": operation_details["achieved"],
                            "rate": operation_details["rate"],
                            "calculation": operation_details["calculation"],
                            "message": operation_details["message"],
                        },
                        "summary": {
                            "status": "complete" if (target_profit > 0 and key_product_target > 0 and operation_details["status"] == "calculated") else "partial",
                            "ready_dimensions": [
                                dimension
                                for dimension, ready in [
                                    ("sales", True),
                                    ("profit", target_profit > 0),
                                    ("key_product", key_product_target > 0),
                                    ("operation", operation_details["status"] == "calculated"),
                                ]
                                if ready
                            ],
                            "pending_dimensions": [
                                dimension
                                for dimension, ready in [
                                    ("profit", target_profit > 0),
                                    ("key_product", key_product_target > 0),
                                    ("operation", operation_details["status"] == "calculated"),
                                ]
                                if not ready
                            ],
                            "message": "Sales, profit, key product, and operation dimensions are independently calculated." if (target_profit > 0 and key_product_target > 0 and operation_details["status"] == "calculated") else "Partial dimensions are independently calculated.",
                        },
                    },
                }
            )

        # 4) upsert c_class.performance_scores
        upserts = 0
        for row in calc_list:
            existed = (
                await db.execute(
                    select(PerformanceScore).where(
                        PerformanceScore.platform_code == row["platform_code"],
                        PerformanceScore.shop_id == row["shop_id"],
                        PerformanceScore.period == period,
                    )
                )
            ).scalar_one_or_none()
            details = row["score_details"]
            if existed:
                existed.total_score = row["total_score"]
                existed.sales_score = row["sales_score"]
                existed.profit_score = row["profit_score"]
                existed.key_product_score = row["key_product_score"]
                existed.operation_score = row["operation_score"]
                existed.rank = row["rank"]
                existed.performance_coefficient = row["performance_coefficient"]
                existed.score_details = details
                existed.updated_at = datetime.now(timezone.utc)
            else:
                db.add(
                    PerformanceScore(
                        platform_code=row["platform_code"],
                        shop_id=row["shop_id"],
                        period=period,
                        total_score=row["total_score"],
                        sales_score=row["sales_score"],
                        profit_score=row["profit_score"],
                        key_product_score=row["key_product_score"],
                        operation_score=row["operation_score"],
                        rank=row["rank"],
                        performance_coefficient=row["performance_coefficient"],
                        score_details=details,
                    )
                )
            upserts += 1
        income_service = HRIncomeCalculationService(db=db)
        income_result = await income_service.calculate_month(period)
        payroll_service = PayrollGenerationService(db=db)
        payroll_result = await payroll_service.generate_month(period)
        await db.commit()
        try:
            from backend.services.cache_service import get_cache_service
            await invalidate_performance_related_caches(get_cache_service())
        except Exception as inv_err:
            logger.warning(f"[PerformanceManagement] 写时失效绩效缓存失败: {inv_err}")
        return success_response(
            data={
                "period": period,
                "upserts": upserts,
                "shop_performance_upserts": upserts,
                "employee_count": income_result.get("employee_count", 0),
                "commission_upserts": income_result.get("commission_upserts", 0),
                "employee_performance_upserts": income_result.get("performance_upserts", 0),
                "payroll_upserts": payroll_result.get("payroll_upserts", 0),
                "payroll_locked_conflicts": payroll_result.get("locked_conflicts", 0),
                "payroll_locked_conflict_details": payroll_result.get("locked_conflict_details", []),
            },
            message="绩效计算完成",
        )
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"考核周期格式无效: {e}")
        return error_response(
            code=ErrorCode.DATA_FORMAT_INVALID,
            message="考核周期格式无效，应为 YYYY-MM",
            error_type=get_error_type(ErrorCode.DATA_FORMAT_INVALID),
            detail=str(e),
            status_code=400
        )
    except Exception as e:
        logger.error(f"计算绩效评分失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="计算绩效评分失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限,或联系系统管理员",
            status_code=500
        )
