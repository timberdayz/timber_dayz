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

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import date, datetime, timedelta

from backend.models.database import get_db, get_async_db
from backend.utils.api_response import success_response, error_response, pagination_response
from backend.utils.error_codes import ErrorCode, get_error_type
from modules.core.db import (
    PerformanceConfig,
    PerformanceScore,
    SalesTarget,
    Employee,
    EmployeePerformance,
    # [DELETED] v4.19.0: FactOrder 已删除
    FactProductMetric,
    DimShop,
    PlatformAccount,
)
from modules.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/performance", tags=["绩效管理"])


# ==================== Request/Response Models ====================

class PerformanceConfigCreateRequest(BaseModel):
    """创建绩效配置请求"""
    config_name: str = Field("default", description="配置名称")
    sales_weight: int = Field(30, ge=0, le=100, description="销售额权重(%)")
    profit_weight: int = Field(25, ge=0, le=100, description="毛利权重(%)")
    key_product_weight: int = Field(25, ge=0, le=100, description="重点产品权重(%)")
    operation_weight: int = Field(20, ge=0, le=100, description="运营权重(%)")
    sales_max_score: int = Field(30, ge=0, le=100, description="销售额满分(达成率>100%得满分)")
    profit_max_score: int = Field(25, ge=0, le=100, description="毛利满分")
    key_product_max_score: int = Field(25, ge=0, le=100, description="重点产品满分")
    operation_max_score: int = Field(20, ge=0, le=100, description="运营满分")
    effective_from: date = Field(..., description="生效开始日期")
    effective_to: Optional[date] = Field(None, description="生效结束日期")


class PerformanceConfigUpdateRequest(BaseModel):
    """更新绩效配置请求"""
    config_name: Optional[str] = None
    sales_weight: Optional[int] = Field(None, ge=0, le=100)
    profit_weight: Optional[int] = Field(None, ge=0, le=100)
    key_product_weight: Optional[int] = Field(None, ge=0, le=100)
    operation_weight: Optional[int] = Field(None, ge=0, le=100)
    sales_max_score: Optional[int] = Field(None, ge=0, le=100)
    profit_max_score: Optional[int] = Field(None, ge=0, le=100)
    key_product_max_score: Optional[int] = Field(None, ge=0, le=100)
    operation_max_score: Optional[int] = Field(None, ge=0, le=100)
    is_active: Optional[bool] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None


class PerformanceConfigResponse(BaseModel):
    """绩效配置响应"""
    id: int
    config_name: str
    sales_weight: int
    profit_weight: int
    key_product_weight: int
    operation_weight: int
    sales_max_score: int = 30
    profit_max_score: int = 25
    key_product_max_score: int = 25
    operation_max_score: int = 20
    is_active: bool
    effective_from: date
    effective_to: Optional[date]
    created_by: Optional[str]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class PerformanceScoreResponse(BaseModel):
    """绩效评分响应"""
    id: int
    platform_code: str
    shop_id: str
    shop_name: Optional[str] = None
    period: str
    total_score: float
    sales_score: float
    profit_score: float
    key_product_score: float
    operation_score: float
    rank: Optional[int]
    performance_coefficient: float
    
    class Config:
        from_attributes = True


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
        total = db.execute(total_query).scalar() or 0
        
        # 分页查询
        query = query.order_by(PerformanceConfig.effective_from.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        
        configs = db.execute(query).scalars().all()
        
        return pagination_response(
            data=[PerformanceConfigResponse.from_orm(c).dict() for c in configs],
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
        config = db.execute(
            select(PerformanceConfig).where(PerformanceConfig.id == config_id)
        ).scalar_one_or_none()
        
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
            "data": PerformanceConfigResponse.from_orm(config).dict()
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
            data=PerformanceConfigResponse.from_orm(config).dict(),
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
        config = db.execute(
            select(PerformanceConfig).where(PerformanceConfig.id == config_id)
        ).scalar_one_or_none()
        
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
        
        config.updated_at = datetime.utcnow()
        
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
            data=PerformanceConfigResponse.from_orm(config).dict(),
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
        config = db.execute(
            select(PerformanceConfig).where(PerformanceConfig.id == config_id)
        ).scalar_one_or_none()
        
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


@router.get("/scores", response_model=Dict[str, Any])
async def list_performance_scores(
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
        if group_by == "person":
            # 按人员：从 employee_performance 取数据
            query = select(EmployeePerformance)
            if period:
                query = query.where(EmployeePerformance.year_month == period)
            total_query = select(func.count()).select_from(query.subquery())
            total = (await db.execute(total_query)).scalar() or 0
            query = query.order_by(EmployeePerformance.performance_score.desc())
            query = query.offset((page - 1) * page_size).limit(page_size)
            rows = (await db.execute(query)).scalars().all()
            # 兼容 Row
            ep_list = [r[0] if hasattr(r, "__getitem__") and len(r) == 1 else r for r in rows]
            # 取员工姓名
            codes = list({getattr(e, "employee_code", None) for e in ep_list if e})
            name_map = {}
            if codes:
                emp_query = select(Employee.employee_code, Employee.name).where(Employee.employee_code.in_(codes))
                emp_rows = (await db.execute(emp_query)).all()
                for r in emp_rows:
                    ec = r[0] if hasattr(r, "__getitem__") else getattr(r, "employee_code", "")
                    nm = r[1] if hasattr(r, "__getitem__") and len(r) > 1 else getattr(r, "name", "")
                    name_map[ec] = nm or ec
            # 计算排名
            all_query = select(EmployeePerformance)
            if period:
                all_query = all_query.where(EmployeePerformance.year_month == period)
            all_rows = (await db.execute(all_query)).scalars().all()
            all_ep = [r[0] if hasattr(r, "__getitem__") and len(r) == 1 else r for r in all_rows]
            sorted_ep = sorted(all_ep, key=lambda x: float(getattr(x, "performance_score", 0) or 0), reverse=True)
            rank_by_code = {}
            for i, e in enumerate(sorted_ep, 1):
                ec = getattr(e, "employee_code", None)
                if ec:
                    rank_by_code[ec] = i
            score_responses = []
            for ep in ep_list:
                ec = getattr(ep, "employee_code", "")
                scr = float(getattr(ep, "performance_score", 0) or 0)
                ach = float(getattr(ep, "achievement_rate", 0) or 0) * 100
                score_responses.append({
                    "employee_code": ec,
                    "employee_name": name_map.get(ec, ec),
                    "sales_target": None,
                    "sales_achieved": getattr(ep, "actual_sales", None),
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
            return {
                "success": True,
                "data": score_responses,
                "total": total,
                "page": page,
                "page_size": page_size,
                "has_more": (page * page_size) < total,
            }

        # 按店铺：以 platform_accounts（正在经营店铺）为主，合并 performance_scores
        shop_query = (
            select(PlatformAccount)
            .where(PlatformAccount.enabled == True)
            .order_by(PlatformAccount.platform, PlatformAccount.store_name)
        )
        shop_rows = (await db.execute(shop_query)).scalars().all()
        all_shops = [
            {
                "platform_code": (r.platform or "").lower() if r.platform else "",
                "shop_id": r.shop_id or r.account_id or str(r.id),
                "shop_name": r.store_name or (r.account_alias or "") or r.account_id or "",
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
                    "sales_score": getattr(s, "sales_score", None),
                    "profit_target": _score_details_field(details, "profit", "target"),
                    "profit_achieved": _score_details_field(details, "profit", "achieved"),
                    "profit_rate": _score_details_field(details, "profit", "rate"),
                    "profit_score": getattr(s, "profit_score", None),
                    "key_product_target": _score_details_field(details, "key_product", "target"),
                    "key_product_achieved": _score_details_field(details, "key_product", "achieved"),
                    "key_product_rate": _score_details_field(details, "key_product", "rate"),
                    "key_product_score": getattr(s, "key_product_score", None),
                    "operation_score": getattr(s, "operation_score", None),
                    "total_score": getattr(s, "total_score", None),
                    "rank": getattr(s, "rank", None),
                    "performance_coefficient": getattr(s, "performance_coefficient", None),
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
            }
            score_responses.append(row)
        
        return {
            "success": True,
            "data": score_responses,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_more": (page * page_size) < total
        }
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
        
        score_data = PerformanceScoreResponse.from_orm(score).dict()
        if shop:
            score_data["shop_name"] = shop.shop_name
        
        return {
            "success": True,
            "data": score_data
        }
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
    
    基于以下数据计算:
    1. 销售额得分:从sales_targets和fact_orders计算达成率 × 权重
    2. 毛利得分:从fact_orders计算毛利达成率 × 权重
    3. 重点产品得分:从fact_product_metrics计算重点产品达成率 × 权重
    4. 运营得分:从shop_health_scores计算运营指标得分 × 权重
    
    注意:这是一个复杂的计算逻辑,需要根据实际业务规则实现
    """
    try:
        # 获取绩效配置
        if config_id:
            result = await db.execute(
                select(PerformanceConfig).where(PerformanceConfig.id == config_id)
            )
            config = result.scalar_one_or_none()
        else:
            # 获取当前生效的配置
            today = date.today()
            result = await db.execute(
                select(PerformanceConfig).where(
                    PerformanceConfig.is_active == True,
                    PerformanceConfig.effective_from <= today,
                    or_(
                        PerformanceConfig.effective_to.is_(None),
                        PerformanceConfig.effective_to >= today
                    )
                ).order_by(PerformanceConfig.effective_from.desc())
            )
            config = result.scalar_one_or_none()
        
        if not config:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="未找到生效的绩效配置",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="请先创建并启用绩效配置",
                status_code=404
            )
        
        # 获取所有店铺
        result = await db.execute(select(DimShop))
        shops = result.scalars().all()
        
        # 解析周期(如"2025-01")
        period_start = datetime.strptime(period, "%Y-%m").date().replace(day=1)
        if period_start.month == 12:
            period_end = period_start.replace(year=period_start.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            period_end = period_start.replace(month=period_start.month + 1, day=1) - timedelta(days=1)
        
        calculated_scores = []
        
        for shop in shops:
            # TODO: 实现具体的计算逻辑
            # 这里需要根据业务规则计算各项得分
            # 1. 销售额得分:查询sales_targets和fact_orders
            # 2. 毛利得分:查询fact_orders计算毛利
            # 3. 重点产品得分:查询fact_product_metrics
            # 4. 运营得分:查询shop_health_scores
            
            # 临时实现:使用默认值
            sales_score = 0.0
            profit_score = 0.0
            key_product_score = 0.0
            operation_score = 0.0
            
            total_score = (
                sales_score * config.sales_weight / 100 +
                profit_score * config.profit_weight / 100 +
                key_product_score * config.key_product_weight / 100 +
                operation_score * config.operation_weight / 100
            )
            
            # 创建或更新绩效评分
            result = await db.execute(
                select(PerformanceScore).where(
                    PerformanceScore.platform_code == shop.platform_code,
                    PerformanceScore.shop_id == shop.shop_id,
                    PerformanceScore.period == period
                )
            )
            existing_score = result.scalar_one_or_none()
            
            if existing_score:
                existing_score.total_score = total_score
                existing_score.sales_score = sales_score
                existing_score.profit_score = profit_score
                existing_score.key_product_score = key_product_score
                existing_score.operation_score = operation_score
                score = existing_score
            else:
                score = PerformanceScore(
                    platform_code=shop.platform_code,
                    shop_id=shop.shop_id,
                    period=period,
                    total_score=total_score,
                    sales_score=sales_score,
                    profit_score=profit_score,
                    key_product_score=key_product_score,
                    operation_score=operation_score,
                    score_details={}  # TODO: 存储详细计算过程
                )
                db.add(score)
            
            calculated_scores.append(score)
        
        # 计算排名
        calculated_scores.sort(key=lambda x: x.total_score, reverse=True)
        for rank, score in enumerate(calculated_scores, start=1):
            score.rank = rank
        
        await db.commit()
        
        return {
            "success": True,
            "data": {
                "period": period,
                "calculated_count": len(calculated_scores),
                "config": PerformanceConfigResponse.from_orm(config).dict()
            },
            "message": "绩效评分计算完成"
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"计算绩效评分失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="计算绩效评分失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限,或联系系统管理员",
            status_code=500
        )

