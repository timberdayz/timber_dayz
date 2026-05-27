#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
费用管理API(v4.21.0新增)

功能:
1. 费用CRUD(创建、查询、更新、删除)
2. 费用列表查询(分页、筛选)
3. 费用汇总统计

路由:
- GET /api/expenses - 查询费用列表
- GET /api/expenses/{id} - 查询费用详情
- POST /api/expenses - 创建/更新费用(Upsert)
- PUT /api/expenses/{id} - 更新费用
- DELETE /api/expenses/{id} - 删除费用
- GET /api/expenses/shops - 获取店铺列表(复用目标管理的店铺API)
- GET /api/expenses/summary - 按月汇总统计

注意:
- 使用 a_class.operating_costs 表(中文字段名)
- 底层物理列已迁移为 "营销费用"
- 字段: 店铺ID, 年月, 租金, 营销费用, 水电费, 其他成本
"""

from fastapi import APIRouter, Depends, Query, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select, or_
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
import json

from backend.models.database import get_async_db
from backend.utils.api_response import error_response
from backend.utils.error_codes import ErrorCode, get_error_type
from modules.core.db import (
    DimUser,
    ShopAccount,
)
from modules.core.logger import get_logger
from backend.schemas.expense import (
    ExpenseCreateRequest,
    ExpenseUpdateRequest,
    ExpenseResponse,
    ExpenseSummaryResponse,
)
from backend.dependencies.auth import get_current_user
from backend.services.employee_task_sources import sync_monthly_cost_entry_task

logger = get_logger(__name__)
router = APIRouter(prefix="/expenses", tags=["费用管理"])


def _calc_total_cost(
    rent: float,
    marketing_fee: float,
    utilities: float,
    ai_token_cost: float,
    other_costs: float,
) -> float:
    return (
        float(rent or 0)
        + float(marketing_fee or 0)
        + float(utilities or 0)
        + float(ai_token_cost or 0)
        + float(other_costs or 0)
    )


async def _resolve_shop_platform_code(db: AsyncSession, shop_id: str) -> Optional[str]:
    result = await db.execute(
        select(ShopAccount).where(
            ShopAccount.enabled == True,
            or_(
                ShopAccount.platform_shop_id == shop_id,
                ShopAccount.shop_account_id == shop_id,
            ),
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        return None
    return (row.platform or "").lower() or None


async def _ensure_platform_code(
    db: AsyncSession,
    platform_code: Optional[str],
    shop_id: str,
) -> Optional[str]:
    normalized = str(platform_code or "").strip().lower()
    if normalized:
        return normalized
    return await _resolve_shop_platform_code(db, shop_id)


# ==================== Request/Response Models ====================

# ==================== API Endpoints ====================

@router.get("/shops", response_model=Dict[str, Any])
async def list_expense_shops(
    db: AsyncSession = Depends(get_async_db),
    current_user: DimUser = Depends(get_current_user),
):
    """
    获取供费用管理使用的店铺列表(复用目标管理的店铺API)
    
    返回字段: platform_code、shop_id、shop_name
    """
    try:
        logger.info(f"[ExpenseManagement] 开始查询店铺列表, 用户: {current_user.username if current_user else 'unknown'}")
        
        query = (
            select(ShopAccount)
            .where(ShopAccount.enabled == True)
            .order_by(ShopAccount.platform, ShopAccount.store_name)
        )
        
        logger.debug(f"[ExpenseManagement] 执行查询: {query}")
        rows = (await db.execute(query)).scalars().all()
        logger.info(f"[ExpenseManagement] 查询到 {len(rows)} 条店铺记录")
        
        items = []
        for r in rows:
            try:
                items.append({
                    "platform_code": r.platform.lower() if r.platform else None,
                    "shop_id": getattr(r, "platform_shop_id", None) or getattr(r, "shop_account_id", None) or getattr(r, "shop_id", None) or getattr(r, "account_id", None) or str(r.id),
                    "shop_name": getattr(r, "store_name", None) or getattr(r, "shop_account_id", None) or getattr(r, "account_id", None) or "",
                })
            except Exception as item_err:
                logger.warning(f"[ExpenseManagement] 处理店铺记录失败 (id={r.id}): {item_err}")
                continue
        
        logger.info(f"[ExpenseManagement] 成功返回 {len(items)} 条店铺记录")
        return {"success": True, "data": items}
    except HTTPException:
        # 重新抛出HTTP异常(如认证失败)
        raise
    except Exception as e:
        logger.error(f"[ExpenseManagement] 查询费用用店铺列表失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="查询店铺列表失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500,
        )


def _normalize_cache_params(params: Dict[str, Any]) -> Dict[str, str]:
    """规范化缓存 key 参数（None->空字符串）"""
    return {k: "" if v is None else str(v) for k, v in params.items()}


@router.get("/summary/monthly", response_model=Dict[str, Any])
async def get_expense_summary(
    request: Request,
    year_month: Optional[str] = Query(None, description="年月筛选(YYYY-MM)"),
    db: AsyncSession = Depends(get_async_db),
    current_user: DimUser = Depends(get_current_user),
):
    """
    按月汇总统计费用
    """
    try:
        cache_params = _normalize_cache_params({"year_month": year_month})
        cache_status = "BYPASS"
        if request and hasattr(request.app.state, "cache_service"):
            cache_service = request.app.state.cache_service
            cached = await cache_service.get("expense_summary_monthly", **cache_params)
            if cached is not None:
                return JSONResponse(content=cached, headers={"X-Cache": "HIT"})
            cache_status = "MISS"
        # 使用原始SQL查询(因为需要聚合计算)
        if year_month:
            query = text("""
                SELECT 
                    "年月",
                    COUNT(DISTINCT "店铺ID") as shop_count,
                    COALESCE(SUM("租金"), 0) as total_rent,
                    COALESCE(SUM("营销费用"), 0) as total_marketing_fee,
                    COALESCE(SUM("水电费"), 0) as total_utilities,
                    COALESCE(SUM("AI Token费用"), 0) as total_ai_token_cost,
                    COALESCE(SUM("其他成本"), 0) as total_other_costs,
                    COALESCE(SUM("成本合计"), 0) as total_amount
                FROM a_class.operating_costs
                WHERE "年月" = :year_month
                  AND "删除时间" IS NULL
                GROUP BY "年月"
                ORDER BY "年月" DESC
            """)
            result = await db.execute(query, {"year_month": year_month})
        else:
            query = text("""
                SELECT 
                    "年月",
                    COUNT(DISTINCT "店铺ID") as shop_count,
                    COALESCE(SUM("租金"), 0) as total_rent,
                    COALESCE(SUM("营销费用"), 0) as total_marketing_fee,
                    COALESCE(SUM("水电费"), 0) as total_utilities,
                    COALESCE(SUM("AI Token费用"), 0) as total_ai_token_cost,
                    COALESCE(SUM("其他成本"), 0) as total_other_costs,
                    COALESCE(SUM("成本合计"), 0) as total_amount
                FROM a_class.operating_costs
                WHERE "删除时间" IS NULL
                GROUP BY "年月"
                ORDER BY "年月" DESC
            """)
            result = await db.execute(query)
        
        rows = result.fetchall()
        items = [
            {
                "year_month": row[0],
                "shop_count": row[1],
                "total_rent": float(row[2] or 0),
                "total_marketing_fee": float(row[3] or 0),
                "total_utilities": float(row[4] or 0),
                "total_ai_token_cost": float(row[5] or 0),
                "total_other_costs": float(row[6] or 0),
                "total_amount": float(row[7] or 0),
            }
            for row in rows
        ]
        result = {"success": True, "data": items}
        if request and hasattr(request.app.state, "cache_service"):
            await request.app.state.cache_service.set("expense_summary_monthly", result, **cache_params)
        return JSONResponse(content=result, headers={"X-Cache": cache_status})
    except Exception as e:
        logger.error(f"查询费用汇总失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="查询失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )


@router.get("/summary/yearly", response_model=Dict[str, Any])
async def get_yearly_expense_summary(
    request: Request,
    year: str = Query(..., description="年份(YYYY)"),
    db: AsyncSession = Depends(get_async_db),
    current_user: DimUser = Depends(get_current_user),
):
    """
    获取年度费用汇总（用于费用管理页面显示年度累计）
    
    返回:
    - 年度总费用（所有月份所有店铺汇总）
    - 各类费用汇总（租金、营销费用、水电费、其他成本）
    """
    try:
        cache_params = {"year": year}
        cache_status = "BYPASS"
        if request and hasattr(request.app.state, "cache_service"):
            cache_service = request.app.state.cache_service
            cached = await cache_service.get("expense_summary_yearly", **cache_params)
            if cached is not None:
                return JSONResponse(content=cached, headers={"X-Cache": "HIT"})
            cache_status = "MISS"
        query = text("""
            SELECT 
                COALESCE(SUM("租金"), 0) as total_rent,
                COALESCE(SUM("营销费用"), 0) as total_marketing_fee,
                COALESCE(SUM("水电费"), 0) as total_utilities,
                COALESCE(SUM("AI Token费用"), 0) as total_ai_token_cost,
                COALESCE(SUM("其他成本"), 0) as total_other_costs,
                COALESCE(SUM("成本合计"), 0) as total_amount,
                COUNT(DISTINCT "店铺ID") as shop_count,
                COUNT(DISTINCT "年月") as month_count
            FROM a_class.operating_costs
            WHERE "年月" LIKE :year_pattern
              AND "删除时间" IS NULL
        """)
        db_result = await db.execute(query, {"year_pattern": f"{year}-%"})
        row = db_result.fetchone()
        if row:
            result = {
                "success": True,
                "data": {
                    "year": year,
                    "total_rent": float(row[0] or 0),
                    "total_marketing_fee": float(row[1] or 0),
                    "total_utilities": float(row[2] or 0),
                    "total_ai_token_cost": float(row[3] or 0),
                    "total_other_costs": float(row[4] or 0),
                    "total_amount": float(row[5] or 0),
                    "shop_count": row[6] or 0,
                    "month_count": row[7] or 0,
                }
            }
        else:
            result = {
                "success": True,
                "data": {
                    "year": year,
                    "total_rent": 0,
                    "total_marketing_fee": 0,
                    "total_utilities": 0,
                    "total_ai_token_cost": 0,
                    "total_other_costs": 0,
                    "total_amount": 0,
                    "shop_count": 0,
                    "month_count": 0,
                }
            }
        if request and hasattr(request.app.state, "cache_service"):
            await request.app.state.cache_service.set("expense_summary_yearly", result, **cache_params)
        return JSONResponse(content=result, headers={"X-Cache": cache_status})
    except Exception as e:
        logger.error(f"查询年度费用汇总失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="查询失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )


@router.get("/by-shop", response_model=Dict[str, Any])
async def list_expenses_by_shop(
    shop_id: str = Query(..., description="店铺ID"),
    year: Optional[str] = Query(None, description="年份(YYYY)，不传则返回所有数据"),
    db: AsyncSession = Depends(get_async_db),
    current_user: DimUser = Depends(get_current_user),
):
    """
    按店铺查询费用（用于按店铺查看模式）
    
    返回该店铺全年或所有时间的费用记录
    """
    try:
        # 构建WHERE条件
        where_clause = '"店铺ID" = :shop_id'
        params = {'shop_id': shop_id}
        
        if year:
            where_clause += ' AND "年月" LIKE :year_pattern'
            params['year_pattern'] = f"{year}-%"
        
        # 查询该店铺的费用数据
        data_query = text(f"""
            SELECT 
                id,
                "店铺ID" as shop_id,
                "platform_code" as platform_code,
                "年月" as year_month,
                "租金" as rent,
                "营销费用" as marketing_fee,
                "水电费" as utilities,
                "AI Token费用" as ai_token_cost,
                "其他成本" as other_costs,
                "成本合计" as total_cost,
                "备注" as note,
                "附件" as attachments,
                "是否锁定" as locked,
                "创建时间" as created_at,
                "更新时间" as updated_at
            FROM a_class.operating_costs
            WHERE {where_clause}
              AND "删除时间" IS NULL
            ORDER BY "年月" ASC
        """)
        
        result = await db.execute(data_query, params)
        rows = result.fetchall()
        
        # 转换为响应格式
        items = []
        total_amount = 0
        for row in rows:
            rent = float(row.rent or 0)
            marketing_fee = float(row.marketing_fee or 0)
            utilities = float(row.utilities or 0)
            ai_token_cost = float(row.ai_token_cost or 0)
            other_costs = float(row.other_costs or 0)
            row_total = float(row.total_cost or _calc_total_cost(rent, marketing_fee, utilities, ai_token_cost, other_costs))
            total_amount += row_total
            
            items.append({
                "id": row.id,
                "shop_id": row.shop_id,
                "platform_code": row.platform_code,
                "year_month": row.year_month,
                "rent": rent,
                "marketing_fee": marketing_fee,
                "utilities": utilities,
                "ai_token_cost": ai_token_cost,
                "other_costs": other_costs,
                "total_cost": row_total,
                "total": row_total,
                "note": row.note,
                "attachments": row.attachments or [],
                "locked": bool(row.locked or False),
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            })
        
        # 计算汇总
        summary = {
            "total_amount": total_amount,
            "total_rent": sum(item["rent"] for item in items),
            "total_marketing_fee": sum(item["marketing_fee"] for item in items),
            "total_utilities": sum(item["utilities"] for item in items),
            "total_ai_token_cost": sum(item.get("ai_token_cost", 0) for item in items),
            "total_other_costs": sum(item["other_costs"] for item in items),
            "month_count": len(items),
        }
        
        return {
            "success": True,
            "data": {
                "items": items,
                "summary": summary,
                "shop_id": shop_id,
                "year": year,
            },
        }
    except Exception as e:
        logger.error(f"按店铺查询费用失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="查询失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )


@router.get("", response_model=Dict[str, Any])
async def list_expenses(
    shop_id: Optional[str] = Query(None, description="店铺ID筛选"),
    year_month: Optional[str] = Query(None, description="年月筛选(YYYY-MM)"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=1000, description="每页数量"),
    db: AsyncSession = Depends(get_async_db),
    current_user: DimUser = Depends(get_current_user),
):
    """
    查询费用列表(支持分页和筛选)
    
    注意:使用原始SQL查询，因为数据库表使用中文字段名
    """
    try:
        # 构建WHERE条件
        where_conditions = []
        params = {}
        
        if shop_id:
            where_conditions.append('"店铺ID" = :shop_id')
            params['shop_id'] = shop_id
        if year_month:
            where_conditions.append('"年月" = :year_month')
            params['year_month'] = year_month
        
        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
        
        # 总数查询
        count_query = text(f"""
            SELECT COUNT(*) 
            FROM a_class.operating_costs 
            WHERE {where_clause}
              AND "删除时间" IS NULL
        """)
        total = (await db.execute(count_query, params)).scalar() or 0
        
        # 分页查询(使用中文字段名)
        offset = (page - 1) * page_size
        data_query = text(f"""
            SELECT 
                id,
                "店铺ID" as shop_id,
                "platform_code" as platform_code,
                "年月" as year_month,
                "租金" as rent,
                "营销费用" as marketing_fee,
                "水电费" as utilities,
                "AI Token费用" as ai_token_cost,
                "其他成本" as other_costs,
                "成本合计" as total_cost,
                "备注" as note,
                "附件" as attachments,
                "是否锁定" as locked,
                "创建时间" as created_at,
                "更新时间" as updated_at
            FROM a_class.operating_costs
            WHERE {where_clause}
              AND "删除时间" IS NULL
            ORDER BY "年月" DESC, "店铺ID"
            LIMIT :limit OFFSET :offset
        """)
        params['limit'] = page_size
        params['offset'] = offset
        
        result = await db.execute(data_query, params)
        rows = result.fetchall()
        
        # 转换为响应格式(计算total字段)
        items = []
        for row in rows:
            rent = float(row.rent or 0)
            marketing_fee = float(row.marketing_fee or 0)
            utilities = float(row.utilities or 0)
            ai_token_cost = float(row.ai_token_cost or 0)
            other_costs = float(row.other_costs or 0)
            total_amount = float(row.total_cost or _calc_total_cost(rent, marketing_fee, utilities, ai_token_cost, other_costs))
            
            items.append({
                "id": row.id,
                "shop_id": row.shop_id,
                "platform_code": row.platform_code,
                "year_month": row.year_month,
                "rent": rent,
                "marketing_fee": marketing_fee,
                "utilities": utilities,
                "ai_token_cost": ai_token_cost,
                "other_costs": other_costs,
                "total_cost": total_amount,
                "total": total_amount,
                "note": row.note,
                "attachments": row.attachments or [],
                "locked": bool(row.locked or False),
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            })
        
        return {
            "success": True,
            "data": {
                "items": items,
                "total": total,
                "page": page,
                "page_size": page_size,
            },
        }
    except Exception as e:
        logger.error(f"查询费用列表失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="查询失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )


@router.get("/deleted", response_model=Dict[str, Any])
async def list_deleted_expenses(
    shop_id: Optional[str] = Query(None, description="店铺ID筛选"),
    year_month: Optional[str] = Query(None, description="年月筛选(YYYY-MM)"),
    year: Optional[str] = Query(None, description="年份筛选(YYYY)"),
    db: AsyncSession = Depends(get_async_db),
    current_user: DimUser = Depends(get_current_user),
):
    """查询已删除费用记录（软删除记录）"""
    try:
        where_conditions = ['"删除时间" IS NOT NULL']
        params = {}
        if shop_id:
            where_conditions.append('"店铺ID" = :shop_id')
            params["shop_id"] = shop_id
        if year_month:
            where_conditions.append('"年月" = :year_month')
            params["year_month"] = year_month
        if year:
            where_conditions.append('"年月" LIKE :year_pattern')
            params["year_pattern"] = f"{year}-%"

        query = text(f"""
            SELECT
                id,
                "店铺ID" as shop_id,
                "platform_code" as platform_code,
                "年月" as year_month,
                "租金" as rent,
                "营销费用" as marketing_fee,
                "水电费" as utilities,
                "AI Token费用" as ai_token_cost,
                "其他成本" as other_costs,
                "成本合计" as total_cost,
                "备注" as note,
                "附件" as attachments,
                "是否锁定" as locked,
                "删除时间" as deleted_at,
                "删除人" as deleted_by,
                "创建时间" as created_at,
                "更新时间" as updated_at
            FROM a_class.operating_costs
            WHERE {' AND '.join(where_conditions)}
            ORDER BY "删除时间" DESC, "更新时间" DESC
        """)
        result = await db.execute(query, params)
        rows = result.fetchall()
        items = []
        for row in rows:
            rent = float(row.rent or 0)
            marketing_fee = float(row.marketing_fee or 0)
            utilities = float(row.utilities or 0)
            ai_token_cost = float(row.ai_token_cost or 0)
            other_costs = float(row.other_costs or 0)
            total_amount = float(row.total_cost or _calc_total_cost(rent, marketing_fee, utilities, ai_token_cost, other_costs))
            items.append({
                "id": row.id,
                "shop_id": row.shop_id,
                "platform_code": row.platform_code,
                "year_month": row.year_month,
                "rent": rent,
                "marketing_fee": marketing_fee,
                "utilities": utilities,
                "ai_token_cost": ai_token_cost,
                "other_costs": other_costs,
                "total_cost": total_amount,
                "total": total_amount,
                "note": row.note,
                "attachments": row.attachments or [],
                "locked": bool(row.locked or False),
                "deleted_at": row.deleted_at,
                "deleted_by": row.deleted_by,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            })
        return {"success": True, "data": {"items": items}}
    except Exception as e:
        logger.error(f"查询已删除费用失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="查询失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )


@router.get("/{expense_id}", response_model=Dict[str, Any])
async def get_expense(
    expense_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: DimUser = Depends(get_current_user),
):
    """
    查询费用详情
    
    注意:使用原始SQL查询，因为数据库表使用中文字段名
    """
    try:
        query = text("""
            SELECT 
                id,
                "店铺ID" as shop_id,
                "platform_code" as platform_code,
                "年月" as year_month,
                "租金" as rent,
                "营销费用" as marketing_fee,
                "水电费" as utilities,
                "AI Token费用" as ai_token_cost,
                "其他成本" as other_costs,
                "成本合计" as total_cost,
                "备注" as note,
                "附件" as attachments,
                "是否锁定" as locked,
                "创建时间" as created_at,
                "更新时间" as updated_at
            FROM a_class.operating_costs
            WHERE id = :expense_id
              AND "删除时间" IS NULL
        """)
        
        result = await db.execute(query, {"expense_id": expense_id})
        row = result.fetchone()
        
        if not row:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="费用记录不存在",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="请检查费用ID是否正确",
                status_code=404
            )
        
        rent = float(row.rent or 0)
        marketing_fee = float(row.marketing_fee or 0)
        utilities = float(row.utilities or 0)
        ai_token_cost = float(row.ai_token_cost or 0)
        other_costs = float(row.other_costs or 0)
        total_amount = float(row.total_cost or _calc_total_cost(rent, marketing_fee, utilities, ai_token_cost, other_costs))
        
        return {
            "success": True,
            "data": {
                "id": row.id,
                "shop_id": row.shop_id,
                "platform_code": row.platform_code,
                "year_month": row.year_month,
                "rent": rent,
                "marketing_fee": marketing_fee,
                "utilities": utilities,
                "ai_token_cost": ai_token_cost,
                "other_costs": other_costs,
                "total_cost": total_amount,
                "total": total_amount,
                "note": row.note,
                "attachments": row.attachments or [],
                "locked": bool(row.locked or False),
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
        }
    except Exception as e:
        logger.error(f"查询费用详情失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="查询失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )


@router.post("", response_model=Dict[str, Any])
async def create_or_update_expense(
    request: ExpenseCreateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: DimUser = Depends(get_current_user),
):
    """
    创建/更新费用(Upsert逻辑)
    
    如果该店铺该月份已有费用记录，则更新；否则创建新记录
    
    注意:使用原始SQL执行upsert，因为数据库表使用中文字段名
    """
    try:
        lock_check = text(
            """
            SELECT COALESCE("是否锁定", false) AS locked
            FROM a_class.operating_costs
            WHERE COALESCE("platform_code", '') = :platform_code
              AND "店铺ID" = :shop_id
              AND "年月" = :year_month
              AND "删除时间" IS NULL
            """
        )
        requested_platform_code = await _ensure_platform_code(db, request.platform_code, request.shop_id)
        if not requested_platform_code:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="无法识别店铺所属平台",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="请重新选择店铺，或补齐该店铺的平台账号映射",
                status_code=400,
            )
        lock_row = (
            await db.execute(
                lock_check,
                {
                    "platform_code": requested_platform_code,
                    "shop_id": request.shop_id,
                    "year_month": request.year_month,
                },
            )
        ).fetchone()
        if lock_row and bool(lock_row.locked):
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="该店铺该月份已锁定，无法修改",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="请先解锁该月份或联系管理员处理",
                status_code=400,
            )

        platform_code = requested_platform_code

        total_cost = _calc_total_cost(
            request.rent,
            request.marketing_fee,
            request.utilities,
            request.ai_token_cost,
            request.other_costs,
        )

        # asyncpg 对 jsonb 参数的默认编码行为依赖驱动配置，直接传 Python list/dict 可能导致类型错误。
        # 统一序列化为 JSON 字符串，并在 SQL 中显式 cast 为 jsonb。
        attachments_json = json.dumps(request.attachments or [], ensure_ascii=False)

        # 使用UPSERT语法(ON CONFLICT DO UPDATE)
        upsert_query = text("""
            INSERT INTO a_class.operating_costs 
                ("店铺ID", "platform_code", "年月", "租金", "营销费用", "水电费", "AI Token费用", "其他成本", "成本合计", "备注", "附件", "创建时间", "更新时间")
            VALUES 
                (:shop_id, :platform_code, :year_month, :rent, :marketing_fee, :utilities, :ai_token_cost, :other_costs, :total_cost, :note, CAST(:attachments AS jsonb), NOW(), NOW())
            ON CONFLICT ("platform_code", "店铺ID", "年月") 
            DO UPDATE SET 
                "platform_code" = EXCLUDED."platform_code",
                "租金" = EXCLUDED."租金",
                "营销费用" = EXCLUDED."营销费用",
                "水电费" = EXCLUDED."水电费",
                "AI Token费用" = EXCLUDED."AI Token费用",
                "其他成本" = EXCLUDED."其他成本",
                "成本合计" = EXCLUDED."成本合计",
                "备注" = EXCLUDED."备注",
                "附件" = EXCLUDED."附件",
                "更新时间" = NOW()
            RETURNING 
                id,
                "店铺ID" as shop_id,
                "platform_code" as platform_code,
                "年月" as year_month,
                "租金" as rent,
                "营销费用" as marketing_fee,
                "水电费" as utilities,
                "AI Token费用" as ai_token_cost,
                "其他成本" as other_costs,
                "成本合计" as total_cost,
                "备注" as note,
                "附件" as attachments,
                "是否锁定" as locked,
                "创建时间" as created_at,
                "更新时间" as updated_at
        """)
        
        result = await db.execute(upsert_query, {
            "shop_id": request.shop_id,
            "platform_code": platform_code,
            "year_month": request.year_month,
            "rent": request.rent,
            "marketing_fee": request.marketing_fee,
            "utilities": request.utilities,
            "ai_token_cost": request.ai_token_cost,
            "other_costs": request.other_costs,
            "total_cost": total_cost,
            "note": request.note,
            "attachments": attachments_json,
        })
        
        await db.commit()
        
        row = result.fetchone()
        if not row:
            raise Exception("Upsert操作未返回数据")

        try:
            if platform_code:
                await sync_monthly_cost_entry_task(
                    db,
                    year_month=request.year_month,
                    platform_code=platform_code,
                    shop_id=request.shop_id,
                    created_by=getattr(current_user, "user_id", None),
                )
        except Exception as task_err:
            logger.warning(f"[ExpenseManagement] employee task sync failed: {task_err}")
        
        rent = float(row.rent or 0)
        marketing_fee = float(row.marketing_fee or 0)
        utilities = float(row.utilities or 0)
        ai_token_cost = float(row.ai_token_cost or 0)
        other_costs = float(row.other_costs or 0)
        total_amount = float(row.total_cost or _calc_total_cost(rent, marketing_fee, utilities, ai_token_cost, other_costs))
        
        return {
            "success": True,
            "data": {
                "id": row.id,
                "shop_id": row.shop_id,
                "platform_code": row.platform_code,
                "year_month": row.year_month,
                "rent": rent,
                "marketing_fee": marketing_fee,
                "utilities": utilities,
                "ai_token_cost": ai_token_cost,
                "other_costs": other_costs,
                "total_cost": total_amount,
                "total": total_amount,
                "note": row.note,
                "attachments": row.attachments or [],
                "locked": bool(row.locked or False),
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            },
            "message": "费用保存成功"
        }
    except Exception as e:
        await db.rollback()
        logger.error(f"创建/更新费用失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="创建/更新失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )


@router.put("/{expense_id}", response_model=Dict[str, Any])
async def update_expense(
    expense_id: int,
    request: ExpenseUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: DimUser = Depends(get_current_user),
):
    """
    更新费用
    
    注意:使用原始SQL查询和更新，因为数据库表使用中文字段名
    """
    try:
        # 先查询现有记录
        select_query = text("""
            SELECT 
                id,
                "店铺ID" as shop_id,
                "platform_code" as platform_code,
                "年月" as year_month,
                "租金" as rent,
                "营销费用" as marketing_fee,
                "水电费" as utilities,
                "AI Token费用" as ai_token_cost,
                "其他成本" as other_costs,
                "备注" as note,
                "附件" as attachments,
                "是否锁定" as locked
            FROM a_class.operating_costs
            WHERE id = :expense_id
              AND "删除时间" IS NULL
        """)
        
        result = await db.execute(select_query, {"expense_id": expense_id})
        row = result.fetchone()
        
        if not row:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="费用记录不存在",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="请检查费用ID是否正确",
                status_code=404
            )

        if bool(getattr(row, "locked", False)):
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="该记录已锁定，无法修改",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="请先解锁该月份或联系管理员处理",
                status_code=400,
            )

        # 构建UPDATE语句(只更新提供的字段)
        update_fields = []
        params = {"expense_id": expense_id}
        
        update_data = request.dict(exclude_unset=True)
        platform_code = await _ensure_platform_code(
            db,
            update_data.get("platform_code"),
            row.shop_id,
        )
        if not platform_code:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="无法识别店铺所属平台",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="请重新选择店铺，或补齐该店铺的平台账号映射",
                status_code=400,
            )
        update_fields.append('"platform_code" = :platform_code')
        params["platform_code"] = platform_code
        if "rent" in update_data:
            update_fields.append('"租金" = :rent')
            params["rent"] = update_data["rent"]
        else:
            params["rent"] = float(row.rent or 0)
            
        if "marketing_fee" in update_data:
            update_fields.append('"营销费用" = :marketing_fee')
            params["marketing_fee"] = update_data["marketing_fee"]
        else:
            params["marketing_fee"] = float(row.marketing_fee or 0)
            
        if "utilities" in update_data:
            update_fields.append('"水电费" = :utilities')
            params["utilities"] = update_data["utilities"]
        else:
            params["utilities"] = float(row.utilities or 0)

        if "ai_token_cost" in update_data:
            update_fields.append('"AI Token费用" = :ai_token_cost')
            params["ai_token_cost"] = update_data["ai_token_cost"]
        else:
            params["ai_token_cost"] = float(getattr(row, "ai_token_cost", 0) or 0)
            
        if "other_costs" in update_data:
            update_fields.append('"其他成本" = :other_costs')
            params["other_costs"] = update_data["other_costs"]
        else:
            params["other_costs"] = float(row.other_costs or 0)

        if "note" in update_data:
            update_fields.append('"备注" = :note')
            params["note"] = update_data["note"]
        else:
            params["note"] = getattr(row, "note", None)

        if "attachments" in update_data:
            update_fields.append('"附件" = CAST(:attachments AS jsonb)')
            params["attachments"] = json.dumps(update_data["attachments"] or [], ensure_ascii=False)
        else:
            # 数据库存的是 jsonb，读取出来可能是 list/dict；为了统一 update 绑定参数，仍序列化回字符串
            params["attachments"] = json.dumps(getattr(row, "attachments", None) or [], ensure_ascii=False)

        total_cost = _calc_total_cost(
            params["rent"],
            params["marketing_fee"],
            params["utilities"],
            params["ai_token_cost"],
            params["other_costs"],
        )
        update_fields.append('"成本合计" = :total_cost')
        params["total_cost"] = total_cost
        
        if not update_fields:
            # 没有字段需要更新
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="没有提供需要更新的字段",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                status_code=400
            )
        
        # 执行更新
        update_query = text(f"""
            UPDATE a_class.operating_costs
            SET {', '.join(update_fields)}, "更新时间" = NOW()
            WHERE id = :expense_id
            RETURNING 
                id,
                "店铺ID" as shop_id,
                "platform_code" as platform_code,
                "年月" as year_month,
                "租金" as rent,
                "营销费用" as marketing_fee,
                "水电费" as utilities,
                "AI Token费用" as ai_token_cost,
                "其他成本" as other_costs,
                "成本合计" as total_cost,
                "备注" as note,
                "附件" as attachments,
                "是否锁定" as locked,
                "创建时间" as created_at,
                "更新时间" as updated_at
        """)
        
        result = await db.execute(update_query, params)
        await db.commit()
        
        updated_row = result.fetchone()
        if not updated_row:
            raise Exception("更新操作未返回数据")
        
        rent = float(updated_row.rent or 0)
        marketing_fee = float(updated_row.marketing_fee or 0)
        utilities = float(updated_row.utilities or 0)
        ai_token_cost = float(updated_row.ai_token_cost or 0)
        other_costs = float(updated_row.other_costs or 0)
        total_amount = float(updated_row.total_cost or _calc_total_cost(rent, marketing_fee, utilities, ai_token_cost, other_costs))
        
        return {
            "success": True,
            "data": {
                "id": updated_row.id,
                "shop_id": updated_row.shop_id,
                "platform_code": updated_row.platform_code,
                "year_month": updated_row.year_month,
                "rent": rent,
                "marketing_fee": marketing_fee,
                "utilities": utilities,
                "ai_token_cost": ai_token_cost,
                "other_costs": other_costs,
                "total_cost": total_amount,
                "total": total_amount,
                "note": updated_row.note,
                "attachments": updated_row.attachments or [],
                "locked": bool(updated_row.locked or False),
                "created_at": updated_row.created_at,
                "updated_at": updated_row.updated_at,
            },
            "message": "费用更新成功"
        }
    except Exception as e:
        await db.rollback()
        logger.error(f"更新费用失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="更新失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )


@router.delete("/{expense_id}", response_model=Dict[str, Any])
async def delete_expense(
    expense_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: DimUser = Depends(get_current_user),
):
    """
    删除费用（软删除）
    
    注意:使用原始SQL删除，因为数据库表使用中文字段名
    """
    try:
        # 先检查记录是否存在
        check_query = text("""
            SELECT id FROM a_class.operating_costs WHERE id = :expense_id AND "删除时间" IS NULL
        """)
        result = await db.execute(check_query, {"expense_id": expense_id})
        if not result.fetchone():
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="费用记录不存在",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="请检查费用ID是否正确",
                status_code=404
            )
        
        delete_query = text("""
            UPDATE a_class.operating_costs
            SET "删除时间" = NOW(),
                "删除人" = :deleted_by,
                "更新时间" = NOW()
            WHERE id = :expense_id
        """)
        await db.execute(
            delete_query,
            {"expense_id": expense_id, "deleted_by": getattr(current_user, "user_id", None)},
        )
        await db.commit()
        
        return {
            "success": True,
            "message": "费用已删除(软删除，可恢复)"
        }
    except Exception as e:
        await db.rollback()
        logger.error(f"删除费用失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="删除失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )


@router.post("/{expense_id}/restore", response_model=Dict[str, Any])
async def restore_expense(
    expense_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: DimUser = Depends(get_current_user),
):
    try:
        check_query = text("""
            SELECT id
            FROM a_class.operating_costs
            WHERE id = :expense_id
              AND "删除时间" IS NOT NULL
        """)
        result = await db.execute(check_query, {"expense_id": expense_id})
        if not result.fetchone():
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="费用记录不存在或未被删除",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="请检查费用ID是否正确",
                status_code=404,
            )

        restore_query = text("""
            UPDATE a_class.operating_costs
            SET "删除时间" = NULL,
                "删除人" = NULL,
                "更新时间" = NOW()
            WHERE id = :expense_id
        """)
        await db.execute(restore_query, {"expense_id": expense_id})
        await db.commit()

        return {"success": True, "message": "费用记录已恢复"}
    except Exception as e:
        await db.rollback()
        logger.error(f"恢复费用失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="恢复失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )
