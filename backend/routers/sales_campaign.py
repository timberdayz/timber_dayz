#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
销售战役管理API（v4.11.0新增）

功能：
1. 销售战役CRUD（创建、查询、更新、删除）
2. 战役参与店铺管理
3. 战役达成情况查询（自动计算）
4. 战役列表查询（分页、筛选）

路由：
- GET /api/sales-campaigns - 查询战役列表
- GET /api/sales-campaigns/{campaign_id} - 查询战役详情
- POST /api/sales-campaigns - 创建战役
- PUT /api/sales-campaigns/{campaign_id} - 更新战役
- DELETE /api/sales-campaigns/{campaign_id} - 删除战役
- POST /api/sales-campaigns/{campaign_id}/shops - 添加参与店铺
- DELETE /api/sales-campaigns/{campaign_id}/shops/{shop_id} - 移除参与店铺
- POST /api/sales-campaigns/{campaign_id}/calculate - 计算达成情况
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, delete
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import date, datetime

from backend.models.database import get_db, get_async_db
from backend.utils.api_response import success_response, error_response, pagination_response
from backend.utils.error_codes import ErrorCode, get_error_type
from modules.core.db import (
    SalesCampaign,
    SalesCampaignShop,
    FactOrder,
    DimShop
)
from modules.core.logger import get_logger
logger = get_logger(__name__)
router = APIRouter(prefix="/sales-campaigns", tags=["销售战役管理"])


# ==================== Request/Response Models ====================

class CampaignCreateRequest(BaseModel):
    """创建战役请求"""
    campaign_name: str = Field(..., description="战役名称")
    campaign_type: str = Field(..., description="战役类型：holiday/new_product/special_event")
    start_date: date = Field(..., description="开始日期")
    end_date: date = Field(..., description="结束日期")
    target_amount: float = Field(0.0, ge=0, description="目标销售额（CNY）")
    target_quantity: int = Field(0, ge=0, description="目标订单数/销量")
    description: Optional[str] = Field(None, description="战役描述")
    shop_ids: Optional[List[Dict[str, str]]] = Field(None, description="参与店铺列表：[{platform_code, shop_id, target_amount, target_quantity}]")


class CampaignUpdateRequest(BaseModel):
    """更新战役请求"""
    campaign_name: Optional[str] = None
    campaign_type: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    target_amount: Optional[float] = Field(None, ge=0)
    target_quantity: Optional[int] = Field(None, ge=0)
    status: Optional[str] = None
    description: Optional[str] = None


class CampaignShopRequest(BaseModel):
    """添加参与店铺请求"""
    platform_code: str
    shop_id: str
    target_amount: float = Field(0.0, ge=0)
    target_quantity: int = Field(0, ge=0)


class CampaignResponse(BaseModel):
    """战役响应"""
    id: int
    campaign_name: str
    campaign_type: str
    start_date: date
    end_date: date
    target_amount: float
    target_quantity: int
    actual_amount: float
    actual_quantity: int
    achievement_rate: float
    status: str
    description: Optional[str]
    created_by: Optional[str]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class CampaignShopResponse(BaseModel):
    """战役店铺响应"""
    id: int
    campaign_id: int
    platform_code: Optional[str]
    shop_id: Optional[str]
    shop_name: Optional[str] = None
    target_amount: float
    target_quantity: int
    actual_amount: float
    actual_quantity: int
    achievement_rate: float
    rank: Optional[int]
    
    class Config:
        from_attributes = True


# ==================== API Endpoints ====================

@router.get("", response_model=Dict[str, Any])
async def list_campaigns(
    status: Optional[str] = Query(None, description="状态筛选：active/completed/pending/cancelled"),
    campaign_type: Optional[str] = Query(None, description="战役类型筛选"),
    start_date: Optional[date] = Query(None, description="开始日期筛选（>=）"),
    end_date: Optional[date] = Query(None, description="结束日期筛选（<=）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    查询战役列表
    
    支持筛选：状态、类型、日期范围
    支持分页
    """
    try:
        query = select(SalesCampaign)
        
        # 筛选条件
        if status:
            query = query.where(SalesCampaign.status == status)
        if campaign_type:
            query = query.where(SalesCampaign.campaign_type == campaign_type)
        if start_date:
            query = query.where(SalesCampaign.start_date >= start_date)
        if end_date:
            query = query.where(SalesCampaign.end_date <= end_date)
        
        # 总数查询
        total_query = select(func.count()).select_from(query.subquery())
        result = await db.execute(total_query)
        total = result.scalar() or 0
        
        # 分页查询
        query = query.order_by(SalesCampaign.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        
        result = await db.execute(query)
        campaigns = result.scalars().all()
        
        return pagination_response(
            data=[CampaignResponse.from_orm(c).dict() for c in campaigns],
            page=page,
            page_size=page_size,
            total=total
        )
    except Exception as e:
        logger.error(f"查询战役列表失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="查询失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )


@router.get("/{campaign_id}", response_model=Dict[str, Any])
async def get_campaign(
    campaign_id: int,
    db: AsyncSession = Depends(get_async_db)
):
    """
    查询战役详情
    
    包含战役基本信息和参与店铺列表
    """
    try:
        # 查询战役
        result = await db.execute(
            select(SalesCampaign).where(SalesCampaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()
        
        if not campaign:
            return error_response(
                code=ErrorCode.SALES_CAMPAIGN_NOT_FOUND,
                message="战役不存在",
                error_type=get_error_type(ErrorCode.SALES_CAMPAIGN_NOT_FOUND),
                recovery_suggestion="请检查战役ID是否正确，或确认该战役已创建",
                status_code=404
            )
        
        # 查询参与店铺
        shops_query = select(SalesCampaignShop).where(
            SalesCampaignShop.campaign_id == campaign_id
        ).order_by(SalesCampaignShop.rank.asc().nullslast())
        
        shops = db.execute(shops_query).scalars().all()
        
        # 获取店铺名称
        shop_responses = []
        for shop in shops:
            shop_data = CampaignShopResponse.from_orm(shop).dict()
            if shop.platform_code and shop.shop_id:
                dim_shop = db.execute(
                    select(DimShop).where(
                        DimShop.platform_code == shop.platform_code,
                        DimShop.shop_id == shop.shop_id
                    )
                ).scalar_one_or_none()
                if dim_shop:
                    shop_data["shop_name"] = dim_shop.shop_name
            shop_responses.append(shop_data)
        
        return {
            "success": True,
            "data": {
                "campaign": CampaignResponse.from_orm(campaign).dict(),
                "shops": shop_responses
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询战役详情失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="查询战役详情失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和查询参数，或联系系统管理员",
            status_code=500
        )


@router.post("", response_model=Dict[str, Any])
async def create_campaign(
    request: CampaignCreateRequest,
    db: AsyncSession = Depends(get_async_db),
    created_by: str = "admin"  # TODO: 从认证中获取当前用户
):
    """
    创建战役
    
    可以同时指定参与店铺
    """
    try:
        # 验证日期
        if request.end_date < request.start_date:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="结束日期必须大于等于开始日期",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="请调整日期范围，确保结束日期大于等于开始日期",
                status_code=400
            )
        
        # 创建战役
        campaign = SalesCampaign(
            campaign_name=request.campaign_name,
            campaign_type=request.campaign_type,
            start_date=request.start_date,
            end_date=request.end_date,
            target_amount=request.target_amount,
            target_quantity=request.target_quantity,
            description=request.description,
            created_by=created_by,
            status="pending"
        )
        
        db.add(campaign)
        db.flush()  # 获取campaign.id
        
        # 添加参与店铺
        if request.shop_ids:
            for shop_info in request.shop_ids:
                campaign_shop = SalesCampaignShop(
                    campaign_id=campaign.id,
                    platform_code=shop_info.get("platform_code"),
                    shop_id=shop_info.get("shop_id"),
                    target_amount=shop_info.get("target_amount", 0.0),
                    target_quantity=shop_info.get("target_quantity", 0)
                )
                db.add(campaign_shop)
        
        await db.commit()
        await db.refresh(campaign)
        
        # 触发A_CLASS_UPDATED事件（数据流转流程自动化）
        try:
            from backend.utils.events import AClassUpdatedEvent
            from backend.services.event_listeners import event_listener
            
            # 获取受影响的店铺和平台
            shops = db.execute(
                select(SalesCampaignShop).where(SalesCampaignShop.campaign_id == campaign.id)
            ).scalars().all()
            affected_shops = [shop.shop_id for shop in shops if shop.shop_id]
            affected_platforms = list(set([shop.platform_code for shop in shops if shop.platform_code]))
            
            event = AClassUpdatedEvent(
                data_type="sales_campaign",
                record_id=campaign.id,
                action="create",
                affected_shops=affected_shops if affected_shops else None,
                affected_platforms=affected_platforms if affected_platforms else None
            )
            event_listener.handle_a_class_updated(event)
            logger.info(f"[SalesCampaign] 已触发A_CLASS_UPDATED事件: campaign_id={campaign.id}, action=create")
        except Exception as event_err:
            # 事件触发失败不影响主流程
            logger.warning(f"[SalesCampaign] 触发A_CLASS_UPDATED事件失败: {event_err}")
        
        return {
            "success": True,
            "data": CampaignResponse.from_orm(campaign).dict(),
            "message": "战役创建成功"
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"创建战役失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="创建战役失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限，或联系系统管理员",
            status_code=500
        )


@router.put("/{campaign_id}", response_model=Dict[str, Any])
async def update_campaign(
    campaign_id: int,
    request: CampaignUpdateRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """
    更新战役
    
    只更新提供的字段
    """
    try:
        result = await db.execute(
            select(SalesCampaign).where(SalesCampaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()
        
        if not campaign:
            return error_response(
                code=ErrorCode.SALES_CAMPAIGN_NOT_FOUND,
                message="战役不存在",
                error_type=get_error_type(ErrorCode.SALES_CAMPAIGN_NOT_FOUND),
                recovery_suggestion="请检查战役ID是否正确，或确认该战役已创建",
                status_code=404
            )
        
        # 更新字段
        update_data = request.dict(exclude_unset=True)
        
        # 验证日期
        if "start_date" in update_data or "end_date" in update_data:
            start_date = update_data.get("start_date", campaign.start_date)
            end_date = update_data.get("end_date", campaign.end_date)
            if end_date < start_date:
                return error_response(
                    code=ErrorCode.DATA_VALIDATION_FAILED,
                    message="结束日期必须大于等于开始日期",
                    error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                    recovery_suggestion="请调整日期范围，确保结束日期大于等于开始日期",
                    status_code=400
                )
        
        for key, value in update_data.items():
            setattr(campaign, key, value)
        
        campaign.updated_at = datetime.utcnow()
        
        await db.commit()
        await db.refresh(campaign)
        
        # 触发A_CLASS_UPDATED事件（数据流转流程自动化）
        try:
            from backend.utils.events import AClassUpdatedEvent
            from backend.services.event_listeners import event_listener
            
            # 获取受影响的店铺和平台
            shops = db.execute(
                select(SalesCampaignShop).where(SalesCampaignShop.campaign_id == campaign_id)
            ).scalars().all()
            affected_shops = [shop.shop_id for shop in shops if shop.shop_id]
            affected_platforms = list(set([shop.platform_code for shop in shops if shop.platform_code]))
            
            event = AClassUpdatedEvent(
                data_type="sales_campaign",
                record_id=campaign_id,
                action="update",
                affected_shops=affected_shops if affected_shops else None,
                affected_platforms=affected_platforms if affected_platforms else None
            )
            event_listener.handle_a_class_updated(event)
            logger.info(f"[SalesCampaign] 已触发A_CLASS_UPDATED事件: campaign_id={campaign_id}, action=update")
        except Exception as event_err:
            # 事件触发失败不影响主流程
            logger.warning(f"[SalesCampaign] 触发A_CLASS_UPDATED事件失败: {event_err}")
        
        return {
            "success": True,
            "data": CampaignResponse.from_orm(campaign).dict(),
            "message": "战役更新成功"
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"更新战役失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="更新战役失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限，或联系系统管理员",
            status_code=500
        )


@router.delete("/{campaign_id}", response_model=Dict[str, Any])
async def delete_campaign(
    campaign_id: int,
    db: AsyncSession = Depends(get_async_db)
):
    """
    删除战役
    
    同时删除关联的参与店铺记录（CASCADE）
    """
    try:
        result = await db.execute(
            select(SalesCampaign).where(SalesCampaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()
        
        if not campaign:
            return error_response(
                code=ErrorCode.SALES_CAMPAIGN_NOT_FOUND,
                message="战役不存在",
                error_type=get_error_type(ErrorCode.SALES_CAMPAIGN_NOT_FOUND),
                recovery_suggestion="请检查战役ID是否正确，或确认该战役已创建",
                status_code=404
            )
        
        # 获取受影响的店铺和平台（删除前）
        shops = db.execute(
            select(SalesCampaignShop).where(SalesCampaignShop.campaign_id == campaign_id)
        ).scalars().all()
        affected_shops = [shop.shop_id for shop in shops if shop.shop_id]
        affected_platforms = list(set([shop.platform_code for shop in shops if shop.platform_code]))
        
        await db.delete(campaign)
        await db.commit()
        
        # 触发A_CLASS_UPDATED事件（数据流转流程自动化）
        try:
            from backend.utils.events import AClassUpdatedEvent
            from backend.services.event_listeners import event_listener
            
            event = AClassUpdatedEvent(
                data_type="sales_campaign",
                record_id=campaign_id,
                action="delete",
                affected_shops=affected_shops if affected_shops else None,
                affected_platforms=affected_platforms if affected_platforms else None
            )
            event_listener.handle_a_class_updated(event)
            logger.info(f"[SalesCampaign] 已触发A_CLASS_UPDATED事件: campaign_id={campaign_id}, action=delete")
        except Exception as event_err:
            # 事件触发失败不影响主流程
            logger.warning(f"[SalesCampaign] 触发A_CLASS_UPDATED事件失败: {event_err}")
        
        return {
            "success": True,
            "message": "战役删除成功"
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"删除战役失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="删除战役失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限，或联系系统管理员",
            status_code=500
        )


@router.post("/{campaign_id}/shops", response_model=Dict[str, Any])
async def add_campaign_shop(
    campaign_id: int,
    request: CampaignShopRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """
    添加参与店铺
    
    验证店铺是否存在
    """
    try:
        # 验证战役存在
        result = await db.execute(
            select(SalesCampaign).where(SalesCampaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()
        
        if not campaign:
            return error_response(
                code=ErrorCode.SALES_CAMPAIGN_NOT_FOUND,
                message="战役不存在",
                error_type=get_error_type(ErrorCode.SALES_CAMPAIGN_NOT_FOUND),
                recovery_suggestion="请检查战役ID是否正确，或确认该战役已创建",
                status_code=404
            )
        
        # 验证店铺存在
        shop = db.execute(
            select(DimShop).where(
                DimShop.platform_code == request.platform_code,
                DimShop.shop_id == request.shop_id
            )
        ).scalar_one_or_none()
        
        if not shop:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="店铺不存在",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="请检查店铺ID是否正确，或确认该店铺已创建",
                status_code=404
            )
        
        # 检查是否已添加
        existing = db.execute(
            select(SalesCampaignShop).where(
                SalesCampaignShop.campaign_id == campaign_id,
                SalesCampaignShop.platform_code == request.platform_code,
                SalesCampaignShop.shop_id == request.shop_id
            )
        ).scalar_one_or_none()
        
        if existing:
            return error_response(
                code=ErrorCode.DATA_UNIQUE_CONSTRAINT_VIOLATION,
                message="店铺已参与该战役",
                error_type=get_error_type(ErrorCode.DATA_UNIQUE_CONSTRAINT_VIOLATION),
                recovery_suggestion="该店铺已参与此战役，无需重复添加",
                status_code=400
            )
        
        # 添加店铺
        campaign_shop = SalesCampaignShop(
            campaign_id=campaign_id,
            platform_code=request.platform_code,
            shop_id=request.shop_id,
            target_amount=request.target_amount,
            target_quantity=request.target_quantity
        )
        
        db.add(campaign_shop)
        await db.commit()
        await db.refresh(campaign_shop)
        
        shop_data = CampaignShopResponse.from_orm(campaign_shop).dict()
        shop_data["shop_name"] = shop.shop_name
        
        return {
            "success": True,
            "data": shop_data,
            "message": "店铺添加成功"
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"添加店铺失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="添加店铺失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限，或联系系统管理员",
            status_code=500
        )


@router.delete("/{campaign_id}/shops/{shop_id}", response_model=Dict[str, Any])
async def remove_campaign_shop(
    campaign_id: int,
    shop_id: str,
    platform_code: str = Query(..., description="平台代码"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    移除参与店铺
    """
    try:
        campaign_shop = db.execute(
            select(SalesCampaignShop).where(
                SalesCampaignShop.campaign_id == campaign_id,
                SalesCampaignShop.platform_code == platform_code,
                SalesCampaignShop.shop_id == shop_id
            )
        ).scalar_one_or_none()
        
        if not campaign_shop:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="店铺未参与该战役",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="请检查店铺ID是否正确，或确认该店铺已参与此战役",
                status_code=404
            )
        
        await db.delete(campaign_shop)
        await db.commit()
        
        return {
            "success": True,
            "message": "店铺移除成功"
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"移除店铺失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="移除店铺失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限，或联系系统管理员",
            status_code=500
        )


@router.post("/{campaign_id}/calculate", response_model=Dict[str, Any])
async def calculate_campaign_achievement(
    campaign_id: int,
    db: AsyncSession = Depends(get_async_db)
):
    """
    计算战役达成情况（C类数据：系统自动计算）
    
    从fact_orders表聚合计算实际销售额和订单数
    更新战役和参与店铺的达成数据
    """
    try:
        from backend.services.sales_campaign_service import SalesCampaignService
        
        service = SalesCampaignService(db)
        result = service.calculate_campaign_achievement(campaign_id)
        
        return {
            "success": True,
            "data": CampaignResponse.from_orm(result["campaign"]).dict(),
            "message": "达成情况计算完成"
        }
    except ValueError as e:
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message=str(e),
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            recovery_suggestion="请检查战役ID是否正确，或确认该战役已创建",
            status_code=404
        )
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"计算达成情况失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="计算达成情况失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和查询参数，或联系系统管理员",
            status_code=500
        )

