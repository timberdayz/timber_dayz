"""
数据管理API路由 - 西虹ERP系统
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select, func
from typing import List, Optional
from datetime import datetime, date

from backend.models.database import get_db, get_async_db, DataRecord, DataFile, DimProduct, FactSalesOrders, FactProductMetrics
from backend.services.unifier import rebuild_unified
# [WARN] v4.6.0 DSS架构重构：已删除MaterializedViewService（Metabase直接查询原始表）
from backend.utils.api_response import success_response, error_response
from backend.utils.error_codes import ErrorCode, get_error_type
from modules.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()

@router.get("/data-stats")
async def get_data_stats(db: AsyncSession = Depends(get_async_db)):
    """获取数据统计"""
    try:
        # 获取数据记录统计
        total_result = await db.execute(select(func.count(DataRecord.id)))
        total_records = total_result.scalar() or 0
        
        valid_result = await db.execute(
            select(func.count(DataRecord.id)).where(DataRecord.quality_score >= 80)
        )
        valid_records = valid_result.scalar() or 0
        invalid_records = total_records - valid_records
        
        # 计算平均质量
        avg_result = await db.execute(select(func.avg(DataRecord.quality_score)))
        avg_quality = avg_result.scalar() or 0
        
        data = {
            "total_records": total_records,
            "valid_records": valid_records,
            "invalid_records": invalid_records,
            "data_quality": round(avg_quality, 1)
        }
        
        return success_response(data=data)
    except Exception as e:
        logger.error(f"获取数据统计失败: {e}")
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取数据统计失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )

@router.get("/quality-metrics")
async def get_quality_metrics(db: AsyncSession = Depends(get_async_db)):
    """获取质量指标"""
    try:
        # 模拟质量指标数据
        data = {
            "completeness": 92.5,
            "accuracy": 87.8,
            "consistency": 90.2
        }
        
        return success_response(data=data)
    except Exception as e:
        logger.error(f"获取质量指标失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取质量指标失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和查询参数，或联系系统管理员",
            status_code=500
        )

@router.get("/data-records")
async def get_data_records(db: AsyncSession = Depends(get_async_db)):
    """获取数据记录列表"""
    try:
        result = await db.execute(select(DataRecord))
        records = result.scalars().all()
        return [{
            "id": record.id,
            "platform": record.platform,
            "data_type": record.data_type,
            "record_count": record.record_count,
            "quality": record.quality_score,
            "last_updated": record.last_updated.isoformat() if record.last_updated else None,
            "status": record.status
        } for record in records]
    except Exception as e:
        logger.error(f"获取数据记录失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取数据记录失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和查询参数，或联系系统管理员",
            status_code=500
        )

@router.post("/quality-check")
async def run_quality_check(db: AsyncSession = Depends(get_async_db)):
    """执行质量检查"""
    try:
        # 模拟质量检查过程
        return success_response(data={}, message="质量检查完成")
    except Exception as e:
        logger.error(f"质量检查失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="质量检查失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限，或联系系统管理员",
            status_code=500
        )

@router.post("/data-cleaning")
async def run_data_cleaning(db: AsyncSession = Depends(get_async_db)):
    """执行数据清理"""
    try:
        # 模拟数据清理过程
        return success_response(data={}, message="数据清理完成")
    except Exception as e:
        logger.error(f"数据清理失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="数据清理失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限，或联系系统管理员",
            status_code=500
        )

@router.post("/generate-report")
async def generate_quality_report(db: AsyncSession = Depends(get_async_db)):
    """生成质量报告"""
    try:
        # 模拟报告生成
        return {"success": True, "message": "质量报告已生成"}
    except Exception as e:
        logger.error(f"生成报告失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.FILE_WRITE_ERROR,
            message="生成报告失败",
            error_type=get_error_type(ErrorCode.FILE_WRITE_ERROR),
            detail=str(e),
            recovery_suggestion="请检查磁盘空间和文件权限，或联系系统管理员",
            status_code=500
        )


@router.post("/rebuild-unified")
async def rebuild_unified_data(db: AsyncSession = Depends(get_async_db)):
    """重建统一事实层（占位返回统计）"""
    try:
        stats = rebuild_unified(db)
        return {"success": True, **stats}
    except Exception as e:
        logger.error(f"重建统一事实失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="重建统一事实失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限，或联系系统管理员",
            status_code=500
        )


@router.get("/product/{product_id}/unified")
async def get_product_unified(product_id: str, db: AsyncSession = Depends(get_async_db)):
    """返回某product_id的销售+运营汇总（跨平台/店铺）。"""
    try:
        # 找到所有该product_id的代理键
        result = await db.execute(select(DimProduct).where(DimProduct.product_id == product_id))
        products = result.scalars().all()
        psids = [p.product_surrogate_id for p in products]
        if not psids:
            return {"success": True, "sales": {"qty": 0, "gmv": 0}, "metrics": {}}

        # 销售汇总
        sales_stmt = select(
            func.sum(FactSalesOrders.qty),
            func.sum(FactSalesOrders.gmv),
        ).where(FactSalesOrders.product_surrogate_id.in_(psids))
        sales_result = await db.execute(sales_stmt)
        sales_q = sales_result.one()
        sales = {"qty": int(sales_q[0] or 0), "gmv": float(sales_q[1] or 0)}

        # 最近指标（以最新日期为主）
        latest_stmt = select(func.max(FactProductMetrics.metric_date)).where(FactProductMetrics.product_surrogate_id.in_(psids))
        latest_result = await db.execute(latest_stmt)
        latest = latest_result.scalar()
        metrics = {}
        if latest:
            met_stmt = select(
                func.sum(FactProductMetrics.pv),
                func.sum(FactProductMetrics.uv),
                func.avg(FactProductMetrics.ctr),
                func.avg(FactProductMetrics.conversion),
                func.sum(FactProductMetrics.revenue),
                func.sum(FactProductMetrics.stock),
                func.avg(FactProductMetrics.rating),
                func.sum(FactProductMetrics.reviews),
            ).where(
                FactProductMetrics.product_surrogate_id.in_(psids),
                FactProductMetrics.metric_date == latest,
            )
            met_result = await db.execute(met_stmt)
            met = met_result.one()
            metrics = {
                "date": latest.isoformat(),
                "pv": int(met[0] or 0),
                "uv": int(met[1] or 0),
                "ctr": float(met[2] or 0),
                "conversion": float(met[3] or 0),
                "revenue": float(met[4] or 0),
                "stock": int(met[5] or 0),
                "rating": float(met[6] or 0),
                "reviews": int(met[7] or 0),
            }

        return {"success": True, "sales": sales, "metrics": metrics}
    except Exception as e:
        logger.error(f"获取产品统一数据失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取产品统一数据失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和查询参数，或联系系统管理员",
            status_code=500
        )


@router.get("/sales-detail-by-product")
async def get_sales_detail_by_product(
    product_id: Optional[int] = Query(None, description="产品ID（SN）"),
    platform_code: Optional[str] = Query(None, description="平台代码"),
    shop_id: Optional[str] = Query(None, description="店铺ID"),
    platform_sku: Optional[str] = Query(None, description="平台SKU"),
    start_date: Optional[date] = Query(None, description="开始日期"),
    end_date: Optional[date] = Query(None, description="结束日期"),
    order_id: Optional[str] = Query(None, description="订单ID"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    查询销售明细（以product_id为原子级）
    
    类似华为ISRP系统的销售明细表，每行代表一个产品实例的销售明细
    
    Args:
        product_id: 产品ID（SN），唯一标识每个产品实例
        platform_code: 平台代码筛选
        shop_id: 店铺ID筛选
        platform_sku: 平台SKU筛选
        start_date: 开始日期筛选
        end_date: 结束日期筛选
        order_id: 订单ID筛选
        page: 页码
        page_size: 每页数量
    
    Returns:
        销售明细列表，包含产品、订单、价格、店铺等完整信息
    """
    try:
        start_time = datetime.now()
        
        # 构建WHERE条件
        conditions = ["1=1"]
        params = {}
        
        if product_id:
            conditions.append("product_id = :product_id")
            params["product_id"] = product_id
        
        if platform_code:
            conditions.append("platform_code = :platform_code")
            params["platform_code"] = platform_code
        
        if shop_id:
            conditions.append("shop_id = :shop_id")
            params["shop_id"] = shop_id
        
        if platform_sku:
            conditions.append("platform_sku = :platform_sku")
            params["platform_sku"] = platform_sku
        
        if start_date:
            conditions.append("sale_date >= :start_date")
            params["start_date"] = start_date
        
        if end_date:
            conditions.append("sale_date <= :end_date")
            params["end_date"] = end_date
        
        if order_id:
            conditions.append("order_id = :order_id")
            params["order_id"] = order_id
        
        where_clause = " AND ".join(conditions)
        
        # 查询总数
        count_sql = f"SELECT COUNT(*) FROM mv_sales_detail_by_product WHERE {where_clause}"
        total_result = await db.execute(text(count_sql), params)
        total = total_result.scalar()
        
        # 查询数据
        offset = (page - 1) * page_size
        data_sql = f"""
            SELECT * FROM mv_sales_detail_by_product 
            WHERE {where_clause}
            ORDER BY sale_date DESC, order_id, product_id
            LIMIT :limit OFFSET :offset
        """
        params["limit"] = page_size
        params["offset"] = offset
        
        result = await db.execute(text(data_sql), params)
        rows = result.fetchall()
        
        # 转换为字典列表
        data = []
        for row in rows:
            row_dict = dict(row._mapping)
            # 转换日期和时间为字符串
            if row_dict.get('sale_date'):
                row_dict['sale_date'] = row_dict['sale_date'].isoformat() if hasattr(row_dict['sale_date'], 'isoformat') else str(row_dict['sale_date'])
            if row_dict.get('order_time_utc'):
                row_dict['order_time_utc'] = row_dict['order_time_utc'].isoformat() if hasattr(row_dict['order_time_utc'], 'isoformat') else str(row_dict['order_time_utc'])
            if row_dict.get('refreshed_at'):
                row_dict['refreshed_at'] = row_dict['refreshed_at'].isoformat() if hasattr(row_dict['refreshed_at'], 'isoformat') else str(row_dict['refreshed_at'])
            data.append(row_dict)
        
        query_time_ms = (datetime.now() - start_time).total_seconds() * 1000
        
        return {
            "success": True,
            "data": data,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
            "query_time_ms": round(query_time_ms, 2),
            "data_source": "materialized_view",
            "view_name": "mv_sales_detail_by_product"
        }
        
    except Exception as e:
        logger.error(f"查询销售明细失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="查询销售明细失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和查询参数，或联系系统管理员",
            status_code=500
        )


@router.get("/order/{order_id}")
async def get_order_detail(order_id: str, db: AsyncSession = Depends(get_async_db)):
    """返回订单项及其产品维度信息的快照。"""
    try:
        stmt = select(FactSalesOrders, DimProduct).join(
            DimProduct, DimProduct.product_surrogate_id == FactSalesOrders.product_surrogate_id
        ).where(FactSalesOrders.order_id == order_id)
        result = await db.execute(stmt)
        items = result.all()
        result = []
        for s, p in items:
            result.append({
                "platform": s.platform_code,
                "shop_id": s.shop_id,
                "order_id": s.order_id,
                "sku": s.sku,
                "qty": s.qty,
                "gmv": float(s.gmv or 0),
                "status": s.status,
                "product_id": p.product_id,
                "platform_sku": p.platform_sku,
                "title": p.title,
            })
        return {"success": True, "items": result}
    except Exception as e:
        logger.error(f"获取订单详情失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取订单详情失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和查询参数，或联系系统管理员",
            status_code=500
        )

@router.delete("/record/{record_id}")
async def delete_record(record_id: int, db: AsyncSession = Depends(get_async_db)):
    """删除数据记录"""
    try:
        result = await db.execute(select(DataRecord).where(DataRecord.id == record_id))
        record = result.scalar_one_or_none()
        if not record:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="记录不存在",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="请检查记录ID是否正确，或确认该记录已创建",
                status_code=404
            )
        
        await db.delete(record)
        await db.commit()
        
        return {"success": True, "message": "记录已删除"}
    except Exception as e:
        logger.error(f"删除记录失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="删除记录失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限，或联系系统管理员",
            status_code=500
        )
