#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动入库API路由

v4.5.0新增：
- 治理统计API（3个）
- 自动入库API（3个）
- 复用现有的progress_tracker
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

from backend.models.database import get_db, get_async_db
from backend.services.governance_stats import get_governance_stats
from backend.services.auto_ingest_orchestrator import get_auto_ingest_orchestrator
from backend.services.progress_tracker import progress_tracker
from backend.utils.api_response import success_response, error_response
from backend.utils.error_codes import ErrorCode, get_error_type
from modules.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()

# ==================== 请求模型 ====================

class BatchAutoIngestRequest(BaseModel):
    """批量自动入库请求"""
    platform: Optional[str] = Field(
        None, description="平台代码；传入'*'或省略表示全部平台"
    )
    domains: Optional[List[str]] = Field(None, description="数据域列表（可选，空=全部）")
    granularities: Optional[List[str]] = Field(None, description="粒度列表（可选，空=全部）")
    since_hours: Optional[int] = Field(None, description="只处理最近N小时的文件")
    limit: int = Field(100, description="最多处理N个文件", ge=1, le=1000)
    only_with_template: bool = Field(True, description="只处理有模板的文件")
    allow_quarantine: bool = Field(True, description="允许隔离错误数据")


class SingleAutoIngestRequest(BaseModel):
    """单文件自动入库请求"""
    file_id: int = Field(..., description="文件ID")
    only_with_template: bool = Field(True, description="只处理有模板的文件")
    allow_quarantine: bool = Field(True, description="允许隔离错误数据")


# ==================== 治理统计API ====================

@router.get("/governance/overview")
async def get_governance_overview(
    platform: Optional[str] = Query(None, description="平台代码"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    获取治理概览统计
    
    返回：
    - pending_files: 待入库文件数
    - template_coverage: 模板覆盖度（%）
    - today_auto_ingested: 今日自动入库数
    - missing_templates_count: 缺少模板的域×粒度数
    """
    try:
        stats_service = get_governance_stats(db)
        overview = stats_service.get_overview(platform)
        
        return success_response(data=overview)
    except Exception as e:
        logger.error(f"[API] 获取治理概览失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取治理概览失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )


@router.get("/governance/missing-templates")
async def get_missing_templates(
    platform: Optional[str] = Query(None, description="平台代码"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    获取缺少模板的域×粒度清单
    
    返回：
    [{domain, granularity, file_count}]
    """
    try:
        stats_service = get_governance_stats(db)
        missing = stats_service.get_missing_templates(platform)
        
        return {
            "success": True,
            "data": missing
        }
    except Exception as e:
        logger.error(f"[API] 获取缺少模板清单失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取缺少模板清单失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和查询参数，或联系系统管理员",
            status_code=500
        )


@router.get("/governance/pending-files")
async def get_pending_files(
    platform: Optional[str] = Query(None, description="平台代码"),
    data_domain: Optional[str] = Query(None, description="数据域"),
    granularity: Optional[str] = Query(None, description="粒度"),
    since_hours: Optional[int] = Query(None, description="最近N小时"),
    limit: int = Query(100, description="返回数量限制", ge=1, le=1000),
    group_by_batch: bool = Query(False, description="是否按数据域+粒度分组统计"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    获取待入库文件列表
    
    v4.11.5新增：
    - group_by_batch参数：按数据域+粒度分组统计批次信息
    
    返回：
    [{file_id, file_name, platform, domain, granularity, shop_id, collected_at}]
    或（当group_by_batch=True时）：
    {
        batches: [{domain, granularity, file_count, files: [...]}],
        total_files: int
    }
    """
    try:
        stats_service = get_governance_stats(db)
        files = stats_service.get_pending_files(
            platform=platform,
            data_domain=data_domain,
            granularity=granularity,
            since_hours=since_hours,
            limit=limit
        )
        
        # ⭐ v4.11.5新增：按数据域+粒度分组统计
        if group_by_batch:
            from collections import defaultdict
            batches = defaultdict(lambda: {'domain': '', 'granularity': '', 'file_count': 0, 'files': []})
            
            for file_info in files:
                domain = file_info.get('domain', 'unknown')
                granularity_val = file_info.get('granularity', 'unknown')
                batch_key = f"{domain}_{granularity_val}"
                
                batches[batch_key]['domain'] = domain
                batches[batch_key]['granularity'] = granularity_val
                batches[batch_key]['file_count'] += 1
                batches[batch_key]['files'].append(file_info)
            
            batch_list = list(batches.values())
            total_files = len(files)
            
            return {
                "success": True,
                "data": {
                    "batches": batch_list,
                    "total_files": total_files,
                    "batch_count": len(batch_list)
                }
            }
        
        return {
            "success": True,
            "data": files
        }
    except Exception as e:
        logger.error(f"[API] 获取待入库文件失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取待入库文件失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和查询参数，或联系系统管理员",
            status_code=500
        )


# ==================== 自动入库API ====================

@router.post("/auto-ingest/single")
async def auto_ingest_single_file(
    request: SingleAutoIngestRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """
    单文件自动入库（采集完成触发）
    
    流程：
    1. 获取文件信息
    2. 查找模板
    3. 预览文件
    4. 应用模板
    5. 调用ingest接口
    
    返回：
    {
        success: bool,
        file_id: int,
        file_name: str,
        status: 'success'|'quarantined'|'failed'|'skipped',
        message: str
    }
    """
    try:
        orchestrator = get_auto_ingest_orchestrator(db)
        # ⭐ v4.11.6修复：单文件同步时生成task_id用于追踪
        import uuid
        task_id = f"single_file_{request.file_id}_{uuid.uuid4().hex[:8]}"
        
        result = await orchestrator.ingest_single_file(
            file_id=request.file_id,
            only_with_template=request.only_with_template,
            allow_quarantine=request.allow_quarantine,
            task_id=task_id  # ⭐ v4.11.6修复：传递task_id用于追踪
        )
        
        # ⭐ v4.11.6修复：在返回结果中包含task_id，方便前端追踪
        if result and isinstance(result, dict):
            result['task_id'] = task_id
        
        return result
        
    except Exception as e:
        logger.error(f"[API] 单文件自动入库失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="单文件自动入库失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限，或联系系统管理员",
            status_code=500
        )


@router.post("/auto-ingest/batch")
async def auto_ingest_batch(
    request: BatchAutoIngestRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """
    批量自动入库（手动触发）
    
    流程：
    1. 扫描符合条件的文件
    2. 创建进度任务
    3. 逐个调用ingest_single_file
    4. 返回汇总统计
    
    返回：
    {
        success: bool,
        task_id: str,
        summary: {
            total_files: int,
            processed: int,
            succeeded: int,
            quarantined: int,
            failed: int,
            skipped_no_template: int
        }
    }
    """
    try:
        orchestrator = get_auto_ingest_orchestrator(db)
        result = await orchestrator.batch_ingest(
            platform=request.platform,
            domains=request.domains,
            granularities=request.granularities,
            since_hours=request.since_hours,
            limit=request.limit,
            only_with_template=request.only_with_template,
            allow_quarantine=request.allow_quarantine
        )
        
        return result
        
    except Exception as e:
        logger.error(f"[API] 批量自动入库失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="批量自动入库失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限，或联系系统管理员",
            status_code=500
        )


@router.get("/auto-ingest/progress/{task_id}")
async def get_auto_ingest_progress(task_id: str):
    """
    查询自动入库进度（复用progress_tracker）
    
    返回：
    {
        task_id: str,
        type: 'auto_ingest',
        total: int,
        processed: int,
        succeeded: int,
        quarantined: int,
        failed: int,
        skipped: int,
        status: 'running'|'completed'|'failed',
        percentage: float,
        files: [...]  # 最近处理的文件
    }
    """
    try:
        progress = await progress_tracker.get_task(task_id)
        
        if progress is None:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="任务不存在",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="请检查任务ID是否正确，或确认该任务已创建",
                status_code=404
            )
        
        # 适配ProgressTracker返回格式到前端期望格式
        total = progress.get('total_files', progress.get('total', 0))
        processed = progress.get('processed_files', progress.get('processed', 0))
        succeeded = progress.get('valid_rows', progress.get('succeeded', 0))
        quarantined = progress.get('quarantined_rows', progress.get('quarantined', 0))
        failed = progress.get('error_rows', progress.get('failed', 0))
        skipped = progress.get('skipped', 0)
        status = progress.get('status', 'running')
        
        # 状态映射：pending/processing -> running, completed -> completed, failed -> failed
        if status == 'pending' or status == 'processing':
            status = 'running'
        elif status == 'completed':
            status = 'completed'
        elif status == 'failed':
            status = 'failed'
        
        # 计算百分比
        percentage = (processed / total * 100) if total > 0 else 0
        
        # 🆕 v4.11.5增强：添加当前文件、处理阶段、预计时间、错误详情
        current_file = progress.get('current_file', '')
        current_stage = progress.get('current_stage', '')
        
        # 计算预计时间
        start_time_str = progress.get('start_time')
        estimated_time_remaining = None
        if start_time_str and processed > 0 and total > 0:
            try:
                from datetime import datetime
                start_time = datetime.fromisoformat(start_time_str)
                elapsed_seconds = (datetime.now() - start_time).total_seconds()
                avg_time_per_file = elapsed_seconds / processed if processed > 0 else 0
                remaining_files = total - processed
                estimated_seconds = avg_time_per_file * remaining_files
                estimated_time_remaining = round(estimated_seconds, 1)
            except Exception:
                pass
        
        # 获取错误详情
        errors = progress.get('errors', [])
        warnings = progress.get('warnings', [])
        
        # ⭐ v4.11.5新增：获取数据质量检查结果
        quality_check = progress.get('quality_check', None)
        
        data = {
                'task_id': task_id,
                'type': progress.get('task_type', 'auto_ingest'),
                'total': total,
                'processed': processed,
                'succeeded': succeeded,
                'quarantined': quarantined,
                'failed': failed,
                'skipped': skipped,
                'status': status,
                'percentage': round(percentage, 1),
                'files': progress.get('files', []),
                # 🆕 v4.11.5增强字段
                'current_file': current_file,
                'current_stage': current_stage,
                'estimated_time_remaining': estimated_time_remaining,
                'errors': errors[-10:] if errors else [],  # 最近10个错误
                'warnings': warnings[-10:] if warnings else [],  # 最近10个警告
                'start_time': start_time_str,
                'elapsed_seconds': round((datetime.now() - datetime.fromisoformat(start_time_str)).total_seconds(), 1) if start_time_str else None,
                'quality_check': quality_check  # ⭐ v4.11.5新增：数据质量检查结果
            }
        
        return success_response(data=data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] 查询进度失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="查询进度失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和查询参数，或联系系统管理员",
            status_code=500
        )


@router.get("/auto-ingest/task/{task_id}/logs")
async def get_task_logs(task_id: str, limit: int = Query(50, ge=1, le=200), db: AsyncSession = Depends(get_async_db)):
    """
    获取任务日志详情（v4.11.4新增）
    
    返回：
    {
        success: bool,
        task_id: str,
        logs: [
            {
                file_id: int,
                file_name: str,
                status: str,
                staged: int,
                imported: int,
                quarantined: int,
                error_message: str,
                duration_seconds: float
            }
        ]
    }
    """
    try:
        from modules.core.db import CatalogFile, StagingOrders, StagingProductMetrics, StagingInventory
        from sqlalchemy import func, text
        
        # 查询staging表中的文件列表（按task_id）
        staging_files = []
        
        # 从staging_orders查询
        orders_stmt = select(
            StagingOrders.file_id,
            func.count(StagingOrders.id).label('staged_count')
        ).where(
            StagingOrders.ingest_task_id == task_id
        ).group_by(StagingOrders.file_id)
        orders_result = await db.execute(orders_stmt)
        orders_files = orders_result.all()
        
        for file_id, staged_count in orders_files:
            if file_id:
                file_result = await db.execute(select(CatalogFile).where(CatalogFile.id == file_id))
                file_record = file_result.scalar_one_or_none()
                staging_files.append({
                    'file_id': file_id,
                    'file_name': file_record.file_name if file_record else f'文件{file_id}',
                    'staged': staged_count,
                    'domain': 'orders'
                })
        
        # 从staging_product_metrics查询
        metrics_stmt = select(
            StagingProductMetrics.file_id,
            func.count(StagingProductMetrics.id).label('staged_count')
        ).where(
            StagingProductMetrics.ingest_task_id == task_id
        ).group_by(StagingProductMetrics.file_id)
        metrics_result = await db.execute(metrics_stmt)
        metrics_files = metrics_result.all()
        
        for file_id, staged_count in metrics_files:
            if file_id:
                file_result = await db.execute(select(CatalogFile).where(CatalogFile.id == file_id))
                file_record = file_result.scalar_one_or_none()
                # 检查是否已存在
                existing = next((f for f in staging_files if f['file_id'] == file_id), None)
                if existing:
                    existing['staged'] += staged_count
                else:
                    staging_files.append({
                        'file_id': file_id,
                        'file_name': file_record.file_name if file_record else f'文件{file_id}',
                        'staged': staged_count,
                        'domain': 'products'
                    })
        
        # 从staging_inventory查询
        inventory_stmt = select(
            StagingInventory.file_id,
            func.count(StagingInventory.id).label('staged_count')
        ).where(
            StagingInventory.ingest_task_id == task_id
        ).group_by(StagingInventory.file_id)
        inventory_result = await db.execute(inventory_stmt)
        inventory_files = inventory_result.all()
        
        for file_id, staged_count in inventory_files:
            if file_id:
                file_result = await db.execute(select(CatalogFile).where(CatalogFile.id == file_id))
                file_record = file_result.scalar_one_or_none()
                existing = next((f for f in staging_files if f['file_id'] == file_id), None)
                if existing:
                    existing['staged'] += staged_count
                else:
                    staging_files.append({
                        'file_id': file_id,
                        'file_name': file_record.file_name if file_record else f'文件{file_id}',
                        'staged': staged_count,
                        'domain': 'inventory'
                    })
        
        # 查询文件状态和入库结果
        logs = []
        for file_info in staging_files[:limit]:
            file_id = file_info['file_id']
            file_result = await db.execute(select(CatalogFile).where(CatalogFile.id == file_id))
            file_record = file_result.scalar_one_or_none()
            
            if file_record:
                # 查询fact表入库数量
                imported = 0
                if file_info['domain'] == 'orders':
                    result = await db.execute(text("""
                        SELECT COUNT(*) FROM fact_orders WHERE file_id = :file_id
                    """), {"file_id": file_id})
                    imported = result.scalar() or 0
                else:
                    result = await db.execute(text("""
                        SELECT COUNT(*) FROM fact_product_metrics WHERE source_catalog_id = :file_id
                    """), {"file_id": file_id})
                    imported = result.scalar() or 0
                
                # 查询隔离数量（⭐ v4.12.1修复：使用catalog_file_id字段）
                result = await db.execute(text("""
                    SELECT COUNT(*) FROM data_quarantine WHERE catalog_file_id = :file_id
                """), {"file_id": file_id})
                quarantined = result.scalar() or 0
                
                logs.append({
                    'file_id': file_id,
                    'file_name': file_record.file_name,
                    'status': file_record.status or 'unknown',
                    'staged': file_info['staged'],
                    'imported': imported,
                    'quarantined': quarantined,
                    'domain': file_info['domain']
                })
        
        return {
            "success": True,
            "task_id": task_id,
            "logs": logs,
            "total": len(logs)
        }
        
    except Exception as e:
        logger.error(f"[API] 查询任务日志失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="查询任务日志失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和查询参数，或联系系统管理员",
            status_code=500
        )


@router.get("/auto-ingest/file/{file_id}/logs")
async def get_file_logs(file_id: int, limit: int = Query(50, ge=1, le=200), db: AsyncSession = Depends(get_async_db)):
    """
    通过文件ID获取任务日志（v4.11.5新增）
    
    返回：
    {
        success: bool,
        file_id: int,
        logs: [
            {
                file_id: int,
                file_name: str,
                status: str,
                staged: int,
                imported: int,
                quarantined: int,
                error_message: str,
                duration_seconds: float
            }
        ]
    }
    """
    try:
        from modules.core.db import CatalogFile, StagingOrders, StagingProductMetrics, StagingInventory, DataQuarantine
        from sqlalchemy import func, text
        
        # 获取文件信息
        file_result = await db.execute(select(CatalogFile).where(CatalogFile.id == file_id))
        file_record = file_result.scalar_one_or_none()
        if not file_record:
            return error_response(
                code=ErrorCode.FILE_NOT_FOUND,
                message=f"文件不存在: id={file_id}",
                error_type=get_error_type(ErrorCode.FILE_NOT_FOUND),
                recovery_suggestion="请检查文件ID是否正确，或确认该文件已注册",
                status_code=404
            )
        
        data_domain = file_record.data_domain or "products"
        
        # 查询staging层数据量
        staged = 0
        if data_domain == "orders":
            result = await db.execute(select(func.count(StagingOrders.id)).where(
                StagingOrders.file_id == file_id
            ))
            staged = result.scalar() or 0
        elif data_domain in ["products", "traffic", "analytics"]:
            result = await db.execute(select(func.count(StagingProductMetrics.id)).where(
                StagingProductMetrics.file_id == file_id
            ))
            staged = result.scalar() or 0
        elif data_domain == "inventory":
            result = await db.execute(select(func.count(StagingInventory.id)).where(
                StagingInventory.file_id == file_id
            ))
            staged = result.scalar() or 0
        
        # 查询fact层数据量
        imported = 0
        if data_domain == "orders":
            result = await db.execute(text("""
                SELECT COUNT(*) FROM fact_orders WHERE file_id = :file_id
            """), {"file_id": file_id})
            imported = result.scalar() or 0
        else:
            result = await db.execute(text("""
                SELECT COUNT(*) FROM fact_product_metrics WHERE source_catalog_id = :file_id
            """), {"file_id": file_id})
            imported = result.scalar() or 0
        
        # 查询隔离区数据量（⭐ v4.12.1修复：使用catalog_file_id字段）
        result = await db.execute(text("""
            SELECT COUNT(*) FROM data_quarantine WHERE catalog_file_id = :file_id
        """), {"file_id": file_id})
        quarantined = result.scalar() or 0
        
        # 确定状态
        status = 'ingested'
        if imported == 0 and staged > 0:
            status = 'failed'
        elif quarantined > 0:
            status = 'partial_success'
        elif staged == 0:
            status = 'skipped'
        
        logs = [{
            'file_id': file_id,
            'file_name': file_record.file_name,
            'status': status,
            'staged': staged,
            'imported': imported,
            'quarantined': quarantined,
            'domain': data_domain,
            'error_message': None,
            'duration_seconds': None
        }]
        
        return {
            "success": True,
            "file_id": file_id,
            "logs": logs,
            "total": len(logs)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] 获取文件日志失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取文件日志失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和查询参数，或联系系统管理员",
            status_code=500
        )


class ClearDataRequest(BaseModel):
    """数据库清理请求"""
    confirm: bool = Field(True, description="必须显式确认")


@router.post("/database/clear-all-data")
async def clear_all_data(
    request: ClearDataRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """
    一键清理数据库中所有业务数据（开发阶段使用）
    
    清理范围：
    - 所有事实表（fact_orders, fact_order_items, fact_order_amounts, fact_product_metrics）
    - 所有暂存表（staging_orders, staging_product_metrics）
    - 数据隔离表（data_quarantine）
    - catalog_files状态重置为pending
    
    保留：
    - 维度表（dim_platforms, dim_shops, dim_products等）
    - 配置表（field_mapping_dictionary, field_mapping_templates等）
    - catalog_files元数据（只重置状态）
    
    警告：此操作不可逆！
    """
    if not request.confirm:
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message="必须显式确认：请传递 confirm=true 参数",
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            recovery_suggestion="请设置confirm=true以确认执行清理操作",
            status_code=400
        )
    
    try:
        from sqlalchemy import text
        from backend.models.database import engine
        
        # 清理事实表（使用正确的表名）
        fact_tables = [
            'fact_orders',
            'fact_order_items',
            'fact_order_amounts',  # ⭐ v4.18.2：已不再写入新数据，但保留清理逻辑以清理旧数据
            'fact_product_metrics',
            'fact_expenses_month',
            'fact_expenses_allocated_day_shop_sku'  # 修正表名
        ]
        
        # 清理暂存表
        staging_tables = [
            'staging_orders',
            'staging_product_metrics'
        ]
        
        # 清理数据隔离表
        quarantine_tables = [
            'data_quarantine'
        ]
        
        cleared_counts = {}
        total_cleared = 0
        
        async def safe_truncate_table(table_name: str, use_cascade: bool = True) -> int:
            """
            安全地清理表，如果表不存在则跳过
            
            Returns:
                清理的行数
            """
            try:
                # 先检查表是否存在
                result = await db.execute(text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name = :table_name
                    )
                """), {"table_name": table_name})
                check_result = result.scalar()
                
                if not check_result:
                    logger.info(f"[DB Cleanup] 表 {table_name} 不存在，跳过")
                    cleared_counts[table_name] = 0
                    return 0
                
                # 统计清理前的行数
                result = await db.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                count_before = result.scalar() or 0
                
                if count_before > 0:
                    # 使用SAVEPOINT隔离错误，避免一个表的错误影响其他表
                    await db.execute(text("SAVEPOINT cleanup_table"))
                    try:
                        if use_cascade:
                            await db.execute(text(f"TRUNCATE TABLE {table_name} RESTART IDENTITY CASCADE"))
                        else:
                            await db.execute(text(f"TRUNCATE TABLE {table_name} RESTART IDENTITY"))
                        await db.execute(text("RELEASE SAVEPOINT cleanup_table"))
                    except Exception as e:
                        await db.execute(text("ROLLBACK TO SAVEPOINT cleanup_table"))
                        raise e
                
                cleared_counts[table_name] = count_before
                return count_before
                
            except Exception as e:
                logger.warning(f"[DB Cleanup] 清理表 {table_name} 失败: {e}")
                cleared_counts[table_name] = cleared_counts.get(table_name, 0)
                return 0
        
        # 清理事实表（使用TRUNCATE确保级联删除，并统计清理数量）
        for table in fact_tables:
            count = await safe_truncate_table(table, use_cascade=True)
            total_cleared += count
        
        # 清理暂存表
        for table in staging_tables:
            count = await safe_truncate_table(table, use_cascade=True)
            total_cleared += count
        
        # 清理数据隔离表
        for table in quarantine_tables:
            count = await safe_truncate_table(table, use_cascade=False)
            total_cleared += count
        
        # 重置catalog_files状态为pending（重置所有非pending状态）
        try:
            # 先统计需要重置的文件数（所有非pending状态）
            result = await db.execute(text("""
                SELECT COUNT(*) FROM catalog_files 
                WHERE status != 'pending' OR status IS NULL
            """))
            reset_count = result.scalar() or 0
            cleared_counts['catalog_files_reset'] = reset_count
            if reset_count > 0:
                # 重置所有非pending状态为pending
                await db.execute(text("""
                    UPDATE catalog_files 
                    SET status = 'pending',
                        last_processed_at = NULL
                    WHERE status != 'pending' OR status IS NULL
                """))
                total_cleared += reset_count
                logger.info(f"[DB Cleanup] 重置了 {reset_count} 个catalog_files的状态为pending")
        except Exception as e:
            logger.warning(f"[DB Cleanup] 重置catalog_files状态失败: {e}")
            cleared_counts['catalog_files_reset'] = cleared_counts.get('catalog_files_reset', 0)
 
        await db.commit()

        # 刷新物化视图（清空）
        try:
            with engine.connect() as conn:
                conn = conn.execution_options(isolation_level="AUTOCOMMIT")
                conn.execute(text("REFRESH MATERIALIZED VIEW mv_product_management"))
                conn.execute(text("REFRESH MATERIALIZED VIEW mv_product_sales_trend"))
                conn.execute(text("REFRESH MATERIALIZED VIEW mv_top_products"))
            cleared_counts['materialized_views'] = 'refreshed'
        except Exception as e:
            logger.warning(f"[DB Cleanup] 刷新物化视图失败: {e}")
            cleared_counts['materialized_views'] = 'failed'
 
        # 根据清理结果返回不同的消息
        if total_cleared == 0:
            message = "数据库已为空，无需清理"
            logger.info("[DB Cleanup] 数据库已为空，无需清理")
        else:
            message = f"数据库清理完成，共清理 {total_cleared} 行数据"
            logger.info(f"[DB Cleanup] 数据库清理完成: 共清理 {total_cleared} 行数据")
        
        # ⭐ 修复：使用标准API响应格式
        from backend.utils.api_response import success_response
        return success_response(
            data={
                "rows_cleared": total_cleared,
                "details": cleared_counts
            },
            message=message
        )
        
    except Exception as e:
        await db.rollback()
        logger.error(f"[DB Cleanup] 数据库清理失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="数据库清理失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限，或联系系统管理员",
            status_code=500
        )

