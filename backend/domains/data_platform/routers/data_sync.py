#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据同步API路由(Data Sync API)

v4.12.0新增:
- 统一的数据同步API入口
- 使用DataSyncService(直接函数调用,不通过HTTP)
- 使用SyncProgressTracker(数据库存储,持久化)

职责:
- 只负责API接口(参数解析、响应格式化)
- 业务逻辑由DataSyncService处理

v4.18.0: Pydantic模型已迁移到backend/schemas/data_sync.py(Contract-First架构)
"""

from fastapi import APIRouter, Depends, Query, HTTPException, Request, Body, Path
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, timezone
from pathlib import Path as PathLib  # [*] 修复:重命名避免与 fastapi.Path 冲突
import re
import uuid
import asyncio
import copy
import time
import pandas as pd

from backend.models.database import get_db, get_async_db, SessionLocal, AsyncSessionLocal
from sqlalchemy.ext.asyncio import AsyncSession
from backend.services.data_sync_service import DataSyncService
from backend.services.data_sync_cleanup_service import DataSyncCleanupService
from backend.services.data_sync_template_status_service import DataSyncTemplateStatusService
from backend.services.spreadsheet_normalization_service import get_spreadsheet_normalization_service
from backend.services.sync_progress_tracker import SyncProgressTracker
from backend.services.sync_standardization_quality_service import SyncStandardizationQualityService
from backend.dependencies.auth import get_current_user, require_admin  # [*] Phase 4.2: 用户认证
from backend.services.user_task_quota import get_user_task_quota_service  # [*] Phase 4.2: 用户任务配额

# [*] Phase 2: API 限流(使用 slowapi)
# [*] v4.19.4 更新:使用基于角色的动态限流
try:
    from backend.middleware.rate_limiter import limiter, role_based_rate_limit
    RATE_LIMIT_ENABLED = True
except ImportError:
    limiter = None
    role_based_rate_limit = None
    RATE_LIMIT_ENABLED = False

# [*] v4.19.4 保留:条件装饰器辅助函数(向后兼容,但建议使用 role_based_rate_limit)
def conditional_rate_limit(limit_str: str):
    """条件应用限流装饰器(已废弃,建议使用 role_based_rate_limit)"""
    if RATE_LIMIT_ENABLED and limiter:
        return limiter.limit(limit_str)
    else:
        # 返回一个无操作的装饰器
        def noop_decorator(func):
            return func
        return noop_decorator

# [*] v4.18.2修复:全局并发控制,限制同时运行的后台同步任务数量
# 最多允许10个并发任务,避免资源耗尽
MAX_CONCURRENT_SYNC_TASKS = asyncio.Semaphore(10)
TEMPLATE_STATUS_CACHE_TTL_SECONDS = 180
_template_status_cache: dict[tuple[Any, ...], tuple[float, Dict[str, Any]]] = {}
from backend.services.c_class_data_validator import get_c_class_data_validator
from backend.services.data_loss_analyzer import (
    analyze_data_loss, check_data_loss_threshold,
    async_analyze_data_loss, async_check_data_loss_threshold  # [*] v4.18.2新增:异步版本
)
from backend.services.field_mapping_validator import validate_field_mapping, calculate_mapping_quality_score
from backend.utils.api_response import success_response, error_response
from backend.utils.error_codes import ErrorCode, get_error_type
from modules.core.db import CatalogFile, CollectionTask
from modules.core.file_naming import StandardFileName
from modules.core.logger import get_logger
from modules.core.path_manager import get_data_raw_dir, to_absolute_path
from modules.services.catalog_scanner import _compute_sha256
from modules.services.catalog_scanner import scan_and_register
from modules.services.metadata_manager import MetadataManager
from modules.services.file_semantics import is_catalog_file_semantically_valid, validate_file_semantics
from sqlalchemy import select, func, and_, distinct, case

# v4.18.0: 导入schemas(Contract-First架构)
from backend.schemas.data_sync import (
    SingleFileSyncRequest,
    BatchSyncRequest,
    BatchSyncByFileIdsRequest,
    DataSyncFilePreviewRequest,
    FileListRequest,
    CeleryTaskStatusResponse,  # [*] Phase 1.4.3: 任务状态管理
    CancelTaskResponse,  # [*] Phase 1.4.3: 任务状态管理
    RetryTaskResponse,  # [*] Phase 1.4.3: 任务状态管理
)

from backend.schemas.catalog_file_delete import (
    CatalogFileBatchDeleteImpactResponse,
    CatalogFileBatchDeleteRequest,
    CatalogFileBatchDeleteResultResponse,
    CatalogFileDeleteImpactResponse,
    CatalogFileDeleteResultResponse,
)
from backend.services.catalog_file_delete_service import (
    CatalogFileDeleteNotFoundError,
    DataSyncSchemaDriftError,
    CatalogFileDeleteService,
)

logger = get_logger(__name__)
router = APIRouter(dependencies=[Depends(require_admin)])


def _is_governance_excluded_sample_file(catalog_file: CatalogFile | None) -> bool:
    if catalog_file is None:
        return False

    file_path = str(getattr(catalog_file, "file_path", "") or "").replace("\\", "/").lower()
    file_name = str(getattr(catalog_file, "file_name", "") or "").lower()

    if file_path.startswith("temp/development/") or "/temp/development/" in file_path:
        return True
    if "_case" in file_name and "products" in file_name:
        return True
    return False


def _semantic_anomaly_reason(catalog_file: CatalogFile | None) -> str:
    result = validate_file_semantics(
        source_platform=getattr(catalog_file, "source_platform", None) or getattr(catalog_file, "platform_code", None),
        platform_code=getattr(catalog_file, "platform_code", None),
        data_domain=getattr(catalog_file, "data_domain", None),
        granularity=getattr(catalog_file, "granularity", None),
        sub_domain=getattr(catalog_file, "sub_domain", None),
        file_name=getattr(catalog_file, "file_name", None),
    )
    return result.reason


def _semantic_anomaly_display_reason(reason: str) -> str:
    mapping = {
        "miaoshou_orders_business_platform_collapsed": "妙手 orders 业务平台语义错误，需先修复平台语义",
        "inventory_granularity_invalid": "库存文件只能使用 snapshot 粒度，需先修复为 snapshot",
        "services_invalid_subdomain": "services 文件子类型不合法",
        "nonsvc_should_not_have_subdomain": "当前数据域不允许配置子类型",
        "orders_subdomain_not_allowed": "orders 数据域不允许子类型",
    }
    return mapping.get(reason, reason or "语义异常")


def _is_inventory_granularity_anomaly(catalog_file: CatalogFile | None) -> bool:
    return _semantic_anomaly_reason(catalog_file) == "inventory_granularity_invalid"


DATA_SYNC_RAW_EXTENSIONS = {".xlsx", ".xls", ".csv", ".tsv", ".html", ".htm"}


def _raw_path_parts(raw_root: PathLib, file_path: PathLib) -> list[str]:
    try:
        relative = file_path.relative_to(raw_root)
    except ValueError:
        relative = file_path
    return [part.lower() for part in relative.parts]


def _is_repaired_raw_file(raw_root: PathLib, file_path: PathLib) -> bool:
    return "repaired" in _raw_path_parts(raw_root, file_path)


def _is_legacy_without_meta(raw_root: PathLib, file_path: PathLib) -> bool:
    parts = _raw_path_parts(raw_root, file_path)
    if not parts:
        return False
    year_part = parts[0]
    if not year_part.isdigit() or len(year_part) != 4:
        return False
    if int(year_part) >= datetime.now(timezone.utc).year:
        return False
    return not file_path.with_suffix(".meta.json").exists()


def _resolve_catalog_file_path(file_record: CatalogFile) -> PathLib:
    file_path = PathLib(str(file_record.file_path))
    if file_path.is_absolute():
        return file_path

    from modules.core.path_manager import get_project_root

    return get_project_root() / file_path


def _resolve_catalog_meta_path(file_record: CatalogFile, raw_path: PathLib | None = None) -> PathLib:
    meta_file_path = getattr(file_record, "meta_file_path", None)
    if meta_file_path:
        meta_path = PathLib(str(meta_file_path))
        if meta_path.is_absolute():
            return meta_path
        return to_absolute_path(str(meta_file_path))

    if raw_path is None:
        raw_path = _resolve_catalog_file_path(file_record)
    return raw_path.with_suffix(".meta.json")


def _read_catalog_meta(file_record: CatalogFile, raw_path: PathLib | None = None) -> dict[str, Any]:
    meta_path = _resolve_catalog_meta_path(file_record, raw_path)
    if not meta_path.exists():
        return {}
    try:
        return MetadataManager.read_meta_file(meta_path)
    except Exception as exc:
        logger.warning("[DataSync Files] 读取伴生meta失败: %s, 错误: %s", meta_path, exc)
        return {}


def _extract_collection_task_ids_from_meta(meta: dict[str, Any]) -> set[str]:
    collection_info = meta.get("collection_info") or {}
    task_ids = {
        str(value)
        for value in (
            collection_info.get("collection_task_id"),
            collection_info.get("collection_task_uuid"),
            collection_info.get("task_id"),
            collection_info.get("task_uuid"),
            meta.get("collection_task_id"),
            meta.get("collection_task_uuid"),
        )
        if value
    }

    original_path = str(collection_info.get("original_path") or "")
    normalized_path = original_path.replace("\\", "/")
    if normalized_path:
        task_ids.update(
            re.findall(
                r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
                normalized_path,
            )
        )
        path_parts = [part for part in normalized_path.split("/") if part]
        for marker in ("downloads", "collection", "tasks"):
            if marker in path_parts:
                marker_index = path_parts.index(marker)
                if marker_index + 1 < len(path_parts):
                    task_ids.add(path_parts[marker_index + 1])

    return task_ids


def _catalog_file_matches_collection_task(file_record: CatalogFile, collection_task_id: str) -> bool:
    if not collection_task_id:
        return True
    meta = _read_catalog_meta(file_record)
    return collection_task_id in _extract_collection_task_ids_from_meta(meta)


def _normalize_local_path_key(path_value: Any) -> str:
    try:
        path = PathLib(str(path_value))
        if not path.is_absolute():
            path = to_absolute_path(str(path_value))
        return str(path.resolve()).replace("\\", "/").lower()
    except Exception:
        return str(path_value or "").replace("\\", "/").lower()


def _iter_data_raw_files(limit: int | None = None) -> list[PathLib]:
    raw_root = PathLib(get_data_raw_dir())
    if not raw_root.exists():
        return []

    files: list[PathLib] = []
    for candidate in raw_root.rglob("*"):
        if not candidate.is_file():
            continue
        if candidate.suffix.lower() == ".json" and candidate.name.endswith(".meta.json"):
            continue
        if candidate.suffix.lower() not in DATA_SYNC_RAW_EXTENSIONS:
            continue
        if _is_repaired_raw_file(raw_root, candidate):
            continue
        if _is_legacy_without_meta(raw_root, candidate):
            continue
        files.append(candidate)
        if limit is not None and len(files) >= limit:
            break
    return files


def _collect_raw_file_categories(limit: int | None = None) -> dict[str, list[PathLib]]:
    raw_root = PathLib(get_data_raw_dir())
    categories = {
        "official": [],
        "repaired_cache": [],
        "legacy_without_meta": [],
    }
    if not raw_root.exists():
        return categories

    seen = 0
    for candidate in raw_root.rglob("*"):
        if not candidate.is_file():
            continue
        if candidate.suffix.lower() == ".json" and candidate.name.endswith(".meta.json"):
            continue
        if candidate.suffix.lower() not in DATA_SYNC_RAW_EXTENSIONS:
            continue

        if _is_repaired_raw_file(raw_root, candidate):
            categories["repaired_cache"].append(candidate)
        elif _is_legacy_without_meta(raw_root, candidate):
            categories["legacy_without_meta"].append(candidate)
        else:
            categories["official"].append(candidate)

        seen += 1
        if limit is not None and seen >= limit:
            break
    return categories


async def _build_raw_unregistered_hint(db: AsyncSession) -> dict[str, Any] | None:
    raw_categories = _collect_raw_file_categories(limit=1001)
    raw_files = raw_categories["official"]
    repaired_cache_count = len(raw_categories["repaired_cache"])
    legacy_without_meta_count = len(raw_categories["legacy_without_meta"])
    if not raw_files:
        if repaired_cache_count == 0 and legacy_without_meta_count == 0:
            return None
        return {
            "candidate_count": 0,
            "official_unregistered_count": 0,
            "repaired_cache_count": repaired_cache_count,
            "legacy_without_meta_count": legacy_without_meta_count,
            "sample_files": [],
            "action": "refresh_data_sync_files",
        }

    result = await db.execute(select(CatalogFile.file_path))
    catalog_path_keys = {
        _normalize_local_path_key(row[0])
        for row in result.all()
        if row[0]
    }
    unregistered = [
        raw_file
        for raw_file in raw_files
        if _normalize_local_path_key(raw_file) not in catalog_path_keys
    ]
    if not unregistered and repaired_cache_count == 0 and legacy_without_meta_count == 0:
        return None

    return {
        "candidate_count": len(unregistered),
        "official_unregistered_count": len(unregistered),
        "repaired_cache_count": repaired_cache_count,
        "legacy_without_meta_count": legacy_without_meta_count,
        "sample_files": [str(path) for path in unregistered[:5]],
        "action": "refresh_data_sync_files",
    }


async def _build_data_sync_file_diagnostics(db: AsyncSession, hours: int) -> dict[str, Any]:
    safe_hours = max(1, min(int(hours or 24), 24 * 30))
    since_time = datetime.now(timezone.utc) - timedelta(hours=safe_hours)

    raw_files = _iter_data_raw_files()
    raw_hint = await _build_raw_unregistered_hint(db)

    catalog_result = await db.execute(select(CatalogFile))
    catalog_files = catalog_result.scalars().all()
    semantic_invalid_count = sum(
        1
        for file_record in catalog_files
        if not is_catalog_file_semantically_valid(file_record)
        and not _is_inventory_granularity_anomaly(file_record)
    )

    recent_collection_tasks: list[dict[str, Any]] = []
    try:
        task_result = await db.execute(
            select(CollectionTask)
            .where(CollectionTask.created_at >= since_time)
            .order_by(CollectionTask.created_at.desc())
            .limit(10)
        )
        for task in task_result.scalars().all():
            recent_collection_tasks.append(
                {
                    "id": getattr(task, "id", None),
                    "task_id": getattr(task, "task_id", None) or getattr(task, "id", None),
                    "status": getattr(task, "status", None),
                    "files_collected": getattr(task, "files_collected", 0) or 0,
                    "created_at": (
                        task.created_at.isoformat()
                        if getattr(task, "created_at", None)
                        else None
                    ),
                }
            )
    except Exception as exc:
        logger.debug("[DataSync Diagnostics] collection task lookup skipped: %s", exc)

    recommendations = []
    if raw_hint and raw_hint.get("candidate_count", 0) > 0:
        recommendations.append("点击刷新文件目录，将 data/raw 中未注册文件补录到文件列表。")
    if semantic_invalid_count > 0:
        recommendations.append("存在语义异常 catalog 文件，请清理或修复后再同步。")
    if not recommendations:
        recommendations.append("未发现明显的文件注册链路异常。")

    return {
        "recent_collection_tasks": recent_collection_tasks,
        "raw_file_count": len(raw_files),
        "catalog_file_count": len(catalog_files),
        "unregistered_raw_candidates": (raw_hint or {}).get("candidate_count", 0),
        "official_unregistered_count": (raw_hint or {}).get("official_unregistered_count", 0),
        "repaired_cache_count": (raw_hint or {}).get("repaired_cache_count", 0),
        "legacy_without_meta_count": (raw_hint or {}).get("legacy_without_meta_count", 0),
        "semantic_invalid_count": semantic_invalid_count,
        "recommendations": recommendations,
    }


def _resolve_miaoshou_orders_business_platform(catalog_file: CatalogFile) -> str | None:
    file_name = str(getattr(catalog_file, "file_name", "") or "")
    try:
        parsed = StandardFileName.parse(file_name)
        if (
            str(parsed.get("source_platform", "")).strip().lower() == "miaoshou"
            and str(parsed.get("data_domain", "")).strip().lower() == "orders"
        ):
            candidate = str(parsed.get("sub_domain", "")).strip().lower()
            if candidate in {"tiktok", "shopee"}:
                return candidate
    except Exception:
        pass

    meta_path = getattr(catalog_file, "meta_file_path", None)
    if meta_path:
        try:
            meta_content = MetadataManager.read_meta_file(to_absolute_path(str(meta_path)))
            business_metadata = meta_content.get("business_metadata", {}) or {}
            candidate = str(business_metadata.get("sub_domain", "")).strip().lower()
            if candidate in {"tiktok", "shopee"}:
                return candidate

            original_path = str((meta_content.get("collection_info", {}) or {}).get("original_path", "")).lower()
            if "/orders/tiktok/" in original_path.replace("\\", "/"):
                return "tiktok"
            if "/orders/shopee/" in original_path.replace("\\", "/"):
                return "shopee"
        except Exception:
            pass

    normalized_file_name = file_name.lower()
    if "miaoshou_orders_tiktok_" in normalized_file_name:
        return "tiktok"
    if "miaoshou_orders_shopee_" in normalized_file_name:
        return "shopee"
    return None


def _infer_miaoshou_orders_business_platform(catalog_file: CatalogFile) -> str | None:
    file_name = str(getattr(catalog_file, "file_name", "") or "")
    try:
        parsed = StandardFileName.parse(file_name)
        if (
            parsed.get("source_platform") == "miaoshou"
            and parsed.get("data_domain") == "orders"
            and parsed.get("sub_domain") in {"tiktok", "shopee"}
        ):
            return parsed["sub_domain"]
    except Exception:
        pass

    meta_path = getattr(catalog_file, "meta_file_path", None)
    if meta_path:
        try:
            meta = MetadataManager.read_meta_file(to_absolute_path(str(meta_path)))
            business = meta.get("business_metadata", {}) or {}
            collection = meta.get("collection_info", {}) or {}
            source_platform = str(business.get("source_platform", "")).strip().lower()
            if source_platform in {"tiktok", "shopee"}:
                return source_platform
            sub_domain = str(business.get("sub_domain", "")).strip().lower()
            if sub_domain in {"tiktok", "shopee"}:
                return sub_domain
            original_path = str(collection.get("original_path", "")).replace("\\", "/").lower()
            matched = re.search(r"/orders/(tiktok|shopee)/", original_path)
            if matched:
                return matched.group(1)
        except Exception:
            pass

    return None


def _build_template_status_cache_key(file_record: CatalogFile, template) -> tuple[Any, ...]:
    return (
        getattr(file_record, "id", None),
        getattr(template, "id", None),
        getattr(template, "version", None),
        getattr(template, "header_row", None),
        getattr(file_record, "status", None),
    )


def _get_cached_template_status(cache_key: tuple[Any, ...]) -> Dict[str, Any] | None:
    cached = _template_status_cache.get(cache_key)
    if cached is None:
        return None

    expires_at, payload = cached
    if expires_at <= time.monotonic():
        _template_status_cache.pop(cache_key, None)
        return None
    return copy.deepcopy(payload)


def _set_cached_template_status(cache_key: tuple[Any, ...], payload: Dict[str, Any]) -> None:
    _template_status_cache[cache_key] = (
        time.monotonic() + TEMPLATE_STATUS_CACHE_TTL_SECONDS,
        copy.deepcopy(payload),
    )


# ==================== 数据同步API ====================

@router.post("/data-sync/preview")
async def preview_file(
    request: DataSyncFilePreviewRequest,
    db: AsyncSession = Depends(get_async_db)  # [*] v4.18.2:改为异步会话
):
    """
    文件预览API(支持表头行参数)[*] **新增(2025-01-31)**
    
    功能:
    - 使用用户手动选择的表头行读取文件
    - 不进行自动检测,直接使用用户选择的表头行
    - 返回数据预览(前100行)、原始表头字段列表、示例数据
    
    Args:
        file_id: 文件ID
        header_row: 表头行(0-based,0=Excel第1行,1=Excel第2行...)
    
    v4.18.2: 迁移到异步会话(AsyncSession)
    """
    try:
        from backend.services.excel_parser import ExcelParser
        
        # 1. 获取文件信息([*] v4.18.2:使用 await)
        result = await db.execute(
            select(CatalogFile).where(CatalogFile.id == request.file_id)
        )
        catalog_record = result.scalar_one_or_none()
        
        if not catalog_record:
            return error_response(
                code=ErrorCode.DATA_NOT_FOUND,
                message="文件未注册",
                error_type=get_error_type(ErrorCode.DATA_NOT_FOUND),
                detail=f"文件未注册: id={request.file_id}",
                recovery_suggestion="请先扫描采集文件,确保文件已注册到系统中",
                status_code=404
            )
        
        file_path_relative = catalog_record.file_path
        
        # [*] v4.19.8修复:使用 to_absolute_path 正确解析路径(支持Docker容器和Windows环境)
        from modules.core.path_manager import to_absolute_path
        file_path = to_absolute_path(file_path_relative)
        
        # [*] v4.18.2修复:使用 run_in_executor 包装文件系统检查,避免阻塞事件循环
        loop = asyncio.get_running_loop()
        file_exists = await loop.run_in_executor(
            None,
            lambda: file_path.exists()
        )
        if not file_exists:
            return error_response(
                code=ErrorCode.DATA_NOT_FOUND,
                message="文件不存在",
                error_type=get_error_type(ErrorCode.DATA_NOT_FOUND),
                detail=f"文件不存在: {file_path}(原始路径: {file_path_relative})",
                recovery_suggestion="请检查文件路径是否正确,或重新扫描采集文件",
                status_code=404
            )
        
        # 2. 使用用户选择的表头行读取文件(不自动检测)
        logger.info(f"[DataSync Preview] 使用表头行 {request.header_row} 读取文件: {catalog_record.file_name}")
        
        # [*] v4.18.2修复:使用 run_in_executor 包装文件大小获取,避免阻塞事件循环
        file_size_mb = await loop.run_in_executor(
            None,
            lambda: PathLib(file_path).stat().st_size / (1024 * 1024)
        )
        preview_rows = 50 if file_size_mb > 10 else 100
        runtime_file_path = file_path
        runtime_source_format = ExcelParser.detect_file_format(PathLib(file_path))
        if runtime_source_format in {"xls", "xlsx_with_ole", "html"}:
            normalized = get_spreadsheet_normalization_service().normalize_for_runtime(
                file_path,
                source_format=runtime_source_format,
            )
            runtime_file_path = str(normalized.path)
        
        # [*] v4.18.2修复:使用 run_in_executor 包装文件读取,避免阻塞事件循环
        df = await loop.run_in_executor(
            None,
            ExcelParser.read_excel,
            runtime_file_path,
            request.header_row,  # [*] 直接使用用户选择的表头行
            preview_rows
        )
        
        # 3. 规范化处理(合并单元格还原)
        normalization_report = {}
        try:
            df, normalization_report = ExcelParser.normalize_table(
                df,
                data_domain=catalog_record.data_domain or "products",
                file_size_mb=file_size_mb,
                source_path=runtime_file_path,
                header_row=request.header_row,
            )
        except Exception as norm_error:
            logger.warning(f"[DataSync Preview] 规范化失败: {norm_error}", exc_info=True)
            normalization_report = {"error": str(norm_error)}
        
        # 4. 数据清洗
        df.columns = [str(col).strip() for col in df.columns]
        df = df.dropna(how='all')
        df = df.fillna('')
        
        # 5. 提取原始表头字段列表和示例数据
        header_columns = df.columns.tolist()
        sample_data = {}
        if len(df) > 0:
            first_row = df.iloc[0]
            for col in header_columns:
                sample_data[col] = str(first_row[col]) if pd.notna(first_row[col]) else ""
        
        # 6. 转换为前端格式
        preview_data = df.head(100).to_dict('records')
        
        return success_response(
            data={
                "preview_data": preview_data,
                "header_columns": header_columns,
                "sample_data": sample_data,
                "row_count": len(df),
                "column_count": len(header_columns),
                "file_name": catalog_record.file_name,
                "file_size": file_size_mb,
                "header_row": request.header_row,
                "normalization_report": normalization_report
            },
            message=f"文件预览成功(表头行: {request.header_row})"
        )
        
    except Exception as e:
        logger.error(f"[DataSync Preview] 预览失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message="文件预览失败",
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            detail=str(e)[:500],
            recovery_suggestion="建议:1) 检查文件格式是否正确;2) 尝试调整表头行;3) 联系技术支持",
            status_code=500
        )


@router.get("/data-sync/files")
async def list_files(
    platform: Optional[str] = Query(None, description="平台代码"),
    domain: Optional[str] = Query(None, description="数据域"),
    granularity: Optional[str] = Query(None, description="粒度"),
    sub_domain: Optional[str] = Query(None, description="子类型"),
    status: Optional[str] = Query(None, description="状态(pending/ingested/failed/partial_success/quarantined/needs_shop,为空则显示所有状态)"),  # [*] v4.17.3修复:默认None,显示所有状态
    page: int = Query(1, description="页码", ge=1),  # v4.18.0新增:分页支持
    page_size: int = Query(50, description="每页数量", ge=1, le=200),  # v4.18.0新增:分页支持
    limit: int = Query(None, description="数量限制(已废弃,使用page和page_size)"),  # v4.18.0:向后兼容
    collection_task_id: Optional[str] = Query(None, description="采集任务ID/UUID，兼容从meta original_path解析"),
    db: AsyncSession = Depends(get_async_db)  # [*] v4.18.2:改为异步会话
):
    """
    文件列表API [*] **新增(2025-01-31)**
    
    功能:
    - 显示待同步文件列表
    - 支持筛选:platform, domain, granularity, sub_domain, status
    - 返回文件列表和模板匹配状态
    
    v4.18.2: 迁移到异步会话(AsyncSession)
    """
    try:
        from backend.services.template_family_service import get_template_resolver
        from backend.services.template_matcher import get_template_matcher
        
        # 1. 构建查询条件
        query = select(CatalogFile)
        conditions = []
        
        if platform:
            conditions.append(CatalogFile.platform_code == platform)
        if domain:
            conditions.append(CatalogFile.data_domain == domain)
        if granularity:
            conditions.append(CatalogFile.granularity == granularity)
        if sub_domain:
            conditions.append(CatalogFile.sub_domain == sub_domain)
        if status:
            conditions.append(CatalogFile.status == status)
        
        if conditions:
            query = query.where(*conditions)
        
        query = query.order_by(CatalogFile.first_seen_at.desc())

        # 2. 查询文件列表([*] v4.18.2:使用 await)
        result = await db.execute(query)
        all_files = result.scalars().all()
        display_files = [
            file_record
            for file_record in all_files
            if is_catalog_file_semantically_valid(file_record) or _is_inventory_granularity_anomaly(file_record)
        ]
        if collection_task_id:
            display_files = [
                file_record
                for file_record in display_files
                if _catalog_file_matches_collection_task(file_record, collection_task_id)
            ]
        hidden_semantic_invalid_count = len(all_files) - len(display_files)
        raw_unregistered_hint = await _build_raw_unregistered_hint(db)
        total_count = len(display_files)

        if limit is not None:
            files = display_files[:limit]
        else:
            offset = (page - 1) * page_size
            files = display_files[offset: offset + page_size]
        
        # [*] v4.19.5 优化:预加载所有已发布模板,减少重复查询
        from modules.core.db import FieldMappingTemplate
        from sqlalchemy import desc
        
        # 预加载所有已发布模板(一次性查询)
        templates_result = await db.execute(
            select(FieldMappingTemplate).where(
                FieldMappingTemplate.status == 'published'
            ).order_by(desc(FieldMappingTemplate.version))
        )
        all_templates = templates_result.scalars().all()
        
        # 文件列表页的模板可用性判断必须与 TemplateMatcher 一致。
        # 否则会出现“页面显示有模板,实际同步报无模板”的假阳性。
        exact_template_cache = {}
        loose_template_cache = {}
        for t in all_templates:
            key1 = f"{t.platform}:{t.data_domain}:{t.granularity or ''}:{t.sub_domain or ''}"
            if key1 not in exact_template_cache:
                exact_template_cache[key1] = t
            key2 = f"{t.platform}:{t.data_domain}:{t.granularity or ''}:"
            if key2 not in loose_template_cache:
                loose_template_cache[key2] = t
        
        # 3. 检查模板匹配状态
        template_matcher = get_template_matcher(db)
        template_resolver = get_template_resolver(db)
        data_sync_service = DataSyncService(db)
        file_list = []
        
        # [*] v4.18.2修复:在循环外获取事件循环,避免重复获取
        loop = asyncio.get_running_loop()
        
        for file_record in files:
            semantic_anomaly_type = None
            if not is_catalog_file_semantically_valid(file_record):
                semantic_anomaly_type = _semantic_anomaly_reason(file_record)
            # [*] v4.19.5 优化:使用缓存快速匹配模板,避免重复查询数据库
            template = None
            platform = file_record.platform_code or ""
            data_domain = file_record.data_domain or ""
            granularity = file_record.granularity or ""
            sub_domain = file_record.sub_domain or ""
            
            key1 = f"{platform}:{data_domain}:{granularity}:{sub_domain}"
            if key1 in exact_template_cache:
                template = exact_template_cache[key1]
            else:
                allow_loose_match = not (
                    data_domain.lower() == "services" and bool(sub_domain)
                )
                key2 = f"{platform}:{data_domain}:{granularity}:"
                if allow_loose_match and key2 in loose_template_cache:
                    template = loose_template_cache[key2]
                else:
                    template = await template_matcher.find_best_template(
                        platform=platform,
                        data_domain=data_domain,
                        granularity=granularity,
                        sub_domain=sub_domain if sub_domain else None
                    )
            
            # [*] 修复:使用安全路径解析,确保文件大小正确显示
            from modules.core.path_manager import get_project_root, get_data_input_dir, get_data_raw_dir
            
            # 解析文件路径(支持相对路径和绝对路径)
            file_path_str = file_record.file_path
            if PathLib(file_path_str).is_absolute():
                resolved_path = PathLib(file_path_str)
            else:
                # 相对路径:从项目根目录解析
                project_root = get_project_root()
                resolved_path = project_root / file_path_str
            
            # [*] v4.18.2修复:使用 run_in_executor 包装文件系统操作,避免阻塞事件循环
            # 获取文件大小(如果文件存在)
            file_size = 0
            file_exists = await loop.run_in_executor(
                None,
                lambda: resolved_path.exists()
            )
            if file_exists:
                try:
                    file_size = await loop.run_in_executor(
                        None,
                        lambda: resolved_path.stat().st_size
                    )
                except Exception as e:
                    logger.warning(f"[DataSync Files] 获取文件大小失败: {file_path_str}, 错误: {e}")
            
            meta_file_path = getattr(file_record, "meta_file_path", None)
            if meta_file_path:
                meta_path_value = PathLib(str(meta_file_path))
                meta_resolved_path = (
                    meta_path_value
                    if meta_path_value.is_absolute()
                    else to_absolute_path(str(meta_file_path))
                )
            else:
                meta_resolved_path = resolved_path.with_suffix(".meta.json")
            meta_exists = await loop.run_in_executor(
                None,
                lambda: meta_resolved_path.exists()
            )

            if semantic_anomaly_type:
                template_status_info = {
                    "has_template": False,
                    "template_status": "semantic_invalid",
                    "governance_status": "semantic_invalid",
                    "template_update_required": False,
                    "update_reason": _semantic_anomaly_display_reason(semantic_anomaly_type),
                    "template_name": None,
                    "template_header_row": None,
                    "shadow_compare": None,
                    "semantic_anomaly_type": semantic_anomaly_type,
                    "semantic_repair_action": (
                        "repair_inventory_snapshot"
                        if semantic_anomaly_type == "inventory_granularity_invalid"
                        else None
                    ),
                }
            else:
                cache_key = _build_template_status_cache_key(file_record, template)
                template_status_info = _get_cached_template_status(cache_key)
                if template_status_info is None:
                    template_status_info = await data_sync_service.evaluate_catalog_file_template_status(
                        file_record,
                        template=template,
                    )
                    _set_cached_template_status(cache_key, template_status_info)

            file_list.append({
                "id": file_record.id,
                "file_name": file_record.file_name,
                "platform": file_record.platform_code,
                "business_platform": file_record.platform_code,
                "collection_platform": file_record.source_platform,
                "domain": file_record.data_domain,
                "granularity": file_record.granularity,
                "sub_domain": file_record.sub_domain,
                "account": file_record.account,
                "shop_id": file_record.shop_id,
                "date_from": file_record.date_from.isoformat() if file_record.date_from else None,
                "date_to": file_record.date_to.isoformat() if file_record.date_to else None,
                "file_size": file_size,
                "meta_file_path": str(meta_resolved_path),
                "meta_exists": meta_exists,
                "catalog_registered": True,
                "file_path": str(resolved_path),  # [*] 新增:返回解析后的文件路径(用于调试)
                "collected_at": file_record.first_seen_at.isoformat() if file_record.first_seen_at else None,
                "has_template": template_status_info["has_template"],
                "template_status": template_status_info["template_status"],
                "governance_status": template_status_info.get("governance_status", template_status_info["template_status"]),
                "template_update_required": template_status_info["template_update_required"],
                "update_reason": template_status_info["update_reason"],
                "template_name": template_status_info["template_name"],
                "template_header_row": template_status_info["template_header_row"],
                "shadow_compare": template_status_info.get("shadow_compare"),
                "semantic_anomaly_type": template_status_info.get("semantic_anomaly_type"),
                "semantic_repair_action": template_status_info.get("semantic_repair_action"),
                "status": file_record.status
            })
        
        return success_response(
            data={
                "files": file_list,
                "total": total_count,  # v4.18.0: 返回总数(用于分页)
                "page": page,
                "page_size": page_size,
                "total_pages": (total_count + page_size - 1) // page_size if page_size > 0 else 1,
                "hidden_semantic_invalid_count": hidden_semantic_invalid_count,
                "raw_unregistered_hint": raw_unregistered_hint,
            },
            message=f"查询到 {len(file_list)} 个文件(共 {total_count} 个)"
        )
        
    except Exception as e:
        logger.error(f"[DataSync Files] 查询文件列表失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="查询文件列表失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查查询参数和数据库连接,或联系系统管理员",
            status_code=500
        )


@router.post("/data-sync/files/refresh")
async def refresh_data_sync_files(
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin),
):
    try:
        result = await asyncio.to_thread(scan_and_register, get_data_raw_dir())
        data = {
            "seen": result.seen,
            "registered": result.registered,
            "skipped": result.skipped,
            "new_file_ids": result.new_file_ids,
        }
        return success_response(data=data, message="刷新文件目录完成")
    except Exception as e:
        logger.error(f"[DataSync Files Refresh] 刷新文件目录失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.FILE_OPERATION_ERROR,
            message="刷新文件目录失败",
            error_type=get_error_type(ErrorCode.FILE_OPERATION_ERROR),
            detail=str(e),
            recovery_suggestion="请检查 data/raw 目录权限和文件命名是否符合规范",
            status_code=500,
        )


@router.get("/data-sync/files/diagnostics")
async def get_data_sync_file_diagnostics(
    hours: int = Query(24, ge=1, le=720),
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin),
):
    try:
        data = await _build_data_sync_file_diagnostics(db, hours)
        return success_response(data=data, message="获取文件链路诊断成功")
    except Exception as e:
        logger.error(f"[DataSync Files Diagnostics] 获取文件链路诊断失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取文件链路诊断失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和 data/raw 目录权限",
            status_code=500,
        )


@router.post("/data-sync/files/batch-delete-impact")
async def get_batch_file_delete_impact(
    body: CatalogFileBatchDeleteRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin),
):
    try:
        service = CatalogFileDeleteService(db)
        impact = await service.analyze_batch_delete_impact(body.file_ids)
        payload = CatalogFileBatchDeleteImpactResponse.model_validate(impact.to_dict())
        return success_response(data=payload.model_dump(), message="获取批量删除影响成功")
    except DataSyncSchemaDriftError as exc:
        logger.error(f"[DataSync BatchDeleteImpact] Schema drift: {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取批量删除影响失败：数据库结构未完成迁移，请执行 Alembic 迁移",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(exc),
            recovery_suggestion=f"执行 Alembic 迁移: {exc.recovery_command}",
            status_code=500,
        )
    except Exception as exc:
        logger.error(f"[DataSync BatchDeleteImpact] 查询失败: {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取批量删除影响失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(exc),
            status_code=500,
        )


@router.delete("/data-sync/files/batch")
async def delete_catalog_files_batch(
    body: CatalogFileBatchDeleteRequest = Body(...),
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin),
):
    try:
        service = CatalogFileDeleteService(db)
        result = await service.delete_catalog_files_batch(body.file_ids)
        payload = CatalogFileBatchDeleteResultResponse.model_validate(result.to_dict())
        return success_response(data=payload.model_dump(), message="批量删除文件成功")
    except DataSyncSchemaDriftError as exc:
        await db.rollback()
        logger.error(f"[DataSync BatchDelete] Schema drift: {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="批量删除文件失败：数据库结构未完成迁移，请执行 Alembic 迁移",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(exc),
            recovery_suggestion=f"执行 Alembic 迁移: {exc.recovery_command}",
            status_code=500,
        )
    except Exception as exc:
        await db.rollback()
        logger.error(f"[DataSync BatchDelete] 删除失败: {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="批量删除文件失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(exc),
            status_code=500,
        )


@router.get("/data-sync/files/{file_id}")
async def get_data_sync_file_detail(
    file_id: int = Path(..., description="文件ID"),
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin),
):
    try:
        result = await db.execute(select(CatalogFile).where(CatalogFile.id == file_id))
        file_record = result.scalar_one_or_none()
        if not file_record:
            return error_response(
                code=ErrorCode.DATA_NOT_FOUND,
                message="文件不存在",
                error_type=get_error_type(ErrorCode.DATA_NOT_FOUND),
                detail=f"CatalogFile id={file_id} not found",
                status_code=404,
            )

        raw_path = _resolve_catalog_file_path(file_record)
        raw_exists = raw_path.exists()
        meta_path = _resolve_catalog_meta_path(file_record, raw_path)
        meta_exists = meta_path.exists()
        meta_content = _read_catalog_meta(file_record, raw_path) if meta_exists else {}
        collection_info = meta_content.get("collection_info") or {}
        collection_task_ids = sorted(_extract_collection_task_ids_from_meta(meta_content))

        payload = {
            "id": file_record.id,
            "file_name": file_record.file_name,
            "platform": file_record.platform_code,
            "business_platform": file_record.platform_code,
            "collection_platform": file_record.source_platform,
            "domain": file_record.data_domain,
            "granularity": file_record.granularity,
            "sub_domain": file_record.sub_domain,
            "account": file_record.account,
            "shop_id": file_record.shop_id,
            "date_from": file_record.date_from.isoformat() if file_record.date_from else None,
            "date_to": file_record.date_to.isoformat() if file_record.date_to else None,
            "status": file_record.status,
            "collected_at": file_record.first_seen_at.isoformat() if file_record.first_seen_at else None,
            "catalog_registered": True,
            "meta_exists": meta_exists,
            "meta_file_path": str(meta_path),
            "file_path": str(raw_path),
            "raw_file": {
                "path": str(raw_path),
                "exists": raw_exists,
                "size": raw_path.stat().st_size if raw_exists else 0,
            },
            "meta_file": {
                "path": str(meta_path),
                "exists": meta_exists,
                "collection_info": collection_info,
                "original_path": collection_info.get("original_path"),
                "collection_task_ids": collection_task_ids,
            },
            "catalog_record": {
                "id": file_record.id,
                "file_path": file_record.file_path,
                "file_name": file_record.file_name,
                "source_platform": file_record.source_platform,
                "platform_code": file_record.platform_code,
                "data_domain": file_record.data_domain,
                "sub_domain": file_record.sub_domain,
                "granularity": file_record.granularity,
                "status": file_record.status,
                "first_seen_at": file_record.first_seen_at.isoformat() if file_record.first_seen_at else None,
                "account": file_record.account,
                "shop_id": file_record.shop_id,
                "date_from": file_record.date_from.isoformat() if file_record.date_from else None,
                "date_to": file_record.date_to.isoformat() if file_record.date_to else None,
            },
        }
        return success_response(data=payload, message="获取采集文件详情成功")
    except Exception as exc:
        logger.error("[DataSync FileDetail] 查询失败: %s", exc, exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取采集文件详情失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(exc),
            status_code=500,
        )


@router.get("/data-sync/files/{file_id}/delete-impact")
async def get_file_delete_impact(
    file_id: int = Path(..., description="文件ID"),
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin),
):
    try:
        service = CatalogFileDeleteService(db)
        impact = await service.analyze_delete_impact(file_id)
        payload = CatalogFileDeleteImpactResponse.model_validate(impact.to_dict())
        return success_response(data=payload.model_dump(), message="获取删除影响成功")
    except CatalogFileDeleteNotFoundError as exc:
        return error_response(
            code=ErrorCode.DATA_NOT_FOUND,
            message="文件不存在",
            error_type=get_error_type(ErrorCode.DATA_NOT_FOUND),
            detail=str(exc),
            status_code=404,
        )
    except DataSyncSchemaDriftError as exc:
        logger.error(f"[DataSync DeleteImpact] Schema drift: {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取删除影响失败：数据库结构未完成迁移，请执行 Alembic 迁移",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(exc),
            recovery_suggestion=f"执行 Alembic 迁移: {exc.recovery_command}",
            status_code=500,
        )
    except Exception as exc:
        logger.error(f"[DataSync DeleteImpact] 查询失败: {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取删除影响失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(exc),
            status_code=500,
        )


@router.delete("/data-sync/files/{file_id}")
async def delete_catalog_file(
    file_id: int = Path(..., description="文件ID"),
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin),
):
    try:
        service = CatalogFileDeleteService(db)
        result = await service.delete_catalog_file(file_id, force=True)
        payload = CatalogFileDeleteResultResponse.model_validate(result.to_dict())
        return success_response(data=payload.model_dump(), message="删除文件成功")
    except CatalogFileDeleteNotFoundError as exc:
        return error_response(
            code=ErrorCode.DATA_NOT_FOUND,
            message="文件不存在",
            error_type=get_error_type(ErrorCode.DATA_NOT_FOUND),
            detail=str(exc),
            status_code=404,
        )
    except DataSyncSchemaDriftError as exc:
        await db.rollback()
        logger.error(f"[DataSync Delete] Schema drift: {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="删除文件失败：数据库结构未完成迁移，请执行 Alembic 迁移",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(exc),
            recovery_suggestion=f"执行 Alembic 迁移: {exc.recovery_command}",
            status_code=500,
        )
    except Exception as exc:
        await db.rollback()
        logger.error(f"[DataSync Delete] 删除失败: {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="删除文件失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(exc),
            status_code=500,
        )


@router.post("/data-sync/single")
@role_based_rate_limit(endpoint_type="data_sync")  # [*] v4.19.4: 基于角色的动态限流
async def sync_single_file(
    body: SingleFileSyncRequest,  # [*] 修复:重命名为 body 避免与 slowapi 的 request 参数冲突
    request: Request,  # [*] 修复:参数名必须为 request(slowapi 要求)
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user)  # [*] Phase 4.2: 用户认证
):
    """
    单文件数据同步(使用 Celery 任务)
    
    [*] Phase 2: 限流(10次/分钟)
    """
    """
    单文件数据同步(使用 Celery 任务)
    
    v4.19.1 恢复:使用 Celery 任务队列执行数据同步
    - 任务持久化:任务存储在 Redis 中,服务器重启后自动恢复
    - 资源隔离:任务在独立的 Celery worker 进程中执行,不影响 API 服务
    - 降级处理:Celery 不可用时,降级到 asyncio.create_task()
    """
    try:
        # 验证文件是否存在
        result = await db.execute(
            select(CatalogFile).where(CatalogFile.id == body.file_id)
        )
        catalog_file = result.scalar_one_or_none()
        if not catalog_file:
            return error_response(
                code=ErrorCode.FILE_NOT_FOUND,
                message="文件不存在",
                error_type=get_error_type(ErrorCode.FILE_NOT_FOUND),
                detail=f"文件ID: {body.file_id}",
                recovery_suggestion="请检查文件ID是否正确",
                status_code=404
            )
        
        # 检查状态(防止并发)
        if catalog_file.status == 'processing':
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="文件正在处理中",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                detail=f"文件ID: {body.file_id}, 文件名: {catalog_file.file_name}",
                recovery_suggestion="请等待当前同步任务完成",
                status_code=409
            )
        
        # [*] Phase 4.2: 检查用户任务配额
        user_id = current_user.user_id
        quota_service = get_user_task_quota_service()
        can_submit, error_message = await quota_service.can_submit_task(user_id)
        if not can_submit:
            return error_response(
                code=ErrorCode.VALIDATION_ERROR,
                message="任务数量超过限制",
                error_type=get_error_type(ErrorCode.VALIDATION_ERROR),
                detail=error_message,
                recovery_suggestion=f"请等待当前任务完成后再提交新任务(最多允许 {quota_service.max_concurrent_tasks} 个并发任务)",
                status_code=429  # Too Many Requests
            )
        
        # 生成task_id
        task_id = f"single_file_{body.file_id}_{uuid.uuid4().hex[:8]}"

        async def _attach_task_subject_links() -> None:
            from backend.services.platform_table_manager import PlatformTableManager
            from backend.services.task_center_service import TaskCenterService

            task_center_service = TaskCenterService(db)
            source_table_name = None
            if (
                catalog_file.platform_code
                and catalog_file.data_domain
                and catalog_file.granularity
            ):
                source_table_name = PlatformTableManager(db).get_table_name(
                    platform=catalog_file.platform_code,
                    data_domain=catalog_file.data_domain,
                    sub_domain=catalog_file.sub_domain,
                    granularity=catalog_file.granularity,
                )

            await task_center_service.update_task(
                task_id,
                source_file_id=catalog_file.id,
                platform_code=catalog_file.platform_code,
                source_table_name=source_table_name,
            )
            await task_center_service.add_link(
                task_id,
                subject_type="catalog_file",
                subject_id=str(catalog_file.id),
            )
            if source_table_name:
                await task_center_service.add_link(
                    task_id,
                    subject_type="source_table",
                    subject_key=source_table_name,
                )
        
        # v4.19.1: 提交 Celery 任务,添加降级处理
        try:
            from backend.tasks.data_sync_tasks import sync_single_file_task
            
            # [*] 修复:在提交Celery任务之前,先创建进度记录(避免前端查询404)
            # 注意:create_task默认状态就是pending(数据库约束允许的状态)
            progress_tracker = SyncProgressTracker(db)
            await progress_tracker.create_task(
                task_id=task_id,
                task_type="single_file",
                total_files=1
            )
            await _attach_task_subject_links()
            # 可选:更新消息说明任务已提交
            submission_task_details = {
                "submission_args": {
                    "file_id": body.file_id,
                },
                "submission_kwargs": {
                    "only_with_template": body.only_with_template,
                    "allow_quarantine": body.allow_quarantine,
                    "use_template_header_row": body.use_template_header_row,
                    "user_id": user_id,
                },
                "priority": body.priority,
            }
            await progress_tracker.update_task(task_id, {
                "message": "任务已提交,等待Celery worker处理",
                "task_details": submission_task_details,
            })
            
            # [*] Phase 4.2: 增加用户任务计数
            await quota_service.increment_user_task_count(user_id)
            
            # [*] Phase 4: 使用 apply_async 支持优先级参数
            celery_task = sync_single_file_task.apply_async(
                args=(body.file_id, task_id),
                kwargs={
                    'only_with_template': body.only_with_template,
                    'allow_quarantine': body.allow_quarantine,
                    'use_template_header_row': body.use_template_header_row,
                    'user_id': user_id  # [*] Phase 4.2: 添加用户ID(用于审计和配额管理)
                },
                priority=body.priority  # [*] Phase 4: 任务优先级(1-10,10最高)
            )
            await progress_tracker.set_runner(
                task_id,
                runner_kind="celery",
                external_runner_id=celery_task.id,
            )
            
            logger.info(
                f"[API] 单文件同步任务已提交 file_id={body.file_id}, task_id={task_id}, "
                f"celery_task_id={celery_task.id}"
            )
            
            # 立即返回task_id
            return success_response(
                data={
                    'task_id': task_id,
                    'celery_task_id': celery_task.id,
                    'file_id': body.file_id,
                    'file_name': catalog_file.file_name,
                    'status': 'pending',  # [*] 修复:使用pending状态(与数据库一致)
                    'message': '同步任务已提交,正在后台处理'
                },
                message='同步任务已提交'
            )
        except Exception as celery_error:
            # Celery任务提交失败时的降级处理
            error_type = type(celery_error).__name__
            if "OperationalError" in error_type or "ConnectionError" in error_type or "redis" in str(celery_error).lower():
                # Redis连接失败,降级到 asyncio.create_task()
                logger.warning(f"[API] Redis/Celery连接失败({error_type}),降级到 asyncio.create_task()")
                
                # 创建进度任务
                progress_tracker = SyncProgressTracker(db)
                await progress_tracker.create_task(
                    task_id=task_id,
                    task_type="single_file",
                    total_files=1
                )
                await _attach_task_subject_links()
                await progress_tracker.update_task(
                    task_id,
                    {
                        "message": "Celery不可用,使用降级模式",
                        "task_details": {
                            "submission_args": {
                                "file_id": body.file_id,
                            },
                            "submission_kwargs": {
                                "only_with_template": body.only_with_template,
                                "allow_quarantine": body.allow_quarantine,
                                "use_template_header_row": body.use_template_header_row,
                                "user_id": user_id,
                            },
                            "priority": body.priority,
                            "fallback": True,
                        },
                    },
                )
                
                # [*] Phase 4.2: 增加用户任务计数(降级模式也需要配额管理)
                await quota_service.increment_user_task_count(user_id)
                
                # 降级到 asyncio.create_task()
                asyncio.create_task(
                    process_single_sync_background(
                        file_id=body.file_id,
                        task_id=task_id,
                        only_with_template=body.only_with_template,
                        allow_quarantine=body.allow_quarantine,
                        use_template_header_row=body.use_template_header_row,
                        user_id=user_id  # [*] Phase 4.2: 传递用户ID
                    )
                )
                
                logger.info(
                    f"[API] 单文件同步任务已提交(降级模式)file_id={body.file_id}, task_id={task_id}"
                )
                
                return success_response(
                    data={
                        'task_id': task_id,
                        'file_id': body.file_id,
                        'file_name': catalog_file.file_name,
                        'status': 'pending',  # [*] 修复:使用pending状态(与数据库一致)
                        'fallback': True,
                        'message': 'Celery不可用,使用降级模式'
                    },
                    message='同步任务已提交(降级模式)'
                )
            else:
                # 其他错误,重新抛出
                raise celery_error
        
    except Exception as e:
        logger.error(f"[API] 单文件同步失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="单文件同步失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限,或联系系统管理员",
            status_code=500
        )


# ==================== 后台任务处理函数 ====================

async def process_single_sync_background(
    file_id: int,
    task_id: str,
    only_with_template: bool = True,
    allow_quarantine: bool = True,
    use_template_header_row: bool = True,
    user_id: int = None  # [*] Phase 4.2: 用户ID(可选,用于配额管理)
):
    """
    后台单文件同步处理函数(使用 asyncio.create_task)
    
    v4.18.0新增:将单文件同步改为异步处理,避免前端页面阻塞
    v4.18.2更新:使用AsyncSessionLocal真异步会话,避免阻塞事件循环
    v4.18.2修复:使用 asyncio.create_task() 替代 BackgroundTasks,添加并发控制
    - 立即返回task_id
    - 后台异步处理
    - 进度跟踪(数据库存储)
    - 并发控制(Semaphore)
    """
    # [*] v4.18.2修复:使用 Semaphore 控制并发
    # [*] v4.18.2性能监控:记录任务开始时间
    import time
    task_start_time = time.time()
    async with MAX_CONCURRENT_SYNC_TASKS:
        # [*] v4.18.2修复:使用异步会话
        db = AsyncSessionLocal()
        progress_tracker = SyncProgressTracker(db)
    
        try:
            logger.info(f"[BackgroundTask] 开始单文件同步 file_id={file_id}, task_id={task_id}")
            
            # 创建进度任务(异步方法)
            await progress_tracker.create_task(
                task_id=task_id,
                task_type="single_file",
                total_files=1
            )
            await progress_tracker.update_task(task_id, {"status": "processing"})
            
            # 创建独立的异步数据库会话进行同步
            db_sync = AsyncSessionLocal()
            try:
                sync_service = DataSyncService(db_sync)
                result = await sync_service.sync_single_file(
                    file_id=file_id,
                    only_with_template=only_with_template,
                    allow_quarantine=allow_quarantine,
                    task_id=task_id,
                    use_template_header_row=use_template_header_row
                )
                
                # 更新进度并完成任务(异步方法)
                if result.get('success', False):
                    await progress_tracker.update_task(task_id, {
                        "processed_files": 1,
                        "current_file": result.get('file_name', ''),
                        "file_progress": 100.0
                    })
                    await progress_tracker.complete_task(task_id, success=True)
                    # [*] v4.18.2性能监控:记录任务总耗时
                    task_elapsed = (time.time() - task_start_time) * 1000
                    logger.info(
                        f"[BackgroundTask] 单文件同步成功 file_id={file_id}, task_id={task_id}, "
                        f"总耗时={task_elapsed:.2f}ms"
                    )
                else:
                    # 记录错误
                    error_msg = result.get('message', '同步失败')
                    await progress_tracker.update_task(task_id, {
                        "processed_files": 1,
                        "current_file": result.get('file_name', ''),
                        "file_progress": 100.0
                    })
                    await progress_tracker.add_error(task_id, error_msg)
                    await progress_tracker.complete_task(task_id, success=False, error=error_msg)
                    # [*] v4.18.2性能监控:记录任务总耗时
                    task_elapsed = (time.time() - task_start_time) * 1000
                    logger.warning(
                        f"[BackgroundTask] 单文件同步失败 file_id={file_id}, task_id={task_id}, "
                        f"message={error_msg}, 总耗时={task_elapsed:.2f}ms"
                    )
            finally:
                await db_sync.close()
                
        except Exception as e:
            logger.error(f"[BackgroundTask] 单文件同步异常 file_id={file_id}, task_id={task_id}: {e}", exc_info=True)
            try:
                error_msg = str(e)
                await progress_tracker.add_error(task_id, error_msg)
                await progress_tracker.complete_task(task_id, success=False, error=error_msg)
            except Exception:
                pass
        finally:
            # [*] Phase 4.2: 减少用户任务计数(任务完成或失败时)
            if user_id:
                try:
                    quota_service = get_user_task_quota_service()
                    await quota_service.decrement_user_task_count(user_id)
                except Exception as quota_error:
                    logger.warning(f"[BackgroundTask] 减少用户 {user_id} 任务计数失败: {quota_error}")
            
            try:
                await db.close()
            except Exception:
                pass


async def process_batch_sync_background(
    file_ids: List[int],
    task_id: str,
    only_with_template: bool = True,
    allow_quarantine: bool = True,
    use_template_header_row: bool = True,  # [*] 新增:使用模板表头行
    max_concurrent: int = 10,
    user_id: int = None  # [*] Phase 4.2: 用户ID(可选,用于配额管理)
):
    """
    后台批量同步处理函数(使用FastAPI BackgroundTasks)
    
    [*] v4.12.2简化:使用FastAPI BackgroundTasks替代Celery
    v4.18.2更新:使用AsyncSessionLocal真异步会话,避免阻塞事件循环
    - 支持并发控制(最多10个并发)
    - 自动数据质量Gate检查
    - 进度跟踪(数据库存储)
    """
    # [*] v4.18.2修复:使用异步会话
    db_main = AsyncSessionLocal()
    progress_tracker = SyncProgressTracker(db_main)
    
    # [*] v4.17.1新增:任务超时保护(默认30分钟)
    TASK_TIMEOUT_SECONDS = 30 * 60  # 30分钟
    task_start_time = datetime.now()
    
    try:
        logger.info(f"[BackgroundTask] 开始批量同步 {len(file_ids)} 个文件, task_id={task_id}, 超时时间={TASK_TIMEOUT_SECONDS}秒")
        
        # 统计变量
        processed_files = 0
        success_files = 0
        failed_files = 0
        skipped_files = 0  # [*] 新增:跳过文件数(全部数据重复)
        total_rows = 0
        valid_rows = 0
        error_rows = 0
        quarantined_rows = 0
        
        def check_timeout() -> bool:
            """检查任务是否超时"""
            elapsed = (datetime.now() - task_start_time).total_seconds()
            if elapsed > TASK_TIMEOUT_SECONDS:
                logger.warning(
                    f"[BackgroundTask] 任务{task_id}超时: 已运行{elapsed:.1f}秒,超过限制{TASK_TIMEOUT_SECONDS}秒"
                )
                return True
            return False
        
        # [*] 并发控制(使用信号量限制并发数)
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def sync_file_with_semaphore(file_id: int) -> Dict[str, Any]:
            """
            带信号量的文件同步
            
            [*] 修复:每个协程使用独立的数据库会话,避免并发冲突
            v4.18.2更新:使用异步会话
            """
            async with semaphore:
                # [*] v4.18.2修复:为每个协程创建独立的异步数据库会话
                db = AsyncSessionLocal()
                try:
                    sync_service = DataSyncService(db)
                    result = await sync_service.sync_single_file(
                        file_id=file_id,
                        only_with_template=only_with_template,
                        allow_quarantine=allow_quarantine,
                        task_id=task_id,
                        use_template_header_row=use_template_header_row
                    )
                    return result
                except Exception as e:
                    # 记录协程级别的异常
                    logger.error(f"[BackgroundTask] 文件{file_id}同步异常: {e}", exc_info=True)
                    # [*] v4.18.2修复:确保异常时回滚事务并关闭会话(异步)
                    try:
                        await db.rollback()
                    except Exception:
                        pass
                    # 返回错误结果而不是抛出异常(让gather收集)
                    return {
                        'success': False,
                        'file_id': file_id,
                        'status': 'failed',
                        'message': f'同步异常: {str(e)}'
                    }
                finally:
                    # [*] v4.18.2修复:确保每个协程的异步会话都被正确关闭
                    try:
                        await db.close()
                    except Exception:
                        pass
        
        # [*] v4.17.1新增:超时检查 - 在开始处理前检查
        if check_timeout():
            raise TimeoutError(f"任务{task_id}在开始处理前已超时")
        
        # 批量处理文件(异步并发)
        tasks = [sync_file_with_semaphore(file_id) for file_id in file_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # [*] v4.17.1新增:超时检查 - 在处理完成后检查
        if check_timeout():
            logger.warning(f"[BackgroundTask] 任务{task_id}在处理完成后发现超时,但已完成处理")
        
        # 处理结果(使用主会话查询文件信息)
        for i, result in enumerate(results):
            # [*] v4.17.1新增:在处理每个文件结果时检查超时
            if check_timeout():
                logger.warning(
                    f"[BackgroundTask] 任务{task_id}在处理结果时超时,已处理{processed_files}/{len(file_ids)}个文件,"
                    f"剩余{len(file_ids) - processed_files}个文件未处理"
                )
                # 标记剩余文件为超时失败
                remaining_files = len(file_ids) - processed_files
                failed_files += remaining_files
                processed_files = len(file_ids)  # 标记所有文件已处理
                break  # 停止处理剩余文件
            
            file_id = file_ids[i]
            
            # [*] v4.15.0修复:获取文件信息时处理事务错误
            file_name = f"文件{file_id}"
            try:
                # v4.18.2更新:使用异步查询
                result_query = await db_main.execute(
                    select(CatalogFile).where(CatalogFile.id == file_id)
                )
                file_record = result_query.scalar_one_or_none()
                if file_record:
                    file_name = file_record.file_name
            except Exception as query_error:
                # 如果查询失败(可能是事务错误),记录警告但继续处理
                error_str = str(query_error)
                is_transaction_error = (
                    'InFailedSqlTransaction' in error_str or 
                    'current transaction is aborted' in error_str.lower()
                )
                if is_transaction_error:
                    logger.warning(f"[BackgroundTask] 查询文件信息时事务错误,尝试回滚: {query_error}")
                    try:
                        await db_main.rollback()
                        # 重试查询(异步)
                        result_query = await db_main.execute(
                            select(CatalogFile).where(CatalogFile.id == file_id)
                        )
                        file_record = result_query.scalar_one_or_none()
                        if file_record:
                            file_name = file_record.file_name
                    except Exception as retry_error:
                        logger.error(f"[BackgroundTask] 重试查询文件信息失败: {retry_error}")
                else:
                    logger.error(f"[BackgroundTask] 查询文件信息失败: {query_error}")
            
            if isinstance(result, Exception):
                # [*] v4.15.0修复:异常情况(这种情况不应该发生,因为我们已经修复了协程异常处理)
                processed_files += 1
                failed_files += 1
                error_str = str(result)
                error_type = type(result).__name__
                
                # 构建详细的错误消息
                if 'InFailedSqlTransaction' in error_str or 'current transaction is aborted' in error_str.lower():
                    error_msg = f"文件{file_name}({file_id})数据库事务错误: {error_str}(可能是并发冲突)"
                else:
                    error_msg = f"文件{file_name}({file_id})同步异常 ({error_type}): {error_str}"
                
                await progress_tracker.add_error(task_id, error_msg)
                logger.error(f"[BackgroundTask] {error_msg}", exc_info=True)
                
                # 更新进度(异步)
                await progress_tracker.update_task(task_id, {
                    "processed_files": processed_files,
                    "current_file": file_name,
                    "status": "processing"
                })
            else:
                # 正常结果
                processed_files += 1
                
                # 累计行数统计
                total_rows += result.get("staged", 0) + result.get("imported", 0) + result.get("quarantined", 0)
                valid_rows += result.get("imported", 0)
                quarantined_rows += result.get("quarantined", 0)
                
                if result.get("success"):
                    # [*] v4.15.0增强:区分INSERT策略的跳过和UPSERT策略的更新
                    skip_reason = result.get("skip_reason", "")
                    
                    # 检查是否是已入库文件跳过
                    if skip_reason == "file_already_ingested":
                        # 已入库文件:统计为跳过(不是失败)
                        skipped_files += 1
                        logger.info(
                            f"[BackgroundTask] [v4.15.0] 文件{file_name}({file_id})已入库,跳过同步"
                        )
                    else:
                        import_stats = result.get("import_stats")
                        if import_stats and import_stats.get("updated", 0) > 0:
                            # UPSERT策略:有更新的文件统计为成功(更新)
                            success_files += 1
                            logger.info(
                                f"[BackgroundTask] [v4.15.0] 文件{file_name}({file_id})使用UPSERT策略: "
                                f"新插入{import_stats.get('inserted', 0)}行,更新{import_stats.get('updated', 0)}行"
                            )
                        elif result.get("skipped", False):
                            # [*] v4.16.0更新:检查是否有更新统计信息(UPSERT策略)
                            import_stats = result.get("import_stats", {})
                            updated_count = import_stats.get('updated', 0) if import_stats else 0
                            
                            if updated_count > 0:
                                # UPSERT策略:有更新,统计为成功(更新)
                                success_files += 1
                                logger.info(
                                    f"[BackgroundTask] [v4.16.0] 文件{file_name}({file_id})使用UPSERT策略: "
                                    f"所有数据都已存在,已更新{updated_count}行"
                                )
                            else:
                                # INSERT策略或异常情况:全部数据重复,统计为跳过
                                skipped_files += 1
                                logger.info(
                                    f"[BackgroundTask] 文件{file_name}({file_id})所有数据都已存在,已跳过重复数据"
                                )
                        else:
                            # 正常插入
                            success_files += 1
                else:
                    failed_files += 1
                    error_rows += result.get("staged", 0)
                    
                    # [*] v4.15.0修复:获取详细的错误消息
                    error_message = result.get('message')
                    if not error_message or error_message == '未知错误':
                        # 尝试从其他字段获取错误信息
                        error_message = result.get('error') or result.get('detail') or f"同步失败(状态: {result.get('status', 'unknown')})"
                    
                    error_msg = f"文件{file_name}({file_id})同步失败: {error_message}"
                    await progress_tracker.add_error(task_id, error_msg)
                    logger.error(f"[BackgroundTask] {error_msg}")
                
                # 更新进度(将跳过文件数存储在task_details中)(异步)
                task_details = {"skipped_files": skipped_files}
                await progress_tracker.update_task(task_id, {
                    "processed_files": processed_files,
                    "total_rows": total_rows,
                    "processed_rows": valid_rows + quarantined_rows + error_rows,
                    "valid_rows": valid_rows,
                    "quarantined_rows": quarantined_rows,
                    "error_rows": error_rows,
                    "current_file": file_name,
                    "status": "processing",
                    "task_details": task_details  # [*] 新增:存储跳过文件数
                })
        
        # [*] v4.17.1新增:超时检查 - 在质量检查前检查
        if check_timeout():
            logger.warning(f"[BackgroundTask] 任务{task_id}在质量检查前超时,跳过质量检查")
        else:
            # [*] 数据质量Gate(批量同步完成后自动质量检查)
            # [*] v4.17.1修复:使用独立的数据库会话进行质量检查,避免事务错误影响主流程
            quality_check_result = None
            db_quality = None
            try:
                # [*] v4.18.2修复:使用异步会话查询成功文件
                success_file_ids = [
                    fid for i, fid in enumerate(file_ids) 
                    if not isinstance(results[i], Exception) and results[i].get("success")
                ]
                
                if success_file_ids:
                    result_query = await db_main.execute(
                        select(CatalogFile).where(CatalogFile.id.in_(success_file_ids))
                    )
                    successful_files = result_query.scalars().all()
                else:
                    successful_files = []
                
                # [*] v4.18.2修复:质量检查使用run_in_executor包装同步调用
                if successful_files:
                    # 按平台+店铺分组
                    platform_shops = {}
                    for file_record in successful_files:
                        key = f"{file_record.platform_code}_{file_record.shop_id or 'default'}"
                        if key not in platform_shops:
                            platform_shops[key] = {
                                "platform_code": file_record.platform_code,
                                "shop_id": file_record.shop_id
                            }
                    
                    # 对每个平台+店铺组合进行质量检查(使用run_in_executor包装)
                    def _sync_quality_check(platform_shops_dict):
                        """同步质量检查函数"""
                        from backend.models.database import SessionLocal
                        db_quality = SessionLocal()
                        try:
                            validator = get_c_class_data_validator(db_quality)
                            quality_scores = []
                            missing_fields_list = []
                            
                            for key, info in platform_shops_dict.items():
                                try:
                                    check_result = validator.check_b_class_completeness(
                                        platform_code=info["platform_code"],
                                        shop_id=info["shop_id"],
                                        metric_date=datetime.now().date()
                                    )
                                    
                                    if check_result and not check_result.get("error"):
                                        quality_scores.append(check_result.get("data_quality_score", 0))
                                        missing_fields = check_result.get("missing_fields", [])  # [*] 修复:使用正确的字段名(check_b_class_completeness 返回的是 missing_fields,不是 missing_core_fields)
                                        if missing_fields:
                                            missing_fields_list.extend(missing_fields)
                                except Exception as check_error:
                                    # [*] v4.17.1修复:单个平台的质量检查失败不影响其他平台
                                    error_str = str(check_error)
                                    if 'InFailedSqlTransaction' in error_str or 'UndefinedColumn' in error_str:
                                        logger.warning(
                                            f"[BackgroundTask] 平台{info['platform_code']}质量检查失败(可能是表结构问题): {check_error}"
                                        )
                                        # 回滚质量检查会话的事务
                                        try:
                                            db_quality.rollback()
                                        except Exception:
                                            pass
                                    else:
                                        logger.warning(
                                            f"[BackgroundTask] 平台{info['platform_code']}质量检查失败: {check_error}"
                                        )
                            
                            return {
                                "quality_scores": quality_scores,
                                "missing_fields_list": missing_fields_list
                            }
                        finally:
                            db_quality.close()
                    
                    # 使用run_in_executor执行同步质量检查
                    loop = asyncio.get_running_loop()
                    quality_result = await loop.run_in_executor(None, _sync_quality_check, platform_shops)
                    
                    quality_scores = quality_result["quality_scores"]
                    missing_fields_list = quality_result["missing_fields_list"]
                    
                    # 计算平均质量评分
                    avg_quality_score = sum(quality_scores) / len(quality_scores) if quality_scores else 0
                    
                    quality_check_result = {
                        "avg_quality_score": round(avg_quality_score, 2),
                        "checked_platforms": len(platform_shops),
                        "missing_fields": list(set(missing_fields_list)),
                        "timestamp": datetime.now().isoformat()
                    }
                    
                    # 保存质量检查结果到任务详情(使用主会话,异步)
                    await progress_tracker.update_task(task_id, {
                        "task_details": {
                            "quality_check": quality_check_result
                        }
                    })
                    
                    logger.info(f"[BackgroundTask] 数据质量检查完成: 平均评分={avg_quality_score:.2f}")

                    standardization_checks = []
                    quality_service = SyncStandardizationQualityService()
                    product_groups = {}
                    for file_record in successful_files:
                        if getattr(file_record, "data_domain", None) != "products":
                            continue
                        group_key = (
                            file_record.platform_code,
                            getattr(file_record, "granularity", None) or "daily",
                        )
                        product_groups.setdefault(group_key, []).append(file_record.id)

                    for (platform_code, granularity), grouped_file_ids in product_groups.items():
                        check = await quality_service.check_products_file(
                            db_main,
                            platform_code=platform_code,
                            granularity=granularity,
                            file_ids=grouped_file_ids,
                        )
                        warnings = list(check.get("warnings") or [])
                        for warning in warnings:
                            await progress_tracker.add_warning(task_id, warning)
                        standardization_checks.append(
                            {
                                "platform_code": platform_code,
                                "data_domain": "products",
                                "granularity": granularity,
                                "file_ids": grouped_file_ids,
                                "warnings": warnings,
                            }
                        )

                    if standardization_checks:
                        await progress_tracker.update_task(
                            task_id,
                            {"task_details": {"standardization_quality": standardization_checks}},
                        )
            except Exception as e:
                logger.warning(f"[BackgroundTask] 数据质量检查失败: {e}", exc_info=True)
                # [*] v4.17.1修复:确保质量检查会话回滚,不影响主流程
                if db_quality:
                    try:
                        db_quality.rollback()
                    except Exception:
                        pass
                # 质量检查失败不影响同步结果
            finally:
                # [*] v4.17.1修复:确保质量检查会话被关闭
                if db_quality:
                    try:
                        db_quality.close()
                    except Exception:
                        pass
        
        # 完成任务(更新最终统计信息)(异步)
        final_task_details = {
            "success_files": success_files,
            "failed_files": failed_files,
            "skipped_files": skipped_files
        }
        await progress_tracker.update_task(task_id, {
            "task_details": final_task_details
        })
        
        # 构建完成消息(包含跳过文件数)
        if skipped_files > 0:
            completion_message = f"成功{success_files}个,失败{failed_files}个,跳过{skipped_files}个"
        else:
            completion_message = f"成功{success_files}个,失败{failed_files}个"
        
        # [*] v4.17.1新增:检查是否因超时失败
        task_elapsed = (datetime.now() - task_start_time).total_seconds()
        if task_elapsed > TASK_TIMEOUT_SECONDS:
            completion_message = f"任务超时(已运行{task_elapsed:.1f}秒,超过限制{TASK_TIMEOUT_SECONDS}秒): {completion_message}"
            logger.warning(f"[BackgroundTask] {completion_message}")
            await progress_tracker.complete_task(
                task_id,
                success=False,
                error=completion_message
            )
        else:
            await progress_tracker.complete_task(
                task_id,
                success=(failed_files == 0),
                error=None if failed_files == 0 else completion_message
            )
            logger.info(f"[BackgroundTask] 批量同步完成: {completion_message}(耗时{task_elapsed:.1f}秒)")
        
    except Exception as e:
        # [*] v4.15.0修复:捕获批量同步的整体异常,记录详细错误信息
        error_str = str(e)
        error_type = type(e).__name__
        
        # 构建详细的错误消息
        if 'InFailedSqlTransaction' in error_str or 'current transaction is aborted' in error_str.lower():
            error_message = f"批量同步失败:数据库事务错误 ({error_type}): {error_str}(可能是并发冲突或数据库连接问题)"
        else:
            error_message = f"批量同步失败 ({error_type}): {error_str}"
        
        logger.error(f"[BackgroundTask] {error_message}", exc_info=True)
        
        # 记录所有已处理的文件信息(异步)
        try:
            await progress_tracker.add_error(task_id, error_message)
        except Exception as add_error_err:
            logger.error(f"[BackgroundTask] 添加错误信息失败: {add_error_err}")
        
        # 完成任务(异步)
        try:
            await progress_tracker.complete_task(task_id, success=False, error=error_message)
        except Exception as complete_err:
            logger.error(f"[BackgroundTask] 完成任务失败: {complete_err}")
            # 如果complete_task也失败,至少记录日志
    finally:
        # [*] Phase 4.2: 减少用户任务计数(任务完成或失败时)
        if user_id:
            try:
                quota_service = get_user_task_quota_service()
                await quota_service.decrement_user_task_count(user_id)
            except Exception as quota_error:
                logger.warning(f"[BackgroundTask] 减少用户 {user_id} 任务计数失败: {quota_error}")
        
        # [*] v4.18.2修复:关闭主异步会话
        await db_main.close()


@router.post("/data-sync/batch")
@role_based_rate_limit(endpoint_type="data_sync")  # [*] v4.19.4: 基于角色的动态限流
async def sync_batch(
    body: BatchSyncRequest,  # [*] 修复:重命名为 body 避免与 slowapi 的 request 参数冲突
    request: Request,  # [*] 修复:参数名必须为 request(slowapi 要求)
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user)  # [*] Phase 4.2: 用户认证
):
    """
    批量数据同步(使用 Celery 任务)
    
    v4.19.1 恢复:使用 Celery 任务队列执行数据同步
    - 任务持久化:任务存储在 Redis 中,服务器重启后自动恢复
    - 资源隔离:任务在独立的 Celery worker 进程中执行,不影响 API 服务
    - 降级处理:Celery 不可用时,降级到 asyncio.create_task()
    """
    try:
        progress_tracker = SyncProgressTracker(db)
        
        # 生成task_id
        task_id = f"batch_{uuid.uuid4().hex[:8]}"
        
        # 查询待处理文件
        query = select(CatalogFile).where(
            CatalogFile.status == "pending"
        )
        
        # 平台筛选
        if body.platform and body.platform != "*":
            query = query.where(CatalogFile.platform_code == body.platform)
        
        # 数据域筛选
        if body.domains:
            query = query.where(CatalogFile.data_domain.in_(body.domains))
        
        # 粒度筛选
        if body.granularities:
            query = query.where(CatalogFile.granularity.in_(body.granularities))
        
        # 时间筛选(使用 UTC 时间)
        if body.since_hours:
            from datetime import timezone
            since_time = datetime.now(timezone.utc) - timedelta(hours=body.since_hours)
            query = query.where(CatalogFile.first_seen_at >= since_time)
        
        # 限制数量
        query = query.limit(body.limit)
        
        # 执行查询
        result = await db.execute(query)
        files = result.scalars().all()
        file_ids = [f.id for f in files]
        total_files = len(file_ids)
        
        if total_files == 0:
            return success_response(
                data={
                    "task_id": task_id,
                    "total_files": 0,
                    "processed_files": 0,
                },
                message="没有待处理的文件"
            )
        
        # [*] Phase 4.2: 检查用户任务配额
        user_id = current_user.user_id
        quota_service = get_user_task_quota_service()
        can_submit, error_message = await quota_service.can_submit_task(user_id)
        if not can_submit:
            return error_response(
                code=ErrorCode.VALIDATION_ERROR,
                message="任务数量超过限制",
                error_type=get_error_type(ErrorCode.VALIDATION_ERROR),
                detail=error_message,
                recovery_suggestion=f"请等待当前任务完成后再提交新任务(最多允许 {quota_service.max_concurrent_tasks} 个并发任务)",
                status_code=429  # Too Many Requests
            )
        
        # 创建进度任务
        await progress_tracker.create_task(
            task_id=task_id,
            total_files=total_files,
            task_type="bulk_ingest"
        )
        
        # v4.19.1: 提交 Celery 任务,添加降级处理
        try:
            from backend.tasks.data_sync_tasks import sync_batch_task
            
            # [*] Phase 4.2: 增加用户任务计数
            await quota_service.increment_user_task_count(user_id)
            
            # 动态并发数(最多20个并发)
            max_concurrent = min(20, max(5, len(file_ids) // 10 + 1))
            
            # [*] Phase 4: 使用 apply_async 支持优先级参数
            celery_task = sync_batch_task.apply_async(
                args=(file_ids, task_id),
                kwargs={
                    'only_with_template': body.only_with_template,
                    'allow_quarantine': body.allow_quarantine,
                    'use_template_header_row': True,  # BatchSyncRequest没有此字段,使用固定值True
                    'max_concurrent': max_concurrent,
                    'user_id': user_id  # [*] Phase 4.2: 添加用户ID(用于审计和配额管理)
                },
                priority=body.priority  # [*] Phase 4: 任务优先级(1-10,10最高)
            )
            
            logger.info(f"[API] 批量同步任务已提交: task_id={task_id}, 文件数={total_files}, celery_task_id={celery_task.id}")
            
            # 立即返回task_id
            return success_response(
                data={
                    "task_id": task_id,
                    "celery_task_id": celery_task.id,
                    "total_files": total_files,
                    "processed_files": 0,
                },
                message=f"批量同步任务已提交,正在处理{total_files}个文件"
            )
        except Exception as celery_error:
            # Celery任务提交失败时的降级处理
            error_type = type(celery_error).__name__
            if "OperationalError" in error_type or "ConnectionError" in error_type or "redis" in str(celery_error).lower():
                # Redis连接失败,降级到 asyncio.create_task()
                logger.warning(f"[API] Redis/Celery连接失败({error_type}),降级到 asyncio.create_task()")
                
                # 动态并发数
                max_concurrent = min(20, max(5, len(file_ids) // 10 + 1))
                
                # [*] Phase 4.2: 增加用户任务计数(降级模式也需要配额管理)
                await quota_service.increment_user_task_count(user_id)
                
                # 降级到 asyncio.create_task()
                asyncio.create_task(
                    process_batch_sync_background(
                        file_ids=file_ids,
                        task_id=task_id,
                        only_with_template=body.only_with_template,
                        allow_quarantine=body.allow_quarantine,
                        use_template_header_row=True,
                        max_concurrent=max_concurrent,
                        user_id=user_id  # [*] Phase 4.2: 传递用户ID
                    )
                )
                
                logger.info(f"[API] 批量同步任务已提交(降级模式): task_id={task_id}, 文件数={total_files}")
                
                return success_response(
                    data={
                        "task_id": task_id,
                        "total_files": total_files,
                        "processed_files": 0,
                        "fallback": True,
                        "message": "Celery不可用,使用降级模式"
                    },
                    message=f"批量同步任务已提交(降级模式),正在处理{total_files}个文件"
                )
            else:
                # 其他错误,重新抛出
                raise celery_error
        
    except Exception as e:
        logger.error(f"[API] 批量同步失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="批量同步失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限,或联系系统管理员",
            status_code=500
        )


@router.post("/data-sync/batch-by-ids")
@role_based_rate_limit(endpoint_type="data_sync")  # [*] v4.19.4: 基于角色的动态限流
async def sync_batch_by_file_ids(
    body: BatchSyncByFileIdsRequest,  # [*] 修复:重命名为 body 避免与 slowapi 的 request 参数冲突
    request: Request,  # [*] 修复:参数名必须为 request(slowapi 要求)
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user)  # [*] Phase 4.2: 用户认证
):
    """
    批量数据同步(基于文件ID列表,使用 Celery 任务)
    
    v4.19.1 恢复:使用 Celery 任务队列执行数据同步
    - 任务持久化:任务存储在 Redis 中,服务器重启后自动恢复
    - 资源隔离:任务在独立的 Celery worker 进程中执行,不影响 API 服务
    - 降级处理:Celery 不可用时,降级到 asyncio.create_task()
    
    Args:
        file_ids: 文件ID列表(1-1000个)
        only_with_template: 是否只处理有模板的文件
        allow_quarantine: 是否允许隔离错误数据
        use_template_header_row: 是否使用模板表头行(严格模式)
    """
    try:
        progress_tracker = SyncProgressTracker(db)
        
        # 生成task_id
        task_id = f"batch_ids_{uuid.uuid4().hex[:8]}"
        
        # 验证文件ID列表
        if not body.file_ids or len(body.file_ids) == 0:
            return error_response(
                code=ErrorCode.VALIDATION_ERROR,
                message="文件ID列表不能为空",
                error_type=get_error_type(ErrorCode.VALIDATION_ERROR),
                detail="file_ids参数必填且不能为空",
                status_code=400
            )
        
        # 限制文件数量
        if len(body.file_ids) > 1000:
            return error_response(
                code=ErrorCode.VALIDATION_ERROR,
                message="文件数量超过限制",
                error_type=get_error_type(ErrorCode.VALIDATION_ERROR),
                detail=f"最多支持1000个文件,当前{len(body.file_ids)}个",
                status_code=400
            )
        
        # 验证文件是否存在
        result = await db.execute(
            select(CatalogFile).where(CatalogFile.id.in_(body.file_ids))
        )
        existing_files = result.scalars().all()
        
        existing_file_ids = [f.id for f in existing_files]
        missing_file_ids = set(body.file_ids) - set(existing_file_ids)
        
        if missing_file_ids:
            logger.warning(f"[API] 部分文件不存在: {missing_file_ids}")
            # 只处理存在的文件
            file_ids = existing_file_ids
        else:
            file_ids = body.file_ids
        
        total_files = len(file_ids)
        
        if total_files == 0:
            return error_response(
                code=ErrorCode.DATA_NOT_FOUND,
                message="没有找到有效的文件",
                error_type=get_error_type(ErrorCode.DATA_NOT_FOUND),
                detail=f"请求的文件ID都不存在: {body.file_ids}",
                status_code=404
            )
        
        # [*] Phase 4.2: 检查用户任务配额
        user_id = current_user.user_id
        quota_service = get_user_task_quota_service()
        can_submit, error_message = await quota_service.can_submit_task(user_id)
        if not can_submit:
            return error_response(
                code=ErrorCode.VALIDATION_ERROR,
                message="任务数量超过限制",
                error_type=get_error_type(ErrorCode.VALIDATION_ERROR),
                detail=error_message,
                recovery_suggestion=f"请等待当前任务完成后再提交新任务(最多允许 {quota_service.max_concurrent_tasks} 个并发任务)",
                status_code=429  # Too Many Requests
            )
        
        # 创建进度任务
        await progress_tracker.create_task(
            task_id=task_id,
            total_files=total_files,
            task_type="batch_ingest"
        )
        
        # v4.19.1: 提交 Celery 任务,添加降级处理
        try:
            from backend.tasks.data_sync_tasks import sync_batch_task
            
            # [*] Phase 4.2: 增加用户任务计数
            await quota_service.increment_user_task_count(user_id)
            
            # 动态并发数(最多20个并发)
            max_concurrent = min(20, max(5, len(file_ids) // 10 + 1))
            
            # [*] Phase 4: 使用 apply_async 支持优先级参数
            celery_task = sync_batch_task.apply_async(
                args=(file_ids, task_id),
                kwargs={
                    'only_with_template': body.only_with_template,
                    'allow_quarantine': body.allow_quarantine,
                    'use_template_header_row': body.use_template_header_row,
                    'max_concurrent': max_concurrent,
                    'user_id': user_id  # [*] Phase 4.2: 添加用户ID(用于审计和配额管理)
                },
                priority=body.priority  # [*] Phase 4: 任务优先级(1-10,10最高)
            )
            
            logger.info(f"[API] 批量同步任务已提交: task_id={task_id}, 文件数={total_files}, celery_task_id={celery_task.id}")
            
            # 立即返回task_id
            return success_response(
                data={
                    "task_id": task_id,
                    "celery_task_id": celery_task.id,
                    "total_files": total_files,
                    "processed_files": 0,
                    "missing_file_ids": list(missing_file_ids) if missing_file_ids else None
                },
                message=f"批量同步任务已提交,正在处理{total_files}个文件"
            )
        except Exception as celery_error:
            # Celery任务提交失败时的降级处理
            error_type = type(celery_error).__name__
            if "OperationalError" in error_type or "ConnectionError" in error_type or "redis" in str(celery_error).lower():
                # Redis连接失败,降级到 asyncio.create_task()
                logger.warning(f"[API] Redis/Celery连接失败({error_type}),降级到 asyncio.create_task()")
                
                # 动态并发数
                max_concurrent = min(20, max(5, len(file_ids) // 10 + 1))
                
                # 降级到 asyncio.create_task()
                asyncio.create_task(
                    process_batch_sync_background(
                        file_ids=file_ids,
                        task_id=task_id,
                        only_with_template=body.only_with_template,
                        allow_quarantine=body.allow_quarantine,
                        use_template_header_row=body.use_template_header_row,
                        max_concurrent=max_concurrent
                    )
                )
                
                logger.info(f"[API] 批量同步任务已提交(降级模式): task_id={task_id}, 文件数={total_files}")
                
                return success_response(
                    data={
                        "task_id": task_id,
                        "total_files": total_files,
                        "processed_files": 0,
                        "fallback": True,
                        "missing_file_ids": list(missing_file_ids) if missing_file_ids else None,
                        "message": "Celery不可用,使用降级模式"
                    },
                    message=f"批量同步任务已提交(降级模式),正在处理{total_files}个文件"
                )
            else:
                # 其他错误,重新抛出
                raise celery_error
        
    except Exception as e:
        logger.error(f"[API] 批量同步失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="批量同步失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限,或联系系统管理员",
            status_code=500
        )


@router.get("/data-sync/progress/{task_id}")
async def get_sync_progress(
    task_id: str,
    db: AsyncSession = Depends(get_async_db)  # [*] v4.18.2:改为异步会话
):
    """
    获取同步进度
    
    查询指定任务的同步进度信息。
    
    v4.18.2: 迁移到异步会话(AsyncSession)
    """
    try:
        # [*] v4.18.2修复:确保使用干净的事务(先回滚任何失败的事务)
        try:
            await db.rollback()
        except:
            pass  # 如果没有活动事务,忽略错误
        
        progress_tracker = SyncProgressTracker(db)
        task_info = await progress_tracker.get_task(task_id)
        
        if not task_info:
            return error_response(
                code=ErrorCode.FILE_NOT_FOUND,
                message=f"任务{task_id}不存在",
                error_type=get_error_type(ErrorCode.FILE_NOT_FOUND),
                recovery_suggestion="请检查任务ID是否正确,或查看任务列表确认任务是否存在",
                status_code=404
            )
        
        return success_response(data=task_info)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] 获取同步进度失败: {e}", exc_info=True)
        # [*] v4.18.2修复:确保异常时回滚事务
        try:
            await db.rollback()
        except:
            pass
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取同步进度失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限,或联系系统管理员",
            status_code=500
        )


@router.get("/data-sync/tasks")
async def list_sync_tasks(
    status: Optional[str] = Query(None, description="状态筛选"),
    limit: int = Query(100, description="返回数量限制", ge=1, le=1000),
    db: AsyncSession = Depends(get_async_db)  # [*] v4.18.2:改为异步会话
):
    """
    列出所有同步任务
    
    查询所有同步任务列表,支持状态筛选。
    
    v4.18.2: 迁移到异步会话(AsyncSession)
    """
    try:
        progress_tracker = SyncProgressTracker(db)
        tasks = await progress_tracker.list_tasks(status=status, limit=limit)
        
        return success_response(
            data=tasks,
            message=f"共找到{len(tasks)}个任务"
        )
        
    except Exception as e:
        logger.error(f"[API] 列出同步任务失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="列出同步任务失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和查询参数,或联系系统管理员",
            status_code=500
        )


@router.get("/data-sync/loss-analysis")
async def analyze_data_loss_endpoint(
    file_id: Optional[int] = Query(None, description="文件ID"),
    task_id: Optional[str] = Query(None, description="任务ID"),
    data_domain: Optional[str] = Query(None, description="数据域"),
    db: AsyncSession = Depends(get_async_db)  # [*] v4.18.2:改为异步会话
):
    """
    分析数据丢失情况
    
    功能:
    - 统计各层数据数量(Raw、Staging、Fact、Quarantine)
    - 计算数据丢失率
    - 分析丢失数据的共同特征
    - 识别丢失位置(Raw->Staging、Staging->Fact)
    
    v4.18.2: 迁移到异步会话(AsyncSession)
    """
    try:
        # [*] v4.18.2:使用异步版本
        result = await async_analyze_data_loss(db, file_id, task_id, data_domain)
        
        if not result.get("success"):
            return error_response(
                code=ErrorCode.DATABASE_QUERY_ERROR,
                message="分析数据丢失失败",
                error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
                detail=result.get("error"),
                recovery_suggestion="请检查查询参数和数据库连接,或联系系统管理员",
                status_code=500
            )
        
        return success_response(
            data=result,
            message="数据丢失分析完成"
        )
    
    except Exception as e:
        logger.error(f"[API] 分析数据丢失失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="分析数据丢失失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查查询参数和数据库连接,或联系系统管理员",
            status_code=500
        )


@router.get("/data-sync/loss-alert")
async def check_data_loss_alert(
    file_id: Optional[int] = Query(None, description="文件ID"),
    task_id: Optional[str] = Query(None, description="任务ID"),
    data_domain: Optional[str] = Query(None, description="数据域"),
    threshold: float = Query(5.0, description="丢失率阈值(%)", ge=0, le=100),
    db: AsyncSession = Depends(get_async_db)  # [*] v4.18.2:改为异步会话
):
    """
    检查数据丢失预警
    
    功能:
    - 检查数据丢失率是否超过阈值
    - 如果超过阈值,返回预警信息
    - 提供丢失数据统计和特征分析
    
    v4.18.2: 迁移到异步会话(AsyncSession)
    """
    try:
        # [*] v4.18.2:使用异步版本
        result = await async_check_data_loss_threshold(db, file_id, task_id, data_domain, threshold)
        
        if not result.get("success"):
            return error_response(
                code=ErrorCode.DATABASE_QUERY_ERROR,
                message="检查数据丢失预警失败",
                error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
                detail=result.get("error"),
                recovery_suggestion="请检查查询参数和数据库连接,或联系系统管理员",
                status_code=500
            )
        
        return success_response(
            data=result,
            message=result.get("message", "检查完成")
        )
    
    except Exception as e:
        logger.error(f"[API] 检查数据丢失预警失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="检查数据丢失预警失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查查询参数和数据库连接,或联系系统管理员",
            status_code=500
        )


@router.get("/data-sync/platforms")
async def get_available_platforms(
    db: AsyncSession = Depends(get_async_db)  # [*] v4.18.2:改为异步会话
):
    """
    获取可用的平台列表 [*] **新增(2025-02-01)**
    
    功能:
    - 从catalog_files表中获取所有有文件的平台
    - 用于动态加载平台选项
    
    v4.18.2: 迁移到异步会话(AsyncSession)
    """
    try:
        # 查询所有有文件的平台([*] v4.18.2:使用 await)
        result = await db.execute(
            select(distinct(CatalogFile.platform_code))
            .where(CatalogFile.platform_code.isnot(None))
            .order_by(CatalogFile.platform_code)
        )
        platforms = result.scalars().all()
        
        return success_response(
            data={"platforms": [p for p in platforms if p]},
            message="获取平台列表成功"
        )
        
    except Exception as e:
        logger.error(f"[DataSync Platforms] 获取平台列表失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取平台列表失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接,或联系系统管理员",
            status_code=500
        )


@router.get("/data-sync/governance/detailed-coverage")
async def get_detailed_template_coverage(
    db: AsyncSession = Depends(get_async_db)  # [*] v4.18.2:改为异步会话
):
    """
    获取详细的模板覆盖统计 [*] **新增(2025-02-01)**
    
    功能:
    - 按平台、数据域、子类型、粒度统计模板覆盖情况
    - 检测需要更新的模板(表头字段变化)
    - 返回详细的覆盖和缺失清单
    
    v4.18.2: 迁移到异步会话(AsyncSession)
    """
    try:
        from backend.services.template_family_service import get_template_resolver
        from backend.services.template_matcher import get_template_matcher
        
        template_matcher = get_template_matcher(db)
        template_resolver = get_template_resolver(db)
        
        # [*] v4.15.0修复:基于所有模板统计,而不是只基于待同步文件
        # 1. 查询所有模板(published状态)([*] v4.18.2:使用 await)
        from modules.core.db import FieldMappingTemplate
        templates_stmt = select(FieldMappingTemplate).where(
            FieldMappingTemplate.status == 'published'
        )
        templates_result = await db.execute(templates_stmt)
        all_templates = templates_result.scalars().all()
        
        # 2. 从模板构建唯一组合(平台+数据域+子类型+粒度)
        template_combinations = {}
        for template in all_templates:
            key = (
                template.platform,
                template.data_domain,
                template.sub_domain or None,
                template.granularity
            )
            if key not in template_combinations:
                template_combinations[key] = {
                    'platform': template.platform,
                    'domain': template.data_domain,
                    'sub_domain': template.sub_domain,
                    'granularity': template.granularity,
                    'template': template
                }
        
        # 3. 查询所有文件的唯一组合(包括pending/failed/ingested,用于统计文件数)
        files_stmt = select(
            CatalogFile.platform_code,
            CatalogFile.data_domain,
            CatalogFile.sub_domain,
            CatalogFile.granularity
        ).where(
            CatalogFile.platform_code.isnot(None),
            CatalogFile.data_domain.isnot(None),
            CatalogFile.granularity.isnot(None),
            CatalogFile.status.in_(['pending', 'failed', 'ingested'])  # [*] 包括失败待修复的文件
        ).distinct()
        
        # [*] v4.18.2:使用 await
        file_combinations_result = await db.execute(files_stmt)
        all_file_combinations_raw = file_combinations_result.all()
        
        # 4. 合并模板组合和文件组合(确保统计完整)
        all_combinations_dict = {}
        
        # 先添加模板组合
        for key, combo in template_combinations.items():
            all_combinations_dict[key] = (
                combo['platform'],
                combo['domain'],
                combo['sub_domain'],
                combo['granularity']
            )
        
        # 再添加文件组合(如果不在模板组合中)
        for platform, domain, sub_domain, granularity in all_file_combinations_raw:
            key = (platform, domain, sub_domain or None, granularity)
            if key not in all_combinations_dict:
                all_combinations_dict[key] = (platform, domain, sub_domain, granularity)
        
        all_combinations = list(all_combinations_dict.values())
        
        # 2. 统计覆盖情况
        covered_list = []
        missing_list = []
        needs_update_list = []
        archived_compatibility_list = []
        template_status_service = DataSyncTemplateStatusService(db)
        detailed_coverage_missing_files: list[str] = []
        detailed_coverage_error_types: dict[str, int] = {}
        
        for platform, domain, sub_domain, granularity in all_combinations:
            if not platform or not domain or not granularity:
                continue
            from modules.core.path_manager import to_absolute_path

            current_combo_file_result = await db.execute(
                select(CatalogFile).where(
                    CatalogFile.platform_code == platform,
                    CatalogFile.data_domain == domain,
                    CatalogFile.granularity == granularity,
                    CatalogFile.sub_domain == sub_domain,
                    CatalogFile.status.in_(['pending', 'failed'])
                ).order_by(
                    case(
                        (CatalogFile.status == 'pending', 0),
                        (CatalogFile.status == 'failed', 1),
                        else_=2,
                    ),
                    CatalogFile.first_seen_at.desc()
                ).limit(20)
            )
            current_combo_files = current_combo_file_result.scalars().all()
            valid_current_combo_files = [
                candidate
                for candidate in current_combo_files
                if is_catalog_file_semantically_valid(candidate)
                and to_absolute_path(candidate.file_path).exists()
            ]
            valid_pending_combo_files = [
                candidate for candidate in valid_current_combo_files if candidate.status == 'pending'
            ]

            combo_file_candidates_result = await db.execute(
                select(CatalogFile).where(
                    CatalogFile.platform_code == platform,
                    CatalogFile.data_domain == domain,
                    CatalogFile.granularity == granularity,
                    CatalogFile.sub_domain == sub_domain,
                    CatalogFile.status.in_(['pending', 'failed', 'ingested'])
                ).order_by(
                    case(
                        (CatalogFile.status == 'pending', 0),
                        (CatalogFile.status == 'failed', 1),
                        else_=2,
                    ),
                    CatalogFile.first_seen_at.desc()
                ).limit(20)
            )
            combo_file_candidates = combo_file_candidates_result.scalars().all()
            valid_combo_file_candidates = [
                candidate
                for candidate in combo_file_candidates
                if is_catalog_file_semantically_valid(candidate)
                and to_absolute_path(candidate.file_path).exists()
            ]
            if combo_file_candidates and not valid_combo_file_candidates:
                continue
            
            # 查找模板([*] v4.18.2:添加 await)
            try:
                resolve_result = await template_resolver.resolve(
                    platform=platform,
                    data_domain=domain,
                    granularity=granularity,
                    sub_domain=sub_domain,
                    header_columns=[],
                    sample_rows=[],
                )
            except Exception:
                resolve_result = {
                    "governance_status": "missing_family",
                    "shadow_compare": None,
                }
            template = await template_matcher.find_best_template(
                platform=platform,
                data_domain=domain,
                granularity=granularity,
                sub_domain=sub_domain
            )
            
            # [*] 统计该组合的文件数(包括pending/failed/ingested)
            # [*] v4.18.2:使用 await
            file_count_stmt = select(func.count(CatalogFile.id)).where(
                CatalogFile.platform_code == platform,
                CatalogFile.data_domain == domain,
                CatalogFile.granularity == granularity,
                CatalogFile.sub_domain == sub_domain,
                CatalogFile.status.in_(['pending', 'failed', 'ingested'])  # [*] 包括失败待修复的文件
            )
            file_count_result = await db.execute(file_count_stmt)
            file_count = file_count_result.scalar() or 0
            current_file_count = len(valid_current_combo_files)
            pending_file_count = len(valid_pending_combo_files)
            
            combo_info = {
                'family_id': ((resolve_result.get('family') or {}).get('id') if resolve_result else None),
                'platform': platform,
                'domain': domain,
                'sub_domain': sub_domain or 'N/A',
                'granularity': granularity,
                'file_count': file_count,
                'historical_file_count': file_count,
                'current_file_count': current_file_count,
                'pending_file_count': pending_file_count,
                'governance_status': resolve_result.get('governance_status', 'missing_family')
            }
            
            if template:
                # 检查模板是否需要更新(通过检测最近文件的表头变化)
                needs_update = False
                update_reason = None
                template_status = "ready"
                semantic_match = True
                
                # [*] 获取该组合的一个示例文件(优先pending,其次failed,最后ingested)
                # [*] v4.18.2:使用 await
                sample_file_candidates = [
                    *valid_current_combo_files,
                    *[
                        candidate
                        for candidate in valid_combo_file_candidates
                        if candidate not in valid_current_combo_files
                    ],
                    *[
                        candidate
                        for candidate in combo_file_candidates
                        if candidate not in valid_combo_file_candidates
                    ],
                ]
                sample_file = next(
                    (
                        candidate
                        for candidate in sample_file_candidates
                        if not _is_governance_excluded_sample_file(candidate)
                    ),
                    None,
                )
                if sample_file:
                    from modules.core.path_manager import to_absolute_path

                    sample_path = to_absolute_path(sample_file.file_path)
                    if not sample_path.exists():
                        detailed_coverage_missing_files.append(str(getattr(sample_file, "file_path", "")))
                        sample_file = None
                sample_file_info = {
                    'sample_file_id': sample_file.id if sample_file else None,
                    'sample_file_name': sample_file.file_name if sample_file else None,
                }
                shadow_compare = resolve_result.get('shadow_compare')
                
                if sample_file:
                    try:
                        from backend.services.excel_parser import ExcelParser
                        
                        # [*] v4.18.2修复:使用 run_in_executor 包装文件读取,避免阻塞事件循环
                        loop = asyncio.get_running_loop()
                        runtime_sample_path = str(sample_file.file_path)
                        runtime_source_format = ExcelParser.detect_file_format(PathLib(runtime_sample_path))
                        if runtime_source_format in {"xls", "xlsx_with_ole", "html"}:
                            normalized = get_spreadsheet_normalization_service().normalize_for_runtime(
                                runtime_sample_path,
                                source_format=runtime_source_format,
                            )
                            runtime_sample_path = str(normalized.path)
                        df = await loop.run_in_executor(
                            None,
                            ExcelParser.read_excel,
                            runtime_sample_path,
                            template.header_row or 0,
                            5  # nrows=5
                        )
                        current_columns = df.columns.tolist()

                        status_info = await template_status_service.evaluate_catalog_file(
                            sample_file,
                            template=template,
                            current_columns=current_columns,
                            sample_rows=df.head(3).fillna("").to_dict("records"),
                        )
                        template_status = status_info.get("template_status", "ready")
                        combo_info["governance_status"] = status_info.get(
                            "governance_status",
                            {
                                "ready": "ready",
                                "alias_only": "non_breaking_drift",
                                "update_required": "breaking_drift",
                                "missing_variant": "missing_variant",
                                "missing": "missing_family",
                            }.get(template_status, combo_info["governance_status"]),
                        )
                        semantic_match = status_info.get("semantic_match", False)
                        shadow_compare = status_info.get("shadow_compare") or shadow_compare

                        if template_status == "update_required":
                            needs_update = True
                            header_changes = status_info.get("header_changes", {})
                            added = header_changes.get('added_fields', [])
                            removed = header_changes.get('removed_fields', [])
                            if added or removed:
                                update_reason = f"新增{len(added)}个字段,删除{len(removed)}个字段"
                            else:
                                update_reason = f"匹配率{header_changes.get('match_rate', 0):.1f}%"
                    except Exception as e:
                        if isinstance(e, FileNotFoundError):
                            detailed_coverage_missing_files.append(str(getattr(sample_file, "file_path", "")))
                        else:
                            error_type = type(e).__name__
                            detailed_coverage_error_types[error_type] = (
                                detailed_coverage_error_types.get(error_type, 0) + 1
                            )
                
                covered_row = {
                    **combo_info,
                    **sample_file_info,
                    'template_id': template.id,
                    'template_name': template.template_name,
                    'template_version': template.version,
                    'template_status': template_status,
                    'needs_update': needs_update,
                    'update_reason': update_reason,
                    'semantic_match': semantic_match,
                    'shadow_compare': shadow_compare,
                }

                if combo_info['current_file_count'] == 0:
                    archived_compatibility_list.append(covered_row)
                    continue

                covered_list.append(covered_row)
                
                if needs_update:
                    needs_update_list.append({
                        **combo_info,
                        **sample_file_info,
                        'template_id': template.id,
                        'template_name': template.template_name,
                        'update_reason': update_reason,
                        'shadow_compare': shadow_compare,
                    })
            else:
                if combo_info['current_file_count'] == 0:
                    archived_compatibility_list.append({
                        **combo_info,
                        'shadow_compare': resolve_result.get('shadow_compare'),
                    })
                    continue
                missing_list.append({
                    **combo_info,
                    'shadow_compare': resolve_result.get('shadow_compare'),
                })
        
        # 3. 计算统计
        # [*] v4.15.0修复:覆盖率应该基于所有模板,而不是基于文件组合
        # total_combinations = 所有模板数 + 缺少模板的文件组合数
        total_combinations = len(template_combinations) + len(missing_list)
        archived_compatibility_list = locals().get('archived_compatibility_list', [])
        current_covered_list = [
            item for item in covered_list
            if item.get("governance_status") in {"ready", "non_breaking_drift"}
        ]
        current_missing_list = [
            item for item in missing_list
            if item.get("governance_status") == "missing_family"
        ]
        missing_variant_rows = [
            {
                **item,
                "update_reason": item.get("update_reason") or "缺少当前有效变体",
            }
            for item in covered_list
            if item.get("governance_status") == "missing_variant"
            and (item.get("current_file_count") or 0) > 0
            and item.get("sample_file_id")
        ]
        breaking_drift_rows = [
            item for item in needs_update_list
            if item.get("governance_status") == "breaking_drift"
        ]
        current_needs_update_list = [*breaking_drift_rows, *missing_variant_rows]
        archived_compatibility_list = [
            *archived_compatibility_list,
            *[
                item for item in covered_list
                if item.get("governance_status") not in {"ready", "non_breaking_drift", "missing_variant", "breaking_drift"}
            ],
        ]

        covered_count = len(current_covered_list)
        missing_count = len(current_missing_list)
        needs_update_count = len(breaking_drift_rows)
        missing_variant_count = len(missing_variant_rows)
        breaking_drift_count = sum(
            1 for item in current_needs_update_list if item.get("governance_status") == "breaking_drift"
        )
        non_breaking_drift_count = sum(
            1 for item in current_covered_list if item.get("governance_status") == "non_breaking_drift"
        )
        
        # [*] v4.15.0修复:覆盖率 = 有模板的组合数 / 总组合数
        # 总组合数 = 所有模板数(已覆盖)+ 缺少模板的文件组合数(未覆盖)
        coverage_percentage = (covered_count / total_combinations * 100) if total_combinations > 0 else 0
        
        if detailed_coverage_missing_files:
            preview = ", ".join(detailed_coverage_missing_files[:3])
            suffix = "" if len(detailed_coverage_missing_files) <= 3 else f" ... (+{len(detailed_coverage_missing_files) - 3})"
            logger.info(
                f"[DetailedCoverage] 跳过 {len(detailed_coverage_missing_files)} 个示例文件缺失: {preview}{suffix}"
            )
        if detailed_coverage_error_types:
            summary = ", ".join(
                f"{name}={count}" for name, count in sorted(detailed_coverage_error_types.items())
            )
            logger.warning(f"[DetailedCoverage] 示例文件检测出现异常(已聚合): {summary}")

        return success_response(
            data={
                'summary': {
                    'total_combinations': total_combinations,
                    'covered_count': covered_count,
                    'missing_count': missing_count,
                    'needs_update_count': needs_update_count,
                    'missing_variant_count': missing_variant_count,
                    'breaking_drift_count': breaking_drift_count,
                    'non_breaking_drift_count': non_breaking_drift_count,
                    'coverage_percentage': round(coverage_percentage, 1)
                },
                'current_covered': current_covered_list,
                'current_missing': current_missing_list,
                'current_needs_update': current_needs_update_list,
                'archived_compatibility': archived_compatibility_list,
                'covered': covered_list,
                'missing': missing_list,
                'needs_update': needs_update_list
            },
            message="获取详细模板覆盖统计成功"
        )
        
    except Exception as e:
        logger.error(f"[DataSync DetailedCoverage] 获取详细统计失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取详细模板覆盖统计失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接,或联系系统管理员",
            status_code=500
        )


@router.get("/data-sync/governance/stats")
async def get_governance_stats(
    db: AsyncSession = Depends(get_async_db)  # [*] v4.18.2:改为异步会话
):
    """
    数据治理统计API [*] **新增(2025-02-01)**
    
    功能:
    - 统计待同步文件数量
    - 统计已同步文件数量
    - 用于数据治理概览显示
    
    v4.18.1修复:所有统计都从数据库查询,保持数据一致性
    - pending_count: 查询 status='pending' 的文件数
    - ingested_count: 查询 status='ingested' 的文件数
    - 解决问题:同步后待同步数量不减少的问题
    
    v4.18.2: 迁移到异步会话(AsyncSession)
    """
    try:
        # [*] v4.18.1修复:统一从数据库查询,保持数据一致性
        # 之前的问题:pending_count通过文件系统扫描,ingested_count通过数据库查询
        # 导致同步后,pending_count不减少(因为文件仍在文件系统中)
        
        # [*] v4.18.2:使用 await 进行异步查询
        # 统计待同步文件(status='pending')
        pending_files_result = await db.execute(
            select(CatalogFile).where(CatalogFile.status == 'pending')
        )
        pending_files = [
            file_record
            for file_record in pending_files_result.scalars().all()
            if is_catalog_file_semantically_valid(file_record)
        ]
        pending_count = len(pending_files)
        ready_to_sync_count = 0
        template_update_required_count = 0
        missing_template_count = 0
        semantic_anomaly_count = 0
        data_sync_service = DataSyncService(db)

        all_pending_files_result = await db.execute(
            select(CatalogFile).where(CatalogFile.status == 'pending')
        )
        all_pending_files = all_pending_files_result.scalars().all()
        semantic_anomaly_count = sum(
            1 for file_record in all_pending_files if not is_catalog_file_semantically_valid(file_record)
        )

        for file_record in pending_files:
            readiness = await data_sync_service.get_file_sync_readiness(
                file_record.id,
                use_template_header_row=True,
            )
            template_status = readiness.get("template_status")
            if readiness.get("should_auto_sync"):
                ready_to_sync_count += 1
            elif template_status == "update_required":
                template_update_required_count += 1
            elif template_status == "missing":
                missing_template_count += 1
        
        # 统计已同步文件(status='ingested')
        ingested_result = await db.execute(
            select(func.count(CatalogFile.id)).where(CatalogFile.status == 'ingested')
        )
        ingested_count = ingested_result.scalar() or 0
        
        # [*] v4.17.2修复:单独统计失败文件(status='failed'),用于显示失败文件数
        failed_result = await db.execute(
            select(func.count(CatalogFile.id)).where(CatalogFile.status == 'failed')
        )
        failed_count = failed_result.scalar() or 0

        source_missing_result = await db.execute(
            select(func.count(CatalogFile.id)).where(CatalogFile.status == 'source_missing')
        )
        source_missing_count = source_missing_result.scalar() or 0
        
        # [*] v4.17.2新增:统计各状态的详细数量(用于调试和显示)
        status_counts = {}
        for status_name in ['pending', 'partial_success', 'failed', 'quarantined', 'needs_shop', 'ingested', 'processing', 'source_missing']:
            count_result = await db.execute(
                select(func.count(CatalogFile.id)).where(CatalogFile.status == status_name)
            )
            count = count_result.scalar() or 0
            if count > 0:
                status_counts[status_name] = count
        
        # 计算总文件数(所有已注册的文件)
        total_result = await db.execute(select(func.count(CatalogFile.id)))
        total_count = total_result.scalar() or 0
        raw_hint = await _build_raw_unregistered_hint(db)
        official_unregistered_count = (
            (raw_hint or {}).get("official_unregistered_count", 0)
        )
        legacy_file_count = (
            (raw_hint or {}).get("legacy_without_meta_count", 0)
            + (raw_hint or {}).get("repaired_cache_count", 0)
        )
        
        return success_response(
            data={
                "pending_count": pending_count,  # [*] v4.18.1修复:从数据库查询status='pending'
                "ingested_count": ingested_count,
                "registered_count": total_count,
                "recent_collected_count": total_count,
                "official_unregistered_count": official_unregistered_count,
                "legacy_file_count": legacy_file_count,
                "failed_count": failed_count,  # 仅failed状态的文件数
                "source_missing_count": source_missing_count,
                "total_count": total_count,  # [*] v4.18.1修复:总文件数从数据库查询
                "status_counts": status_counts,  # [*] 各状态的详细数量
                "ready_to_sync_count": ready_to_sync_count,
                "template_update_required_count": template_update_required_count,
                "missing_template_count": missing_template_count,
                "semantic_anomaly_count": semantic_anomaly_count,
            },
            message="数据治理统计查询成功"
        )
        
    except Exception as e:
        logger.error(f"[DataSync Governance] 查询统计失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="查询数据治理统计失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接,或联系系统管理员",
            status_code=500
        )


@router.post("/data-sync/cleanup-semantic-anomalies")
async def cleanup_semantic_anomalies(
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin),
):
    try:
        result = await db.execute(
            select(CatalogFile).where(CatalogFile.status == 'pending')
        )
        pending_files = result.scalars().all()
        semantic_anomalies = [
            file_record
            for file_record in pending_files
            if not is_catalog_file_semantically_valid(file_record)
        ]

        deleted_file_count = 0
        deleted_meta_count = 0
        deleted_catalog_count = 0
        failures: list[dict[str, Any]] = []

        for file_record in semantic_anomalies:
            file_path = getattr(file_record, "file_path", None)
            meta_file_path = getattr(file_record, "meta_file_path", None)

            try:
                if file_path:
                    absolute_file_path = to_absolute_path(str(file_path))
                    if absolute_file_path.exists():
                        absolute_file_path.unlink()
                        deleted_file_count += 1
            except Exception as exc:
                failures.append({
                    "file_id": file_record.id,
                    "file_name": file_record.file_name,
                    "stage": "file",
                    "reason": _semantic_anomaly_reason(file_record),
                    "error": str(exc),
                })

            try:
                if meta_file_path:
                    absolute_meta_path = to_absolute_path(str(meta_file_path))
                    if absolute_meta_path.exists():
                        absolute_meta_path.unlink()
                        deleted_meta_count += 1
            except Exception as exc:
                failures.append({
                    "file_id": file_record.id,
                    "file_name": file_record.file_name,
                    "stage": "meta",
                    "reason": _semantic_anomaly_reason(file_record),
                    "error": str(exc),
                })

            await db.delete(file_record)
            deleted_catalog_count += 1

        await db.commit()

        return success_response(
            data={
                "matched_count": len(semantic_anomalies),
                "deleted_catalog_count": deleted_catalog_count,
                "deleted_file_count": deleted_file_count,
                "deleted_meta_count": deleted_meta_count,
                "failures": failures,
            },
            message=f"语义异常待同步文件清理完成，共匹配 {len(semantic_anomalies)} 个文件",
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"[DataSync SemanticCleanup] 清理语义异常待同步文件失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="清理语义异常待同步文件失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和文件权限，或联系系统管理员",
            status_code=500
        )

@router.post("/data-sync/repair-inventory-snapshot-semantics")
async def repair_inventory_snapshot_semantics(
    file_ids: list[int] | None = Body(default=None),
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin),
):
    from scripts.repair_inventory_snapshot_granularity import repair_inventory_record

    try:
        query = select(CatalogFile).where(
            CatalogFile.status == "pending",
            CatalogFile.data_domain == "inventory",
            CatalogFile.granularity != "snapshot",
        )
        if file_ids:
            query = query.where(CatalogFile.id.in_(file_ids))

        result = await db.execute(query)
        pending_records = result.scalars().all()

        repaired_rows: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []

        for file_record in pending_records:
            if _semantic_anomaly_reason(file_record) != "inventory_granularity_invalid":
                continue

            original_file_name = file_record.file_name
            original_granularity = file_record.granularity
            try:
                fixed = repair_inventory_record(
                    {
                        "id": file_record.id,
                        "file_name": file_record.file_name,
                        "file_path": file_record.file_path,
                        "data_domain": file_record.data_domain,
                        "granularity": file_record.granularity,
                    },
                    apply_changes=True,
                )
                file_record.file_name = fixed["file_name"]
                file_record.file_path = fixed["file_path"]
                file_record.granularity = fixed["granularity"]
                if isinstance(file_record.file_metadata, dict):
                    file_record.file_metadata = {
                        **file_record.file_metadata,
                        "semantic_repair": {
                            "reason": "inventory_granularity_invalid",
                            "repaired_at": datetime.now(timezone.utc).isoformat(),
                            "old_granularity": original_granularity,
                            "new_granularity": "snapshot",
                        },
                    }
                repaired_rows.append(
                    {
                        "file_id": file_record.id,
                        "old_file_name": original_file_name,
                        "new_file_name": fixed["file_name"],
                        "old_granularity": original_granularity,
                        "new_granularity": fixed["granularity"],
                    }
                )
            except Exception as exc:
                failures.append(
                    {
                        "file_id": file_record.id,
                        "file_name": file_record.file_name,
                        "error": str(exc),
                    }
                )

        await db.commit()

        return success_response(
            data={
                "matched_count": len(pending_records),
                "repaired_count": len(repaired_rows),
                "repaired_rows": repaired_rows,
                "failures": failures,
            },
            message=f"库存 snapshot 语义修复完成，修复 {len(repaired_rows)} 条记录",
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"[DataSync SemanticRepair] 修复库存 snapshot 语义失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="修复库存 snapshot 语义失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接、文件权限或伴生 meta 文件",
            status_code=500,
        )


@router.post("/data-sync/repair-miaoshou-orders-platform-semantics")
async def repair_miaoshou_orders_platform_semantics(
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin),
):
    try:
        result = await db.execute(
            select(CatalogFile).where(
                CatalogFile.status == "pending",
                CatalogFile.data_domain == "orders",
                CatalogFile.platform_code == "miaoshou",
            )
        )
        pending_records = result.scalars().all()

        repaired_count = 0
        repaired_rows: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []

        for file_record in pending_records:
            target_platform = _resolve_miaoshou_orders_business_platform(file_record)
            if target_platform not in {"tiktok", "shopee"}:
                continue

            old_hash = file_record.file_hash
            try:
                file_path = to_absolute_path(str(file_record.file_path))
                if file_path.exists():
                    file_record.file_hash = _compute_sha256(
                        file_path,
                        shop_id=getattr(file_record, "shop_id", None),
                        platform_code=target_platform,
                    )
                file_record.platform_code = target_platform
                file_record.source_platform = "miaoshou"
                file_record.sub_domain = None
                if isinstance(file_record.file_metadata, dict):
                    file_record.file_metadata = {
                        **file_record.file_metadata,
                        "semantic_repair": {
                            "reason": "miaoshou_orders_business_platform_collapsed",
                            "repaired_at": datetime.now(timezone.utc).isoformat(),
                            "old_platform_code": "miaoshou",
                            "new_platform_code": target_platform,
                        },
                    }
                repaired_count += 1
                repaired_rows.append(
                    {
                        "file_id": file_record.id,
                        "file_name": file_record.file_name,
                        "old_platform_code": "miaoshou",
                        "new_platform_code": target_platform,
                        "file_hash_changed": old_hash != file_record.file_hash,
                    }
                )
            except Exception as exc:
                failures.append(
                    {
                        "file_id": file_record.id,
                        "file_name": file_record.file_name,
                        "error": str(exc),
                    }
                )

        await db.commit()

        return success_response(
            data={
                "matched_count": len(pending_records),
                "repaired_count": repaired_count,
                "repaired_rows": repaired_rows,
                "failures": failures,
            },
            message=f"妙手订单平台语义修复完成，修复 {repaired_count} 条记录",
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"[DataSync SemanticRepair] 修复妙手订单平台语义失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="修复妙手订单平台语义失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接或联系系统管理员",
            status_code=500,
        )


@router.post("/data-sync/repair-miaoshou-orders-platform-semantics")
async def repair_miaoshou_orders_platform_semantics(
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin),
):
    try:
        result = await db.execute(
            select(CatalogFile).where(
                CatalogFile.status == "pending",
                CatalogFile.data_domain == "orders",
                CatalogFile.platform_code == "miaoshou",
            )
        )
        pending_records = result.scalars().all()

        repaired_count = 0
        repaired_rows: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []

        for file_record in pending_records:
            target_platform = _resolve_miaoshou_orders_business_platform(file_record)
            if target_platform not in {"tiktok", "shopee"}:
                continue
            old_hash = file_record.file_hash
            try:
                file_path = to_absolute_path(str(file_record.file_path))
                if file_path.exists():
                    file_record.file_hash = _compute_sha256(
                        file_path,
                        shop_id=getattr(file_record, "shop_id", None),
                        platform_code=target_platform,
                    )
                file_record.platform_code = target_platform
                file_record.source_platform = "miaoshou"
                file_record.sub_domain = None
                if isinstance(file_record.file_metadata, dict):
                    file_record.file_metadata = {
                        **file_record.file_metadata,
                        "semantic_repair": {
                            "reason": "miaoshou_orders_business_platform_collapsed",
                            "repaired_at": datetime.now(timezone.utc).isoformat(),
                            "old_platform_code": "miaoshou",
                            "new_platform_code": target_platform,
                        },
                    }
                repaired_count += 1
                repaired_rows.append(
                    {
                        "file_id": file_record.id,
                        "file_name": file_record.file_name,
                        "old_platform_code": "miaoshou",
                        "new_platform_code": target_platform,
                        "file_hash_changed": old_hash != file_record.file_hash,
                    }
                )
            except Exception as exc:
                failures.append(
                    {
                        "file_id": file_record.id,
                        "file_name": file_record.file_name,
                        "error": str(exc),
                    }
                )

        await db.commit()
        return success_response(
            data={
                "matched_count": len(pending_records),
                "repaired_count": repaired_count,
                "repaired_rows": repaired_rows,
                "failures": failures,
            },
            message=f"妙手订单平台语义修复完成，修复 {repaired_count} 条记录",
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"[DataSync SemanticRepair] 修复妙手订单平台语义失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="修复妙手订单平台语义失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接或联系系统管理员",
            status_code=500,
        )


@router.post("/data-sync/batch-all")
@role_based_rate_limit(endpoint_type="data_sync")  # [*] v4.19.4: 基于角色的动态限流
async def sync_all_with_template(
    request: Request,  # [*] 修复:参数名必须为 request(slowapi 要求)
    db: AsyncSession = Depends(get_async_db),  # [*] v4.18.2:改为异步会话
    current_user = Depends(get_current_user)  # [*] Phase 4.2: 用户认证
):
    """
    手动全部数据同步API [*] **新增(2025-02-01)**
    
    功能:
    - 同步所有有模板的待同步文件
    - 后台任务执行,返回任务ID
    - 用于文件列表页面的"手动全部数据同步"按钮
    
    v4.18.2: 迁移到异步会话(AsyncSession)
    v4.18.2修复:使用 asyncio.create_task() 替代 BackgroundTasks,避免阻塞事件循环
    """
    try:
        # 1. 查询所有待同步文件([*] v4.18.2:使用 await)
        result = await db.execute(
            select(CatalogFile).where(CatalogFile.status == 'pending')
        )
        pending_files = result.scalars().all()
        
        # 2. 筛选真正可同步的文件(有模板且模板无需更新)
        data_sync_service = DataSyncService(db)
        files_with_template = []
        
        for file_record in pending_files:
            readiness = await data_sync_service.get_file_sync_readiness(
                file_record.id,
                use_template_header_row=True,
            )
            if readiness.get("should_auto_sync"):
                files_with_template.append(file_record.id)
        
        if not files_with_template:
            return success_response(
                data={"task_id": None, "file_count": 0},
                message="没有找到有模板的待同步文件"
            )
        
        # 3. 创建批量同步任务
        task_id = f"batch_all_{uuid.uuid4().hex[:8]}"
        progress_tracker = SyncProgressTracker(db)
        
        # [*] Phase 4.2: 检查用户任务配额
        user_id = current_user.user_id
        quota_service = get_user_task_quota_service()
        can_submit, error_message = await quota_service.can_submit_task(user_id)
        if not can_submit:
            return error_response(
                code=ErrorCode.VALIDATION_ERROR,
                message="任务数量超过限制",
                error_type=get_error_type(ErrorCode.VALIDATION_ERROR),
                detail=error_message,
                recovery_suggestion=f"请等待当前任务完成后再提交新任务(最多允许 {quota_service.max_concurrent_tasks} 个并发任务)",
                status_code=429  # Too Many Requests
            )
        
        # 初始化任务(使用正确的参数)(v4.18.2改为异步)
        await progress_tracker.create_task(
            task_id=task_id,
            total_files=len(files_with_template),
            task_type="batch_sync_all"
        )
        
        # [*] v4.19.0修复:使用 Celery 任务替代 asyncio.create_task()
        max_concurrent = min(20, max(5, len(files_with_template) // 10 + 1))
        
        try:
            # [*] v4.19.8修复:添加缺失的导入语句
            from backend.tasks.data_sync_tasks import sync_batch_task
            
            # [*] Phase 4.2: 增加用户任务计数
            await quota_service.increment_user_task_count(user_id)
            
            # [*] Phase 4: 使用 apply_async 支持优先级参数(batch-all 使用默认优先级 5)
            celery_task = sync_batch_task.apply_async(
                args=(files_with_template, task_id),
                kwargs={
                    'only_with_template': True,
                    'allow_quarantine': True,
                    'use_template_header_row': True,
                    'max_concurrent': max_concurrent,
                    'user_id': user_id  # [*] Phase 4.2: 添加用户ID(用于审计和配额管理)
                },
                priority=5  # [*] Phase 4: batch-all 使用默认优先级
            )
            
            return success_response(
                data={
                    "task_id": task_id,
                    "celery_task_id": celery_task.id,
                    "file_count": len(files_with_template),
                    "message": f"已启动批量同步任务,共{len(files_with_template)}个文件"
                },
                message=f"批量同步任务已启动({len(files_with_template)}个文件)"
            )
        except Exception as e:
            # [*] 修复:Celery任务提交失败时的降级处理
            error_type = type(e).__name__
            if "OperationalError" in error_type or "ConnectionError" in error_type:
                # Redis连接失败,降级到 asyncio.create_task()
                logger.warning(f"[API] Redis/Celery连接失败({error_type}),降级到 asyncio.create_task()")
                
                # [*] Phase 4.2: 增加用户任务计数(降级模式也需要配额管理)
                await quota_service.increment_user_task_count(user_id)
                
                asyncio.create_task(
                    process_batch_sync_background(
                        file_ids=files_with_template,
                        task_id=task_id,
                        only_with_template=True,
                        allow_quarantine=True,
                        use_template_header_row=True,
                        max_concurrent=max_concurrent,
                        user_id=user_id  # [*] Phase 4.2: 传递用户ID
                    )
                )
                
                return success_response(
                    data={
                        "task_id": task_id,
                        "file_count": len(files_with_template),
                        "fallback": True,
                        "message": f"已启动批量同步任务(降级模式),共{len(files_with_template)}个文件"
                    },
                    message=f"批量同步任务已启动(降级模式,{len(files_with_template)}个文件)"
                )
            else:
                # 其他错误,重新抛出
                raise
        
    except Exception as e:
        logger.error(f"[DataSync BatchAll] 启动批量同步失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="启动批量同步失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            recovery_suggestion="请检查系统状态,或联系系统管理员",
            status_code=500
        )


@router.post("/data-sync/repair-miaoshou-orders-platform-semantics")
async def repair_miaoshou_orders_platform_semantics(
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin),
):
    try:
        result = await db.execute(
            select(CatalogFile).where(
                CatalogFile.status == "pending",
                CatalogFile.data_domain == "orders",
                CatalogFile.platform_code == "miaoshou",
            )
        )
        pending_records = result.scalars().all()

        repaired_count = 0
        repaired_rows: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []

        for file_record in pending_records:
            target_platform = _resolve_miaoshou_orders_business_platform(file_record)
            if target_platform not in {"tiktok", "shopee"}:
                continue
            old_hash = file_record.file_hash
            try:
                file_path = to_absolute_path(str(file_record.file_path))
                if file_path.exists():
                    file_record.file_hash = _compute_sha256(
                        file_path,
                        shop_id=getattr(file_record, "shop_id", None),
                        platform_code=target_platform,
                    )
                file_record.platform_code = target_platform
                file_record.source_platform = "miaoshou"
                file_record.sub_domain = None
                if isinstance(file_record.file_metadata, dict):
                    file_record.file_metadata = {
                        **file_record.file_metadata,
                        "semantic_repair": {
                            "reason": "miaoshou_orders_business_platform_collapsed",
                            "repaired_at": datetime.now(timezone.utc).isoformat(),
                            "old_platform_code": "miaoshou",
                            "new_platform_code": target_platform,
                        },
                    }
                repaired_count += 1
                repaired_rows.append(
                    {
                        "file_id": file_record.id,
                        "file_name": file_record.file_name,
                        "old_platform_code": "miaoshou",
                        "new_platform_code": target_platform,
                        "file_hash_changed": old_hash != file_record.file_hash,
                    }
                )
            except Exception as exc:
                failures.append(
                    {
                        "file_id": file_record.id,
                        "file_name": file_record.file_name,
                        "error": str(exc),
                    }
                )

        await db.commit()
        return success_response(
            data={
                "matched_count": len(pending_records),
                "repaired_count": repaired_count,
                "repaired_rows": repaired_rows,
                "failures": failures,
            },
            message=f"妙手订单平台语义修复完成，修复 {repaired_count} 条记录",
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"[DataSync SemanticRepair] 修复妙手订单平台语义失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="修复妙手订单平台语义失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接或联系系统管理员",
            status_code=500,
        )


@router.get("/data-sync/cleanup-database/impact")
async def get_cleanup_database_impact(
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin),
):
    """预览清空事实数据会影响的事实行和文件状态。"""
    try:
        service = DataSyncCleanupService(db)
        result = await service.analyze_cleanup_impact()
        return success_response(
            data=result,
            message="清空事实数据影响预览查询成功",
        )
    except Exception as e:
        logger.error(f"[DataSync CleanupImpact] 查询清理影响失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="查询清理影响失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限,或联系系统管理员",
            status_code=500,
        )


@router.post("/data-sync/cleanup-database")
async def cleanup_database(
    db: AsyncSession = Depends(get_async_db),  # [*] v4.18.2:改为异步会话
    current_user = Depends(require_admin),
):
    """
    清理数据库API [*] **新增(2025-02-01)**
    
    功能:
    - 清理所有已入库的数据(B类数据表)
    - 仅将原始文件和伴生文件仍存在的已入库文件重置为pending
    - 将无法重建的已入库文件标记为source_missing
    - 用于测试环境数据清理
    
    v4.18.2: 迁移到异步会话
    """
    try:
        service = DataSyncCleanupService(db)
        result = await service.cleanup_database()

        return success_response(
            data=result,
            message=(
                f"数据库清理完成:删除{result['total_deleted_rows']}行数据,"
                f"重置{result['reset_files_count']}个可重建文件,"
                f"标记{result['marked_source_missing_count']}个源文件缺失记录"
            ),
        )
        
    except Exception as e:
        await db.rollback()
        logger.error(f"[DataSync Cleanup] 清理数据库失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="清理数据库失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限,或联系系统管理员",
            status_code=500
        )


# [*] Phase 1.4.3: 任务状态管理 API
@router.get("/data-sync/task-status/{celery_task_id}", response_model=CeleryTaskStatusResponse)
async def get_celery_task_status(
    celery_task_id: str = Path(..., description="Celery 任务ID")
):
    """
    查询 Celery 任务状态
    
    根据 Celery 任务ID查询任务状态、结果和错误信息。
    
    Args:
        celery_task_id: Celery 任务ID(从任务提交响应中获取的 celery_task_id)
    
    Returns:
        CeleryTaskStatusResponse: 任务状态信息
    """
    try:
        from celery.result import AsyncResult
        from backend.celery_app import celery_app
        
        # 创建 AsyncResult 对象
        task_result = AsyncResult(celery_task_id, app=celery_app)
        
        # 获取任务状态
        state = task_result.state
        ready = task_result.ready()
        successful = task_result.successful() if ready else None
        
        # 获取任务结果和错误信息
        result = None
        traceback = None
        if ready:
            if successful:
                try:
                    result = task_result.result
                except Exception as e:
                    logger.warning(f"[API] 获取任务结果失败: {e}")
                    result = None
            else:
                try:
                    traceback = task_result.traceback
                except Exception as e:
                    logger.warning(f"[API] 获取任务错误信息失败: {e}")
                    traceback = None
        
        # 获取任务详细信息
        # [*] 修复:info 可能是异常对象,需要转换为字典或 None
        info = None
        if hasattr(task_result, 'info') and task_result.info is not None:
            if isinstance(task_result.info, dict):
                info = task_result.info
            elif isinstance(task_result.info, Exception):
                # 如果是异常对象,转换为错误信息字典
                info = {"error": str(task_result.info), "error_type": type(task_result.info).__name__}
            else:
                # 其他类型,尝试转换为字符串
                try:
                    info = {"value": str(task_result.info)}
                except Exception:
                    info = None
        
        # 构建响应
        return CeleryTaskStatusResponse(
            celery_task_id=celery_task_id,
            state=state,
            ready=ready,
            successful=successful,
            result=result,
            traceback=traceback,
            info=info
        )
        
    except Exception as e:
        logger.error(f"[API] 查询 Celery 任务状态失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"查询任务状态失败: {str(e)}"
        )


@router.delete("/data-sync/cancel-task/{celery_task_id}", response_model=CancelTaskResponse)
async def cancel_celery_task(
    celery_task_id: str = Path(..., description="Celery 任务ID"),
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user)  # [*] Phase 4.2: 用户认证
):
    """
    取消 Celery 任务
    
    撤销正在执行或等待执行的 Celery 任务。
    
    Args:
        celery_task_id: Celery 任务ID(从任务提交响应中获取的 celery_task_id)
    
    Returns:
        CancelTaskResponse: 取消操作结果
    """
    try:
        from celery.result import AsyncResult
        from backend.celery_app import celery_app
        import asyncio
        
        # 创建 AsyncResult 对象
        task_result = AsyncResult(celery_task_id, app=celery_app)
        
        # 检查任务状态
        state = task_result.state
        
        # 只能取消 PENDING 或 STARTED 状态的任务
        if state in ['SUCCESS', 'FAILURE', 'REVOKED']:
            raise HTTPException(
                status_code=400,
                detail=f"无法取消已完成的任务(当前状态: {state})"
            )
        
        # 撤销任务
        celery_app.control.revoke(celery_task_id, terminate=True)
        
        # 等待一小段时间确认撤销
        await asyncio.sleep(0.5)
        
        # 检查撤销是否成功
        task_result = AsyncResult(celery_task_id, app=celery_app)
        revoked = task_result.state == 'REVOKED'
        
        logger.info(f"[API] 任务已撤销: celery_task_id={celery_task_id}, state={task_result.state}")
        
        return CancelTaskResponse(
            celery_task_id=celery_task_id,
            message="任务已成功撤销" if revoked else "任务撤销请求已发送",
            revoked=revoked
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] 取消 Celery 任务失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"取消任务失败: {str(e)}"
        )


@router.post("/data-sync/retry-task/{celery_task_id}", response_model=RetryTaskResponse)
async def retry_celery_task(
    celery_task_id: str = Path(..., description="Celery 任务ID"),
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user)  # [*] Phase 4.2: 用户认证
):
    """
    重试 Celery 任务
    
    对于失败的任务,重新提交执行。会创建新的 Celery 任务。
    
    [WARN] 注意:当前实现暂不支持直接重试,需要从数据库查询原始任务参数。
    建议使用原始 API 端点重新提交任务。
    
    Args:
        celery_task_id: 原始 Celery 任务ID
    
    Returns:
        RetryTaskResponse: 重试操作结果(包含新的任务ID)
    """
    try:
        from celery.result import AsyncResult
        from backend.celery_app import celery_app
        
        # 获取原始任务信息
        task_result = AsyncResult(celery_task_id, app=celery_app)
        
        # 检查任务状态
        state = task_result.state
        
        # 只能重试失败的任务
        if state != 'FAILURE':
            raise HTTPException(
                status_code=400,
                detail=f"只能重试失败的任务(当前状态: {state})"
            )
        
        # TODO: 实现完整的重试逻辑
        # 1. 从数据库查询原始任务参数(需要维护 celery_task_id 到任务参数的映射)
        # 2. 使用相同参数创建新任务
        # 3. 返回新的任务ID
        
        # 当前实现:返回提示信息
        return RetryTaskResponse(
            original_celery_task_id=celery_task_id,
            new_celery_task_id=None,
            new_task_id=None,
            message="重试功能需要原始任务参数,当前实现暂不支持。请使用原始 API 端点重新提交任务。"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] 重试 Celery 任务失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"重试任务失败: {str(e)}"
        )
