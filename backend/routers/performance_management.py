#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
绩效管理API（v4.11.0新增）

功能：
1. 绩效权重配置CRUD
2. 绩效评分查询（自动计算）
3. 绩效排名查询

路由：
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
    FactOrder,
    FactProductMetric,
    DimShop
)
from modules.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/performance", tags=["绩效管理"])


# ==================== Request/Response Models ====================

class PerformanceConfigCreateRequest(BaseModel):
    """创建绩效配置请求"""
    config_name: str = Field("default", description="配置名称")
    sales_weight: int = Field(30, ge=0, le=100, description="销售额权重（%）")
    profit_weight: int = Field(25, ge=0, le=100, description="毛利权重（%）")
    key_product_weight: int = Field(25, ge=0, le=100, description="重点产品权重（%）")
    operation_weight: int = Field(20, ge=0, le=100, description="运营权重（%）")
    effective_from: date = Field(..., description="生效开始日期")
    effective_to: Optional[date] = Field(None, description="生效结束日期")


class PerformanceConfigUpdateRequest(BaseModel):
    """更新绩效配置请求"""
    config_name: Optional[str] = None
    sales_weight: Optional[int] = Field(None, ge=0, le=100)
    profit_weight: Optional[int] = Field(None, ge=0, le=100)
    key_product_weight: Optional[int] = Field(None, ge=0, le=100)
    operation_weight: Optional[int] = Field(None, ge=0, le=100)
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
                recovery_suggestion="请检查配置ID是否正确，或确认该配置已创建",
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
            recovery_suggestion="请检查数据库连接和查询参数，或联系系统管理员",
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
                message=f"权重总和必须为100，当前为{total_weight}",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="请调整权重值，确保总和为100",
                status_code=400
            )
        
        # 创建配置
        config = PerformanceConfig(
            config_name=request.config_name,
            sales_weight=request.sales_weight,
            profit_weight=request.profit_weight,
            key_product_weight=request.key_product_weight,
            operation_weight=request.operation_weight,
            effective_from=request.effective_from,
            effective_to=request.effective_to,
            created_by=created_by,
            is_active=True
        )
        
        db.add(config)
        await db.commit()
        await db.refresh(config)
        
        # 触发A_CLASS_UPDATED事件（数据流转流程自动化）
        try:
            from backend.utils.events import AClassUpdatedEvent
            from backend.services.event_listeners import event_listener
            
            # 绩效配置影响所有店铺，不需要指定具体店铺
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
    
    如果更新权重，需要验证总和为100
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
                recovery_suggestion="请检查配置ID是否正确，或确认该配置已创建",
                status_code=404
            )
        
        # 更新字段
        update_data = request.dict(exclude_unset=True)
        
        # 如果更新权重，验证总和
        if any(k in update_data for k in ["sales_weight", "profit_weight", "key_product_weight", "operation_weight"]):
            sales_weight = update_data.get("sales_weight", config.sales_weight)
            profit_weight = update_data.get("profit_weight", config.profit_weight)
            key_product_weight = update_data.get("key_product_weight", config.key_product_weight)
            operation_weight = update_data.get("operation_weight", config.operation_weight)
            
            total_weight = sales_weight + profit_weight + key_product_weight + operation_weight
            if total_weight != 100:
                return error_response(
                    code=ErrorCode.DATA_VALIDATION_FAILED,
                    message=f"权重总和必须为100，当前为{total_weight}",
                    error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                    recovery_suggestion="请调整权重值，确保总和为100",
                    status_code=400
                )
        
        for key, value in update_data.items():
            setattr(config, key, value)
        
        config.updated_at = datetime.utcnow()
        
        await db.commit()
        await db.refresh(config)
        
        # 触发A_CLASS_UPDATED事件（数据流转流程自动化）
        try:
            from backend.utils.events import AClassUpdatedEvent
            from backend.services.event_listeners import event_listener
            
            # 绩效配置影响所有店铺，不需要指定具体店铺
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
                recovery_suggestion="请检查配置ID是否正确，或确认该配置已创建",
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
            recovery_suggestion="请检查数据库连接和权限，或联系系统管理员",
            status_code=500
        )


@router.get("/scores", response_model=Dict[str, Any])
async def list_performance_scores(
    period: Optional[str] = Query(None, description="考核周期，如'2025-01'"),
    platform_code: Optional[str] = Query(None, description="平台筛选"),
    shop_id: Optional[str] = Query(None, description="店铺筛选"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    查询绩效评分列表
    
    按总分降序排列
    """
    try:
        query = select(PerformanceScore)
        
        if period:
            query = query.where(PerformanceScore.period == period)
        if platform_code:
            query = query.where(PerformanceScore.platform_code == platform_code)
        if shop_id:
            query = query.where(PerformanceScore.shop_id == shop_id)
        
        # 总数查询
        total_query = select(func.count()).select_from(query.subquery())
        total = db.execute(total_query).scalar() or 0
        
        # 分页查询（按总分降序）
        query = query.order_by(PerformanceScore.total_score.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        
        scores = db.execute(query).scalars().all()
        
        # 获取店铺名称
        score_responses = []
        for score in scores:
            score_data = PerformanceScoreResponse.from_orm(score).dict()
            shop = db.execute(
                select(DimShop).where(
                    DimShop.platform_code == score.platform_code,
                    DimShop.shop_id == score.shop_id
                )
            ).scalar_one_or_none()
            if shop:
                score_data["shop_name"] = shop.shop_name
            score_responses.append(score_data)
        
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
            recovery_suggestion="请检查数据库连接和查询参数，或联系系统管理员",
            status_code=500
        )


@router.get("/scores/{shop_id}", response_model=Dict[str, Any])
async def get_shop_performance(
    shop_id: str,
    platform_code: str = Query(..., description="平台代码"),
    period: Optional[str] = Query(None, description="考核周期，如'2025-01'"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    查询店铺绩效详情
    
    如果未指定period，返回最新周期的绩效
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
        
        score = db.execute(query).scalar_one_or_none()
        
        if not score:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="绩效数据不存在",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="请检查店铺ID和日期，或确认该绩效数据已计算",
                status_code=404
            )
        
        # 获取店铺名称
        shop = db.execute(
            select(DimShop).where(
                DimShop.platform_code == platform_code,
                DimShop.shop_id == shop_id
            )
        ).scalar_one_or_none()
        
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
            recovery_suggestion="请检查数据库连接和查询参数，或联系系统管理员",
            status_code=500
        )


@router.post("/scores/calculate", response_model=Dict[str, Any])
async def calculate_performance_scores(
    period: str = Query(..., description="考核周期，如'2025-01'"),
    config_id: Optional[int] = Query(None, description="绩效配置ID（默认使用当前生效的配置）"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    计算绩效评分（C类数据：系统自动计算）
    
    基于以下数据计算：
    1. 销售额得分：从sales_targets和fact_orders计算达成率 × 权重
    2. 毛利得分：从fact_orders计算毛利达成率 × 权重
    3. 重点产品得分：从fact_product_metrics计算重点产品达成率 × 权重
    4. 运营得分：从shop_health_scores计算运营指标得分 × 权重
    
    注意：这是一个复杂的计算逻辑，需要根据实际业务规则实现
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
        
        # 解析周期（如"2025-01"）
        period_start = datetime.strptime(period, "%Y-%m").date().replace(day=1)
        if period_start.month == 12:
            period_end = period_start.replace(year=period_start.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            period_end = period_start.replace(month=period_start.month + 1, day=1) - timedelta(days=1)
        
        calculated_scores = []
        
        for shop in shops:
            # TODO: 实现具体的计算逻辑
            # 这里需要根据业务规则计算各项得分
            # 1. 销售额得分：查询sales_targets和fact_orders
            # 2. 毛利得分：查询fact_orders计算毛利
            # 3. 重点产品得分：查询fact_product_metrics
            # 4. 运营得分：查询shop_health_scores
            
            # 临时实现：使用默认值
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
            recovery_suggestion="请检查数据库连接和权限，或联系系统管理员",
            status_code=500
        )

