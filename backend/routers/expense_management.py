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
- 字段: 店铺ID, 年月, 租金, 工资, 水电费, 其他成本
"""

from fastapi import APIRouter, Depends, Query, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime

from backend.models.database import get_async_db
from backend.utils.api_response import error_response
from backend.utils.error_codes import ErrorCode, get_error_type
from modules.core.db import (
    DimUser,
    PlatformAccount,  # 复用目标管理的店铺列表
)
from modules.core.logger import get_logger
from backend.schemas.expense import (
    ExpenseCreateRequest,
    ExpenseUpdateRequest,
    ExpenseResponse,
    ExpenseSummaryResponse,
)
from backend.dependencies.auth import get_current_user

logger = get_logger(__name__)
router = APIRouter(prefix="/expenses", tags=["费用管理"])


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
            select(PlatformAccount)
            .where(PlatformAccount.enabled == True)
            .order_by(PlatformAccount.platform, PlatformAccount.store_name)
        )
        
        logger.debug(f"[ExpenseManagement] 执行查询: {query}")
        rows = (await db.execute(query)).scalars().all()
        logger.info(f"[ExpenseManagement] 查询到 {len(rows)} 条店铺记录")
        
        items = []
        for r in rows:
            try:
                items.append({
                    "platform_code": r.platform.lower() if r.platform else None,
                    "shop_id": r.shop_id or r.account_id or str(r.id),
                    "shop_name": r.store_name or (r.account_alias or ""),
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
    """规范化缓存 key 参数（None→空字符串）"""
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
                    COALESCE(SUM("工资"), 0) as total_salary,
                    COALESCE(SUM("水电费"), 0) as total_utilities,
                    COALESCE(SUM("其他成本"), 0) as total_other_costs,
                    COALESCE(SUM("租金" + "工资" + "水电费" + "其他成本"), 0) as total_amount
                FROM a_class.operating_costs
                WHERE "年月" = :year_month
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
                    COALESCE(SUM("工资"), 0) as total_salary,
                    COALESCE(SUM("水电费"), 0) as total_utilities,
                    COALESCE(SUM("其他成本"), 0) as total_other_costs,
                    COALESCE(SUM("租金" + "工资" + "水电费" + "其他成本"), 0) as total_amount
                FROM a_class.operating_costs
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
                "total_salary": float(row[3] or 0),
                "total_utilities": float(row[4] or 0),
                "total_other_costs": float(row[5] or 0),
                "total_amount": float(row[6] or 0),
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
    - 各类费用汇总（租金、工资、水电费、其他成本）
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
                COALESCE(SUM("工资"), 0) as total_salary,
                COALESCE(SUM("水电费"), 0) as total_utilities,
                COALESCE(SUM("其他成本"), 0) as total_other_costs,
                COALESCE(SUM("租金" + "工资" + "水电费" + "其他成本"), 0) as total_amount,
                COUNT(DISTINCT "店铺ID") as shop_count,
                COUNT(DISTINCT "年月") as month_count
            FROM a_class.operating_costs
            WHERE "年月" LIKE :year_pattern
        """)
        db_result = await db.execute(query, {"year_pattern": f"{year}-%"})
        row = db_result.fetchone()
        if row:
            result = {
                "success": True,
                "data": {
                    "year": year,
                    "total_rent": float(row[0] or 0),
                    "total_salary": float(row[1] or 0),
                    "total_utilities": float(row[2] or 0),
                    "total_other_costs": float(row[3] or 0),
                    "total_amount": float(row[4] or 0),
                    "shop_count": row[5] or 0,
                    "month_count": row[6] or 0,
                }
            }
        else:
            result = {
                "success": True,
                "data": {
                    "year": year,
                    "total_rent": 0,
                    "total_salary": 0,
                    "total_utilities": 0,
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
                "年月" as year_month,
                "租金" as rent,
                "工资" as salary,
                "水电费" as utilities,
                "其他成本" as other_costs,
                "创建时间" as created_at,
                "更新时间" as updated_at
            FROM a_class.operating_costs
            WHERE {where_clause}
            ORDER BY "年月" ASC
        """)
        
        result = await db.execute(data_query, params)
        rows = result.fetchall()
        
        # 转换为响应格式
        items = []
        total_amount = 0
        for row in rows:
            rent = float(row.rent or 0)
            salary = float(row.salary or 0)
            utilities = float(row.utilities or 0)
            other_costs = float(row.other_costs or 0)
            row_total = rent + salary + utilities + other_costs
            total_amount += row_total
            
            items.append({
                "id": row.id,
                "shop_id": row.shop_id,
                "year_month": row.year_month,
                "rent": rent,
                "salary": salary,
                "utilities": utilities,
                "other_costs": other_costs,
                "total": row_total,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            })
        
        # 计算汇总
        summary = {
            "total_amount": total_amount,
            "total_rent": sum(item["rent"] for item in items),
            "total_salary": sum(item["salary"] for item in items),
            "total_utilities": sum(item["utilities"] for item in items),
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
        """)
        total = (await db.execute(count_query, params)).scalar() or 0
        
        # 分页查询(使用中文字段名)
        offset = (page - 1) * page_size
        data_query = text(f"""
            SELECT 
                id,
                "店铺ID" as shop_id,
                "年月" as year_month,
                "租金" as rent,
                "工资" as salary,
                "水电费" as utilities,
                "其他成本" as other_costs,
                "创建时间" as created_at,
                "更新时间" as updated_at
            FROM a_class.operating_costs
            WHERE {where_clause}
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
            salary = float(row.salary or 0)
            utilities = float(row.utilities or 0)
            other_costs = float(row.other_costs or 0)
            total_amount = rent + salary + utilities + other_costs
            
            items.append({
                "id": row.id,
                "shop_id": row.shop_id,
                "year_month": row.year_month,
                "rent": rent,
                "salary": salary,
                "utilities": utilities,
                "other_costs": other_costs,
                "total": total_amount,
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
                "年月" as year_month,
                "租金" as rent,
                "工资" as salary,
                "水电费" as utilities,
                "其他成本" as other_costs,
                "创建时间" as created_at,
                "更新时间" as updated_at
            FROM a_class.operating_costs
            WHERE id = :expense_id
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
        salary = float(row.salary or 0)
        utilities = float(row.utilities or 0)
        other_costs = float(row.other_costs or 0)
        total_amount = rent + salary + utilities + other_costs
        
        return {
            "success": True,
            "data": {
                "id": row.id,
                "shop_id": row.shop_id,
                "year_month": row.year_month,
                "rent": rent,
                "salary": salary,
                "utilities": utilities,
                "other_costs": other_costs,
                "total": total_amount,
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
        # 使用UPSERT语法(ON CONFLICT DO UPDATE)
        upsert_query = text("""
            INSERT INTO a_class.operating_costs 
                ("店铺ID", "年月", "租金", "工资", "水电费", "其他成本", "创建时间", "更新时间")
            VALUES 
                (:shop_id, :year_month, :rent, :salary, :utilities, :other_costs, NOW(), NOW())
            ON CONFLICT ("店铺ID", "年月") 
            DO UPDATE SET 
                "租金" = EXCLUDED."租金",
                "工资" = EXCLUDED."工资",
                "水电费" = EXCLUDED."水电费",
                "其他成本" = EXCLUDED."其他成本",
                "更新时间" = NOW()
            RETURNING 
                id,
                "店铺ID" as shop_id,
                "年月" as year_month,
                "租金" as rent,
                "工资" as salary,
                "水电费" as utilities,
                "其他成本" as other_costs,
                "创建时间" as created_at,
                "更新时间" as updated_at
        """)
        
        result = await db.execute(upsert_query, {
            "shop_id": request.shop_id,
            "year_month": request.year_month,
            "rent": request.rent,
            "salary": request.salary,
            "utilities": request.utilities,
            "other_costs": request.other_costs,
        })
        
        await db.commit()
        
        row = result.fetchone()
        if not row:
            raise Exception("Upsert操作未返回数据")
        
        rent = float(row.rent or 0)
        salary = float(row.salary or 0)
        utilities = float(row.utilities or 0)
        other_costs = float(row.other_costs or 0)
        total_amount = rent + salary + utilities + other_costs
        
        return {
            "success": True,
            "data": {
                "id": row.id,
                "shop_id": row.shop_id,
                "year_month": row.year_month,
                "rent": rent,
                "salary": salary,
                "utilities": utilities,
                "other_costs": other_costs,
                "total": total_amount,
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
                "年月" as year_month,
                "租金" as rent,
                "工资" as salary,
                "水电费" as utilities,
                "其他成本" as other_costs
            FROM a_class.operating_costs
            WHERE id = :expense_id
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
        
        # 构建UPDATE语句(只更新提供的字段)
        update_fields = []
        params = {"expense_id": expense_id}
        
        update_data = request.dict(exclude_unset=True)
        if "rent" in update_data:
            update_fields.append('"租金" = :rent')
            params["rent"] = update_data["rent"]
        else:
            params["rent"] = float(row.rent or 0)
            
        if "salary" in update_data:
            update_fields.append('"工资" = :salary')
            params["salary"] = update_data["salary"]
        else:
            params["salary"] = float(row.salary or 0)
            
        if "utilities" in update_data:
            update_fields.append('"水电费" = :utilities')
            params["utilities"] = update_data["utilities"]
        else:
            params["utilities"] = float(row.utilities or 0)
            
        if "other_costs" in update_data:
            update_fields.append('"其他成本" = :other_costs')
            params["other_costs"] = update_data["other_costs"]
        else:
            params["other_costs"] = float(row.other_costs or 0)
        
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
                "年月" as year_month,
                "租金" as rent,
                "工资" as salary,
                "水电费" as utilities,
                "其他成本" as other_costs,
                "创建时间" as created_at,
                "更新时间" as updated_at
        """)
        
        result = await db.execute(update_query, params)
        await db.commit()
        
        updated_row = result.fetchone()
        if not updated_row:
            raise Exception("更新操作未返回数据")
        
        rent = float(updated_row.rent or 0)
        salary = float(updated_row.salary or 0)
        utilities = float(updated_row.utilities or 0)
        other_costs = float(updated_row.other_costs or 0)
        total_amount = rent + salary + utilities + other_costs
        
        return {
            "success": True,
            "data": {
                "id": updated_row.id,
                "shop_id": updated_row.shop_id,
                "year_month": updated_row.year_month,
                "rent": rent,
                "salary": salary,
                "utilities": utilities,
                "other_costs": other_costs,
                "total": total_amount,
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
    删除费用
    
    注意:使用原始SQL删除，因为数据库表使用中文字段名
    """
    try:
        # 先检查记录是否存在
        check_query = text("""
            SELECT id FROM a_class.operating_costs WHERE id = :expense_id
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
        
        # 执行删除
        delete_query = text("""
            DELETE FROM a_class.operating_costs WHERE id = :expense_id
        """)
        await db.execute(delete_query, {"expense_id": expense_id})
        await db.commit()
        
        return {
            "success": True,
            "message": "费用删除成功"
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