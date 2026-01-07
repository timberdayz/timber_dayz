#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
丢失数据导出API（v4.13.0新增）
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from typing import Optional, Dict, Any, List
import io
import json
import pandas as pd
from datetime import datetime

from backend.models.database import get_db, get_async_db
from backend.utils.api_response import success_response, error_response
from backend.utils.error_codes import ErrorCode, get_error_type
from modules.core.db import CatalogFile, StagingOrders, StagingProductMetrics, FactOrder, FactProductMetric
from modules.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/raw-layer", tags=["原始数据层"])


@router.get("/export-lost-data/{file_id}")
async def export_lost_data(
    file_id: int,
    header_row: int = Query(0, description="表头行（0-based）"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    导出丢失数据到Excel（v4.13.0新增）
    
    功能：
    - 导出Staging→Fact丢失的数据详情
    - 支持orders/products/traffic/analytics/inventory域
    - 导出为Excel格式
    
    返回：
    Excel文件流
    """
    try:
        logger.info(f"[RawLayer] 导出丢失数据: file_id={file_id}")
        
        # Step 1: 获取文件信息
        result = await db.execute(
            select(CatalogFile).where(CatalogFile.id == file_id)
        )
        catalog_record = result.scalar_one_or_none()
        
        if not catalog_record:
            return error_response(
                code=ErrorCode.DATA_NOT_FOUND,
                message=f"文件不存在: file_id={file_id}",
                error_type=get_error_type(ErrorCode.DATA_NOT_FOUND),
                status_code=404
            )
        
        data_domain = catalog_record.data_domain or "products"
        
        # Step 2: 获取丢失数据详情（复用compareRawAndStaging的逻辑）
        lost_in_fact_details = []
        
        if data_domain == "orders":
            result = await db.execute(
                select(StagingOrders).where(StagingOrders.file_id == file_id)
            )
            staging_orders = result.scalars().all()
            
            staging_order_ids = set()
            for staging_order in staging_orders:
                if staging_order.order_id:
                    staging_order_ids.add((
                        staging_order.platform_code or "unknown",
                        staging_order.shop_id or "",
                        staging_order.order_id
                    ))
            
            result = await db.execute(
                select(FactOrder).where(FactOrder.file_id == file_id)
            )
            fact_orders = result.scalars().all()
            
            fact_order_ids = set()
            for fact_order in fact_orders:
                fact_order_ids.add((
                    fact_order.platform_code or "unknown",
                    fact_order.shop_id or "",
                    fact_order.order_id
                ))
            
            lost_order_ids = staging_order_ids - fact_order_ids
            
            for platform_code, shop_id, order_id in lost_order_ids:
                staging_order = next(
                    (so for so in staging_orders 
                     if so.order_id == order_id and 
                        (so.platform_code or "unknown") == platform_code and
                        (so.shop_id or "") == shop_id),
                    None
                )
                
                if staging_order:
                    order_data = staging_order.order_data
                    if isinstance(order_data, str):
                        try:
                            order_data = json.loads(order_data)
                        except:
                            order_data = {}
                    
                    lost_in_fact_details.append({
                        "平台代码": platform_code,
                        "店铺ID": shop_id or "",
                        "订单ID": order_id,
                        "订单状态": order_data.get("status") or order_data.get("订单状态") or "",
                        "订单日期": order_data.get("order_date") or order_data.get("order_date_local") or order_data.get("订单日期") or "",
                        "订单金额": order_data.get("total_amount") or order_data.get("订单金额") or "",
                        "货币": order_data.get("currency") or order_data.get("货币") or "",
                        "Staging ID": staging_order.id,
                        "创建时间": staging_order.created_at.isoformat() if staging_order.created_at else ""
                    })
        
        elif data_domain in ["products", "traffic", "analytics"]:
            result = await db.execute(
                select(StagingProductMetrics).where(StagingProductMetrics.file_id == file_id)
            )
            staging_metrics = result.scalars().all()
            
            staging_metric_keys = set()
            for staging_metric in staging_metrics:
                if staging_metric.platform_sku:
                    staging_metric_keys.add((
                        staging_metric.platform_code or "unknown",
                        staging_metric.shop_id or "",
                        staging_metric.platform_sku
                    ))
            
            result = await db.execute(
                select(FactProductMetric).where(FactProductMetric.source_catalog_id == file_id)
            )
            fact_metrics = result.scalars().all()
            
            fact_metric_keys = set()
            for fact_metric in fact_metrics:
                fact_metric_keys.add((
                    fact_metric.platform_code or "unknown",
                    fact_metric.shop_id or "",
                    fact_metric.platform_sku
                ))
            
            lost_metric_keys = staging_metric_keys - fact_metric_keys
            
            for platform_code, shop_id, platform_sku in lost_metric_keys:
                staging_metric = next(
                    (sm for sm in staging_metrics 
                     if sm.platform_sku == platform_sku and 
                        (sm.platform_code or "unknown") == platform_code and
                        (sm.shop_id or "") == shop_id),
                    None
                )
                
                if staging_metric:
                    metric_data = staging_metric.metric_data
                    if isinstance(metric_data, str):
                        try:
                            metric_data = json.loads(metric_data)
                        except:
                            metric_data = {}
                    
                    lost_in_fact_details.append({
                        "平台代码": platform_code,
                        "店铺ID": shop_id or "",
                        "SKU": platform_sku,
                        "指标日期": metric_data.get("metric_date") or "",
                        "Staging ID": staging_metric.id,
                        "创建时间": staging_metric.created_at.isoformat() if staging_metric.created_at else ""
                    })
        
        # Step 3: 如果没有丢失数据，返回空文件
        if not lost_in_fact_details:
            df = pd.DataFrame(columns=["提示"])
            df.loc[0] = ["没有丢失数据"]
        else:
            df = pd.DataFrame(lost_in_fact_details)
        
        # Step 4: 导出为Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='丢失数据', index=False)
        
        output.seek(0)
        
        # Step 5: 返回文件流
        filename = f"lost_data_{catalog_record.file_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{filename}"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[RawLayer] 导出丢失数据失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.FILE_OPERATION_ERROR,
            message="导出丢失数据失败",
            error_type=get_error_type(ErrorCode.FILE_OPERATION_ERROR),
            detail=str(e),
            status_code=500
        )

