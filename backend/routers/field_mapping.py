"""
字段映射API路由 - 西虹ERP系统
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text  # v4.3.3: 用于needs-shop等查询
from typing import List, Dict, Any
from datetime import datetime
import re

from backend.models.database import get_db, get_async_db, FieldMapping, CatalogFile
from backend.utils.api_response import success_response, error_response, pagination_response
from backend.utils.error_codes import ErrorCode, get_error_type
from backend.services.auto_ingest_orchestrator import get_auto_ingest_orchestrator
# Excel parser is now imported inline where needed
from backend.services.field_mapping.mapper import suggest_mappings
from backend.services.data_validator import validate_orders, validate_product_metrics, validate_services
from backend.services.file_path_resolver import get_file_path_resolver
from backend.services.data_importer import (
    stage_orders,
    stage_product_metrics,
    stage_inventory,  # ⭐ v4.11.4新增：库存数据暂存
    upsert_orders,
    upsert_product_metrics,
    quarantine_failed_data,
    get_quarantine_summary,
)
from backend.services.data_standardizer import standardize_rows  # 新增：数据标准化服务
from backend.services.progress_tracker import progress_tracker
from backend.services.field_mapping_dictionary_service import get_dictionary_service  # v4.3.7
from backend.services.currency_extractor import get_currency_extractor  # ⭐ v4.15.0新增
from modules.core.logger import get_logger
from pathlib import Path

# 设置日志记录器
logger = get_logger(__name__)

router = APIRouter()

# 获取文件路径解析器（兼容保留，后续不再直接用文件系统搜索）
file_path_resolver = get_file_path_resolver()

# ---------------------- 安全路径校验 ----------------------
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
        p = (project_root / p).resolve()

    for root in allowed_roots:
        if _is_subpath(p, root):
            return str(p)

    return error_response(
        code=ErrorCode.DATA_VALIDATION_FAILED,
        message="文件路径不在允许的根目录内",
        error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
        recovery_suggestion="请检查文件路径是否在允许的根目录内，或联系系统管理员",
        status_code=400
    )

@router.get("/file-groups")
async def get_file_groups(db: AsyncSession = Depends(get_async_db)):
    """
    获取文件分组信息（方案B+优化版）
    
    返回格式：
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
        from sqlalchemy import text
        
        # 方案B+：查询source_platform（数据来源）和platform_code（采集平台）
        # 优先使用source_platform，如果为NULL则使用platform_code
        # 仅允许白名单平台，防止遗留/脏数据（如日期/unknown）进入平台下拉
        platforms_result = await db.execute(text("""
            SELECT DISTINCT LOWER(COALESCE(source_platform, platform_code)) AS p
            FROM catalog_files
            WHERE (source_platform IS NOT NULL AND source_platform <> '')
               OR (platform_code IS NOT NULL AND platform_code <> '')
            AND LOWER(COALESCE(source_platform, platform_code)) IN ('shopee','tiktok','miaoshou')
            ORDER BY p
        """))
        platforms = [row[0] for row in platforms_result]
        
        # 增强：如果表为空或无数据，返回空结构而非崩溃
        if not platforms:
            logger.warning("catalog_files表为空，返回空数据结构")
            data = {
                "platforms": [],
                "domains": {},
                "files": {}
            }
            return success_response(data=data, message="获取文件分组成功（无数据）")
        
        # 根据数据采集模块的实际数据域配置
        # 参考 modules/platforms/shopee/components/config_registry.py 中的 DataDomain 枚举
        actual_domains = {
            "analytics": ["daily", "weekly", "monthly"],  # 客流/流量表现（v4.10.0统一：traffic域已废弃）
            "products": ["daily", "weekly", "monthly", "snapshot"],  # 商品表现
            "orders": ["daily", "weekly", "monthly"],  # 订单表现
            "finance": ["daily", "weekly", "monthly"],  # 财务表现
            "services": ["daily", "weekly", "monthly", "agent", "ai_assistant"],  # 服务表现
            "inventory": ["snapshot"]  # v4.10.0新增：库存快照数据
            # traffic域已废弃（v4.10.0），统一使用analytics域
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
        
        # 补充实际配置中的数据域，确保所有配置的域都显示
        for domain, granularities in actual_domains.items():
            if domain not in domains:
                domains[domain] = granularities
            else:
                # 合并实际存在的粒度和配置的粒度
                for granularity in granularities:
                    if granularity not in domains[domain]:
                        domains[domain].append(granularity)
        
        # 查询所有文件（返回id与关键元数据）
        # ⭐ 修复：使用COALESCE优先使用source_platform，如果为NULL则使用platform_code
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
            platform = row[1]  # 使用COALESCE后的platform
            domain = row[2]
            file_name = row[3]
            sub_domain = row[4] if row[4] else ''
            granularity = row[5]
            date_from = row[6]
            date_to = row[7]
            
            # 标准化平台代码为小写
            platform = platform.lower() if platform else None
            if not platform:
                continue
            
            if platform not in files:
                files[platform] = {}
            if domain not in files[platform]:
                files[platform][domain] = []
            
            # 文件信息包含 id 与基础元数据（用于前端展示与精确定位）
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
            "groups": files  # 兼容新前端（groups别名）
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
    """批量入库（支持进度跟踪）"""
    import uuid
    
    try:
        platform = payload.get("platform")
        domain = payload.get("domain")
        batches = payload.get("batches", [])  # [{file_name, rows:[], mappings:{}}]
        
        # 创建进度跟踪任务
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
                # 更新当前处理文件
                await progress_tracker.update_task(task_id, {
                    "current_file": file_name,
                    "processed_files": idx,
                    "total_rows": await progress_tracker.get_task(task_id).get("total_rows", 0) + len(rows)
                })
                
                # 数据验证（根据数据域选择正确的验证函数）
                validation_result = None
                if domain == "orders":
                    validation_result = validate_orders(rows)
                elif domain == "services":
                    # ⭐ v4.6.1新增：services域使用专门的验证函数（不需要product_id）
                    validation_result = validate_services(rows)
                elif domain == "inventory":
                    # ⭐ v4.10.0新增：inventory域使用专门的验证函数
                    from backend.services.enhanced_data_validator import validate_inventory
                    validation_result = validate_inventory(rows)
                else:
                    # products/traffic/analytics等其他域使用产品指标验证
                    validation_result = validate_product_metrics(rows)
                
                # 隔离失败数据（优先使用 file_id；否则通过 file_name 解析为 CatalogFile.id）
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
                # ⭐ v4.6.1修复：获取header_row信息
                header_row = b.get("header_row", 0)  # ⭐ 修复：统一使用0-based
                if header_row is None:
                    header_row = 0
                
                if validation_result.get("errors") and target_file_id:
                    quarantined_count = quarantine_failed_data(db, target_file_id, validation_result, header_row=header_row)
                    await db.commit()
                
                # 只处理通过验证的数据
                valid_rows = []
                error_rows = set()
                for error in validation_result.get("errors", []):
                    error_rows.add(error.get("row", 0))
                
                for row_idx, row in enumerate(rows):
                    if row_idx not in error_rows:
                        valid_rows.append(row)
                
                # 数据入库
                staged, imported = 0, 0
                if valid_rows:
                    # ⭐ v4.6.1修复：获取file_record以传递platform_code等信息
                    file_record = None
                    if target_file_id:
                        file_record_result = await db.execute(select(CatalogFile).where(CatalogFile.id == target_file_id))
                        file_record = file_record_result.scalar_one_or_none()
                    
                    if domain == "orders":
                        staged = stage_orders(db, valid_rows, ingest_task_id=task_id, file_id=target_file_id)  # ⭐ v4.11.4新增：传递task_id和file_id
                        imported = upsert_orders(db, valid_rows, file_record=file_record)  # ⭐ v4.6.1修复：传递file_record
                    else:
                        staged = stage_product_metrics(db, valid_rows, ingest_task_id=task_id, file_id=target_file_id)  # ⭐ v4.11.4新增：传递task_id和file_id
                        imported = upsert_product_metrics(db, valid_rows, file_record=file_record)  # ⭐ v4.6.3修复：传递file_record，解决双维护问题
                
                total_staged += staged
                total_imported += imported
                total_quarantined += quarantined_count
                total_valid += len(valid_rows)
                total_error += len(error_rows)
                
                # 更新进度
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
        
        # 完成任务
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
    """按平台/域/日期扫描目录并返回匹配文件列表（简单策略：文件名包含平台与日期Token）。"""
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
    """获取文件列表（基于 catalog_files）。"""
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

AUTO_INGEST_MAX_PER_SCAN = 20


@router.post("/scan")
async def scan_files(db: AsyncSession = Depends(get_async_db)):
    """扫描文件（完整版：调用catalog_scanner服务）"""
    try:
        from modules.services.catalog_scanner import scan_and_register
        from modules.core.path_manager import get_data_raw_dir
        
        # 使用统一路径管理（修复工作目录问题）
        scan_dir = get_data_raw_dir()
        
        logger.info(f"开始扫描文件: {scan_dir}")
        result = scan_and_register(str(scan_dir))
        logger.info(f"扫描完成: 发现{result.seen}个文件, 新注册{result.registered}个, 跳过{result.skipped}个")

        auto_ingest_results: List[Dict[str, Any]] = []
        new_file_ids = result.new_file_ids[:AUTO_INGEST_MAX_PER_SCAN]

        if result.new_file_ids:
            if len(result.new_file_ids) > AUTO_INGEST_MAX_PER_SCAN:
                logger.warning(
                    "[AutoIngest] 本次扫描新增文件 %s 个，超过限制 %s 个，"
                    "仅自动处理前 %s 个。其余将在定时任务中处理。",
                    len(result.new_file_ids),
                    AUTO_INGEST_MAX_PER_SCAN,
                    AUTO_INGEST_MAX_PER_SCAN,
                )

            orchestrator = get_auto_ingest_orchestrator(db)

            for file_id in new_file_ids:
                try:
                    ingest_result = await orchestrator.ingest_single_file(
                        file_id=file_id,
                        only_with_template=True,
                        allow_quarantine=True,
                    )
                    auto_ingest_results.append(ingest_result)
                except Exception as ingest_error:
                    logger.error(
                        "[AutoIngest] 扫描后自动入库失败: file_id=%s, error=%s",
                        file_id,
                        ingest_error,
                        exc_info=True,
                    )
                    auto_ingest_results.append(
                        {
                            "success": False,
                            "file_id": file_id,
                            "status": "failed",
                            "message": str(ingest_error),
                        }
                    )
        
        data = {
            "total_files": result.seen,
            "registered": result.registered,
            "orphaned_removed": 0,
            "db_records": result.seen,
            "new_file_ids": result.new_file_ids,
            "auto_ingest": auto_ingest_results,
        }
        
        return success_response(data=data, message="文件扫描完成")
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
    获取文件详细信息（v4.3.1：从catalog_files查询，毫秒级响应）
    包括：元数据、完整路径、文件状态
    """
    try:
        logger.info(f"[FileInfo] 查询: id={file_id}")
        
        # 从catalog_files查询
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
                detail="文件未注册，请点击'扫描采集文件'刷新",
                recovery_suggestion="请先扫描采集文件，确保文件已注册到系统中",
                status_code=404
            )
        
        # 读取catalog数据
        file_path = catalog_record.file_path
        file_exists = Path(file_path).exists() if file_path else False
        file_size = Path(file_path).stat().st_size if file_exists else None
        
        # 提取shop_resolution信息（从file_metadata）
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
                "account": catalog_record.account or "N/A",  # ⭐ 从.meta.json提取
                "shop": catalog_record.shop_id or "none",
                "data_type": catalog_record.data_domain or "products",
                "granularity": catalog_record.granularity or "daily",
                "date_range": f"{catalog_record.date_from} 到 {catalog_record.date_to}" if catalog_record.date_from and catalog_record.date_to else "N/A",
                "platform": catalog_record.platform_code or catalog_record.source_platform or "unknown"
            },
            "shop_resolution": shop_resolution,  # v4.3.4: 店铺解析置信度信息
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
    按时间周期查询文件（方案B+：自动处理跨月/跨年数据）
    
    查询原理：
    - 基于数据时间范围（date_from/date_to）而非物理分区
    - 自动包含跨月周数据（如2025-09-30到2025-10-06）
    - 自动包含跨年周数据（如2025-12-30到2026-01-05）
    
    示例：
    - /files-by-period?year=2025&month=9&data_domain=products
      → 返回所有包含2025年9月数据的文件（包括跨月）
    - /files-by-period?year=2025
      → 返回所有包含2025年数据的文件（包括跨年）
    """
    from sqlalchemy import or_, and_
    from datetime import date as date_class
    
    try:
        if month:
            # 查询某个月（包括跨月数据）
            month_start = date_class(year, month, 1)
            if month == 12:
                month_end = date_class(year + 1, 1, 1)
            else:
                month_end = date_class(year, month + 1, 1)
            
            # 日期范围条件：数据与目标月有交集
            date_filter = or_(
                # 情况1：数据起始在目标月
                and_(
                    CatalogFile.date_from >= month_start,
                    CatalogFile.date_from < month_end
                ),
                # 情况2：数据结束在目标月
                and_(
                    CatalogFile.date_to >= month_start,
                    CatalogFile.date_to < month_end
                ),
                # 情况3：数据跨越目标月
                and_(
                    CatalogFile.date_from < month_start,
                    CatalogFile.date_to >= month_end
                )
            )
        else:
            # 查询某一年（包括跨年数据）
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
        
        # 构建查询
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


@router.post("/preview")
async def preview_file(file_data: dict, db: AsyncSession = Depends(get_async_db)):
    """
    预览文件数据（v4.3.1优化版：从catalog_files查询路径，毫秒级响应）
    
    性能优化：
    1. 从PostgreSQL数据库查询file_path（毫秒级）
    2. 只读取前100行数据（秒级）
    3. 避免递归搜索文件系统（避免超时）
    """
    file_id = int(file_data.get("file_id", 0))
    header_row = int(file_data.get("header_row", 0))  # ⭐ 修复：统一使用0-based
    
    logger.info(f"[Preview] 开始预览: id={file_id}")
    
    try:
        # Step 1: 从catalog_files查询文件路径（毫秒级）
        catalog_result = await db.execute(
            select(CatalogFile).where(CatalogFile.id == file_id)
        )
        catalog_record = catalog_result.scalar_one_or_none()
        
        if not catalog_record:
            return error_response(
                code=ErrorCode.DATA_NOT_FOUND,
                message="文件未注册",
                error_type=get_error_type(ErrorCode.DATA_NOT_FOUND),
                detail=f"文件未注册: id={file_id}",
                recovery_suggestion="请先扫描采集文件，确保文件已注册到系统中",
                status_code=404
            )
        
        file_path = catalog_record.file_path
        logger.info(f"[Preview] 文件路径: {file_path}")
        
        # Step 2: 路径安全校验与存在性验证
        safe_path = _safe_resolve_path(file_path)
        if not Path(safe_path).exists():
            return error_response(
                code=ErrorCode.DATA_NOT_FOUND,
                message="文件不存在",
                error_type=get_error_type(ErrorCode.DATA_NOT_FOUND),
                detail=f"文件不存在: {file_path}",
                recovery_suggestion="请检查文件路径是否正确，或重新扫描采集文件",
                status_code=404
            )
        
        # Step 3: 读取Excel（使用智能解析器，自动检测格式）
        from backend.services.excel_parser import ExcelParser
        
        # ⭐ 修复：header_row已经是0-based（与pandas一致），直接使用
        # pandas的header参数：0表示第0行，None表示无表头
        if header_row < 0:
            header_param = None  # 负数表示无表头
        else:
            header_param = header_row  # ⭐ 修复：直接使用，不需要减1
        
        # 使用智能Excel解析器（自动检测文件格式）
        # 大文件保护：>10MB 的文件只读50行
        file_size_mb = Path(safe_path).stat().st_size / (1024 * 1024)
        preview_rows = 50 if file_size_mb > 10 else 100
        
        logger.info(f"[Preview] 文件大小: {file_size_mb:.2f}MB, 预览行数: {preview_rows}")
        
        df = ExcelParser.read_excel(
            safe_path,
            header=header_param,
            nrows=preview_rows
        )
        # 规范化（通用合并单元格还原，v4.6.0增强版）
        # v4.6.0变更：大文件也处理关键列，不跳过规范化
        normalization_report = {}
        try:
            df, normalization_report = ExcelParser.normalize_table(
                df,
                data_domain=catalog_record.data_domain or "products",
                file_size_mb=file_size_mb  # v4.6.0新增：传入文件大小，大文件只处理关键列
            )
            if file_size_mb > 10:
                logger.info(f"[Preview] 大文件规范化完成（只处理关键列）: {file_size_mb:.2f}MB")
        except Exception as norm_error:
            logger.warning(f"[Preview] 规范化失败（使用原始数据）: {norm_error}", exc_info=True)
            normalization_report = {"filled_columns": [], "filled_rows": 0, "strategy": "none", "error": str(norm_error)}
        
        # Step 4: 数据清洗
        df.columns = [str(col).strip() for col in df.columns]
        df = df.dropna(how='all')
        df = df.fillna('')
        
        # Step 5: 转换为前端格式
        columns = df.columns.tolist()
        # ⭐ v4.7.0增强：增加预览行数（从20行增加到100行）
        preview_rows_limit = 100
        data = df.head(preview_rows_limit).to_dict('records')
        
        data = {
            "file_path": file_path,
            "file_name": catalog_record.file_name,
            "file_size": Path(file_path).stat().st_size,
            "columns": columns,
            "data": data,
            "total_rows": len(df),
            "preview_rows": len(data),
            "preview_limit": preview_rows_limit,  # ⭐ v4.7.0新增：显示预览限制
            
            # 方案B+新字段
            "source_platform": catalog_record.source_platform,
            "data_domain": catalog_record.data_domain,
            "sub_domain": catalog_record.sub_domain,
            "granularity": catalog_record.granularity,
            "quality_score": catalog_record.quality_score,
            "storage_layer": catalog_record.storage_layer or 'raw',
            "date_from": str(catalog_record.date_from) if catalog_record.date_from else None,
            "date_to": str(catalog_record.date_to) if catalog_record.date_to else None,
            "normalization_report": normalization_report,
            
            # 兼容性字段
            "platform": catalog_record.platform_code,
        }
        
        logger.info(f"[Preview] 成功: {len(columns)}列, {len(data)}行, 质量={catalog_record.quality_score}")
        return success_response(data=data, message="文件预览成功")
        
    except Exception as e:
        logger.error(f"[Preview] 失败: {e}", exc_info=True)
        
        # 结构化错误返回（避免前端显示"Network Error"）
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message="文件预览失败",
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            detail=str(e)[:500],
            recovery_suggestion="建议：1) 检查文件格式是否正确；2) 尝试在Excel中重新导出为标准.xlsx；3) 联系技术支持",
            status_code=500
        )

@router.post("/generate-mapping")
async def generate_field_mapping(mapping_data: dict):
    """生成字段映射（智能映射算法）"""
    try:
        columns = mapping_data.get("columns", [])
        domain = mapping_data.get("domain", "products")
        platform = mapping_data.get("platform", "shopee")
        granularity = mapping_data.get("granularity", "daily")
        
        # 根据数据域定义标准字段
        standard_fields = {
            "products": {
                "product_id": "商品ID",
                "product_name": "商品名称", 
                "price": "价格",
                "stock": "库存",
                "sales": "销量",
                "rating": "评分",
                "category": "分类",
                "brand": "品牌",
                "sku": "SKU",
                "description": "描述",
                "image_url": "图片链接",
                "status": "状态"
            },
            "orders": {
                "order_id": "订单ID",
                "order_date": "订单日期",
                "customer_id": "客户ID",
                "total_amount": "订单金额",
                "status": "订单状态",
                "payment_method": "支付方式",
                "shipping_address": "收货地址"
            },
            "analytics": {
                "date": "日期",
                "page_views": "页面浏览量",
                "visitors": "访客数",
                "bounce_rate": "跳出率",
                "conversion_rate": "转化率"
            },
            "finance": {
                "date": "日期",
                "revenue": "收入",
                "cost": "成本",
                "profit": "利润",
                "currency": "货币"
            },
            "services": {
                "date": "日期",
                "service_type": "服务类型",
                "response_time": "响应时间",
                "satisfaction": "满意度",
                "agent_id": "客服ID"
            }
        }
        
        # 智能字段映射算法
        mappings = []
        domain_fields = standard_fields.get(domain, standard_fields["products"])
        
        for column in columns:
            column_lower = column.lower()
            best_match = None
            best_confidence = 0.0
            match_method = "none"
            
            # 精确匹配
            for std_field, std_name in domain_fields.items():
                if column_lower == std_field.lower() or column_lower == std_name.lower():
                    best_match = std_field
                    best_confidence = 1.0
                    match_method = "exact_match"
                    break
            
            # 模糊匹配
            if not best_match:
                for std_field, std_name in domain_fields.items():
                    # 关键词匹配
                    keywords = {
                        "product_id": ["product", "id", "商品", "id"],
                        "product_name": ["product", "name", "商品", "名称", "title"],
                        "price": ["price", "价格", "cost", "费用"],
                        "stock": ["stock", "库存", "quantity", "数量"],
                        "sales": ["sales", "销量", "sold", "售出"],
                        "rating": ["rating", "评分", "score", "评价"],
                        "category": ["category", "分类", "type", "类型"],
                        "brand": ["brand", "品牌", "manufacturer"],
                        "sku": ["sku", "code", "编码"],
                        "description": ["description", "描述", "desc", "detail"],
                        "image_url": ["image", "图片", "photo", "url"],
                        "status": ["status", "状态", "state"]
                    }
                    
                    if std_field in keywords:
                        for keyword in keywords[std_field]:
                            if keyword in column_lower:
                                confidence = 0.8
                                if confidence > best_confidence:
                                    best_match = std_field
                                    best_confidence = confidence
                                    match_method = "fuzzy_match"
                                break
            
            # 关键词匹配
            if not best_match:
                for std_field, std_name in domain_fields.items():
                    if std_field in column_lower or std_name in column:
                        confidence = 0.6
                        if confidence > best_confidence:
                            best_match = std_field
                            best_confidence = confidence
                            match_method = "keyword"
            
            mappings.append({
                "original": column,
                "standard": best_match or "未映射",
                "confidence": best_confidence,
                "method": match_method
            })
        
        data = {
            "mappings": mappings,
            "source": "ai_generated",
            "domain": domain,
            "platform": platform,
            "granularity": granularity
        }
        
        return success_response(data=data, message="字段映射生成成功")
    except Exception as e:
        logger.error(f"生成字段映射失败: {str(e)}", exc_info=True)
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message="生成字段映射失败",
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            detail=str(e),
            status_code=500
        )

@router.post("/ingest")
async def ingest_file(
    ingest_data: dict, 
    db: AsyncSession = Depends(get_async_db),
    extract_images: bool = True  # v3.0新增：是否提取图片（默认true）
):
    """
    数据入库（集成隔离机制 + v3.0图片提取）
    
    v3.0增强：
    - 数据入库后，自动后台提取Excel中的产品图片
    - 不阻塞入库响应（异步处理）
    """
    try:
        file_id = int(ingest_data.get("file_id", 0))
        platform = ingest_data.get("platform", "")
        # ⭐ v4.6.1修复：同时支持domain和data_domain字段
        domain = ingest_data.get("domain") or ingest_data.get("data_domain", "")
        mappings = ingest_data.get("mappings", {})  # 向后兼容：保留mappings参数
        header_columns = ingest_data.get("header_columns", [])  # ⭐ v4.6.0新增：原始表头字段列表
        rows = ingest_data.get("rows", [])  # 已按标准字段映射后的行（预览数据，实际会重新读取文件）
        header_row = ingest_data.get("header_row", 0)  # ⭐ 修复：统一使用0-based，默认0（与数据库定义一致）
        if header_row is None:
            header_row = 0  # ⭐ 修复：统一使用0-based
        
        # ⭐ v4.11.5新增：接收task_id参数（批量入库时传递，单文件入库时为空）
        task_id = ingest_data.get("task_id")
        # 如果task_id为空，使用single_file_{file_id}作为默认值（单文件入库）
        if not task_id:
            task_id = f"single_file_{file_id}" if file_id else None

        # 获取文件记录（CatalogFile）
        file_record_result = await db.execute(select(CatalogFile).where(CatalogFile.id == file_id))
        file_record = file_record_result.scalar_one_or_none()
        if not file_record:
            return error_response(
                code=ErrorCode.DATA_NOT_FOUND,
                message="文件记录不存在",
                error_type=get_error_type(ErrorCode.DATA_NOT_FOUND),
                detail="文件记录不存在",
                recovery_suggestion="请先扫描采集文件，确保文件已注册到系统中",
                status_code=404
            )
        
        # ⭐ v4.6.1修复：如果domain为空，从文件记录中获取（二次确认）
        if not domain and file_record.data_domain:
            domain = file_record.data_domain
            logger.info(f"[Ingest] 从文件记录获取data_domain（二次确认）: {domain}")
        
        # ⭐ v4.6.1修复：记录domain用于调试
        # ⭐ v4.10.0增强：记录header_row用于调试（确保入库时使用正确的表头行）
        logger.info(f"[Ingest] 数据域: {domain}, header_row: {header_row} (0-based, Excel第{header_row+1}行)")
        
        # ⭐ v4.6.1新增：重复入库防护（全0文件）
        if file_record.status == "ingested":
            # 检查是否已标记为全0文件（使用error_message字段存储标识）
            error_msg = file_record.error_message or ""
            if "[全0数据标识]" in error_msg:
                data = {
                    "message": "该文件已识别为全0数据文件，无需重复入库。所有数值字段均为0，这是正常情况（如采集期间无业务）。",
                    "staged": 0,
                    "imported": 0,
                    "amount_imported": 0,
                    "quarantined": 0,
                    "skipped": True,
                    "skip_reason": "all_zero_data_already_processed"
                }
                return success_response(data=data)

        # ⭐ v4.7.0修复：重新读取完整文件，而不是使用前端传入的预览数据
        # 这样可以确保入库所有数据行，而不受预览限制（20行）的影响
        logger.info(f"[Ingest] 开始重新读取完整文件: {file_record.file_path}")
        
        from backend.services.excel_parser import ExcelParser
        from pathlib import Path
        
        # 路径安全校验
        safe_path = _safe_resolve_path(file_record.file_path)
        if not Path(safe_path).exists():
            return error_response(
                code=ErrorCode.DATA_NOT_FOUND,
                message="文件不存在",
                error_type=get_error_type(ErrorCode.DATA_NOT_FOUND),
                detail=f"文件不存在: {file_record.file_path}",
                recovery_suggestion="请检查文件路径是否正确，或重新扫描采集文件",
                status_code=404
            )
        
        # ⭐ 修复：header_row已经是0-based（与pandas一致），直接使用
        # pandas的header参数：0表示第0行，None表示无表头
        if header_row < 0:
            header_param = None  # 负数表示无表头
        else:
            header_param = header_row  # ⭐ 修复：直接使用，不需要减1
        
        # ⭐ v4.10.0增强：记录实际使用的header_param值（用于调试）
        logger.info(f"[Ingest] 实际使用的表头行: header_param={header_param} (0-based, Excel第{header_param+1 if header_param is not None else '无表头'}行)")
        
        # 读取完整文件（不限制行数）
        try:
            df = ExcelParser.read_excel(
                safe_path,
                header=header_param,
                nrows=None  # ⭐ 不限制行数，读取全部数据
            )
            
            # 规范化（通用合并单元格还原，v4.6.0增强版）
            file_size_mb = Path(safe_path).stat().st_size / (1024 * 1024)
            normalization_report = {}
            try:
                df, normalization_report = ExcelParser.normalize_table(
                    df,
                    data_domain=domain or "products",
                    file_size_mb=file_size_mb  # v4.6.0新增：传入文件大小，大文件只处理关键列
                )
                if file_size_mb > 10:
                    logger.info(f"[Ingest] 大文件规范化完成（只处理关键列）: {file_size_mb:.2f}MB")
            except Exception as norm_error:
                logger.warning(f"[Ingest] 规范化失败（使用原始数据）: {norm_error}", exc_info=True)
                normalization_report = {"filled_columns": [], "filled_rows": 0, "strategy": "none", "error": str(norm_error)}
            
            # 数据清洗
            df.columns = [str(col).strip() for col in df.columns]
            df = df.dropna(how='all')
            df = df.fillna('')
            
            # 转换为字典列表
            all_rows = df.to_dict('records')
            logger.info(f"[Ingest] 读取完整文件成功: {len(all_rows)}行数据")
            
        except Exception as read_error:
            logger.error(f"[Ingest] 读取文件失败: {read_error}", exc_info=True)
            return error_response(
                code=ErrorCode.FILE_OPERATION_ERROR,
                message="读取文件失败",
                error_type=get_error_type(ErrorCode.FILE_OPERATION_ERROR),
                detail=str(read_error),
                recovery_suggestion="请检查文件格式是否正确，或尝试重新导出文件",
                status_code=500
            )
        
        # ⭐ v4.6.0 DSS架构：使用新的B类数据表结构
        # 如果提供了header_columns，使用RawDataImporter直接入库到fact_raw_data表
        # 否则，使用旧的字段映射逻辑（向后兼容）
        
        # ⭐ v4.16.0修复：始终使用文件原始的列名（包含货币代码）用于追溯和货币代码提取
        # 即使传入了归一化的header_columns（来自模板），也要使用文件原始列名
        file_original_columns = list(df.columns)  # 文件原始列名（包含货币代码）
        original_header_columns = file_original_columns  # 始终使用文件原始列名
        
        # 获取header_columns（用于向后兼容，但实际使用file_original_columns）
        if not header_columns:
            header_columns = file_original_columns
            logger.info(f"[Ingest] 未提供header_columns，从DataFrame获取: {len(header_columns)}个字段")
        else:
            logger.info(f"[Ingest] 使用传入的header_columns: {len(header_columns)}个字段（但实际使用文件原始列名）")
        
        # ⭐ v4.6.0 DSS架构：直接使用原始数据（不进行字段映射）
        # 原始数据将作为JSONB存储在raw_data字段中
        enhanced_rows = all_rows  # 使用原始数据，保留所有原始列名
        
        # 向后兼容：如果提供了mappings，记录日志但不使用（DSS架构不需要字段映射）
        processed_mappings = {}
        if mappings:
            for orig_col, mapping_info in mappings.items():
                if isinstance(mapping_info, dict):
                    processed_mappings[orig_col] = mapping_info
                elif isinstance(mapping_info, str):
                    processed_mappings[orig_col] = {"standard_field": mapping_info, "confidence": 0.95}
            logger.info(f"[Ingest] 检测到mappings参数（{len(processed_mappings)}个），DSS架构将忽略，直接使用原始数据")
        
        logger.info(f"[Ingest] [DSS] 准备入库原始数据到B类数据表，{len(enhanced_rows)}行，{len(header_columns)}个字段")
        
        # ⭐ DSS架构：跳过数据标准化，保留原始数据
        # DSS架构原则：数据同步只做数据采集和存储，数据标准化在Metabase中完成
        logger.info(f"[Ingest] [DSS] 跳过数据标准化，保留原始数据格式")
        
        # ⭐ DSS架构：移除特殊处理，保留原始数据
        # DSS架构原则：不修改原始数据，所有数据处理在Metabase中完成
        logger.info(f"[Ingest] [DSS] 跳过特殊处理，保留原始数据完整性")
        
        # ⭐ DSS架构：跳过数据验证，直接使用所有数据
        # DSS架构原则：数据同步只做去重和入库，不做业务逻辑验证
        # 业务逻辑验证应在Metabase中完成（Metabase知道字段映射关系）
        logger.info(f"[Ingest] [DSS] 跳过数据验证，所有{len(enhanced_rows)}行数据将直接进入去重和入库流程")
        validation_result = {
            "errors": [],
            "warnings": [],
            "ok_rows": len(enhanced_rows),
            "total": len(enhanced_rows)
        }
        quarantined_count = 0  # DSS架构下不隔离数据

        # ⭐ DSS架构：使用所有数据（不筛选）
        valid_rows = enhanced_rows  # 直接使用所有数据，不做验证筛选

        # ⭐ v4.6.0 DSS架构：数据入库到B类数据表
        staged = 0
        imported = 0
        amount_imported = 0  # ⭐ v4.18.2移除：订单金额维度表功能已移除，此变量保持为0用于向后兼容
        
        if valid_rows:
            # ⭐ v4.6.0 DSS架构：优先使用RawDataImporter入库到fact_raw_data表
            try:
                from backend.services.raw_data_importer import RawDataImporter
                from backend.services.deduplication_service import DeduplicationService
                
                # 获取granularity（从file_record或默认值）
                granularity = file_record.granularity if file_record.granularity else "daily"
                if not granularity:
                    # 根据domain推断默认granularity
                    granularity = "snapshot" if domain == "inventory" else "daily"
                
                logger.info(f"[Ingest] DSS架构：准备入库到B类数据表，domain={domain}, granularity={granularity}")
                
                # 初始化服务
                raw_data_importer = RawDataImporter(db)
                deduplication_service = DeduplicationService(db)
                
                # ⭐ 修复：batch_calculate_data_hash接收字典列表，不是DataFrame
                # 批量计算data_hash
                data_hashes = deduplication_service.batch_calculate_data_hash(valid_rows)
                
                # ⭐ v4.15.0新增：货币代码提取和字段名归一化
                currency_extractor = get_currency_extractor()
                normalized_rows = []
                currency_codes = []
                
                for row in valid_rows:
                    # 归一化字段名（移除货币代码部分）
                    normalized_row = {}
                    for field_name, value in row.items():
                        normalized_field_name = currency_extractor.normalize_field_name(field_name)
                        normalized_row[normalized_field_name] = value
                    normalized_rows.append(normalized_row)
                    
                    # ⭐ v4.16.0修复：提取货币代码时使用文件原始列名（row.keys()），而不是归一化的header_columns
                    # 原因：归一化的header_columns已经移除了货币代码，无法提取
                    # 使用 row.keys() 获取文件原始的字段名（包含货币代码）
                    currency_code = currency_extractor.extract_currency_from_row(
                        row,
                        header_columns=None  # ⭐ 修复：传入None，让方法使用row.keys()（原始字段名）
                    )
                    currency_codes.append(currency_code)
                
                # ⭐ v4.16.0新增：获取sub_domain（services域必须提供）
                sub_domain_value = None
                if file_record and hasattr(file_record, 'sub_domain'):
                    sub_domain_value = file_record.sub_domain
                
                # ⭐ v4.16.0修复：准备归一化的header_columns用于动态列管理
                # 动态列应该使用归一化的列名（不包含货币代码），避免创建重复的列
                normalized_header_columns = currency_extractor.normalize_field_list(original_header_columns)
                
                # 批量插入到B类数据表
                imported = raw_data_importer.batch_insert_raw_data(
                    rows=normalized_rows,  # ⭐ v4.15.0更新：使用归一化后的数据
                    data_hashes=data_hashes,
                    data_domain=domain,
                    granularity=granularity,
                    platform_code=file_record.platform_code or platform,
                    shop_id=file_record.shop_id,
                    file_id=file_record.id,
                    header_columns=normalized_header_columns,  # ⭐ v4.16.0修复：使用归一化的header_columns用于动态列管理（避免创建重复列）
                    currency_codes=currency_codes,  # ⭐ v4.15.0新增：货币代码列表
                    sub_domain=sub_domain_value,  # ⭐ v4.16.0新增：子类型（services域必须提供）
                    original_header_columns=original_header_columns  # ⭐ v4.16.0新增：原始header_columns（包含货币代码，用于保存到数据库）
                )
                
                # ⭐ v4.16.0更新：日志信息包含sub_domain
                table_suffix = f"{domain}_{granularity}"
                if sub_domain_value:
                    table_suffix = f"{domain}_{sub_domain_value}_{granularity}"
                logger.info(f"[Ingest] DSS架构：成功入库 {imported} 条记录到 fact_raw_data_{table_suffix}")
                
                # ⭐ 修复：如果DSS架构入库成功，设置staged并跳过旧逻辑
                staged = imported
                
            except Exception as dss_error:
                logger.error(f"[Ingest] DSS架构入库失败，降级到旧逻辑: {dss_error}", exc_info=True)
                # 降级到旧的入库逻辑（向后兼容）
            # ⭐ v4.11.5修复：使用传入的task_id（批量入库时使用批量task_id，单文件入库时使用single_file_{file_id}）
            
            if domain == "orders":
                staged = stage_orders(db, valid_rows, ingest_task_id=task_id, file_id=file_id)  # ⭐ v4.11.5修复：使用传入的task_id
                imported = upsert_orders(db, valid_rows, file_record=file_record)  # ⭐ v4.6.1修复：传递file_record
                
                # ⭐ v4.18.2移除：订单金额维度表功能已移除
                # 原因：DSS架构下，数据已完整存储在 b_class.fact_raw_data_orders_* 表的 JSONB 字段中
                # 货币代码已提取到 currency_code 系统字段，字段名已归一化
                # 数据标准化应在 Metabase 中完成，该表属于"只写不读"的冗余数据
                # 如需订单金额统计，请通过 Metabase 查询 b_class.fact_raw_data_orders_* 表
            elif domain == "inventory":
                # ⭐ v4.10.0新增：inventory域数据入库到fact_product_metrics表
                # ⭐ v4.11.5修复：使用传入的task_id
                staged = stage_inventory(db, valid_rows, ingest_task_id=task_id, file_id=file_id)  # ⭐ v4.11.5修复：使用传入的task_id
                # 确保inventory域数据设置data_domain='inventory'和granularity='snapshot'
                for row in valid_rows:
                    row['data_domain'] = 'inventory'
                    if not row.get('granularity'):
                        row['granularity'] = 'snapshot'
                imported = upsert_product_metrics(db, valid_rows, file_record=file_record, data_domain='inventory')
            else:
                # products/traffic/analytics等其他域使用产品指标验证
                staged = stage_product_metrics(db, valid_rows, ingest_task_id=task_id, file_id=file_id)  # ⭐ v4.11.5修复：使用传入的task_id
                imported = upsert_product_metrics(db, valid_rows, file_record=file_record)  # ⭐ v4.6.3修复：传递file_record，解决双维护问题

        # 更新文件状态
        if validation_result.get("errors"):
            file_record.status = "partial_success"
        else:
            file_record.status = "ingested"
        try:
            # 新字段命名校验：部分代码库用 last_processed_at
            setattr(file_record, "last_processed_at", datetime.now())
        except Exception:
            file_record.last_processed = datetime.now()
        await db.commit()
        
        # v3.0新增：异步提取图片（不阻塞响应）
        image_extraction_started = False
        if extract_images and imported > 0:
            try:
                # 导入后台任务（延迟导入，避免循环依赖）
                from backend.tasks.image_extraction import extract_product_images_task
                
                # 提交后台任务
                extract_product_images_task.delay(
                    file_id=file_id,
                    file_path=file_record.file_path,
                    platform_code=platform,
                    shop_id=file_record.shop_id or "unknown"
                )
            except (ImportError, Exception) as e:
                # 捕获Redis连接错误，不影响主流程
                error_type = type(e).__name__
                if "OperationalError" in error_type or "ConnectionError" in error_type:
                    logger.warning(
                        f"[字段映射] Redis/Celery连接失败（{error_type}），跳过图片提取任务"
                    )
                else:
                    logger.warning(
                        f"[字段映射] 图片提取任务调用失败（{error_type}），跳过"
                    )
                
                image_extraction_started = True
                logger.info(f"[Ingest] 图片提取任务已提交: file_id={file_id}")
                
            except ImportError:
                logger.warning("[Ingest] Celery未配置，图片提取任务跳过（同步模式下可手动调用）")
            except Exception as img_error:
                logger.warning(f"[Ingest] 图片提取任务提交失败（继续）: {img_error}")

        # v4.5.1新增：优化0条入库的提示（解决问题3）
        # ⭐ v4.6.1增强：全0数据识别和重复入库防护
        if imported == 0:
            # 检查是否为全0数据（增强版）
            all_zero = check_if_all_zero_data(valid_rows, domain, processed_mappings)
            
            # 分析原因
            reasons = []
            if quarantined_count > 0:
                reasons.append(f"{quarantined_count}条因数据质量问题被隔离")
            if len(valid_rows) == 0 and len(error_rows) > 0:
                reasons.append(f"所有{len(error_rows)}条记录验证失败")
            
            if all_zero:
                reasons.append("数据源本身所有数值列均为0（非系统错误）")
                
                # ⭐ v4.6.1新增：标记全0文件，防止重复入库（使用error_message字段）
                existing_msg = file_record.error_message or ""
                file_record.error_message = existing_msg + f"\n[全0数据标识] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - 所有数值字段为0，已识别"
                await db.commit()
                
                message = f"入库成功，但导入0条有效记录。原因：{'; '.join(reasons) if reasons else '数据源无有效记录'}。\n提示：数据源所有数值字段均为0，这是正常情况（如采集期间无业务），无需查看隔离区。"
            else:
                message = f"入库成功，但导入0条有效记录。原因：{'; '.join(reasons) if reasons else '数据源无有效记录'}"
        else:
            message = f"入库完成，成功导入{imported}条记录"
        
        # ⭐ v4.18.2移除：订单金额维度表功能已移除，amount_imported 始终为 0
        # 保留此逻辑用于向后兼容，但不会再有维度表入库信息
        
        data = {
            "message": message,  # ✅ 更详细的提示
            "staged": staged, 
            "imported": imported,
            "amount_imported": amount_imported,  # ⭐ v4.18.2：已移除，始终为0用于向后兼容
            "quarantined": quarantined_count,
            "image_extraction": "processing" if image_extraction_started else "skipped",
            "validation": {
                "total_rows": len(mapped_rows),  # ⭐ v4.7.0修复：使用完整文件行数（映射后）
                "preview_rows": len(rows) if rows else 0,  # 预览行数（用于参考）
                "valid_rows": len(valid_rows),
                "error_rows": len(error_rows),
                "warnings": len(validation_result.get("warnings", []))
            },
            # v4.5.1新增：详细分析（解决问题3）
            "analysis": {
                "all_zero_data": check_if_all_zero_data(valid_rows, domain, processed_mappings) if imported == 0 else False,
                "quarantine_summary": get_quarantine_summary(db, file_record.id) if quarantined_count > 0 else None
            }
        }
        
        return success_response(data=data, message=message)
    except Exception as e:
        await db.rollback()
        logger.error(f"[Ingest] 入库失败: {e}", exc_info=True)
        # ⭐ v4.7.0增强：提供更详细的错误信息
        error_detail = str(e)
        if hasattr(e, '__cause__') and e.__cause__:
            error_detail = f"{error_detail}\n原因: {str(e.__cause__)}"
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="数据入库失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=error_detail,
            status_code=500
        )


def check_if_all_zero_data(rows: List[Dict], domain: str, mappings: Dict = None) -> bool:
    """
    检查数据是否全为0（v4.6.1增强 - 检查所有数值字段）
    
    用于区分：
    - 数据源本身为0（正常情况，如采集期间无业务）
    - 系统错误导致0条（异常情况）
    
    Args:
        rows: 数据行列表
        domain: 数据域
        mappings: 字段映射（可选，用于识别数值字段）
        
    Returns:
        True: 所有数值列均为0
        False: 有非0数值
    """
    if not rows:
        return False
    
    # ⭐ v4.6.1增强：自动检测所有数值字段
    numeric_fields = set()
    
    # 方法1：从映射中识别数值字段（基于字段名模式，避免数据库查询）
    if mappings:
        # 数值字段常见后缀和关键词
        numeric_keywords = ['amount', 'price', 'qty', 'quantity', 'count', 'rate', 'ratio', 
                           'sales', 'revenue', 'cost', 'profit', 'stock', 'inventory',
                           'views', 'visitors', 'conversion', 'refund', 'gmv']
        
        for orig_col, mapping_info in mappings.items():
            if isinstance(mapping_info, dict):
                std_field = mapping_info.get('standard_field')
            else:
                std_field = mapping_info
            
            if std_field and std_field != '未映射':
                # 检查字段名是否包含数值关键词
                std_field_lower = std_field.lower()
                if any(keyword in std_field_lower for keyword in numeric_keywords):
                    numeric_fields.add(std_field)
    
    # 方法2：从预定义字段补充（兜底）
    numeric_fields_by_domain = {
        "orders": ["total_amount", "qty", "gmv", "unit_price", "sales_amount", "refund_amount"],
        "products": ["page_views", "unique_visitors", "sales_amount", "stock"],
        "traffic": ["page_views", "unique_visitors", "conversion_rate", "visitor_count", "chat_inquiry_count"],
        "services": ["amount"]
    }
    
    predefined_fields = numeric_fields_by_domain.get(domain, [])
    numeric_fields.update(predefined_fields)
    
    # 方法3：从数据行中自动检测数值字段（最全面）
    if rows:
        first_row = rows[0]
        for key, value in first_row.items():
            if value is not None:
                try:
                    # 尝试转换为数值
                    float_val = float(value)
                    # 如果是数值类型，且不是ID/日期字段
                    if not any(kw in key.lower() for kw in ['id', 'date', 'time', '编号', '日期', '时间']):
                        numeric_fields.add(key)
                except (ValueError, TypeError):
                    pass
    
    if not numeric_fields:
        return False  # 无法判断
    
    # 检查所有行的数值字段
    non_zero_found = False
    for row in rows:
        for field in numeric_fields:
            value = row.get(field)
            if value is not None:
                try:
                    float_val = float(value)
                    if abs(float_val) > 1e-10:  # 使用小的阈值避免浮点误差
                        non_zero_found = True
                        break
                except (ValueError, TypeError):
                    pass
        if non_zero_found:
            break
    
    return not non_zero_found  # 如果没有找到非0值，说明全为0


@router.post("/validate")
async def validate_data(payload: dict):
    """数据验证接口（支持库存、财务和订单关联验证）"""
    try:
        from backend.services.enhanced_data_validator import (
            validate_inventory, 
            validate_finance,
            validate_order_inventory_relation,
            validate_order_finance_relation
        )
        
        domain = payload.get("domain", "orders")
        rows = payload.get("rows", [])
        
        # 基础验证（根据数据域选择正确的验证函数）
        if domain == "orders":
            result = validate_orders(rows)
        elif domain == "inventory":
            result = validate_inventory(rows)
        elif domain == "finance":
            result = validate_finance(rows)
        elif domain == "services":
            # ⭐ v4.6.1新增：services域使用专门的验证函数（不需要product_id）
            result = validate_services(rows)
        else:
            result = validate_product_metrics(rows)
        
        # 关联验证（如果提供了相关数据）
        if domain == "orders":
            inventory_data = payload.get("inventory_data", [])
            finance_data = payload.get("finance_data", [])
            
            if inventory_data:
                inventory_relation = validate_order_inventory_relation(rows, inventory_data)
                result["inventory_relation"] = inventory_relation
            
            if finance_data:
                finance_relation = validate_order_finance_relation(rows, finance_data)
                result["finance_relation"] = finance_relation
        
        return success_response(data=result)
    except Exception as e:
        logger.error(f"数据验证失败: {e}")
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message="数据验证失败",
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            detail=str(e),
            status_code=500
        )


@router.post("/save-template")
async def save_template_deprecated(payload: dict, db: AsyncSession = Depends(get_async_db)):
    """
    [DEPRECATED v4.5.1] 此API已废弃
    
    请使用新API: POST /field-mapping/dictionary/templates/save
    
    废弃原因：
    - 旧API使用field_mappings表（已废弃）
    - 新API使用field_mapping_templates表（企业级标准）
    - 新API支持header_row和sub_domain字段
    
    迁移指南：
    前端: api.saveTemplate(...) 已自动使用新API
    后端: 请勿调用此endpoint
    
    移除时间：v4.6.0 (预计2025-02-28)
    """
    return error_response(
        code=ErrorCode.API_DEPRECATED,
        message="API已废弃",
        error_type=get_error_type(ErrorCode.API_DEPRECATED),
        detail={
            "deprecated_since": "v4.5.1",
            "removed_in": "v4.6.0",
            "alternative": "POST /field-mapping/dictionary/templates/save",
            "migration_guide": "前端已自动使用新API，后端请勿调用此endpoint",
            "reason": "旧API使用已废弃的field_mappings表，新API使用field_mapping_templates表（符合SSOT原则）"
        },
        recovery_suggestion="请使用新API: POST /field-mapping/dictionary/templates/save",
        status_code=410
    )


@router.post("/apply-template")
async def apply_template_deprecated(payload: dict, db: AsyncSession = Depends(get_async_db)):
    """
    [DEPRECATED v4.5.1] 此API已废弃
    
    请使用新API: POST /field-mapping/dictionary/templates/apply
    
    废弃原因：
    - 旧API使用field_mappings表（已废弃）
    - 新API使用field_mapping_templates表（企业级标准）
    - 新API返回完整config对象（包含header_row配置）
    
    迁移指南：
    前端: api.applyTemplateById(...) 已自动使用新API
    后端: 请勿调用此endpoint
    
    移除时间：v4.6.0 (预计2025-02-28)
    
    ---
    
    原有功能说明（方案B+简化版：3级精确匹配）：
    
    方案B+匹配规则（无回退）：
    1. 唯一精确匹配：source_platform + domain + sub_domain + granularity
    2. 找不到模板 → 智能映射兜底
    
    改进：
    - 使用source_platform（数据来源）而非platform（采集平台）
    - 支持sub_domain（services的agent/ai_assistant）
    - 无复杂回退逻辑（简化维护）
    """
    # 返回410 Gone错误
    return error_response(
        code=ErrorCode.API_DEPRECATED,
        message="API已废弃",
        error_type=get_error_type(ErrorCode.API_DEPRECATED),
        detail={
            "deprecated_since": "v4.5.1",
            "removed_in": "v4.6.0",
            "alternative": "POST /field-mapping/dictionary/templates/apply",
            "migration_guide": "前端已自动使用新API（api.applyTemplateById），后端请勿调用此endpoint",
            "reason": "旧API使用已废弃的field_mappings表，新API使用field_mapping_templates表（符合SSOT原则）",
            "template_features_lost": [
                "header_row自动配置（新API支持）",
                "sub_domain精确匹配（新API支持）",
                "智能降级策略（新API支持）"
            ]
        },
        recovery_suggestion="请使用新API: POST /field-mapping/dictionary/templates/apply",
        status_code=410
    )
    
    # 以下代码不会执行，仅保留作为历史参考
    if False:
        from backend.services.field_mapping.normalizer import normalize_template_key
        from backend.services.field_mapping.entry import get_key_fields

        # ⭐ 新增：如果提供了file_id，优先从文件元数据获取granularity
        file_id = payload.get("file_id")
        file_granularity = None
        if file_id:
            file_record_result = await db.execute(select(CatalogFile).where(CatalogFile.id == file_id))
            file_record = file_record_result.scalar_one_or_none()
            if file_record and file_record.granularity:
                file_granularity = file_record.granularity
                logger.info(f"[ApplyTemplate] 从文件元数据读取粒度: {file_granularity}")
        
        # 归一化模板键
        key = normalize_template_key(payload)
        source_platform = key["source_platform"]
        domain = key["domain"]
        sub_domain = key["sub_domain"]
        # ⭐ 修复：优先使用文件元数据的granularity
        granularity = file_granularity or key["granularity"]
        columns = payload.get("columns", [])
        
        logger.info(f"[ApplyTemplate] {source_platform}/{domain}/{sub_domain}/{granularity} (文件粒度: {file_granularity}, 用户选择: {key['granularity']})")
        
        # 唯一精确匹配（方案B+）- 已废弃的FieldMapping表
        template = None  # 不再查询已废弃的表
        
        if not template:
            # ⭐ 新增：如果粒度不匹配，给出警告提示
            if file_granularity and file_granularity != key["granularity"]:
                logger.warning(f"[ApplyTemplate] 粒度不匹配：文件粒度={file_granularity}，用户选择={key['granularity']}，未找到匹配模板")
            
            # 找不到模板 → 统一入口兜底（模板/AI融合）
            logger.info(f"[ApplyTemplate] 未找到模板，使用统一映射入口")
            from backend.services.field_mapping.entry import get_mappings
            suggestions = get_mappings(columns, domain, source_platform)
            # 关键字段阈值判断
            key_fields = set(get_key_fields(domain))
            need_review = []
            for col, m in suggestions.items():
                if m.get("standard") in key_fields and (m.get("confidence", 0) < 0.8):
                    need_review.append({"column": col, "standard": m.get("standard"), "confidence": m.get("confidence", 0)})

            return {
                "success": True,
                "mappings": suggestions,
                "source": "ai_suggested",
                "message": f"未找到{source_platform}/{domain}/{granularity}的模板，使用智能映射",
                "need_review": need_review,
                "granularity_warning": file_granularity and file_granularity != key["granularity"]
            }
        
        # 获取模板中的所有映射（方案B+：精确匹配）
        template_mappings_result = await db.execute(
            select(FieldMapping).where(
                FieldMapping.platform == template.platform,
                FieldMapping.domain == template.domain,
                FieldMapping.sub_domain == template.sub_domain,
                FieldMapping.granularity == template.granularity,
                FieldMapping.version == template.version
            )
        )
        template_mappings = template_mappings_result.scalars().all()
        
        template_dict = {t.original_field: {"standard": t.standard_field, "confidence": t.confidence} for t in template_mappings}
        
        # 应用模板映射（支持模糊匹配）
        mapping_dict = {}
        for col in columns:
            matched = False
            
            # 1. 精确匹配
            if col in template_dict:
                mapping_dict[col] = template_dict[col]
                matched = True
            else:
                # 2. 模糊匹配（去除空格、特殊字符）
                col_normalized = re.sub(r'[\s_\-()（）]', '', col.lower())
                for template_col, mapping in template_dict.items():
                    template_col_normalized = re.sub(r'[\s_\-()（）]', '', template_col.lower())
                    if col_normalized == template_col_normalized:
                        mapping_dict[col] = mapping
                        matched = True
                        break
            
            if not matched:
                # 3. 未匹配的列使用统一映射入口
                from backend.services.field_mapping.entry import get_mappings
                suggestions = get_mappings([col], domain, source_platform)
                if suggestions and col in suggestions:
                    mapping_dict[col] = suggestions[col]

        return {
            "success": True, 
            "mappings": mapping_dict,
            "source": "template",
            "template_info": {
                "id": template.id,
                "source_platform": template.platform,
                "domain": template.domain,
                "sub_domain": template.sub_domain,
                "granularity": template.granularity,
                "version": template.version,
                "created_at": template.created_at.isoformat() if template.created_at else None
            }
        }


@router.get("/templates")
async def list_templates(platform: str, domain: str, granularity: str | None = None, sheet_name: str | None = None, db: AsyncSession = Depends(get_async_db)):
    """列出模板版本与字段（按平台/域/粒度/Sheet）"""
    try:
        stmt = select(FieldMapping).where(
            FieldMapping.platform == platform,
            FieldMapping.domain == domain,
        )
        if granularity:
            stmt = stmt.where(FieldMapping.granularity == granularity)
        if sheet_name:
            stmt = stmt.where(FieldMapping.sheet_name == sheet_name)
        stmt = stmt.order_by(FieldMapping.version.desc(), FieldMapping.original_field.asc())
        result = await db.execute(stmt)
        rows = result.scalars().all()
        versions = {}
        for r in rows:
            versions.setdefault(r.version, []).append({
                "original": r.original_field,
                "standard": r.standard_field,
                "confidence": r.confidence,
                "sheet_name": r.sheet_name,
                "header_row": None,
            })
        return success_response(data={"versions": versions})
    except Exception as e:
        logger.error(f"获取模板列表失败: {e}")
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取模板列表失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )

@router.get("/catalog-status")
async def get_catalog_status(db: AsyncSession = Depends(get_async_db)):
    """获取目录状态"""
    try:
        # 查询catalog_files表的状态统计
        # 统计总文件数
        total_result = await db.execute(text("SELECT COUNT(*) FROM catalog_files"))
        total_files = total_result.fetchone()[0]
        
        # 如果表为空，返回空状态
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
        
        # 统计各状态文件数
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

@router.get("/template-cache/stats")
async def get_template_cache_stats():
    """获取模板缓存统计信息"""
    try:
        from backend.services.template_cache import get_template_cache
        
        cache = get_template_cache()
        stats = cache.get_cache_stats()
        
        return success_response(data={"stats": stats}, message="获取缓存统计成功")
    except Exception as e:
        logger.error(f"获取缓存统计失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取缓存统计失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )

@router.post("/template-cache/cleanup")
async def cleanup_template_cache(days: int = 30):
    """清理过期模板缓存"""
    try:
        from backend.services.template_cache import get_template_cache
        
        cache = get_template_cache()
        deleted_count = cache.cleanup_expired_templates(days)
        
        data = {
            "deleted_count": deleted_count
        }
        
        return success_response(
            data=data,
            message=f"清理完成，删除了 {deleted_count} 个过期模板"
        )
    except Exception as e:
        logger.error(f"清理缓存失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="清理缓存失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )

@router.get("/template-cache/similar")
async def find_similar_templates(platform: str, domain: str, columns: str):
    """查找相似模板"""
    try:
        from backend.services.template_cache import get_template_cache
        
        cache = get_template_cache()
        columns_list = columns.split(',') if columns else []
        similar_templates = cache.find_similar_templates(platform, domain, columns_list)
        
        return success_response(
            data={"similar_templates": similar_templates},
            message="查找相似模板成功"
        )
    except Exception as e:
        logger.error(f"查找相似模板失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="查找相似模板失败",
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
                recovery_suggestion="请检查商品SKU是否正确，或先添加商品成本信息",
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
    
    # 根据数据域筛选相关字段
    domain_fields = {
        "orders": ["order_id", "product_id", "quantity", "total_amount", "order_date", "buyer_id", "order_status"],
        "inventory": ["product_id", "quantity_on_hand", "quantity_available", "avg_cost", "warehouse_code", "safety_stock"],
        "finance": ["ar_amount_cny", "received_amount_cny", "invoice_date", "due_date", "ar_status", "payment_method"],
        "products": ["product_id", "product_name", "page_views", "conversion_rate", "gmv", "rating"],
        "analytics": ["date", "visits", "page_views", "bounce_rate", "avg_session_duration"]
    }
    
    target_fields = domain_fields.get(domain, [])
    
    # 筛选相关的映射
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
        
        # 验证订单数据
        if "orders" in payload:
            orders_data = payload["orders"]
            results["orders"] = validate_orders(orders_data)
        
        # 验证库存数据
        if "inventory" in payload:
            inventory_data = payload["inventory"]
            results["inventory"] = validate_inventory(inventory_data)
        
        # 验证财务数据
        if "finance" in payload:
            finance_data = payload["finance"]
            results["finance"] = validate_finance(finance_data)
        
        # 验证关联关系
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
    """清理无效文件（基于 catalog_files）。"""
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
                # 记录孤儿并删除
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
            message=f"清理完成，删除了 {orphaned_count} 个无效文件记录"
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
    获取待指派店铺的文件列表（status='needs_shop'）
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
                'account': f.account or '',  # v4.3.4: 账号信息（辅助判断）
                'shop_resolution': None
            }
            
            # 解析文件元数据中的shop_resolution信息
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
    
    请求体：
    {
        "file_ids": [1, 2, 3],
        "shop_id": "shop_12345",
        "auto_retry_ingest": true  # 指派后自动重试入库
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
            
            # 更新shop_id
            catalog_file.shop_id = shop_id
            
            # 更新状态：从needs_shop改为pending（如果适用）
            if catalog_file.status == 'needs_shop':
                catalog_file.status = 'pending'
            
            # 更新元数据
            meta = catalog_file.file_metadata or {}
            if 'shop_resolution' not in meta:
                meta['shop_resolution'] = {}
            meta['shop_resolution']['manual_assigned'] = True
            meta['shop_resolution']['assigned_at'] = datetime.utcnow().isoformat()
            catalog_file.file_metadata = meta
            
            updated_count += 1
        
        await db.commit()
        
        # 可选：自动重试入库
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
