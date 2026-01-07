#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据流转追踪API（v4.11.5新增）

功能：
1. 追踪任务数据流转（Raw → Fact → MV）
2. 按文件追踪数据流转
3. 识别数据丢失位置
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from typing import Optional, Dict, Any, List

from backend.models.database import get_db, get_async_db
from backend.utils.api_response import success_response, error_response
from backend.utils.error_codes import ErrorCode, get_error_type
from modules.core.db import (
    CatalogFile, 
    StagingOrders, 
    StagingProductMetrics, 
    StagingInventory,
    FactOrder,
    FactOrderItem,
    FactProductMetric,
    DataQuarantine
)
from modules.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/data-flow", tags=["数据流转追踪"])


@router.get("/trace/task/{task_id}")
async def trace_task_data_flow(
    task_id: str,
    db: AsyncSession = Depends(get_async_db)
):
    """
    追踪任务数据流转
    
    功能：
    - 查询Raw层、Fact层、隔离区的数据统计
    - 计算流转成功率
    - 识别数据丢失位置
    
    返回：
    {
        success: bool,
        task_id: str,
        flow_summary: {
            raw_layer: {orders: int, products: int, inventory: int},
            fact_layer: {orders: int, products: int, inventory: int},
            quarantine: int,
            overall_success_rate: float
        },
        file_flows: [
            {
                file_id: int,
                file_name: str,
                data_domain: str,
                raw_count: int,
                staging_count: int,
                fact_count: int,
                quarantine_count: int,
                success_rate: float
            }
        ]
    }
    """
    try:
        logger.info(f"[DataFlow] 追踪任务数据流转: task_id={task_id}")
        
        # Step 1: 查询Raw层数据统计（按task_id）
        raw_orders_result = await db.execute(
            select(func.count(StagingOrders.id)).where(StagingOrders.ingest_task_id == task_id)
        )
        raw_orders_count = raw_orders_result.scalar() or 0
        
        raw_products_result = await db.execute(
            select(func.count(StagingProductMetrics.id)).where(StagingProductMetrics.ingest_task_id == task_id)
        )
        raw_products_count = raw_products_result.scalar() or 0
        
        raw_inventory_result = await db.execute(
            select(func.count(StagingInventory.id)).where(StagingInventory.ingest_task_id == task_id)
        )
        raw_inventory_count = raw_inventory_result.scalar() or 0
        
        raw_total = raw_orders_count + raw_products_count + raw_inventory_count
        
        # Step 2: 查询Fact层数据统计（通过file_id关联）
        # 获取任务相关的所有file_id
        file_ids = set()
        
        # 从staging表获取file_id
        orders_file_ids_result = await db.execute(
            select(StagingOrders.file_id).where(
                StagingOrders.ingest_task_id == task_id,
                StagingOrders.file_id.isnot(None)
            ).distinct()
        )
        orders_file_ids = orders_file_ids_result.all()
        file_ids.update([fid[0] for fid in orders_file_ids])
        
        products_file_ids_result = await db.execute(
            select(StagingProductMetrics.file_id).where(
                StagingProductMetrics.ingest_task_id == task_id,
                StagingProductMetrics.file_id.isnot(None)
            ).distinct()
        )
        products_file_ids = products_file_ids_result.all()
        file_ids.update([fid[0] for fid in products_file_ids])
        
        inventory_file_ids_result = await db.execute(
            select(StagingInventory.file_id).where(
                StagingInventory.ingest_task_id == task_id,
                StagingInventory.file_id.isnot(None)
            ).distinct()
        )
        inventory_file_ids = inventory_file_ids_result.all()
        file_ids.update([fid[0] for fid in inventory_file_ids])
        
        # 查询Fact层数据
        fact_orders_count = 0
        fact_products_count = 0
        
        if file_ids:
            fact_orders_result = await db.execute(
                select(func.count(FactOrder.order_id)).where(FactOrder.file_id.in_(list(file_ids)))
            )
            fact_orders_count = fact_orders_result.scalar() or 0
            
            fact_products_result = await db.execute(
                select(func.count(FactProductMetric.platform_code)).where(FactProductMetric.source_catalog_id.in_(list(file_ids)))
            )
            fact_products_count = fact_products_result.scalar() or 0
        
        fact_total = fact_orders_count + fact_products_count
        
        # Step 3: 查询隔离区数据统计
        quarantine_count = 0
        if file_ids:
            quarantine_result = await db.execute(
                select(func.count(DataQuarantine.id)).where(DataQuarantine.catalog_file_id.in_(list(file_ids)))
            )
            quarantine_count = quarantine_result.scalar() or 0
        
        # Step 4: 计算整体成功率
        overall_success_rate = (fact_total / raw_total * 100) if raw_total > 0 else 0
        
        # Step 5: 按文件统计流转情况
        file_flows = []
        
        # 获取所有相关文件
        catalog_files_result = await db.execute(
            select(CatalogFile).where(CatalogFile.id.in_(list(file_ids)))
        )
        catalog_files = catalog_files_result.scalars().all()
        
        for file_record in catalog_files:
            file_id = file_record.id
            data_domain = file_record.data_domain or "products"
            
            # 查询该文件的Raw层数据
            file_raw_count = 0
            if data_domain == "orders":
                file_raw_result = await db.execute(
                    select(func.count(StagingOrders.id)).where(
                        StagingOrders.file_id == file_id,
                        StagingOrders.ingest_task_id == task_id
                    )
                )
                file_raw_count = file_raw_result.scalar() or 0
            elif data_domain in ["products", "traffic", "analytics"]:
                file_raw_result = await db.execute(
                    select(func.count(StagingProductMetrics.id)).where(
                        StagingProductMetrics.file_id == file_id,
                        StagingProductMetrics.ingest_task_id == task_id
                    )
                )
                file_raw_count = file_raw_result.scalar() or 0
            elif data_domain == "inventory":
                file_raw_result = await db.execute(
                    select(func.count(StagingInventory.id)).where(
                        StagingInventory.file_id == file_id,
                        StagingInventory.ingest_task_id == task_id
                    )
                )
                file_raw_count = file_raw_result.scalar() or 0
            
            # 查询该文件的Staging层数据（与Raw层相同，因为staging就是raw）
            file_staging_count = file_raw_count
            
            # 查询该文件的Fact层数据
            file_fact_count = 0
            if data_domain == "orders":
                file_fact_result = await db.execute(
                    select(func.count(FactOrder.order_id)).where(FactOrder.file_id == file_id)
                )
                file_fact_count = file_fact_result.scalar() or 0
            elif data_domain in ["products", "traffic", "analytics", "inventory"]:
                file_fact_result = await db.execute(
                    select(func.count(FactProductMetric.platform_code)).where(FactProductMetric.source_catalog_id == file_id)
                )
                file_fact_count = file_fact_result.scalar() or 0
            
            # 查询该文件的隔离区数据
            file_quarantine_result = await db.execute(
                select(func.count(DataQuarantine.id)).where(DataQuarantine.catalog_file_id == file_id)
            )
            file_quarantine_count = file_quarantine_result.scalar() or 0
            
            # 计算文件成功率
            file_success_rate = (file_fact_count / file_raw_count * 100) if file_raw_count > 0 else 0
            
            file_flows.append({
                "file_id": file_id,
                "file_name": file_record.file_name,
                "data_domain": data_domain,
                "platform_code": file_record.platform_code,
                "raw_count": file_raw_count,
                "staging_count": file_staging_count,
                "fact_count": file_fact_count,
                "quarantine_count": file_quarantine_count,
                "success_rate": round(file_success_rate, 2),
                "lost_in_staging": max(0, file_raw_count - file_staging_count),
                "lost_in_fact": max(0, file_staging_count - file_fact_count),
                "total_lost": max(0, file_raw_count - file_fact_count)
            })
        
        return {
            "success": True,
            "task_id": task_id,
            "flow_summary": {
                "raw_layer": {
                    "orders": raw_orders_count,
                    "products": raw_products_count,
                    "inventory": raw_inventory_count,
                    "total": raw_total
                },
                "fact_layer": {
                    "orders": fact_orders_count,
                    "products": fact_products_count,
                    "total": fact_total
                },
                "quarantine": quarantine_count,
                "overall_success_rate": round(overall_success_rate, 2)
            },
            "file_flows": file_flows
        }
        
        return success_response(data=data)
    except Exception as e:
        logger.error(f"[DataFlow] 追踪任务数据流转失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="追踪任务数据流转失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )


@router.get("/trace/file/{file_id}")
async def trace_file_data_flow(
    file_id: int,
    header_row: int = Query(0, description="表头行（0-based）"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    按文件追踪数据流转
    
    功能：
    - 追踪单个文件的数据流转路径
    - 显示文件在各层的数据量
    - 显示流转状态和错误信息
    
    返回：
    {
        success: bool,
        file_id: int,
        file_name: str,
        data_domain: str,
        flow_details: {
            raw_layer: {
                row_count: int,
                description: str
            },
            staging_layer: {
                row_count: int,
                description: str,
                success_rate: float
            },
            fact_layer: {
                row_count: int,
                table_name: str,
                description: str
            },
            quarantine: {
                row_count: int,
                description: str
            }
        },
        flow_status: {
            raw_to_staging: {
                success: bool,
                message: str,
                lost_rows: int
            },
            staging_to_fact: {
                success: bool,
                message: str,
                lost_rows: int
            },
            overall: {
                success: bool,
                message: str,
                success_rate: float
            }
        }
    }
    """
    try:
        logger.info(f"[DataFlow] 追踪文件数据流转: file_id={file_id}")
        
        # Step 1: 获取文件信息
        result = await db.execute(
            select(CatalogFile).where(CatalogFile.id == file_id)
        )
        catalog_record = result.scalar_one_or_none()
        
        if not catalog_record:
            return error_response(
                code=ErrorCode.FILE_NOT_FOUND,
                message=f"文件未注册: id={file_id}",
                error_type=get_error_type(ErrorCode.FILE_NOT_FOUND),
                recovery_suggestion="请检查文件ID是否正确，或确认该文件已注册",
                status_code=404
            )
        
        data_domain = catalog_record.data_domain or "products"
        
        # Step 2: 查询Raw层数据（通过staging表）
        raw_count = 0
        staging_count = 0
        
        if data_domain == "orders":
            raw_result = await db.execute(
                select(func.count(StagingOrders.id)).where(StagingOrders.file_id == file_id)
            )
            raw_count = raw_result.scalar() or 0
            staging_count = raw_count  # staging就是raw
        
        elif data_domain in ["products", "traffic", "analytics"]:
            raw_result = await db.execute(
                select(func.count(StagingProductMetrics.id)).where(StagingProductMetrics.file_id == file_id)
            )
            raw_count = raw_result.scalar() or 0
            staging_count = raw_count
        
        elif data_domain == "inventory":
            raw_result = await db.execute(
                select(func.count(StagingInventory.id)).where(StagingInventory.file_id == file_id)
            )
            raw_count = raw_result.scalar() or 0
            staging_count = raw_count
        
        # Step 3: 查询Fact层数据
        fact_count = 0
        fact_table_name = None
        
        if data_domain == "orders":
            fact_result = await db.execute(
                select(func.count(FactOrder.order_id)).where(FactOrder.file_id == file_id)
            )
            fact_count = fact_result.scalar() or 0
            fact_table_name = "fact_orders"
        
        elif data_domain in ["products", "traffic", "analytics", "inventory"]:
            fact_result = await db.execute(
                select(func.count(FactProductMetric.platform_code)).where(
                    FactProductMetric.source_catalog_id == file_id
                )
            )
            fact_count = fact_result.scalar() or 0
            fact_table_name = "fact_product_metrics"
        
        # Step 4: 查询隔离区数据
        quarantine_result = await db.execute(
            select(func.count(DataQuarantine.id)).where(DataQuarantine.catalog_file_id == file_id)
        )
        quarantine_count = quarantine_result.scalar() or 0
        
        # Step 5: 计算流转状态
        raw_to_staging_lost = max(0, raw_count - staging_count)
        staging_to_fact_lost = max(0, staging_count - fact_count)
        overall_success_rate = (fact_count / raw_count * 100) if raw_count > 0 else 0
        
        raw_to_staging_success = raw_to_staging_lost == 0
        staging_to_fact_success = staging_to_fact_lost == 0
        overall_success = overall_success_rate == 100
        
        data = {
            "file_id": file_id,
            "file_name": catalog_record.file_name,
            "data_domain": data_domain,
            "platform_code": catalog_record.platform_code,
            "flow_details": {
                "raw_layer": {
                    "row_count": raw_count,
                    "description": "原始Excel文件有效数据行数"
                },
                "staging_layer": {
                    "row_count": staging_count,
                    "description": "Staging表数据行数",
                    "success_rate": round((staging_count / raw_count * 100) if raw_count > 0 else 0, 2)
                },
                "fact_layer": {
                    "row_count": fact_count,
                    "table_name": fact_table_name,
                    "description": "Fact表数据行数"
                },
                "quarantine": {
                    "row_count": quarantine_count,
                    "description": "隔离区数据行数"
                }
            },
            "flow_status": {
                "raw_to_staging": {
                    "success": raw_to_staging_success,
                    "message": f"原始数据 → Staging: {staging_count}/{raw_count} ({round((staging_count / raw_count * 100) if raw_count > 0 else 0, 2)}%)",
                    "lost_rows": raw_to_staging_lost
                },
                "staging_to_fact": {
                    "success": staging_to_fact_success,
                    "message": f"Staging → Fact: {fact_count}/{staging_count} ({round((fact_count / staging_count * 100) if staging_count > 0 else 0, 2)}%)",
                    "lost_rows": staging_to_fact_lost
                },
                "overall": {
                    "success": overall_success,
                    "message": f"原始数据 → Fact: {fact_count}/{raw_count} ({round(overall_success_rate, 2)}%)",
                    "success_rate": round(overall_success_rate, 2)
                }
            }
        }
        
        return success_response(data=data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[DataFlow] 追踪文件数据流转失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="追踪文件数据流转失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )

