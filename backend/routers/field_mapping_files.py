"""
字段映射API路由 - 文件管理子模块

包含文件分组、扫描、预览等文件操作相关的端点。
端点: file-groups, bulk-ingest, scan-files-by-date, files, scan, file-info, files-by-period
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, or_, and_
from typing import List, Dict, Any
from datetime import date as date_class
from pathlib import Path

from backend.models.database import get_async_db, CatalogFile
from backend.utils.api_response import success_response, error_response
from backend.utils.error_codes import ErrorCode, get_error_type
from backend.services.data_validator import validate_orders, validate_product_metrics, validate_services
from backend.services.data_importer import (
    stage_orders,
    stage_product_metrics,
    upsert_orders,
    upsert_product_metrics,
    quarantine_failed_data,
)
from backend.services.progress_tracker import progress_tracker
from modules.core.logger import get_logger
from backend.routers._field_mapping_helpers import (
    file_path_resolver,
    _safe_resolve_path,
)

logger = get_logger(__name__)

router = APIRouter()

@router.get("/file-groups")
async def get_file_groups(db: AsyncSession = Depends(get_async_db)):
    """
    获取文件分组信息(方案B+优化版)
    
    返回格式:
    {
        "platforms": ["shopee", "tiktok", "miaoshou"],
        "domains": {
            "orders": ["daily", "weekly", "monthly"],
            "products": ["daily", "weekly", "monthly", "snapshot"]
        },
        "files": {
            "shopee": {
                "orders": ["shopee_orders_monthly_xxx.xls", ...],
                "products": ["shopee_products_daily_xxx.xlsx", ...]
            },
            "tiktok": {...}
        }
    }
    """
    try:
        # 方案B+:查询source_platform(数据来源)和platform_code(采集平台)
        # 优先使用source_platform,如果为NULL则使用platform_code
        # 仅允许白名单平台,防止遗留/脏数据(如日期/unknown)进入平台下拉
        platforms_result = await db.execute(text("""
            SELECT DISTINCT LOWER(COALESCE(source_platform, platform_code)) AS p
            FROM catalog_files
            WHERE (source_platform IS NOT NULL AND source_platform <> '')
               OR (platform_code IS NOT NULL AND platform_code <> '')
            AND LOWER(COALESCE(source_platform, platform_code)) IN ('shopee','tiktok','miaoshou')
            ORDER BY p
        """))
        platforms = [row[0] for row in platforms_result]
        
        # 增强:如果表为空或无数据,返回空结构而非崩溃
        if not platforms:
            logger.warning("catalog_files表为空,返回空数据结构")
            data = {
                "platforms": [],
                "domains": {},
                "files": {}
            }
            return success_response(data=data, message="获取文件分组成功(无数据)")
        
        # 根据数据采集模块的实际数据域配置
        actual_domains = {
            "analytics": ["daily", "weekly", "monthly"],
            "products": ["daily", "weekly", "monthly", "snapshot"],
            "orders": ["daily", "weekly", "monthly"],
            "finance": ["daily", "weekly", "monthly"],
            "services": ["daily", "weekly", "monthly", "agent", "ai_assistant"],
            "inventory": ["snapshot"]
        }
        
        # 查询实际存在的数据域
        domains_result = await db.execute(text("""
            SELECT DISTINCT data_domain, granularity
            FROM catalog_files 
            WHERE data_domain IS NOT NULL 
            AND data_domain != ''
            AND data_domain != 'unknown'
            ORDER BY data_domain, granularity
        """))
        
        domains = {}
        for row in domains_result:
            domain = row[0]
            granularity = row[1]
            if domain not in domains:
                domains[domain] = []
            if granularity not in domains[domain]:
                domains[domain].append(granularity)
        
        # 补充实际配置中的数据域,确保所有配置的域都显示
        for domain, granularities in actual_domains.items():
            if domain not in domains:
                domains[domain] = granularities
            else:
                for granularity in granularities:
                    if granularity not in domains[domain]:
                        domains[domain].append(granularity)
        
        # 查询所有文件(返回id与关键元数据)
        files_result = await db.execute(text("""
            SELECT id, 
                   COALESCE(source_platform, platform_code) AS platform,
                   data_domain, 
                   file_name, 
                   sub_domain, 
                   granularity, 
                   date_from, 
                   date_to
            FROM catalog_files 
            WHERE (source_platform IS NOT NULL AND source_platform <> '')
               OR (platform_code IS NOT NULL AND platform_code <> '')
              AND data_domain IS NOT NULL
              AND file_name IS NOT NULL
              AND LOWER(COALESCE(source_platform, platform_code)) IN ('shopee','tiktok','miaoshou')
            ORDER BY platform, data_domain, file_name
        """))
        
        files = {}
        for row in files_result:
            _id = row[0]
            platform = row[1]
            domain = row[2]
            file_name = row[3]
            sub_domain = row[4] if row[4] else ''
            granularity = row[5]
            date_from = row[6]
            date_to = row[7]
            
            platform = platform.lower() if platform else None
            if not platform:
                continue
            
            if platform not in files:
                files[platform] = {}
            if domain not in files[platform]:
                files[platform][domain] = []
            
            files[platform][domain].append({
                "id": _id,
                "file_name": file_name,
                "sub_domain": sub_domain,
                "granularity": granularity,
                "date_from": str(date_from) if date_from else None,
                "date_to": str(date_to) if date_to else None,
            })
        
        data = {
            "platforms": platforms,
            "domains": domains,
            "files": files,
            "groups": files
        }
        
        return success_response(data=data)
        
    except Exception as e:
        logger.error(f"获取文件分组失败: {str(e)}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取文件分组失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )

@router.post("/bulk-ingest")
async def bulk_ingest(payload: dict, db: AsyncSession = Depends(get_async_db)):
    """批量入库(支持进度跟踪)"""
    import uuid
    
    try:
        platform = payload.get("platform")
        domain = payload.get("domain")
        batches = payload.get("batches", [])
        
        task_id = str(uuid.uuid4())
        await progress_tracker.create_task(task_id, len(batches), "bulk_ingest")
        await progress_tracker.update_task(task_id, {"status": "processing"})

        total_staged, total_imported, total_quarantined = 0, 0, 0
        total_valid, total_error = 0, 0
        results = []
        
        for idx, b in enumerate(batches):
            file_name = b.get("file_name", f"batch_{idx}")
            file_id = b.get("file_id")
            rows = b.get("rows", [])
            
            try:
                await progress_tracker.update_task(task_id, {
                    "current_file": file_name,
                    "processed_files": idx,
                    "total_rows": await progress_tracker.get_task(task_id).get("total_rows", 0) + len(rows)
                })
                
                validation_result = None
                if domain == "orders":
                    validation_result = validate_orders(rows)
                elif domain == "services":
                    validation_result = validate_services(rows)
                elif domain == "inventory":
                    from backend.services.enhanced_data_validator import validate_inventory
                    validation_result = validate_inventory(rows)
                else:
                    validation_result = validate_product_metrics(rows)
                
                quarantined_count = 0
                target_file_id = None
                if file_id:
                    target_file_id = int(file_id)
                else:
                    try:
                        cf_result = await db.execute(select(CatalogFile).where(CatalogFile.file_name == file_name))
                        cf = cf_result.scalar_one_or_none()
                        if cf:
                            target_file_id = cf.id
                    except Exception:
                        target_file_id = None
                
                header_row = b.get("header_row", 0)
                if header_row is None:
                    header_row = 0
                
                if validation_result.get("errors") and target_file_id:
                    quarantined_count = quarantine_failed_data(db, target_file_id, validation_result, header_row=header_row)
                    await db.commit()
                
                valid_rows = []
                error_rows = set()
                for error in validation_result.get("errors", []):
                    error_rows.add(error.get("row", 0))
                
                for row_idx, row in enumerate(rows):
                    if row_idx not in error_rows:
                        valid_rows.append(row)
                
                staged, imported = 0, 0
                if valid_rows:
                    file_record = None
                    if target_file_id:
                        file_record_result = await db.execute(select(CatalogFile).where(CatalogFile.id == target_file_id))
                        file_record = file_record_result.scalar_one_or_none()
                    
                    if domain == "orders":
                        staged = stage_orders(db, valid_rows, ingest_task_id=task_id, file_id=target_file_id)
                        imported = upsert_orders(db, valid_rows, file_record=file_record)
                    else:
                        staged = stage_product_metrics(db, valid_rows, ingest_task_id=task_id, file_id=target_file_id)
                        imported = upsert_product_metrics(db, valid_rows, file_record=file_record)
                
                total_staged += staged
                total_imported += imported
                total_quarantined += quarantined_count
                total_valid += len(valid_rows)
                total_error += len(error_rows)
                
                current_progress = await progress_tracker.get_task(task_id)
                await progress_tracker.update_task(task_id, {
                    "processed_files": idx + 1,
                    "processed_rows": current_progress.get("processed_rows", 0) + len(rows),
                    "valid_rows": current_progress.get("valid_rows", 0) + len(valid_rows),
                    "error_rows": current_progress.get("error_rows", 0) + len(error_rows),
                    "quarantined_rows": current_progress.get("quarantined_rows", 0) + quarantined_count
                })
                
                results.append({
                    "file": file_name,
                    "total_rows": len(rows),
                    "valid_rows": len(valid_rows),
                    "error_rows": len(error_rows),
                    "staged": staged,
                    "imported": imported,
                    "quarantined": quarantined_count
                })
                
            except Exception as file_error:
                await progress_tracker.add_error(task_id, f"处理文件 {file_name} 失败: {str(file_error)}")
                results.append({
                    "file": file_name,
                    "error": str(file_error)
                })
        
        await progress_tracker.complete_task(task_id, success=True)

        data = {
            "task_id": task_id,
            "staged": total_staged,
            "imported": total_imported,
            "quarantined": total_quarantined,
            "validation": {
                "total_files": len(batches),
                "valid_rows": total_valid,
                "error_rows": total_error
            },
            "results": results
        }
        
        return success_response(
            data=data,
            message="批量入库完成"
        )
    except Exception as e:
        if 'task_id' in locals():
            await progress_tracker.complete_task(task_id, success=False, error=str(e))
        logger.error(f"批量入库失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="批量入库失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )


@router.get("/scan-files-by-date")
async def scan_files_by_date(platform: str, domain: str, date: str, base_dir: str = "downloads"):
    """按平台/域/日期扫描目录并返回匹配文件列表(简单策略:文件名包含平台与日期Token)。"""
    try:
        root = Path(base_dir)
        if not root.exists():
            return success_response(data={"files": []})
        date_token = date.replace('-', '')
        exts = {'.xlsx', '.xls', '.csv', '.tsv', '.html', '.htm'}
        files: List[str] = []
        for p in root.rglob('*'):
            if p.is_file() and p.suffix.lower() in exts:
                name = p.name.lower()
                if platform.lower() in name and date_token in name:
                    files.append(str(p.as_posix()))
        return success_response(data={"files": files[:1000]})
    except Exception as e:
        logger.error(f"扫描文件失败: {e}")
        return error_response(
            code=ErrorCode.FILE_OPERATION_ERROR,
            message="扫描文件失败",
            error_type=get_error_type(ErrorCode.FILE_OPERATION_ERROR),
            detail=str(e),
            status_code=500
        )


@router.get("/files")
async def get_files(db: AsyncSession = Depends(get_async_db)):
    """获取文件列表(基于 catalog_files)。"""
    try:
        rows_result = await db.execute(select(CatalogFile))
        rows = rows_result.scalars().all()
        data = [{
            "id": r.id,
            "file_name": r.file_name,
            "platform": r.platform_code,
            "source_platform": r.source_platform,
            "data_domain": r.data_domain,
            "status": r.status,
            "discovery_time": r.first_seen_at.isoformat() if r.first_seen_at else None
        } for r in rows]
        
        return success_response(data=data, message="获取文件列表成功")
    except Exception as e:
        logger.error(f"获取文件列表失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取文件列表失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )


@router.post("/scan")
async def scan_files(db: AsyncSession = Depends(get_async_db)):
    """扫描文件(完整版:调用catalog_scanner服务)"""
    try:
        from modules.services.catalog_scanner import scan_and_register
        from modules.core.path_manager import get_data_raw_dir
        
        scan_dir = get_data_raw_dir()
        
        logger.info(f"开始扫描文件: {scan_dir}")
        result = scan_and_register(str(scan_dir))
        logger.info(f"扫描完成: 发现{result.seen}个文件, 新注册{result.registered}个, 跳过{result.skipped}个")

        data = {
            "total_files": result.seen,
            "registered": result.registered,
            "orphaned_removed": 0,
            "db_records": result.seen,
            "new_file_ids": result.new_file_ids,
            "auto_ingest": [],
            "sync_triggered": False,
        }
        
        return success_response(
            data=data,
            message="文件扫描完成，已完成目录注册，未触发自动入库"
        )
    except Exception as e:
        logger.error(f"扫描失败: {str(e)}", exc_info=True)
        return error_response(
            code=ErrorCode.FILE_OPERATION_ERROR,
            message="扫描失败",
            error_type=get_error_type(ErrorCode.FILE_OPERATION_ERROR),
            detail=str(e),
            status_code=500
        )

@router.get("/file-info")
async def get_file_info(file_id: int, db: AsyncSession = Depends(get_async_db)):
    """
    获取文件详细信息(v4.3.1:从catalog_files查询,毫秒级响应)
    包括:元数据、完整路径、文件状态
    """
    try:
        logger.info(f"[FileInfo] 查询: id={file_id}")
        
        catalog_result = await db.execute(
            select(CatalogFile).where(CatalogFile.id == file_id)
        )
        catalog_record = catalog_result.scalar_one_or_none()
        
        if not catalog_record:
            logger.warning(f"[FileInfo] 未找到: id={file_id}")
            return error_response(
                code=ErrorCode.DATA_NOT_FOUND,
                message="文件未注册",
                error_type=get_error_type(ErrorCode.DATA_NOT_FOUND),
                detail="文件未注册,请点击'扫描采集文件'刷新",
                recovery_suggestion="请先扫描采集文件,确保文件已注册到系统中",
                status_code=404
            )
        
        file_path = catalog_record.file_path
        file_exists = Path(file_path).exists() if file_path else False
        file_size = Path(file_path).stat().st_size if file_exists else None
        
        shop_resolution = None
        if catalog_record.file_metadata:
            try:
                import json
                metadata = json.loads(catalog_record.file_metadata) if isinstance(catalog_record.file_metadata, str) else catalog_record.file_metadata
                shop_resolution = metadata.get('shop_resolution')
            except Exception:
                pass
        
        data = {
            "file_name": catalog_record.file_name,
            "parsed_metadata": {
                "timestamp": catalog_record.first_seen_at.strftime("%Y%m%d_%H%M%S") if catalog_record.first_seen_at else "unknown",
                "account": catalog_record.account or "N/A",
                "shop": catalog_record.shop_id or "none",
                "data_type": catalog_record.data_domain or "products",
                "granularity": catalog_record.granularity or "daily",
                "date_range": f"{catalog_record.date_from} 到 {catalog_record.date_to}" if catalog_record.date_from and catalog_record.date_to else "N/A",
                "platform": catalog_record.platform_code or catalog_record.source_platform or "unknown"
            },
            "shop_resolution": shop_resolution,
            "actual_path": file_path,
            "file_exists": file_exists,
            "file_size": file_size
        }
        
        logger.info(f"[FileInfo] 成功: platform={catalog_record.platform_code}, exists={file_exists}")
        return success_response(data=data, message="获取文件信息成功")
        
    except Exception as e:
        logger.error(f"[FileInfo] 失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取文件信息失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )


@router.get("/files-by-period")
async def get_files_by_period(
    year: int,
    month: int = None,
    data_domain: str = None,
    source_platform: str = None,
    granularity: str = None,
    db: AsyncSession = Depends(get_async_db)
):
    """
    按时间周期查询文件(方案B+:自动处理跨月/跨年数据)
    
    查询原理:
    - 基于数据时间范围(date_from/date_to)而非物理分区
    - 自动包含跨月周数据(如2025-09-30到2025-10-06)
    - 自动包含跨年周数据(如2025-12-30到2026-01-05)
    """
    try:
        if month:
            month_start = date_class(year, month, 1)
            if month == 12:
                month_end = date_class(year + 1, 1, 1)
            else:
                month_end = date_class(year, month + 1, 1)
            
            date_filter = or_(
                and_(
                    CatalogFile.date_from >= month_start,
                    CatalogFile.date_from < month_end
                ),
                and_(
                    CatalogFile.date_to >= month_start,
                    CatalogFile.date_to < month_end
                ),
                and_(
                    CatalogFile.date_from < month_start,
                    CatalogFile.date_to >= month_end
                )
            )
        else:
            year_start = date_class(year, 1, 1)
            year_end = date_class(year + 1, 1, 1)
            
            date_filter = or_(
                and_(
                    CatalogFile.date_from >= year_start,
                    CatalogFile.date_from < year_end
                ),
                and_(
                    CatalogFile.date_to >= year_start,
                    CatalogFile.date_to < year_end
                ),
                and_(
                    CatalogFile.date_from < year_start,
                    CatalogFile.date_to >= year_end
                )
            )
        
        stmt = select(CatalogFile).where(date_filter)
        
        if data_domain:
            stmt = stmt.where(CatalogFile.data_domain == data_domain)
        if source_platform:
            stmt = stmt.where(CatalogFile.source_platform == source_platform)
        if granularity:
            stmt = stmt.where(CatalogFile.granularity == granularity)
        
        stmt = stmt.order_by(CatalogFile.date_from, CatalogFile.file_name)
        result = await db.execute(stmt)
        files = result.scalars().all()
        
        data = {
            "period": f"{year}-{month:02d}" if month else str(year),
            "total_files": len(files),
            "files": [
                {
                    "file_name": f.file_name,
                    "source_platform": f.source_platform,
                    "data_domain": f.data_domain,
                    "sub_domain": f.sub_domain,
                    "granularity": f.granularity,
                    "date_from": str(f.date_from) if f.date_from else None,
                    "date_to": str(f.date_to) if f.date_to else None,
                    "quality_score": f.quality_score,
                    "storage_layer": f.storage_layer,
                    "status": f.status
                }
                for f in files
            ]
        }
        
        return success_response(data=data, message="查询文件成功")
        
    except Exception as e:
        logger.error(f"查询文件失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="查询文件失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )
