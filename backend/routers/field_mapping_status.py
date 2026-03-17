"""
字段映射API路由 - 状态与管理子模块

包含目录状态、隔离区、进度跟踪、成本填充、数据域管理等端点。
端点: catalog-status, quarantine-summary, progress/{task_id}, progress,
      cost-auto-fill/product, cost-auto-fill/batch-update, cost-auto-fill/auto-fill,
      data-domains, field-mappings/{domain}, bulk-validate, cleanup, needs-shop, assign-shop
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from typing import List, Dict, Any
from datetime import datetime, timezone
from pathlib import Path as _SafePath

from backend.models.database import get_async_db, CatalogFile
from backend.utils.api_response import success_response, error_response
from backend.utils.error_codes import ErrorCode, get_error_type
from backend.services.data_validator import validate_orders, validate_product_metrics
from backend.services.data_importer import get_quarantine_summary
from backend.services.progress_tracker import progress_tracker
from modules.core.logger import get_logger
from backend.routers._field_mapping_helpers import _safe_resolve_path

logger = get_logger(__name__)

router = APIRouter()


@router.get("/catalog-status")
async def get_catalog_status(db: AsyncSession = Depends(get_async_db)):
    """获取目录状态"""
    try:
        total_result = await db.execute(text("SELECT COUNT(*) FROM catalog_files"))
        total_files = total_result.fetchone()[0]
        
        if total_files == 0:
            data = {
                "total": 0,
                "by_status": [
                    {"status": "pending", "count": 0},
                    {"status": "ingested", "count": 0},
                    {"status": "failed", "count": 0}
                ]
            }
            return success_response(data=data, message="获取目录状态成功")
        
        status_result = await db.execute(text("""
            SELECT 
                CASE 
                    WHEN status IS NULL OR status = '' THEN 'pending'
                    ELSE status 
                END as status,
                COUNT(*) as count
            FROM catalog_files 
            GROUP BY 
                CASE 
                    WHEN status IS NULL OR status = '' THEN 'pending'
                    ELSE status 
                END
        """))
        
        status_counts = {row[0]: row[1] for row in status_result.fetchall()}
        
        data = {
            "total": total_files,
            "by_status": [
                {"status": "pending", "count": status_counts.get("pending", 0)},
                {"status": "ingested", "count": status_counts.get("ingested", 0)},
                {"status": "failed", "count": status_counts.get("failed", 0)}
            ]
        }
        
        return success_response(data=data, message="获取目录状态成功")
    except Exception as e:
        logger.error(f"获取目录状态失败: {str(e)}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取目录状态失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )

@router.get("/quarantine-summary")
async def get_quarantine_summary_api(file_id: int = None, db: AsyncSession = Depends(get_async_db)):
    """获取隔离区数据摘要"""
    try:
        summary = get_quarantine_summary(db, file_id)
        return success_response(data={"summary": summary})
    except Exception as e:
        logger.error(f"获取隔离区摘要失败: {e}")
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取隔离区摘要失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )


@router.get("/progress/{task_id}")
async def get_task_progress(task_id: str):
    """获取批量入库任务进度"""
    try:
        progress = await progress_tracker.get_task(task_id)
        if not progress:
            return error_response(
                code=ErrorCode.FILE_NOT_FOUND,
                message=f"任务 {task_id} 不存在",
                error_type=get_error_type(ErrorCode.FILE_NOT_FOUND),
                status_code=404
            )
        return success_response(data={"progress": progress})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取进度失败: {e}")
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取进度失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )


@router.get("/progress")
async def list_task_progress(status: str = None):
    """列出所有任务进度"""
    try:
        tasks = await progress_tracker.list_tasks(status)
        return success_response(data={"tasks": tasks})
    except Exception as e:
        logger.error(f"列出任务失败: {e}")
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="列出任务失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )


@router.get("/cost-auto-fill/product")
async def get_product_cost(platform: str, shop_id: str, sku: str, db: AsyncSession = Depends(get_async_db)):
    """获取商品成本信息"""
    try:
        from backend.services.cost_auto_fill import get_cost_auto_fill_service
        
        cost_service = get_cost_auto_fill_service(db)
        cost_info = cost_service.get_product_cost(platform, shop_id, sku)
        
        if cost_info:
            return success_response(
                data={"cost_info": cost_info},
                message="获取商品成本信息成功"
            )
        else:
            return error_response(
                code=ErrorCode.DATA_NOT_FOUND,
                message="商品成本信息未找到",
                error_type=get_error_type(ErrorCode.DATA_NOT_FOUND),
                detail=f"未找到商品成本信息: platform={platform}, shop_id={shop_id}, sku={sku}",
                recovery_suggestion="请检查商品SKU是否正确,或先添加商品成本信息",
                status_code=404
            )
    except Exception as e:
        logger.error(f"获取商品成本信息失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取商品成本信息失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )

@router.post("/cost-auto-fill/batch-update")
async def batch_update_costs(cost_updates: List[Dict[str, Any]], db: AsyncSession = Depends(get_async_db)):
    """批量更新成本价"""
    try:
        from backend.services.cost_auto_fill import get_cost_auto_fill_service
        
        cost_service = get_cost_auto_fill_service(db)
        result = cost_service.batch_update_costs(cost_updates)
        
        return success_response(
            data={"result": result},
            message="批量更新成本价成功"
        )
    except Exception as e:
        logger.error(f"批量更新成本价失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="批量更新成本价失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )

@router.post("/cost-auto-fill/auto-fill")
async def auto_fill_costs(data: Dict[str, Any], db: AsyncSession = Depends(get_async_db)):
    """自动填充成本价"""
    try:
        from backend.services.cost_auto_fill import get_cost_auto_fill_service
        
        cost_service = get_cost_auto_fill_service(db)
        domain = data.get("domain", "orders")
        rows = data.get("rows", [])
        
        if domain == "orders":
            enhanced_rows = cost_service.auto_fill_cost_for_orders(rows)
        elif domain == "inventory":
            enhanced_rows = cost_service.auto_fill_cost_for_inventory(rows)
        else:
            enhanced_rows = rows
        
        data = {
            "enhanced_rows": enhanced_rows,
            "original_count": len(rows),
            "enhanced_count": len(enhanced_rows)
        }
        
        return success_response(data=data, message="成本价自动填充成功")
    except Exception as e:
        logger.error(f"自动填充成本价失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message="自动填充成本价失败",
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            detail=str(e),
            status_code=500
        )

@router.get("/data-domains")
async def get_supported_data_domains():
    """获取支持的数据域列表"""
    data = {
        "domains": [
            {
                "code": "orders",
                "name": "订单数据",
                "description": "销售订单、订单明细、客户信息",
                "fields": ["order_id", "product_id", "quantity", "total_amount", "order_date"]
            },
            {
                "code": "inventory", 
                "name": "库存数据",
                "description": "实时库存、库存流水、仓库管理",
                "fields": ["product_id", "quantity_on_hand", "quantity_available", "avg_cost", "warehouse_code"]
            },
            {
                "code": "finance",
                "name": "财务数据", 
                "description": "应收账款、收款记录、费用管理",
                "fields": ["ar_amount_cny", "received_amount_cny", "invoice_date", "due_date", "ar_status"]
            },
            {
                "code": "products",
                "name": "商品数据",
                "description": "商品信息、商品指标、商品表现",
                "fields": ["product_id", "product_name", "page_views", "conversion_rate", "gmv"]
            },
            {
                "code": "analytics",
                "name": "分析数据",
                "description": "流量分析、转化分析、用户行为",
                "fields": ["date", "visits", "page_views", "bounce_rate", "avg_session_duration"]
            }
        ]
    }
    
    return success_response(data=data, message="获取数据域列表成功")

@router.get("/field-mappings/{domain}")
async def get_domain_field_mappings(domain: str):
    """获取指定数据域的标准字段映射"""
    from backend.services.field_mapping.mapper import COMPREHENSIVE_ALIAS_DICTIONARY
    
    domain_fields = {
        "orders": ["order_id", "product_id", "quantity", "total_amount", "order_date", "buyer_id", "order_status"],
        "inventory": ["product_id", "quantity_on_hand", "quantity_available", "avg_cost", "warehouse_code", "safety_stock"],
        "finance": ["ar_amount_cny", "received_amount_cny", "invoice_date", "due_date", "ar_status", "payment_method"],
        "products": ["product_id", "product_name", "page_views", "conversion_rate", "gmv", "rating"],
        "analytics": ["date", "visits", "page_views", "bounce_rate", "avg_session_duration"]
    }
    
    target_fields = domain_fields.get(domain, [])
    
    domain_mappings = {}
    for alias, standard in COMPREHENSIVE_ALIAS_DICTIONARY.items():
        if standard in target_fields:
            domain_mappings[alias] = standard
    
    data = {
        "domain": domain,
        "target_fields": target_fields,
        "mappings": domain_mappings
    }
    
    return success_response(data=data, message="获取字段映射成功")

@router.post("/bulk-validate")
async def bulk_validate_data(payload: Dict[str, Any]):
    """批量验证多种数据域"""
    try:
        from backend.services.enhanced_data_validator import (
            validate_inventory, 
            validate_finance,
            validate_order_inventory_relation,
            validate_order_finance_relation
        )
        
        results = {}
        
        if "orders" in payload:
            orders_data = payload["orders"]
            results["orders"] = validate_orders(orders_data)
        
        if "inventory" in payload:
            inventory_data = payload["inventory"]
            results["inventory"] = validate_inventory(inventory_data)
        
        if "finance" in payload:
            finance_data = payload["finance"]
            results["finance"] = validate_finance(finance_data)
        
        if "orders" in payload and "inventory" in payload:
            results["order_inventory_relation"] = validate_order_inventory_relation(
                payload["orders"], payload["inventory"]
            )
        
        if "orders" in payload and "finance" in payload:
            results["order_finance_relation"] = validate_order_finance_relation(
                payload["orders"], payload["finance"]
            )
        
        return success_response(
            data={"validation_results": results},
            message="批量验证完成"
        )
    except Exception as e:
        logger.error(f"批量验证失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message="批量验证失败",
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            detail=str(e),
            status_code=500
        )


@router.post("/cleanup")
async def cleanup_invalid_files(db: AsyncSession = Depends(get_async_db)):
    """清理无效文件(基于 catalog_files)。"""
    try:
        rows_result = await db.execute(select(CatalogFile))
        rows = rows_result.scalars().all()
        orphaned_count = 0
        orphaned_files = []
        valid_count = 0

        for r in rows:
            try:
                if r.file_path and r.file_path.strip():
                    safe_path = _safe_resolve_path(r.file_path)
                    if _SafePath(safe_path).exists():
                        valid_count += 1
                        continue
                orphaned_files.append({
                    "id": r.id,
                    "file_name": r.file_name,
                    "platform": r.platform_code,
                    "domain": r.data_domain,
                    "last_path": r.file_path,
                })
                await db.delete(r)
                orphaned_count += 1
            except Exception as e:
                orphaned_files.append({
                    "id": r.id,
                    "file_name": r.file_name,
                    "platform": r.platform_code,
                    "domain": r.data_domain,
                    "last_path": r.file_path,
                    "error": str(e)
                })
                await db.delete(r)
                orphaned_count += 1

        await db.commit()
        
        data = {
            "total_checked": len(rows),
            "orphaned_removed": orphaned_count,
            "valid_remaining": valid_count,
            "orphaned_files": orphaned_files[:20]
        }
        
        return success_response(
            data=data,
            message=f"清理完成,删除了 {orphaned_count} 个无效文件记录"
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"文件清理失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="文件清理失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )


@router.get("/needs-shop")
async def get_needs_shop_files(db: AsyncSession = Depends(get_async_db)):
    """
    获取待指派店铺的文件列表(status='needs_shop')
    """
    try:
        stmt = select(CatalogFile).where(CatalogFile.status == 'needs_shop').order_by(CatalogFile.first_seen_at.desc())
        result = await db.execute(stmt)
        files = result.scalars().all()
        
        files_data = []
        for f in files:
            file_dict = {
                'id': f.id,
                'file_name': f.file_name,
                'platform_code': f.platform_code or 'unknown',
                'data_domain': f.data_domain or 'unknown',
                'granularity': f.granularity or 'unknown',
                'status': f.status,
                'file_path': f.file_path,
                'account': f.account or '',
                'shop_resolution': None
            }
            
            if f.file_metadata:
                try:
                    import json
                    metadata = json.loads(f.file_metadata) if isinstance(f.file_metadata, str) else f.file_metadata
                    if 'shop_resolution' in metadata:
                        file_dict['shop_resolution'] = metadata['shop_resolution']
                except Exception:
                    pass
            
            files_data.append(file_dict)
        
        return success_response(
            data={
                'files': files_data,
                'count': len(files_data)
            },
            message="获取待指派店铺文件列表成功"
        )
    except Exception as e:
        logger.error(f"获取needs_shop文件失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取待指派店铺文件列表失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )


@router.post("/assign-shop")
async def assign_shop_to_files(request: dict, db: AsyncSession = Depends(get_async_db)):
    """
    批量指派店铺到文件
    
    请求体:
    {
        "file_ids": [1, 2, 3],
        "shop_id": "shop_12345",
        "auto_retry_ingest": true
    }
    """
    try:
        file_ids = request.get("file_ids", [])
        shop_id = request.get("shop_id", "").strip()
        auto_retry = request.get("auto_retry_ingest", False)
        
        if not file_ids:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="未提供file_ids",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                detail="请求体中必须包含file_ids数组",
                recovery_suggestion="请在请求体中提供file_ids数组",
                status_code=400
            )
        if not shop_id:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="未提供shop_id",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                detail="请求体中必须包含shop_id",
                recovery_suggestion="请在请求体中提供shop_id",
                status_code=400
            )
        
        updated_count = 0
        retried_count = 0
        
        for file_id in file_ids:
            catalog_file_result = await db.execute(select(CatalogFile).where(CatalogFile.id == file_id))
            catalog_file = catalog_file_result.scalar_one_or_none()
            if not catalog_file:
                continue
            
            catalog_file.shop_id = shop_id
            
            if catalog_file.status == 'needs_shop':
                catalog_file.status = 'pending'
            
            meta = catalog_file.file_metadata or {}
            if 'shop_resolution' not in meta:
                meta['shop_resolution'] = {}
            meta['shop_resolution']['manual_assigned'] = True
            meta['shop_resolution']['assigned_at'] = datetime.now(timezone.utc).isoformat()
            catalog_file.file_metadata = meta
            
            updated_count += 1
        
        await db.commit()
        
        if auto_retry and updated_count > 0:
            try:
                from modules.services.ingestion_worker import run_once
                stats = run_once(limit=len(file_ids))
                retried_count = stats.succeeded + stats.failed
            except Exception as retry_err:
                logger.warning(f"自动重试入库失败: {retry_err}")
        
        data = {
            "updated_count": updated_count,
            "shop_id": shop_id,
            "retried_ingest": retried_count if auto_retry else None
        }
        
        return success_response(
            data=data,
            message=f"成功指派{updated_count}个文件到店铺{shop_id}"
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"批量指派店铺失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="批量指派店铺失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )
