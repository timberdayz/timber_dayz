#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
原始数据层查看API（v4.11.5新增）

功能：
1. 查看原始Excel数据
2. 查看staging数据
3. 对比原始数据与staging数据
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from pathlib import Path
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
import io
import json
import pandas as pd
from datetime import datetime

from backend.models.database import get_db, get_async_db
from backend.services.excel_parser import ExcelParser
from backend.utils.api_response import success_response, error_response
from backend.utils.error_codes import ErrorCode, get_error_type
from modules.core.db import CatalogFile, StagingOrders, StagingProductMetrics, StagingInventory
from modules.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/raw-layer", tags=["原始数据层"])

# 复用 field_mapping.py 中的路径安全函数
from pathlib import Path as _SafePath


def _is_subpath(child: _SafePath, parent: _SafePath) -> bool:
    """判断 child 是否位于 parent 之下（兼容Python 3.9）。"""
    try:
        child_r = child.resolve()
        parent_r = parent.resolve()
        return str(child_r).startswith(str(parent_r))
    except Exception:
        return False


def _safe_resolve_path(file_path: str) -> str:
    """限制文件访问在允许的根目录：<project>/data/raw 与 <project>/downloads。"""
    from modules.core.path_manager import get_project_root, get_data_raw_dir, get_downloads_dir
    
    project_root = _SafePath(get_project_root())
    allowed_roots = [_SafePath(get_data_raw_dir()), _SafePath(get_downloads_dir())]

    p = _SafePath(file_path)
    if not p.is_absolute():
        p = project_root / p

    resolved = p.resolve()
    for root in allowed_roots:
        root_resolved = root.resolve()
        if _is_subpath(resolved, root_resolved):
            return str(resolved)

    return error_response(
        code=ErrorCode.PERMISSION_DENIED,
        message="文件路径不在允许的根目录内",
        error_type=get_error_type(ErrorCode.PERMISSION_DENIED),
        recovery_suggestion="请检查文件路径是否在允许的根目录内，或联系系统管理员",
        status_code=403
    )


@router.get("/view/{file_id}")
async def view_raw_excel(
    file_id: int,
    header_row: int = Query(0, description="表头行（0-based）"),
    limit: int = Query(100, ge=1, le=1000, description="预览行数限制"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    查看原始Excel数据
    
    功能：
    - 读取原始Excel文件
    - 返回数据预览（前N行）
    - 复用ExcelParser服务，保证一致性
    """
    try:
        logger.info(f"[RawLayer] 查看原始Excel: file_id={file_id}, header_row={header_row}, limit={limit}")
        
        # Step 1: 从catalog_files查询文件路径
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
        
        file_path = catalog_record.file_path
        logger.info(f"[RawLayer] 文件路径: {file_path}")
        
        # Step 2: 路径安全校验与存在性验证
        safe_path = _safe_resolve_path(file_path)
        if not Path(safe_path).exists():
            return error_response(
                code=ErrorCode.FILE_NOT_FOUND,
                message=f"文件不存在: {file_path}",
                error_type=get_error_type(ErrorCode.FILE_NOT_FOUND),
                recovery_suggestion="请检查文件路径是否正确，或确认该文件已存在",
                status_code=404
            )
        
        # Step 3: 读取Excel（使用智能解析器）
        # ⭐ v4.12.1修复：如果用户设置了表头行，跳过表头行之前的数据
        if header_row < 0:
            header_param = None
            skiprows_param = None
        else:
            header_param = header_row
            # 跳过表头行之前的所有行（如果header_row > 0）
            skiprows_param = list(range(header_row)) if header_row > 0 else None
        
        # 大文件保护：>10MB 的文件只读50行
        file_size_mb = Path(safe_path).stat().st_size / (1024 * 1024)
        preview_rows = min(limit, (50 if file_size_mb > 10 else 100))
        
        logger.info(f"[RawLayer] 文件大小: {file_size_mb:.2f}MB, 预览行数: {preview_rows}, 表头行: {header_row}, 跳过行: {skiprows_param}")
        
        # ⭐ v4.12.1修复：使用skiprows跳过表头行之前的数据
        read_kwargs = {}
        if skiprows_param:
            read_kwargs['skiprows'] = skiprows_param
        
        df = ExcelParser.read_excel(
            safe_path,
            header=header_param,
            nrows=preview_rows,
            **read_kwargs
        )
        
        # 规范化（通用合并单元格还原，v4.6.0增强版）
        normalization_report = {}
        try:
            df, normalization_report = ExcelParser.normalize_table(
                df,
                data_domain=catalog_record.data_domain or "products",
                file_size_mb=file_size_mb  # v4.6.0新增：传入文件大小，大文件只处理关键列
            )
            if file_size_mb > 10:
                logger.info(f"[RawLayer] 大文件规范化完成（只处理关键列）: {file_size_mb:.2f}MB")
        except Exception as norm_error:
            logger.warning(f"[RawLayer] 规范化失败（使用原始数据）: {norm_error}", exc_info=True)
            normalization_report = {"filled_columns": [], "filled_rows": 0, "strategy": "none", "error": str(norm_error)}
        
        # Step 4: 数据清洗
        df.columns = [str(col).strip() for col in df.columns]
        df = df.dropna(how='all')
        df = df.fillna('')
        
        # Step 5: 转换为前端格式
        columns = df.columns.tolist()
        data = df.head(preview_rows).to_dict('records')
        
        data = {
            "file_id": file_id,
            "file_name": catalog_record.file_name,
            "file_path": file_path,
            "file_size": Path(file_path).stat().st_size,
            "data_domain": catalog_record.data_domain,
            "platform_code": catalog_record.platform_code,
            "columns": columns,
            "data": data,
            "total_rows": len(df),
            "preview_rows": len(data),
            "preview_limit": preview_rows,
            "normalization_report": normalization_report,
        }
        
        return success_response(data=data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[RawLayer] 查看原始Excel失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.FILE_READ_ERROR,
            message="查看原始Excel失败",
            error_type=get_error_type(ErrorCode.FILE_READ_ERROR),
            detail=str(e),
            recovery_suggestion="请检查文件格式和内容，或联系系统管理员",
            status_code=500
        )


@router.get("/staging/{file_id}")
async def view_staging_data(
    file_id: int,
    limit: int = Query(100, ge=1, le=1000, description="返回行数限制"),
    offset: int = Query(0, ge=0, description="偏移量"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    查看staging数据
    
    功能：
    - 查询staging表（orders/product_metrics/inventory）
    - 返回JSON数据
    - 支持按file_id查询
    """
    try:
        logger.info(f"[RawLayer] 查看staging数据: file_id={file_id}, limit={limit}, offset={offset}")
        
        # 验证文件存在
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
        
        # 根据数据域查询对应的staging表
        staging_data = []
        total_count = 0
        
        if data_domain == "orders":
            # 查询 staging_orders
            count_result = await db.execute(
                select(func.count(StagingOrders.id)).where(StagingOrders.file_id == file_id)
            )
            total_count = count_result.scalar() or 0
            
            records_result = await db.execute(
                select(StagingOrders).where(StagingOrders.file_id == file_id).offset(offset).limit(limit)
            )
            staging_records = records_result.scalars().all()
            
            for record in staging_records:
                staging_data.append({
                    "id": record.id,
                    "platform_code": record.platform_code,
                    "shop_id": record.shop_id,
                    "order_id": record.order_id,
                    "order_data": record.order_data,
                    "ingest_task_id": record.ingest_task_id,
                    "file_id": record.file_id,
                    "created_at": record.created_at.isoformat() if record.created_at else None,
                })
        
        elif data_domain in ["products", "traffic", "analytics"]:
            # 查询 staging_product_metrics
            count_result = await db.execute(
                select(func.count(StagingProductMetrics.id)).where(StagingProductMetrics.file_id == file_id)
            )
            total_count = count_result.scalar() or 0
            
            records_result = await db.execute(
                select(StagingProductMetrics).where(StagingProductMetrics.file_id == file_id).offset(offset).limit(limit)
            )
            staging_records = records_result.scalars().all()
            
            for record in staging_records:
                staging_data.append({
                    "id": record.id,
                    "platform_code": record.platform_code,
                    "shop_id": record.shop_id,
                    "platform_sku": record.platform_sku,
                    "metric_data": record.metric_data,
                    "ingest_task_id": record.ingest_task_id,
                    "file_id": record.file_id,
                    "created_at": record.created_at.isoformat() if record.created_at else None,
                })
        
        elif data_domain == "inventory":
            # 查询 staging_inventory
            count_result = await db.execute(
                select(func.count(StagingInventory.id)).where(StagingInventory.file_id == file_id)
            )
            total_count = count_result.scalar() or 0
            
            records_result = await db.execute(
                select(StagingInventory).where(StagingInventory.file_id == file_id).offset(offset).limit(limit)
            )
            staging_records = records_result.scalars().all()
            
            for record in staging_records:
                staging_data.append({
                    "id": record.id,
                    "platform_code": record.platform_code,
                    "shop_id": record.shop_id,
                    "platform_sku": record.platform_sku,
                    "warehouse_id": record.warehouse_id,
                    "inventory_data": record.inventory_data,
                    "ingest_task_id": record.ingest_task_id,
                    "file_id": record.file_id,
                    "created_at": record.created_at.isoformat() if record.created_at else None,
                })
        
        else:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message=f"不支持的数据域: {data_domain}",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="支持的数据域：products、orders、traffic、services",
                status_code=400
            )
        
        data = {
            "file_id": file_id,
            "file_name": catalog_record.file_name,
            "data_domain": data_domain,
            "total_count": total_count,
            "returned_count": len(staging_data),
            "offset": offset,
            "limit": limit,
            "data": staging_data,
        }
        
        return success_response(data=data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[RawLayer] 查看staging数据失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="查看staging数据失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )


@router.get("/compare/{file_id}")
async def compare_raw_and_staging(
    file_id: int,
    header_row: int = Query(0, description="表头行（0-based）"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    对比原始数据与staging数据
    
    功能：
    - 对比原始Excel行数与staging表行数
    - 识别数据丢失
    - 返回对比报告
    """
    try:
        logger.info(f"[RawLayer] 对比原始数据与staging数据: file_id={file_id}, header_row={header_row}")
        
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
        
        file_path = catalog_record.file_path
        data_domain = catalog_record.data_domain or "products"
        
        # Step 2: 读取原始Excel文件，统计总行数
        safe_path = _safe_resolve_path(file_path)
        if not Path(safe_path).exists():
            return error_response(
                code=ErrorCode.FILE_NOT_FOUND,
                message=f"文件不存在: {file_path}",
                error_type=get_error_type(ErrorCode.FILE_NOT_FOUND),
                recovery_suggestion="请检查文件路径是否正确，或确认该文件已存在",
                status_code=404
            )
        
        # 读取完整文件（不限制行数）
        # ⭐ v4.12.1修复：如果用户设置了表头行，跳过表头行之前的数据
        if header_row < 0:
            header_param = None
            skiprows_param = None
        else:
            header_param = header_row
            # 跳过表头行之前的所有行（如果header_row > 0）
            skiprows_param = list(range(header_row)) if header_row > 0 else None
        
        read_kwargs = {}
        if skiprows_param:
            read_kwargs['skiprows'] = skiprows_param
        
        df = ExcelParser.read_excel(safe_path, header=header_param, **read_kwargs)
        
        # 规范化（如果需要）
        try:
            file_size_mb = Path(safe_path).stat().st_size / (1024 * 1024) if Path(safe_path).exists() else 0.0
            df, _ = ExcelParser.normalize_table(
                df, 
                data_domain=data_domain,
                file_size_mb=file_size_mb  # v4.6.0新增：传入文件大小
            )
        except Exception:
            pass  # 规范化失败不影响行数统计
        
        # 统计有效数据行数（排除空行）
        df = df.dropna(how='all')
        raw_row_count = len(df)
        
        # Step 3: 查询staging表，统计行数
        staging_row_count = 0
        
        if data_domain == "orders":
            count_result = await db.execute(
                select(func.count(StagingOrders.id)).where(StagingOrders.file_id == file_id)
            )
            staging_row_count = count_result.scalar() or 0
        
        elif data_domain in ["products", "traffic", "analytics"]:
            count_result = await db.execute(
                select(func.count(StagingProductMetrics.id)).where(StagingProductMetrics.file_id == file_id)
            )
            staging_row_count = count_result.scalar() or 0
        
        elif data_domain == "inventory":
            count_result = await db.execute(
                select(func.count(StagingInventory.id)).where(StagingInventory.file_id == file_id)
            )
            staging_row_count = count_result.scalar() or 0
        
        # Step 4: 计算差异
        lost_rows = max(0, raw_row_count - staging_row_count)
        success_rate = (staging_row_count / raw_row_count * 100) if raw_row_count > 0 else 0
        
        # Step 5: 查询fact表，统计已入库行数
        fact_row_count = 0
        fact_table_name = None
        
        if data_domain == "orders":
            from modules.core.db import FactOrder
            # ⭐ v4.12.1修复：FactOrder使用file_id字段（数据血缘）
            count_result = await db.execute(
                select(func.count(FactOrder.order_id)).where(FactOrder.file_id == file_id)
            )
            fact_row_count = count_result.scalar() or 0
            fact_table_name = "fact_orders"
        
        elif data_domain in ["products", "traffic", "analytics"]:
            from modules.core.db import FactProductMetric
            # ⭐ v4.12.1修复：FactProductMetric使用source_catalog_id字段，不是file_id
            count_result = await db.execute(
                select(func.count(FactProductMetric.id)).where(FactProductMetric.source_catalog_id == file_id)
            )
            fact_row_count = count_result.scalar() or 0
            fact_table_name = "fact_product_metrics"
        
        elif data_domain == "inventory":
            # inventory域可能没有独立的fact表，使用fact_product_metrics
            from modules.core.db import FactProductMetric
            # ⭐ v4.12.1修复：FactProductMetric使用source_catalog_id字段，不是file_id
            count_result = await db.execute(
                select(func.count(FactProductMetric.id)).where(
                    FactProductMetric.source_catalog_id == file_id,
                    FactProductMetric.data_domain == "inventory"
                )
            )
            fact_row_count = count_result.scalar() or 0
            fact_table_name = "fact_product_metrics"
        
        # Step 6: 查询隔离区，统计隔离行数（⭐ v4.12.1修复：使用catalog_file_id字段）
        from modules.core.db import DataQuarantine
        count_result = await db.execute(
            select(func.count(DataQuarantine.id)).where(DataQuarantine.catalog_file_id == file_id)
        )
        quarantined_count = count_result.scalar() or 0
        
        # Step 7: ⭐ v4.12.1新增：查询丢失的数据详情
        lost_in_staging_details = []
        lost_in_fact_details = []
        
        # 7.1: 查询Raw→Staging丢失的数据（如果有）
        if lost_rows > 0 and data_domain == "orders":
            # 对于订单数据，尝试从原始Excel中找出丢失的行
            # 由于无法精确匹配，这里只返回统计信息
            pass
        
        # 7.2: 查询Staging→Fact丢失的数据（⭐ 重点）
        lost_in_fact_count = max(0, staging_row_count - fact_row_count)
        logger.info(f"[RawLayer] Staging→Fact丢失数据统计: staging={staging_row_count}, fact={fact_row_count}, lost={lost_in_fact_count}")
        
        if lost_in_fact_count > 0 and data_domain == "orders":
            from modules.core.db import FactOrder
            import json
            
            try:
                # 查询Staging中所有的订单ID
                staging_result = await db.execute(
                    select(StagingOrders).where(StagingOrders.file_id == file_id)
                )
                staging_orders = staging_result.scalars().all()
                
                logger.info(f"[RawLayer] Staging中有 {len(staging_orders)} 条订单记录")
                
                staging_order_ids = set()
                for staging_order in staging_orders:
                    if staging_order.order_id:
                        staging_order_ids.add((
                            staging_order.platform_code or "unknown",
                            staging_order.shop_id or "",
                            staging_order.order_id
                        ))
                
                logger.info(f"[RawLayer] Staging中有 {len(staging_order_ids)} 个唯一订单ID")
                
                # 查询Fact中已存在的订单ID（⭐ v4.12.1修复：使用file_id字段）
                fact_result = await db.execute(
                    select(FactOrder).where(FactOrder.file_id == file_id)
                )
                fact_orders = fact_result.scalars().all()
                
                logger.info(f"[RawLayer] Fact中有 {len(fact_orders)} 条订单记录（file_id={file_id}）")
                
                fact_order_ids = set()
                for fact_order in fact_orders:
                    fact_order_ids.add((
                        fact_order.platform_code or "unknown",
                        fact_order.shop_id or "",
                        fact_order.order_id
                    ))
                
                logger.info(f"[RawLayer] Fact中有 {len(fact_order_ids)} 个唯一订单ID")
                
                # 找出在Staging中存在但在Fact中不存在的订单
                lost_order_ids = staging_order_ids - fact_order_ids
                logger.info(f"[RawLayer] 找到 {len(lost_order_ids)} 个丢失的订单（Staging中有但Fact中没有）")
                
                # 构建丢失数据详情（最多返回100条，避免数据过大）
                for platform_code, shop_id, order_id in list(lost_order_ids)[:100]:
                    # 从Staging中获取订单详情
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
                            "platform_code": platform_code,
                            "shop_id": shop_id,
                            "order_id": order_id,
                            "order_status": order_data.get("status") or order_data.get("订单状态"),
                            "order_date": order_data.get("order_date") or order_data.get("order_date_local") or order_data.get("订单日期"),
                            "total_amount": order_data.get("total_amount") or order_data.get("订单金额"),
                            "currency": order_data.get("currency") or order_data.get("货币"),
                            "staging_id": staging_order.id,
                            "staging_created_at": staging_order.created_at.isoformat() if staging_order.created_at else None
                        })
                
                # 如果丢失数据超过100条，添加提示
                if len(lost_order_ids) > 100:
                    lost_in_fact_details.append({
                        "_info": f"还有 {len(lost_order_ids) - 100} 条丢失数据未显示（仅显示前100条）"
                    })
                
                logger.info(f"[RawLayer] 返回 {len(lost_in_fact_details)} 条丢失数据详情")
            except Exception as detail_error:
                logger.error(f"[RawLayer] 查询丢失数据详情失败: {detail_error}", exc_info=True)
                # 即使查询失败，也返回一个提示信息
                lost_in_fact_details.append({
                    "_info": f"查询丢失数据详情失败: {str(detail_error)}"
                })
        
        elif lost_in_fact_count > 0 and data_domain in ["products", "traffic", "analytics"]:
            # 产品数据域的丢失数据查询
            from modules.core.db import FactProductMetric
            
            staging_result = await db.execute(
                select(StagingProductMetrics).where(StagingProductMetrics.file_id == file_id)
            )
            staging_metrics = staging_result.scalars().all()
            
            staging_metric_keys = set()
            for staging_metric in staging_metrics:
                if staging_metric.platform_sku:
                    staging_metric_keys.add((
                        staging_metric.platform_code or "unknown",
                        staging_metric.shop_id or "",
                        staging_metric.platform_sku
                    ))
            
            # ⭐ v4.12.1修复：FactProductMetric使用source_catalog_id字段，不是file_id
            fact_result = await db.execute(
                select(FactProductMetric).where(FactProductMetric.source_catalog_id == file_id)
            )
            fact_metrics = fact_result.scalars().all()
            
            fact_metric_keys = set()
            for fact_metric in fact_metrics:
                fact_metric_keys.add((
                    fact_metric.platform_code or "unknown",
                    fact_metric.shop_id or "",
                    fact_metric.platform_sku
                ))
            
            lost_metric_keys = staging_metric_keys - fact_metric_keys
            
            for platform_code, shop_id, platform_sku in list(lost_metric_keys)[:100]:
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
                        "platform_code": platform_code,
                        "shop_id": shop_id,
                        "platform_sku": platform_sku,
                        "metric_date": metric_data.get("metric_date"),
                        "staging_id": staging_metric.id,
                        "staging_created_at": staging_metric.created_at.isoformat() if staging_metric.created_at else None
                    })
            
            if len(lost_metric_keys) > 100:
                lost_in_fact_details.append({
                    "_info": f"还有 {len(lost_metric_keys) - 100} 条丢失数据未显示（仅显示前100条）"
                })
        
        # Step 8: 构建对比报告
        comparison_report = {
            "file_id": file_id,
            "file_name": catalog_record.file_name,
            "data_domain": data_domain,
            "raw_layer": {
                "row_count": raw_row_count,
                "description": "原始Excel文件有效数据行数"
            },
            "staging_layer": {
                "row_count": staging_row_count,
                "description": "Staging表数据行数",
                "success_rate": round(success_rate, 2)
            },
            "fact_layer": {
                "row_count": fact_row_count,
                "table_name": fact_table_name,
                "description": "Fact表数据行数"
            },
            "quarantine": {
                "row_count": quarantined_count,
                "description": "隔离区数据行数"
            },
            "summary": {
                "lost_in_staging": lost_rows,
                "lost_in_fact": lost_in_fact_count,
                "total_lost": max(0, raw_row_count - fact_row_count),
                "overall_success_rate": round((fact_row_count / raw_row_count * 100) if raw_row_count > 0 else 0, 2)
            },
            "data_flow": {
                "raw_to_staging": {
                    "success": staging_row_count == raw_row_count,
                    "message": f"原始数据 → Staging: {staging_row_count}/{raw_row_count} ({success_rate:.2f}%)"
                },
                "staging_to_fact": {
                    "success": fact_row_count == staging_row_count,
                    "message": f"Staging → Fact: {fact_row_count}/{staging_row_count} ({round((fact_row_count / staging_row_count * 100) if staging_row_count > 0 else 0, 2)}%)"
                },
                "overall": {
                    "success": fact_row_count == raw_row_count,
                    "message": f"原始数据 → Fact: {fact_row_count}/{raw_row_count} ({round((fact_row_count / raw_row_count * 100) if raw_row_count > 0 else 0, 2)}%)"
                }
            },
            # ⭐ v4.12.1新增：丢失数据详情
            "lost_data_details": {
                "lost_in_staging": lost_in_staging_details,
                "lost_in_fact": lost_in_fact_details
            }
        }
        
        return success_response(data={"comparison_report": comparison_report})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[RawLayer] 对比原始数据与staging数据失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="对比原始数据与staging数据失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )

