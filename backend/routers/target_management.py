#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
目标管理API(v4.11.0新增)

功能:
1. 目标CRUD(创建、查询、更新、删除)
2. 目标分解(按店铺/按时间)
3. 目标达成情况查询(自动计算)
4. 目标列表查询(分页、筛选)

路由:
- GET /api/targets - 查询目标列表
- GET /api/targets/{target_id} - 查询目标详情
- POST /api/targets - 创建目标
- PUT /api/targets/{target_id} - 更新目标
- DELETE /api/targets/{target_id} - 删除目标
- POST /api/targets/{target_id}/breakdown - 创建目标分解
- GET /api/targets/{target_id}/breakdown - 查询目标分解列表
- POST /api/targets/{target_id}/calculate - 计算达成情况
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import date, datetime

from backend.models.database import get_db, get_async_db
from backend.utils.api_response import success_response, error_response
from backend.utils.error_codes import ErrorCode, get_error_type
from modules.core.db import (
    SalesTarget,
    TargetBreakdown,
    # [DELETED] v4.19.0: FactOrder 已删除,使用 b_class.fact_{platform}_orders_{granularity} 替代
    DimShop,
    DimUser,  # ✅ 2026-01-08: 添加用户模型用于权限检查
    PlatformAccount,  # 目标管理用店铺列表:来自账号管理 core.platform_accounts
)
from backend.services.shop_sync_service import sync_platform_account_to_dim_shop
from modules.core.logger import get_logger
from backend.routers.auth import get_current_user  # ✅ 2026-01-08: 添加用户认证

logger = get_logger(__name__)
router = APIRouter(prefix="/targets", tags=["目标管理"])

# ✅ 2026-01-08: 添加管理员权限检查
async def require_admin(current_user: DimUser = Depends(get_current_user)):
    """要求管理员权限"""
    # 优先检查 is_superuser 标志
    if current_user.is_superuser:
        return current_user
    
    # 检查角色(使用 role_code 或 role_name)
    is_admin = any(
        (hasattr(role, "role_code") and role.role_code == "admin") or
        (hasattr(role, "role_name") and role.role_name == "admin")
        for role in current_user.roles
    )
    
    if not is_admin:
        raise HTTPException(
            status_code=403,
            detail="Insufficient permissions: Admin access required"
        )
    return current_user


# ==================== Request/Response Models ====================

class TargetCreateRequest(BaseModel):
    """创建目标请求"""
    target_name: str = Field(..., description="目标名称")
    target_type: str = Field(..., description="目标类型:shop/product/campaign")
    period_start: date = Field(..., description="开始时间")
    period_end: date = Field(..., description="结束时间")
    target_amount: float = Field(0.0, ge=0, description="目标销售额(CNY)")
    target_quantity: int = Field(0, ge=0, description="目标订单数/销量")
    description: Optional[str] = Field(None, description="目标描述")


class TargetUpdateRequest(BaseModel):
    """更新目标请求"""
    target_name: Optional[str] = None
    target_type: Optional[str] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    target_amount: Optional[float] = Field(None, ge=0)
    target_quantity: Optional[int] = Field(None, ge=0)
    status: Optional[str] = None
    description: Optional[str] = None


class BreakdownCreateRequest(BaseModel):
    """创建目标分解请求"""
    breakdown_type: str = Field(..., description="分解类型:shop/time")
    # 店铺分解字段
    platform_code: Optional[str] = None
    shop_id: Optional[str] = None
    # 时间分解字段
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    period_label: Optional[str] = None
    # 目标值
    target_amount: float = Field(0.0, ge=0)
    target_quantity: int = Field(0, ge=0)


class TargetResponse(BaseModel):
    """目标响应"""
    id: int
    target_name: str
    target_type: str
    period_start: date
    period_end: date
    target_amount: float
    target_quantity: int
    achieved_amount: float
    achieved_quantity: int
    achievement_rate: float
    status: str
    description: Optional[str]
    created_by: Optional[str]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class BreakdownResponse(BaseModel):
    """目标分解响应"""
    id: int
    target_id: int
    breakdown_type: str
    platform_code: Optional[str]
    shop_id: Optional[str]
    shop_name: Optional[str] = None
    period_start: Optional[date]
    period_end: Optional[date]
    period_label: Optional[str]
    target_amount: float
    target_quantity: int
    achieved_amount: float
    achieved_quantity: int
    achievement_rate: float
    
    class Config:
        from_attributes = True


# ==================== API Endpoints ====================

@router.get("", response_model=Dict[str, Any])
async def list_targets(
    target_type: Optional[str] = Query(None, description="目标类型筛选:shop/product/campaign"),
    status: Optional[str] = Query(None, description="状态筛选:active/completed/cancelled"),
    period_start: Optional[date] = Query(None, description="开始日期筛选(>=)"),
    period_end: Optional[date] = Query(None, description="结束日期筛选(<=)"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_async_db),
    current_user: DimUser = Depends(get_current_user),  # 列表仅需登录可访问
):
    """
    查询目标列表
    
    支持筛选:类型、状态、日期范围
    支持分页
    """
    try:
        query = select(SalesTarget)
        
        # 筛选条件(与下面 count 查询保持一致)
        if target_type:
            query = query.where(SalesTarget.target_type == target_type)
        if status:
            query = query.where(SalesTarget.status == status)
        if period_start:
            query = query.where(SalesTarget.period_start >= period_start)
        if period_end:
            query = query.where(SalesTarget.period_end <= period_end)
        
        # 总数查询:使用独立 count 避免子查询在部分驱动下的兼容性问题
        count_query = select(func.count(SalesTarget.id)).select_from(SalesTarget)
        if target_type:
            count_query = count_query.where(SalesTarget.target_type == target_type)
        if status:
            count_query = count_query.where(SalesTarget.status == status)
        if period_start:
            count_query = count_query.where(SalesTarget.period_start >= period_start)
        if period_end:
            count_query = count_query.where(SalesTarget.period_end <= period_end)
        total = (await db.execute(count_query)).scalar() or 0
        
        # 分页查询
        query = query.order_by(SalesTarget.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        
        targets = (await db.execute(query)).scalars().all()
        
        # 使用 mode='json' 确保日期/时间/Decimal 可序列化,避免 500
        items = [TargetResponse.model_validate(t).model_dump(mode="json") for t in targets]
        
        # 返回 items + total,便于前端在拦截器只返回 data 时仍能拿到分页信息
        return {
            "success": True,
            "data": {
                "items": items,
                "total": total,
                "page": page,
                "page_size": page_size,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询目标列表失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="查询失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )


@router.get("/shops", response_model=Dict[str, Any])
async def list_target_shops(
    db: AsyncSession = Depends(get_async_db),
    current_user: DimUser = Depends(get_current_user),
):
    """
    获取供目标管理使用的店铺列表(来自账号管理 core.platform_accounts)。

    返回字段与分解接口一致:platform_code、shop_id、shop_name。
    创建按店铺分解时,若后端校验 DimShop,需保证该店铺已在 dim_shops 中存在或由同步写入。
    """
    try:
        query = (
            select(PlatformAccount)
            .where(PlatformAccount.enabled == True)
            .order_by(PlatformAccount.platform, PlatformAccount.store_name)
        )
        rows = (await db.execute(query)).scalars().all()
        items = [
            {
                "platform_code": r.platform.lower() if r.platform else None,  # ✅ 统一转小写,与 dim_shops 一致
                "shop_id": r.shop_id or r.account_id or str(r.id),
                "shop_name": r.store_name or (r.account_alias or ""),
            }
            for r in rows
        ]
        return {"success": True, "data": items}
    except Exception as e:
        logger.error(f"查询目标用店铺列表失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="查询店铺列表失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500,
        )


@router.get("/{target_id}", response_model=Dict[str, Any])
async def get_target(
    target_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: DimUser = Depends(get_current_user),  # 详情仅需登录可访问
):
    """
    查询目标详情
    
    包含目标基本信息和分解列表
    """
    try:
        # 查询目标
        target = (await db.execute(
            select(SalesTarget).where(SalesTarget.id == target_id)
        )).scalar_one_or_none()
        
        if not target:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="目标不存在",
                error_type=get_error_type(ErrorCode.TARGET_NOT_FOUND),
                recovery_suggestion="请检查目标ID是否正确,或确认该目标已创建",
                status_code=404
            )
        
        # 查询分解列表
        breakdowns_query = select(TargetBreakdown).where(
            TargetBreakdown.target_id == target_id
        )
        
        breakdowns = (await db.execute(breakdowns_query)).scalars().all()
        
        # 获取店铺名称
        breakdown_responses = []
        for breakdown in breakdowns:
            breakdown_data = BreakdownResponse.model_validate(breakdown).model_dump()
            if breakdown.breakdown_type == "shop" and breakdown.platform_code and breakdown.shop_id:
                dim_shop = (await db.execute(
                    select(DimShop).where(
                        DimShop.platform_code == breakdown.platform_code,
                        DimShop.shop_id == breakdown.shop_id
                    )
                )).scalar_one_or_none()
                if dim_shop:
                    breakdown_data["shop_name"] = dim_shop.shop_name
            breakdown_responses.append(breakdown_data)
        
        return {
            "success": True,
            "data": {
                "target": TargetResponse.model_validate(target).model_dump(),
                "breakdowns": breakdown_responses
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询目标详情失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="查询目标详情失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和查询参数,或联系系统管理员",
            status_code=500
        )


@router.post("", response_model=Dict[str, Any])
async def create_target(
    request: TargetCreateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: DimUser = Depends(require_admin),  # ✅ 2026-01-08: 仅管理员可访问
    created_by: str = None  # ✅ 2026-01-08: 从current_user获取
):
    """
    创建目标
    """
    try:
        # 验证日期
        if request.period_end < request.period_start:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="结束日期必须大于等于开始日期",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="请调整日期范围,确保结束日期大于等于开始日期",
                status_code=400
            )
        
        # 创建目标
        target = SalesTarget(
            target_name=request.target_name,
            target_type=request.target_type,
            period_start=request.period_start,
            period_end=request.period_end,
            target_amount=request.target_amount,
            target_quantity=request.target_quantity,
            description=request.description,
            created_by=current_user.username if current_user else "admin",  # ✅ 2026-01-08: 从current_user获取
            status="active"
        )
        
        db.add(target)
        await db.commit()
        await db.refresh(target)
        
        # 触发A_CLASS_UPDATED事件(数据流转流程自动化)
        try:
            from backend.utils.events import AClassUpdatedEvent
            from backend.services.event_listeners import event_listener
            
            # 获取受影响的店铺和平台(从分解中获取)
            breakdowns = (await db.execute(
                select(TargetBreakdown).where(TargetBreakdown.target_id == target.id)
            )).scalars().all()
            affected_shops = [bd.shop_id for bd in breakdowns if bd.shop_id]
            affected_platforms = list(set([bd.platform_code for bd in breakdowns if bd.platform_code]))
            
            event = AClassUpdatedEvent(
                data_type="target",
                record_id=target.id,
                action="create",
                affected_shops=affected_shops if affected_shops else None,
                affected_platforms=affected_platforms if affected_platforms else None
            )
            event_listener.handle_a_class_updated(event)
            logger.info(f"[TargetManagement] 已触发A_CLASS_UPDATED事件: target_id={target.id}, action=create")
        except Exception as event_err:
            # 事件触发失败不影响主流程
            logger.warning(f"[TargetManagement] 触发A_CLASS_UPDATED事件失败: {event_err}")
        
        return {
            "success": True,
            "data": TargetResponse.model_validate(target).model_dump(),
            "message": "目标创建成功"
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"创建目标失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="创建目标失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限,或联系系统管理员",
            status_code=500
        )


@router.put("/{target_id}", response_model=Dict[str, Any])
async def update_target(
    target_id: int,
    request: TargetUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: DimUser = Depends(require_admin)  # ✅ 2026-01-08: 仅管理员可访问
):
    """
    更新目标
    
    只更新提供的字段
    """
    try:
        target = (await db.execute(
            select(SalesTarget).where(SalesTarget.id == target_id)
        )).scalar_one_or_none()
        
        if not target:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="目标不存在",
                error_type=get_error_type(ErrorCode.TARGET_NOT_FOUND),
                recovery_suggestion="请检查目标ID是否正确,或确认该目标已创建",
                status_code=404
            )
        
        # 更新字段
        update_data = request.dict(exclude_unset=True)
        
        # 验证日期
        if "period_start" in update_data or "period_end" in update_data:
            period_start = update_data.get("period_start", target.period_start)
            period_end = update_data.get("period_end", target.period_end)
            if period_end < period_start:
                return error_response(
                    code=ErrorCode.DATA_VALIDATION_FAILED,
                    message="结束日期必须大于等于开始日期",
                    error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                    recovery_suggestion="请调整日期范围,确保结束日期大于等于开始日期",
                    status_code=400
                )
        
        for key, value in update_data.items():
            setattr(target, key, value)
        
        target.updated_at = datetime.utcnow()
        
        await db.commit()
        await db.refresh(target)
        
        # [*] v4.21.0: 更新目标后，重新同步到 a_class.sales_targets_a（如果有店铺分解）
        try:
            from backend.services.target_sync_service import sync_target_after_create
            sync_result = await sync_target_after_create(db, target_id)
            if sync_result.get("synced", 0) > 0:
                logger.info(f"[TargetManagement] 更新后已同步到a_class: {sync_result['synced']}条记录")
            elif sync_result.get("skipped", 0) > 0:
                logger.debug(f"[TargetManagement] 目标无店铺分解，跳过同步")
            if sync_result.get("errors"):
                logger.warning(f"[TargetManagement] 同步部分失败: {sync_result['errors']}")
        except Exception as sync_err:
            # 同步失败不影响主流程
            logger.warning(f"[TargetManagement] 更新后同步到a_class失败: {sync_err}")
        
        # 触发A_CLASS_UPDATED事件(数据流转流程自动化)
        try:
            from backend.utils.events import AClassUpdatedEvent
            from backend.services.event_listeners import event_listener
            
            # 获取受影响的店铺和平台(从分解中获取)
            breakdowns = (await db.execute(
                select(TargetBreakdown).where(TargetBreakdown.target_id == target_id)
            )).scalars().all()
            affected_shops = [bd.shop_id for bd in breakdowns if bd.shop_id]
            affected_platforms = list(set([bd.platform_code for bd in breakdowns if bd.platform_code]))
            
            event = AClassUpdatedEvent(
                data_type="target",
                record_id=target_id,
                action="update",
                affected_shops=affected_shops if affected_shops else None,
                affected_platforms=affected_platforms if affected_platforms else None
            )
            event_listener.handle_a_class_updated(event)
            logger.info(f"[TargetManagement] 已触发A_CLASS_UPDATED事件: target_id={target_id}, action=update")
        except Exception as event_err:
            # 事件触发失败不影响主流程
            logger.warning(f"[TargetManagement] 触发A_CLASS_UPDATED事件失败: {event_err}")
        
        return {
            "success": True,
            "data": TargetResponse.model_validate(target).model_dump(),
            "message": "目标更新成功"
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"更新目标失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="更新目标失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限,或联系系统管理员",
            status_code=500
        )


@router.delete("/{target_id}", response_model=Dict[str, Any])
async def delete_target(
    target_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: DimUser = Depends(require_admin)  # ✅ 2026-01-08: 仅管理员可访问
):
    """
    删除目标
    
    同时删除关联的分解记录(CASCADE)
    """
    try:
        target = (await db.execute(
            select(SalesTarget).where(SalesTarget.id == target_id)
        )).scalar_one_or_none()
        
        if not target:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="目标不存在",
                error_type=get_error_type(ErrorCode.TARGET_NOT_FOUND),
                recovery_suggestion="请检查目标ID是否正确,或确认该目标已创建",
                status_code=404
            )
        
        # 获取受影响的店铺和平台(删除前)
        breakdowns = (await db.execute(
            select(TargetBreakdown).where(TargetBreakdown.target_id == target_id)
        )).scalars().all()
        affected_shops = [bd.shop_id for bd in breakdowns if bd.shop_id]
        affected_platforms = list(set([bd.platform_code for bd in breakdowns if bd.platform_code]))
        
        # [*] v4.21.0: 删除前清理 a_class.sales_targets_a 中的数据
        try:
            from backend.services.target_sync_service import sync_target_after_delete
            delete_result = await sync_target_after_delete(db, target_id)
            if delete_result.get("deleted", 0) > 0:
                logger.info(f"[TargetManagement] 已从a_class清理: {delete_result['deleted']}条记录")
        except Exception as sync_err:
            # 清理失败不影响主流程
            logger.warning(f"[TargetManagement] 清理a_class失败: {sync_err}")
        
        await db.delete(target)
        await db.commit()
        
        # 触发A_CLASS_UPDATED事件(数据流转流程自动化)
        try:
            from backend.utils.events import AClassUpdatedEvent
            from backend.services.event_listeners import event_listener
            
            event = AClassUpdatedEvent(
                data_type="target",
                record_id=target_id,
                action="delete",
                affected_shops=affected_shops if affected_shops else None,
                affected_platforms=affected_platforms if affected_platforms else None
            )
            event_listener.handle_a_class_updated(event)
            logger.info(f"[TargetManagement] 已触发A_CLASS_UPDATED事件: target_id={target_id}, action=delete")
        except Exception as event_err:
            # 事件触发失败不影响主流程
            logger.warning(f"[TargetManagement] 触发A_CLASS_UPDATED事件失败: {event_err}")
        
        return {
            "success": True,
            "message": "目标删除成功"
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"删除目标失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="删除目标失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限,或联系系统管理员",
            status_code=500
        )


@router.post("/{target_id}/breakdown", response_model=Dict[str, Any])
async def create_breakdown(
    target_id: int,
    request: BreakdownCreateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: DimUser = Depends(require_admin)  # ✅ 2026-01-08: 仅管理员可访问
):
    """
    创建目标分解
    
    支持两种分解类型:
    1. shop:按店铺分解(需要platform_code和shop_id)
    2. time:按时间分解(需要period_start和period_end)
    """
    try:
        # 验证目标存在
        target = (await db.execute(
            select(SalesTarget).where(SalesTarget.id == target_id)
        )).scalar_one_or_none()
        
        if not target:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="目标不存在",
                error_type=get_error_type(ErrorCode.TARGET_NOT_FOUND),
                recovery_suggestion="请检查目标ID是否正确,或确认该目标已创建",
                status_code=404
            )
        
        # ✅ 统一 platform_code 为小写(与 dim_shops 标准格式一致)
        normalized_platform_code = request.platform_code.lower() if request.platform_code else None
        
        # 验证分解类型
        if request.breakdown_type == "shop":
            if not request.platform_code or not request.shop_id:
                return error_response(
                    code=ErrorCode.DATA_REQUIRED_FIELD_MISSING,
                    message="店铺分解需要platform_code和shop_id",
                    error_type=get_error_type(ErrorCode.DATA_REQUIRED_FIELD_MISSING),
                    recovery_suggestion="请提供platform_code和shop_id参数",
                    status_code=400
                )
            
            # 验证店铺存在:优先 DimShop,其次允许来自账号管理 core.platform_accounts
            shop = (await db.execute(
                select(DimShop).where(
                    DimShop.platform_code == normalized_platform_code,
                    DimShop.shop_id == request.shop_id
                )
            )).scalar_one_or_none()
            if not shop:
                # ✅ 查询 platform_accounts 时也使用小写比较(platform 字段可能大小写不一致)
                pa = (await db.execute(
                    select(PlatformAccount).where(
                        func.lower(PlatformAccount.platform) == normalized_platform_code,
                        PlatformAccount.enabled == True,
                        or_(
                            PlatformAccount.shop_id == request.shop_id,
                            PlatformAccount.account_id == request.shop_id,
                        ),
                    )
                )).scalar_one_or_none()
                if not pa:
                    return error_response(
                        code=ErrorCode.DATA_VALIDATION_FAILED,
                        message="店铺不存在",
                        error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                        recovery_suggestion="请从目标管理使用的店铺列表中选择,或先在账号管理中维护该店铺",
                        status_code=404
                    )
                
                # ✅ 自动同步店铺到 dim_shops
                try:
                    shop = await sync_platform_account_to_dim_shop(db, pa)
                    if not shop:
                        return error_response(
                            code=ErrorCode.DATA_VALIDATION_FAILED,
                            message="无法确定店铺ID",
                            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                            recovery_suggestion="请在账号管理中设置 shop_id 字段",
                            status_code=400
                        )
                    logger.info(f"[TargetManagement] 自动创建店铺记录: {pa.platform}/{shop.shop_id}")
                except Exception as e:
                    await db.rollback()
                    logger.error(f"[TargetManagement] 同步店铺失败: {e}", exc_info=True)
                    return error_response(
                        code=ErrorCode.DATABASE_QUERY_ERROR,
                        message="创建店铺记录失败",
                        error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
                        detail=str(e),
                        recovery_suggestion="请检查数据库连接和权限,或联系系统管理员",
                        status_code=500
                    )
            
            # 检查是否已存在(使用标准化后的 platform_code)
            existing = (await db.execute(
                select(TargetBreakdown).where(
                    TargetBreakdown.target_id == target_id,
                    TargetBreakdown.breakdown_type == "shop",
                    TargetBreakdown.platform_code == normalized_platform_code,
                    TargetBreakdown.shop_id == request.shop_id
                )
            )).scalar_one_or_none()
            
            if existing:
                # [*] v4.21.0: Upsert 逻辑 - 如果分解已存在，则更新而非报错
                existing.target_amount = request.target_amount
                existing.target_quantity = request.target_quantity
                existing.updated_at = datetime.utcnow()
                
                await db.commit()
                await db.refresh(existing)
                
                # 同步到 a_class.sales_targets_a
                try:
                    from backend.services.target_sync_service import sync_target_after_create
                    sync_result = await sync_target_after_create(db, target_id)
                    if sync_result.get("synced", 0) > 0:
                        logger.info(f"[TargetManagement] 更新分解后已同步到a_class: {sync_result['synced']}条记录")
                except Exception as sync_err:
                    logger.warning(f"[TargetManagement] 更新分解后同步到a_class失败: {sync_err}")
                
                breakdown_data = BreakdownResponse.model_validate(existing).model_dump()
                # 查询店铺名称
                shop = (await db.execute(
                    select(DimShop).where(
                        DimShop.platform_code == normalized_platform_code,
                        DimShop.shop_id == request.shop_id
                    )
                )).scalar_one_or_none()
                if shop:
                    breakdown_data["shop_name"] = shop.shop_name
                
                return {
                    "success": True,
                    "data": breakdown_data,
                    "message": "店铺分解更新成功"
                }
        
        elif request.breakdown_type == "time":
            if not request.period_start or not request.period_end:
                return error_response(
                    code=ErrorCode.DATA_REQUIRED_FIELD_MISSING,
                    message="时间分解需要period_start和period_end",
                    error_type=get_error_type(ErrorCode.DATA_REQUIRED_FIELD_MISSING),
                    recovery_suggestion="请提供period_start和period_end参数",
                    status_code=400
                )
            
            if request.period_end < request.period_start:
                return error_response(
                    code=ErrorCode.DATA_VALIDATION_FAILED,
                    message="结束日期必须大于等于开始日期",
                    error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                    recovery_suggestion="请调整日期范围,确保结束日期大于等于开始日期",
                    status_code=400
                )
            
            # 检查是否与目标周期重叠
            if request.period_start < target.period_start or request.period_end > target.period_end:
                return error_response(
                    code=ErrorCode.DATA_VALIDATION_FAILED,
                    message="分解周期必须在目标周期范围内",
                    error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                    recovery_suggestion="请调整分解周期,确保在目标周期范围内",
                    status_code=400
                )
        
        else:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="分解类型必须是shop或time",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="请选择shop或time作为分解类型",
                status_code=400
            )
        
        # 创建分解(使用标准化后的 platform_code)
        breakdown = TargetBreakdown(
            target_id=target_id,
            breakdown_type=request.breakdown_type,
            platform_code=normalized_platform_code if request.breakdown_type == "shop" else request.platform_code,
            shop_id=request.shop_id,
            period_start=request.period_start,
            period_end=request.period_end,
            period_label=request.period_label,
            target_amount=request.target_amount,
            target_quantity=request.target_quantity
        )
        
        db.add(breakdown)
        await db.commit()
        await db.refresh(breakdown)
        
        # [*] v4.21.0: 同步到 a_class.sales_targets_a（店铺分解时触发）
        if request.breakdown_type == "shop":
            try:
                from backend.services.target_sync_service import sync_target_after_create
                sync_result = await sync_target_after_create(db, target_id)
                if sync_result.get("synced", 0) > 0:
                    logger.info(f"[TargetManagement] 已同步到a_class: {sync_result['synced']}条记录")
                if sync_result.get("errors"):
                    logger.warning(f"[TargetManagement] 同步部分失败: {sync_result['errors']}")
            except Exception as sync_err:
                # 同步失败不影响主流程
                logger.warning(f"[TargetManagement] 同步到a_class失败: {sync_err}")
        
        breakdown_data = BreakdownResponse.model_validate(breakdown).model_dump()
        if request.breakdown_type == "shop":
            # ✅ 使用标准化后的 platform_code 查询店铺名称
            shop = (await db.execute(
                select(DimShop).where(
                    DimShop.platform_code == normalized_platform_code,
                    DimShop.shop_id == request.shop_id
                )
            )).scalar_one_or_none()
            if shop:
                breakdown_data["shop_name"] = shop.shop_name
        
        return {
            "success": True,
            "data": breakdown_data,
            "message": "目标分解创建成功"
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"创建目标分解失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="创建目标分解失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限,或联系系统管理员",
            status_code=500
        )


@router.get("/{target_id}/breakdown", response_model=Dict[str, Any])
async def list_breakdowns(
    target_id: int,
    breakdown_type: Optional[str] = Query(None, description="分解类型筛选:shop/time"),
    db: AsyncSession = Depends(get_async_db),
    current_user: DimUser = Depends(get_current_user),  # 查询分解仅需登录
):
    """
    查询目标分解列表
    """
    try:
        query = select(TargetBreakdown).where(
            TargetBreakdown.target_id == target_id
        )
        
        if breakdown_type:
            query = query.where(TargetBreakdown.breakdown_type == breakdown_type)
        
        breakdowns = (await db.execute(query)).scalars().all()
        
        # 获取店铺名称
        breakdown_responses = []
        for breakdown in breakdowns:
            breakdown_data = BreakdownResponse.model_validate(breakdown).model_dump()
            if breakdown.breakdown_type == "shop" and breakdown.platform_code and breakdown.shop_id:
                shop = (await db.execute(
                    select(DimShop).where(
                        DimShop.platform_code == breakdown.platform_code,
                        DimShop.shop_id == breakdown.shop_id
                    )
                )).scalar_one_or_none()
                if shop:
                    breakdown_data["shop_name"] = shop.shop_name
            breakdown_responses.append(breakdown_data)
        
        return {
            "success": True,
            "data": breakdown_responses
        }
    except Exception as e:
        logger.error(f"查询目标分解列表失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="查询目标分解列表失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和查询参数,或联系系统管理员",
            status_code=500
        )


@router.post("/{target_id}/calculate", response_model=Dict[str, Any])
async def calculate_target_achievement(
    target_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: DimUser = Depends(require_admin)  # ✅ 2026-01-08: 仅管理员可访问
):
    """
    计算目标达成情况(C类数据:系统自动计算)
    
    从fact_orders表聚合计算实际销售额和订单数
    更新目标和分解的达成数据
    """
    try:
        from backend.services.target_management_service import TargetManagementService
        
        service = TargetManagementService(db)
        result = service.calculate_target_achievement(target_id)
        
        return success_response(
            data=TargetResponse.model_validate(result["target"]).model_dump(),
            message="达成情况计算完成"
        )
    except ValueError as e:
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message=str(e),
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            recovery_suggestion="请检查目标ID是否正确,或确认该目标已创建",
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
            recovery_suggestion="请检查数据库连接和查询参数,或联系系统管理员",
            status_code=500
        )

