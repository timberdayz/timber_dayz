"""
库存管理API路由 - 西虹ERP系统
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from datetime import datetime

from backend.models.database import get_db, get_async_db
from backend.services.business_automation import InventoryAutomation
from backend.utils.api_response import success_response, error_response, pagination_response
from backend.utils.error_codes import ErrorCode, get_error_type
from modules.core.logger import get_logger
from sqlalchemy import text

logger = get_logger(__name__)
router = APIRouter()


@router.get("/list")
async def get_inventory_list(
    platform: Optional[str] = None,
    shop_id: Optional[str] = None,
    low_stock_only: bool = False,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_async_db)
):
    """
    获取库存列表（支持分页和筛选）
    
    Args:
        platform: 平台代码筛选
        shop_id: 店铺ID筛选
        low_stock_only: 只显示低库存商品
        skip: 分页偏移
        limit: 每页数量
    """
    try:
        # 构建查询条件
        where_clauses = []
        params = {}
        
        if platform:
            where_clauses.append("i.platform_code = :platform")
            params["platform"] = platform
        
        if shop_id:
            where_clauses.append("i.shop_id = :shop_id")
            params["shop_id"] = shop_id
        
        if low_stock_only:
            where_clauses.append("i.quantity_available < i.safety_stock")
        
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        
        # 查询总数
        count_sql = f"""
            SELECT COUNT(*)
            FROM fact_inventory i
            WHERE {where_sql}
        """
        total = db.execute(text(count_sql), params).scalar()
        
        # 查询数据
        query_sql = f"""
            SELECT
                i.inventory_id,
                i.platform_code,
                i.shop_id,
                i.warehouse_code,
                p.platform_sku,
                p.title,
                i.quantity_on_hand,
                i.quantity_available,
                i.quantity_reserved,
                i.quantity_incoming,
                i.avg_cost,
                i.total_value,
                i.safety_stock,
                i.reorder_point,
                i.last_updated
            FROM fact_inventory i
            JOIN dim_product p ON i.product_id = p.product_surrogate_id
            WHERE {where_sql}
            ORDER BY i.last_updated DESC
            LIMIT :limit OFFSET :skip
        """
        params["limit"] = limit
        params["skip"] = skip
        
        result = db.execute(text(query_sql), params)
        
        items = []
        for row in result:
            items.append({
                "inventory_id": row[0],
                "platform": row[1],
                "shop_id": row[2],
                "warehouse": row[3],
                "sku": row[4],
                "product_name": row[5],
                "quantity_on_hand": row[6],
                "quantity_available": row[7],
                "quantity_reserved": row[8],
                "quantity_incoming": row[9],
                "avg_cost": float(row[10]) if row[10] else 0,
                "total_value": float(row[11]) if row[11] else 0,
                "safety_stock": row[12],
                "reorder_point": row[13],
                "is_low_stock": row[7] < row[12] if row[12] else False,
                "last_updated": row[14].isoformat() if row[14] else None
            })
        
        page_num = skip // limit + 1
        page_size = limit
        
        return pagination_response(
            data=items,
            page=page_num,
            page_size=page_size,
            total=total
        )
        
    except Exception as e:
        logger.error(f"获取库存列表失败: {e}")
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取库存列表失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )


@router.get("/detail/{product_id}")
async def get_inventory_detail(
    product_id: int,
    db: AsyncSession = Depends(get_async_db)
):
    """获取库存详情（包括库存流水）"""
    try:
        # 查询库存信息
        inventory = db.execute(text("""
            SELECT
                i.*,
                p.platform_sku,
                p.title
            FROM fact_inventory i
            JOIN dim_product p ON i.product_id = p.product_surrogate_id
            WHERE i.product_id = :product_id
        """), {"product_id": product_id}).fetchone()
        
        if not inventory:
            return error_response(
                code=ErrorCode.INVENTORY_NOT_FOUND,
                message="库存记录不存在",
                error_type=get_error_type(ErrorCode.INVENTORY_NOT_FOUND),
                recovery_suggestion="请检查库存记录ID是否正确，或确认该记录已创建",
                status_code=404
            )
        
        # 查询库存流水（最近100条）
        transactions = db.execute(text("""
            SELECT
                transaction_id,
                transaction_type,
                reference_type,
                reference_id,
                quantity_change,
                quantity_before,
                quantity_after,
                unit_cost,
                operator_id,
                transaction_time
            FROM fact_inventory_transactions
            WHERE product_id = :product_id
            ORDER BY transaction_time DESC
            LIMIT 100
        """), {"product_id": product_id}).fetchall()
        
        transaction_list = []
        for row in transactions:
            transaction_list.append({
                "transaction_id": row[0],
                "type": row[1],
                "reference_type": row[2],
                "reference_id": row[3],
                "quantity_change": row[4],
                "quantity_before": row[5],
                "quantity_after": row[6],
                "unit_cost": float(row[7]) if row[7] else None,
                "operator": row[8],
                "time": row[9].isoformat() if row[9] else None
            })
        
        data = {
            "inventory": {
                "inventory_id": inventory.inventory_id,
                "platform": inventory.platform_code,
                "shop_id": inventory.shop_id,
                "warehouse": inventory.warehouse_code,
                "sku": inventory.platform_sku,
                "product_name": inventory.title,
                "quantity_on_hand": inventory.quantity_on_hand,
                "quantity_available": inventory.quantity_available,
                "quantity_reserved": inventory.quantity_reserved,
                "quantity_incoming": inventory.quantity_incoming,
                "avg_cost": float(inventory.avg_cost) if inventory.avg_cost else 0,
                "total_value": float(inventory.total_value) if inventory.total_value else 0,
                "safety_stock": inventory.safety_stock,
                "reorder_point": inventory.reorder_point
            },
            "transactions": transaction_list
        }
        
        return success_response(data=data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取库存详情失败: {e}")
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取库存详情失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )


@router.post("/adjust")
async def adjust_inventory(
    payload: dict,
    db: AsyncSession = Depends(get_async_db)
):
    """
    库存调整
    
    请求体：
    {
        "product_id": 1,
        "platform_code": "shopee",
        "shop_id": "123456",
        "quantity_change": 100,
        "operator_id": "admin",
        "notes": "盘点调整"
    }
    """
    try:
        result = InventoryAutomation.adjust_inventory(
            db,
            product_id=payload.get("product_id"),
            platform_code=payload.get("platform_code"),
            shop_id=payload.get("shop_id"),
            quantity_change=payload.get("quantity_change"),
            operator_id=payload.get("operator_id"),
            notes=payload.get("notes")
        )
        
        if result.get("success"):
            return result
        else:
            return error_response(
                code=ErrorCode.INVENTORY_OPERATION_FAILED,
                message=result.get("error", "库存调整失败"),
                error_type=get_error_type(ErrorCode.INVENTORY_OPERATION_FAILED),
                recovery_suggestion="请检查库存调整参数，或联系系统管理员",
                status_code=400
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"库存调整失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="库存调整失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限，或联系系统管理员",
            status_code=500
        )


@router.get("/low-stock-alert")
async def get_low_stock_alert(db: AsyncSession = Depends(get_async_db)):
    """获取低库存预警列表"""
    try:
        products = InventoryAutomation.check_low_stock_alert(db)
        
        data = {
            "alert_count": len(products),
            "products": products
        }
        
        return success_response(data=data)
        
    except Exception as e:
        logger.error(f"获取低库存预警失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取低库存预警失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和查询参数，或联系系统管理员",
            status_code=500
        )

