#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据同步服务(Data Sync Service)

v4.12.0新增:
- 统一的数据同步入口
- 移除HTTP调用,改为直接函数调用DataIngestionService
- 支持单文件和批量同步

v4.18.2更新:
- 支持异步数据库操作(AsyncSession)
- 所有数据库操作改为 await 调用

v4.19.0更新:
- 移除同步/异步双模式支持,统一为异步架构

职责:
- 编排流程(查找模板 -> 预览文件 -> 应用模板 -> 调用DataIngestionService)
- 不重复实现(复用现有服务)
- 并发控制(状态机)
- 进度跟踪
"""

from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func
from datetime import datetime, timedelta, timezone
import uuid
import asyncio

from pathlib import Path
import os
from modules.core.db import CatalogFile, FieldMappingTemplate
from modules.core.logger import get_logger
from backend.services.template_matcher import get_template_matcher
from backend.services.template_family_service import get_template_resolver
from backend.services.excel_parser import ExcelParser
from backend.services.data_ingestion_service import DataIngestionService
from backend.services.c_class_data_validator import get_c_class_data_validator
from backend.services.executor_manager import (
    get_executor_manager,
)  # v4.19.0新增:使用统一执行器管理器
from backend.services.data_sync_template_status_service import (
    DataSyncTemplateStatusService,
)
from backend.services.spreadsheet_normalization_service import (
    get_spreadsheet_normalization_service,
)
from modules.services.file_semantics import validate_file_semantics

logger = get_logger(__name__)


class DataSyncService:
    """
    数据同步服务(仅支持异步)

    v4.18.2更新:支持 AsyncSession,所有数据库操作改为异步
    v4.19.0更新:移除同步/异步双模式支持,统一为异步架构

    职责:
    - 编排流程(查找模板 -> 预览文件 -> 应用模板 -> 调用DataIngestionService)
    - 不重复实现(复用现有服务)
    - 并发控制(状态机)
    - 进度跟踪
    """

    def __init__(self, db: AsyncSession):
        """
        数据同步服务(仅支持异步)

        v4.19.0更新:移除同步/异步双模式支持,统一为异步架构

        Args:
            db: 异步数据库会话(AsyncSession)
        """
        self.db = db
        self.template_matcher = get_template_matcher(db)
        self.template_resolver = get_template_resolver(db)
        self.ingestion_service = DataIngestionService(db)
        self.template_status_service = DataSyncTemplateStatusService(db)

    def _resolve_runtime_spreadsheet_path(self, file_path: str) -> str:
        resolved_path = self._safe_resolve_path(file_path)
        source_format = ExcelParser.detect_file_format(resolved_path)
        if source_format in {"xls", "xlsx_with_ole", "html"}:
            normalized = get_spreadsheet_normalization_service().normalize_for_runtime(
                resolved_path,
                source_format=source_format,
            )
            logger.info(
                "[DataSync] 使用标准化副本读取文件: %s -> %s (converter=%s, cache_hit=%s)",
                Path(resolved_path).name,
                normalized.path.name,
                normalized.converter,
                normalized.cache_hit,
            )
            return str(normalized.path)
        return str(resolved_path)

    def _safe_resolve_path(self, file_path: str) -> str:
        """
        安全解析文件路径(增强版:兼容绝对路径和相对路径)

        支持:
        - 绝对路径存在:直接使用
        - 绝对路径不存在:尝试从路径中提取相对部分重新解析(兼容云端部署和环境迁移)
        - 相对路径:从项目根目录解析
        - 路径安全校验:限制在允许的根目录内
        """
        from modules.core.path_manager import (
            get_project_root,
            get_data_input_dir,
            get_data_raw_dir,
        )

        project_root = get_project_root()
        path_obj = Path(file_path)

        # 如果是绝对路径
        if path_obj.is_absolute():
            # 如果绝对路径存在,直接使用
            if path_obj.exists():
                return str(path_obj)

            # 绝对路径不存在,尝试从路径中提取相对部分(兼容旧数据和环境迁移)
            # 例如:/path/to/project/data/raw/2025/file.xlsx -> data/raw/2025/file.xlsx
            path_str = file_path.replace("\\", "/")

            # 尝试查找 data/raw 或 data/input 等关键路径
            key_paths = ["data/raw/", "data/input/", "downloads/", "temp/outputs/"]
            for key_path in key_paths:
                if key_path in path_str:
                    idx = path_str.find(key_path)
                    relative_path = path_str[idx:]
                    resolved_path = project_root / relative_path
                    if resolved_path.exists():
                        logger.info(
                            f"[DataSync] 从绝对路径提取相对路径: {file_path} -> {resolved_path}"
                        )
                        return str(resolved_path.resolve())

            # 如果找不到关键路径,记录警告但仍返回原路径(可能需要人工处理)
            logger.warning(f"[DataSync] 绝对路径不存在且无法提取相对路径: {file_path}")
            return file_path

        # 相对路径:从项目根目录解析
        # [*] v4.19.8修复:先处理Windows路径分隔符,确保路径正确解析
        file_path_normalized = file_path.replace("\\", "/")
        resolved_path = project_root / file_path_normalized

        # 检查路径是否在允许的根目录内
        allowed_roots = [
            get_data_input_dir(),
            get_data_raw_dir(),
            project_root / "downloads",
            project_root / "temp",
        ]

        extra_allowed = os.getenv("DATA_SYNC_ALLOWED_ROOTS", "").strip()
        if extra_allowed:
            for token in [
                part.strip() for part in extra_allowed.split(";") if part.strip()
            ]:
                candidate = Path(token)
                allowed_roots.append(
                    candidate if candidate.is_absolute() else (project_root / token)
                )

        resolved_str = str(resolved_path.resolve())
        for root in allowed_roots:
            root_str = str(root.resolve())
            if resolved_str.startswith(root_str):
                return resolved_str

        strict_mode = os.getenv("DATA_SYNC_STRICT_ALLOWED_ROOTS", "false").lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        if strict_mode:
            raise ValueError(
                f"[SafePath] 文件路径不在允许的目录中: {file_path} -> {resolved_str}"
            )

        # 兼容旧数据：返回解析后的路径，但只做一次较轻提示，避免刷屏
        logger.info(
            f"[DataSync] 文件路径不在允许根目录内(已放行): {file_path} -> {resolved_str}"
        )
        return resolved_str

    @staticmethod
    def _touch_auto_meta(
        catalog_file: CatalogFile,
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """获取或创建auto_ingest元数据"""
        meta = (
            catalog_file.file_metadata
            if isinstance(catalog_file.file_metadata, dict)
            else {}
        )
        auto_meta = meta.get("auto_ingest")
        if not isinstance(auto_meta, dict):
            auto_meta = {}
        return meta, auto_meta

    def _save_auto_meta(
        self, catalog_file: CatalogFile, meta: Dict[str, Any], auto_meta: Dict[str, Any]
    ) -> None:
        """保存auto_ingest元数据"""
        meta["auto_ingest"] = auto_meta
        catalog_file.file_metadata = meta

    def _record_attempt(self, catalog_file: CatalogFile) -> None:
        """记录尝试次数"""
        meta, auto_meta = self._touch_auto_meta(catalog_file)
        auto_meta["attempts"] = auto_meta.get("attempts", 0) + 1
        auto_meta["last_attempt_at"] = datetime.now(timezone.utc).isoformat()
        self._save_auto_meta(catalog_file, meta, auto_meta)

    def _record_status(
        self, catalog_file: CatalogFile, status: str, message: Optional[str] = None
    ) -> None:
        """记录状态"""
        meta, auto_meta = self._touch_auto_meta(catalog_file)
        auto_meta["last_status"] = status
        timestamp = datetime.now(timezone.utc).isoformat()
        if status in ("success", "quarantined"):
            auto_meta["last_success_at"] = timestamp
            if message:
                auto_meta["last_success_message"] = message
        else:
            auto_meta["last_failure_at"] = timestamp
            if message:
                auto_meta["last_reason"] = message
        self._save_auto_meta(catalog_file, meta, auto_meta)

    @staticmethod
    def _mark_file_failed(catalog_file: CatalogFile, message: Optional[str]) -> None:
        catalog_file.status = "failed"
        catalog_file.error_message = message or "未知错误"

    @staticmethod
    def _mark_file_ingested(catalog_file: CatalogFile) -> None:
        catalog_file.status = "ingested"
        catalog_file.error_message = None
        try:
            setattr(catalog_file, "last_processed_at", datetime.now())
        except Exception:
            catalog_file.last_processed = datetime.now()

    @staticmethod
    def _format_header_change_reason(header_changes: Dict[str, Any]) -> str:
        added_fields = header_changes.get("added_fields", []) or []
        removed_fields = header_changes.get("removed_fields", []) or []
        match_rate = header_changes.get("match_rate", 0) or 0

        if added_fields or removed_fields:
            return f"新增{len(added_fields)}个字段, 删除{len(removed_fields)}个字段 (匹配率: {match_rate:.1f}%)"
        return f"字段顺序变化 (匹配率: {match_rate:.1f}%)"

    @staticmethod
    def _format_header_match_rate(match_rate: Any) -> str:
        try:
            value = float(match_rate or 0)
        except Exception:
            value = 0.0
        return f"{value:.1f}%"

    @staticmethod
    def _build_sample_rows(df, limit: int = 3) -> List[Dict[str, Any]]:
        try:
            if df is None or getattr(df, "empty", True):
                return []
            return df.head(limit).to_dict("records")
        except Exception:
            return []

    async def _resolve_template_from_resolver_result(
        self,
        resolve_result: Optional[Dict[str, Any]],
    ) -> Optional[FieldMappingTemplate]:
        if not resolve_result:
            return None
        variant = resolve_result.get("variant") or {}
        legacy_template_id = variant.get("source_legacy_template_id")
        if not legacy_template_id:
            return None
        return await self.db.get(FieldMappingTemplate, legacy_template_id)

    @staticmethod
    def _is_blocking_header_change(header_changes: Dict[str, Any]) -> bool:
        if not header_changes.get("detected"):
            return False
        if header_changes.get("is_exact_match", False):
            return False
        if header_changes.get("is_semantic_match", False):
            return False
        return True

    @staticmethod
    def _normalize_governance_status(status: Dict[str, Any]) -> Dict[str, Any]:
        if status.get("governance_status"):
            return status
        template_status = status.get("template_status")
        mapped = {
            "ready": "ready",
            "alias_only": "non_breaking_drift",
            "update_required": "breaking_drift",
            "missing_variant": "missing_variant",
            "missing": "missing_family",
            "file_missing": "file_missing",
            "parse_failed": "parse_failed",
        }.get(template_status, template_status or "unknown")
        status["governance_status"] = mapped
        return status

    async def evaluate_catalog_file_template_status(
        self,
        catalog_file: CatalogFile,
        *,
        template=None,
        use_template_header_row: bool = True,
    ) -> Dict[str, Any]:
        semantic_validation = validate_file_semantics(
            source_platform=getattr(catalog_file, "source_platform", None)
            or getattr(catalog_file, "platform_code", None),
            platform_code=getattr(catalog_file, "platform_code", None),
            data_domain=getattr(catalog_file, "data_domain", None),
            granularity=getattr(catalog_file, "granularity", None),
            sub_domain=getattr(catalog_file, "sub_domain", None),
            file_name=getattr(catalog_file, "file_name", None),
        )
        if not semantic_validation.is_valid:
            return {
                "template_status": "semantic_invalid",
                "governance_status": "semantic_invalid",
                "has_template": False,
                "template_name": None,
                "template_header_row": None,
                "template_update_required": False,
                "update_reason": semantic_validation.reason,
                "error_code": "SEMANTIC_INVALID",
                "should_auto_sync": False,
                "exact_match": False,
                "semantic_match": False,
                "shadow_compare": None,
                "semantic_anomaly_type": semantic_validation.reason,
            }

        normalized_sub_domain = (
            catalog_file.sub_domain if catalog_file.sub_domain else None
        )
        resolver_result = None
        try:
            resolver_result = await self.template_resolver.resolve(
                platform=catalog_file.platform_code,
                data_domain=catalog_file.data_domain,
                granularity=catalog_file.granularity,
                sub_domain=normalized_sub_domain,
                header_columns=[],
                sample_rows=[],
            )
        except Exception:
            resolver_result = None

        if template is None and resolver_result:
            variant = resolver_result.get("variant") or {}
            legacy_template_id = variant.get("source_legacy_template_id")
            if legacy_template_id:
                template = await self.db.get(FieldMappingTemplate, legacy_template_id)

        template = template or await self.template_matcher.find_best_template(
            platform=catalog_file.platform_code,
            data_domain=catalog_file.data_domain,
            granularity=catalog_file.granularity,
            sub_domain=normalized_sub_domain,
        )

        if not template:
            status = await self.template_status_service.evaluate_catalog_file(
                catalog_file,
                template=None,
            )
            status = self._normalize_governance_status(status)
            if resolver_result:
                status["shadow_compare"] = resolver_result.get("shadow_compare")
                status["governance_status"] = resolver_result.get(
                    "governance_status",
                    status.get("governance_status", "missing_family"),
                )
            return status

        if not getattr(template, "header_columns", None):
            return {
                "template_status": "ready",
                "governance_status": "ready",
                "has_template": True,
                "template_name": template.template_name,
                "template_header_row": getattr(template, "header_row", None),
                "template_update_required": False,
                "update_reason": None,
                "error_code": None,
                "should_auto_sync": True,
                "exact_match": True,
                "semantic_match": True,
                "shadow_compare": (
                    resolver_result.get("shadow_compare") if resolver_result else None
                ),
            }

        parse_error: Optional[Exception] = None
        missing_file = False
        try:
            file_path = self._resolve_runtime_spreadsheet_path(catalog_file.file_path)
            loop = asyncio.get_running_loop()
            file_exists = await loop.run_in_executor(
                None, lambda: Path(file_path).exists()
            )
            if not file_exists:
                raise FileNotFoundError(file_path)

            header_row = 0
            if (
                use_template_header_row
                and getattr(template, "header_row", None) is not None
            ):
                header_row = template.header_row

            executor_manager = get_executor_manager()
            df = await executor_manager.run_cpu_intensive(
                ExcelParser.read_excel,
                file_path,
                header=header_row,
                nrows=5,
            )
            current_columns = df.columns.tolist()
            if hasattr(df, "head") and hasattr(df, "to_dict"):
                sample_rows = df.head(3).fillna("").to_dict("records")
            else:
                sample_rows = []
            status = await self.template_status_service.evaluate_catalog_file(
                catalog_file,
                template=template,
                current_columns=current_columns,
                sample_rows=sample_rows,
            )
            status = self._normalize_governance_status(status)
            if status.get("template_status") == "update_required":
                status["update_reason"] = self._format_header_change_reason(
                    status.get("header_changes", {})
                )
                return status
            return status
        except Exception as exc:
            parse_error = exc
            missing_file = isinstance(exc, FileNotFoundError)
            logger.warning(
                "[DataSync] evaluate template status failed for %s: %s",
                catalog_file.file_name,
                exc,
            )

        return {
            "template_status": "file_missing" if missing_file else "parse_failed",
            "governance_status": "parse_failed",
            "has_template": True,
            "template_name": template.template_name,
            "template_header_row": getattr(template, "header_row", None),
            "template_update_required": False,
            "update_reason": (
                f"文件不存在: {parse_error}"
                if missing_file
                else str(parse_error) if parse_error else "文件读取失败"
            ),
            "error_code": "FILE_MISSING" if missing_file else "FILE_PARSE_FAILED",
            "should_auto_sync": False,
            "exact_match": False,
            "semantic_match": False,
            "shadow_compare": (
                resolver_result.get("shadow_compare") if resolver_result else None
            ),
        }

    async def get_file_sync_readiness(
        self,
        file_id: int,
        *,
        use_template_header_row: bool = True,
    ) -> Dict[str, Any]:
        result = await self.db.execute(
            select(CatalogFile).where(CatalogFile.id == file_id)
        )
        catalog_file = result.scalar_one_or_none()
        if not catalog_file:
            return {
                "ready": False,
                "template_status": "missing",
                "message": "文件不存在",
                "should_auto_sync": False,
            }

        template_status = await self.evaluate_catalog_file_template_status(
            catalog_file,
            use_template_header_row=use_template_header_row,
        )
        return {
            "ready": template_status["template_status"] == "ready",
            **template_status,
            "file_id": catalog_file.id,
            "file_name": catalog_file.file_name,
        }

    async def sync_single_file(
        self,
        file_id: int,
        only_with_template: bool = True,
        allow_quarantine: bool = True,
        task_id: Optional[str] = None,
        use_template_header_row: bool = True,  # [*] 新增:使用模板表头行(严格模式)
    ) -> Dict[str, Any]:
        """
        同步单个文件

        Args:
            file_id: 文件ID
            only_with_template: 是否只处理有模板的文件
            allow_quarantine: 是否允许隔离数据
            task_id: 同步任务ID

        Returns:
            同步结果字典
        """
        try:
            # 1. 获取文件信息
            result = await self.db.execute(
                select(CatalogFile).where(CatalogFile.id == file_id)
            )
            catalog_file = result.scalar_one_or_none()

            if not catalog_file:
                return {
                    "success": False,
                    "file_id": file_id,
                    "status": "failed",
                    "message": "文件不存在",
                }

            # 2. 检查状态(防止并发)
            semantic_validation = validate_file_semantics(
                source_platform=getattr(catalog_file, "source_platform", None)
                or getattr(catalog_file, "platform_code", None),
                platform_code=getattr(catalog_file, "platform_code", None),
                data_domain=getattr(catalog_file, "data_domain", None),
                granularity=getattr(catalog_file, "granularity", None),
                sub_domain=getattr(catalog_file, "sub_domain", None),
                file_name=getattr(catalog_file, "file_name", None),
            )
            if not semantic_validation.is_valid:
                return {
                    "success": False,
                    "file_id": file_id,
                    "file_name": catalog_file.file_name,
                    "status": "skipped",
                    "message": f"鏂囦欢璇箟寮傚父: {semantic_validation.reason}",
                    "skip_reason": semantic_validation.reason,
                    "semantic_anomaly_type": semantic_validation.reason,
                }

            if catalog_file.status == "processing":
                file_meta = catalog_file.file_metadata if isinstance(catalog_file.file_metadata, dict) else {}
                auto_meta = file_meta.get("auto_ingest") if isinstance(file_meta.get("auto_ingest"), dict) else {}
                claimed_task_id = auto_meta.get("current_task_id")
                if task_id and claimed_task_id == task_id:
                    logger.info(
                        "[DataSync] continuing claimed auto-ingest file: file_id=%s, task_id=%s",
                        file_id,
                        task_id,
                    )
                else:
                    return {
                        "success": False,
                        "file_id": file_id,
                        "file_name": catalog_file.file_name,
                        "status": "skipped",
                        "message": "文件正在处理中",
                    }

            if catalog_file.status in ["ingested", "partial_success"]:
                # [*] v4.17.0修复:UPSERT策略下,允许已入库文件重新同步(更新数据)
                # 检查去重策略:如果是UPSERT策略,允许重新同步
                from backend.services.deduplication_fields_config import (
                    get_deduplication_strategy,
                )

                strategy = get_deduplication_strategy(
                    catalog_file.data_domain or "unknown"
                )

                if strategy == "UPSERT":
                    # UPSERT策略:允许重新同步(更新数据)
                    logger.info(
                        f"[DataSync] [v4.17.0] 文件{catalog_file.file_name}({file_id})已入库,"
                        f"但使用UPSERT策略,允许重新同步(更新数据)"
                    )
                    # 重置状态为pending,允许重新处理
                    catalog_file.status = "pending"
                    await self.db.commit()
                else:
                    # INSERT策略:跳过(重复数据应该跳过)
                    logger.info(
                        f"[DataSync] 文件{catalog_file.file_name}({file_id})已入库(status={catalog_file.status}),跳过同步"
                    )
                    return {
                        "success": True,  # [*] 改为成功(已入库不是错误)
                        "file_id": file_id,
                        "file_name": catalog_file.file_name,
                        "status": "skipped",
                        "message": f"文件已入库(状态: {catalog_file.status}),跳过同步",
                        "staged": 0,
                        "imported": 0,
                        "quarantined": 0,
                        "skipped": True,  # [*] 标记为跳过
                        "skip_reason": "file_already_ingested",  # [*] 跳过原因
                    }

            # 记录尝试
            self._record_attempt(catalog_file)

            # 3. 查找模板([*] v4.18.2:异步调用)
            normalized_sub_domain = (
                catalog_file.sub_domain if catalog_file.sub_domain else None
            )
            resolve_result = None
            try:
                resolve_result = await self.template_resolver.resolve(
                    platform=catalog_file.platform_code,
                    data_domain=catalog_file.data_domain,
                    granularity=catalog_file.granularity,
                    sub_domain=normalized_sub_domain,
                    header_columns=[],
                    sample_rows=[],
                )
            except Exception:
                resolve_result = None

            template = await self._resolve_template_from_resolver_result(resolve_result)

            template = template or await self.template_matcher.find_best_template(
                platform=catalog_file.platform_code,
                data_domain=catalog_file.data_domain,
                granularity=catalog_file.granularity,
                sub_domain=normalized_sub_domain,
            )

            if not template and only_with_template:
                self._record_status(catalog_file, "skipped", "no_template")
                await self.db.commit()

                logger.warning(
                    f"[DataSync] [v4.16.0] [WARN] 文件{catalog_file.file_name}({file_id})无模板,跳过同步: "
                    f"platform={catalog_file.platform_code}, domain={catalog_file.data_domain}, "
                    f"granularity={catalog_file.granularity}, sub_domain={catalog_file.sub_domain}"
                )

                return {
                    "success": False,
                    "file_id": file_id,
                    "file_name": catalog_file.file_name,
                    "status": "skipped",
                    "message": f"无模板(platform={catalog_file.platform_code}, domain={catalog_file.data_domain}, granularity={catalog_file.granularity}, sub_domain={catalog_file.sub_domain})",
                }

            # 4. 设置processing状态(防止并发)
            catalog_file.status = "processing"
            await self.db.commit()

            # 5. 预览文件(复用ExcelParser)[*] **v4.6.0重构:严格执行模板表头行**
            try:
                # [*] 修复:使用安全路径解析,确保文件路径正确
                file_path = self._resolve_runtime_spreadsheet_path(
                    catalog_file.file_path
                )

                # [*] v4.18.2修复:使用 run_in_executor 包装文件系统检查,避免阻塞事件循环
                loop = asyncio.get_running_loop()
                file_exists = await loop.run_in_executor(
                    None, lambda: Path(file_path).exists()
                )
                if not file_exists:
                    raise FileNotFoundError(
                        f"文件不存在: {file_path}(原始路径: {catalog_file.file_path})"
                    )

                # [*] v4.6.0重构:如果模板存在且use_template_header_row=True,严格执行模板表头行(不自动检测)
                if (
                    use_template_header_row
                    and template
                    and hasattr(template, "header_row")
                    and template.header_row is not None
                ):
                    # 模板存在且设置了表头行:严格执行,不自动检测
                    header_row = template.header_row
                    logger.info(
                        f"[DataSync] [STRICT] 使用模板表头行: {header_row}(严格模式,不自动检测)"
                    )

                    # 直接使用模板指定的表头行读取文件
                    # [*] v4.19.0更新:使用进程池执行CPU密集型操作(Excel读取),完全隔离事件循环
                    executor_manager = get_executor_manager()
                    df = await executor_manager.run_cpu_intensive(
                        ExcelParser.read_excel,
                        file_path,
                        header=header_row,  # 使用关键字参数
                        nrows=100,
                    )
                    columns = df.columns.tolist()

                    # 验证表头匹配(可选,仅用于日志)
                    if (
                        template
                        and hasattr(template, "header_columns")
                        and template.header_columns
                    ):
                        expected_headers = template.header_columns
                        actual_headers = columns
                        match_count = len(set(expected_headers) & set(actual_headers))
                        match_rate = (
                            match_count / len(expected_headers)
                            if expected_headers
                            else 0
                        )

                        if match_rate < 0.8:
                            logger.warning(
                                f"[DataSync] [WARN] 表头匹配率低: {match_rate:.2%} "
                                f"(期望{len(expected_headers)}个,实际{len(actual_headers)}个,匹配{match_count}个),"
                                f"但继续使用模板表头行{header_row}(严格模式)"
                            )
                        else:
                            logger.info(
                                f"[DataSync] 表头匹配率: {match_rate:.2%}(匹配{match_count}/{len(expected_headers)}个字段)"
                            )
                else:
                    # 模板不存在或未设置表头行:使用默认值0,提示用户创建模板
                    header_row = 0
                    if template:
                        logger.warning(
                            f"[DataSync] 模板存在但未设置表头行,使用默认值0(建议用户更新模板)"
                        )
                    else:
                        logger.warning(
                            f"[DataSync] 无模板,使用默认表头行0(建议用户创建模板)"
                        )

                    # 使用默认表头行读取文件
                    # [*] v4.19.0更新:使用进程池执行CPU密集型操作(Excel读取),完全隔离事件循环
                    executor_manager = get_executor_manager()
                    df = await executor_manager.run_cpu_intensive(
                        ExcelParser.read_excel,
                        file_path,
                        header=header_row,  # 使用关键字参数
                        nrows=100,
                    )
                    columns = df.columns.tolist()

                    # [*] v4.6.0重构:无模板时不进行自动检测,直接使用默认值0
                    # 原因:自动检测效果不佳,用户应该手动选择表头行并创建模板
            except Exception as e:
                logger.error(f"[DataSync] 预览文件失败: {e}")
                catalog_file.status = "failed"
                self._record_status(catalog_file, "failed", f"preview_failed: {str(e)}")
                await self.db.commit()
                return {
                    "success": False,
                    "file_id": file_id,
                    "file_name": catalog_file.file_name,
                    "status": "failed",
                    "message": f"预览失败: {str(e)}",
                }

            # 6. [*] v4.14.0安全版本:检测表头变化,任何变化都阻止同步
            # 如果有模板,检测表头是否完全匹配;否则使用从文件读取的columns
            sample_rows = self._build_sample_rows(df)
            resolved_deduplication_fields = list(
                ((resolve_result or {}).get("active_version") or {}).get(
                    "deduplication_fields"
                )
                or []
            )
            resolved_header_bindings = list(
                (resolve_result or {}).get("semantic_bindings") or []
            )
            resolved_field_parse_rules = list(
                (resolve_result or {}).get("field_parse_rules") or []
            )
            try:
                preview_resolve_result = await self.template_resolver.resolve(
                    platform=catalog_file.platform_code,
                    data_domain=catalog_file.data_domain,
                    granularity=catalog_file.granularity,
                    sub_domain=normalized_sub_domain,
                    header_row=header_row,
                    header_columns=columns,
                    sample_rows=sample_rows,
                )
            except Exception:
                preview_resolve_result = None

            preview_template = await self._resolve_template_from_resolver_result(
                preview_resolve_result
            )
            if preview_template is not None:
                if not template or preview_template.id != template.id:
                    logger.info(
                        "[DataSync] resolver在预览后纠正模板: %s -> %s",
                        getattr(template, "template_name", None) or "None",
                        preview_template.template_name,
                    )
                template = preview_template
                resolve_result = preview_resolve_result
                resolved_deduplication_fields = list(
                    ((resolve_result or {}).get("active_version") or {}).get(
                        "deduplication_fields"
                    )
                    or []
                )
                resolved_header_bindings = list(
                    (resolve_result or {}).get("semantic_bindings") or []
                )
                resolved_field_parse_rules = list(
                    (resolve_result or {}).get("field_parse_rules") or []
                )

            if (
                template
                and hasattr(template, "header_columns")
                and template.header_columns
            ):
                template_header_columns = template.header_columns
                file_header_columns = columns  # 使用文件实际的列名

                # [*] 检测表头变化(不进行相似度匹配,任何变化都需要用户确认)
                # [*] v4.18.2:异步调用
                header_changes = await self.template_matcher.detect_header_changes(
                    template_id=template.id, current_columns=file_header_columns
                )

                # [WARN] 安全原则:任何变化都阻止同步,要求用户更新模板
                if header_changes.get("detected"):
                    # 构建详细的错误信息
                    added_fields = header_changes.get("added_fields", [])
                    removed_fields = header_changes.get("removed_fields", [])
                    match_rate = header_changes.get("match_rate", 0)

                    if self._is_blocking_header_change(header_changes):
                        # 表头不匹配,阻止同步
                        catalog_file.status = "failed"
                        error_reason = []

                        if added_fields:
                            error_reason.append(
                                f"新增{len(added_fields)}个字段: {', '.join(added_fields[:5])}"
                            )
                        if removed_fields:
                            error_reason.append(
                                f"删除{len(removed_fields)}个字段: {', '.join(removed_fields[:5])}"
                            )
                        if not added_fields and not removed_fields:
                            error_reason.append("字段顺序变化")

                        # [*] v4.17.0增强:记录详细的表头变化日志
                        logger.error(
                            f"[DataSync] [v4.17.0] [FAIL] 表头字段不匹配,阻止同步: "
                            f"文件={catalog_file.file_name}, "
                            f"模板={template.template_name if template else 'None'}, "
                            f"新增字段={len(added_fields)}个, "
                            f"删除字段={len(removed_fields)}个, "
                            f"匹配率={self._format_header_match_rate(match_rate)}"
                        )

                        # [*] v4.16.0增强:构建详细的错误消息,包含文件名和变化详情
                        error_message_parts = [
                            f"文件{catalog_file.file_name}的表头字段已变化"
                        ]
                        error_message_parts.append("; ".join(error_reason))
                        error_message_parts.append(
                            f"(匹配率: {self._format_header_match_rate(match_rate)})"
                        )
                        error_message = (
                            ",".join(error_message_parts) + ",请更新模板后再同步"
                        )

                        self._record_status(
                            catalog_file,
                            "failed",
                            f'header_changed: {"; ".join(error_reason)}',
                        )
                        await self.db.commit()

                        return {
                            "success": False,
                            "file_id": file_id,
                            "file_name": catalog_file.file_name,
                            "status": "failed",
                            "message": error_message,  # [*] v4.16.0增强:包含文件名和详细变化信息
                            "header_changes": header_changes,  # 返回详细变化信息
                            "error_code": "HEADER_CHANGED",
                            "error_details": {
                                "added_fields": added_fields,
                                "removed_fields": removed_fields,
                                "match_rate": match_rate,
                                "template_columns": header_changes.get(
                                    "template_columns", []
                                ),
                                "current_columns": header_changes.get(
                                    "current_columns", []
                                ),
                            },
                        }

                # 如果表头完全匹配,使用模板的header_columns
                header_columns = template_header_columns
                logger.info(
                    f"[DataSync] [DSS] 表头匹配,使用模板的header_columns: {len(header_columns)}个字段"
                )
            else:
                # 没有模板或模板没有header_columns,使用从文件读取的列名
                header_columns = columns
                logger.info(
                    f"[DataSync] [DSS] 使用文件读取的header_columns: {len(header_columns)}个字段"
                )

            # [*] v4.14.0新增:从模板读取核心去重字段(deduplication_fields)
            deduplication_fields = None
            if resolved_deduplication_fields:
                deduplication_fields = resolved_deduplication_fields
                logger.info(
                    f"[DataSync] [v4.14.0] 使用模板的核心去重字段: {deduplication_fields}"
                )
            else:
                # [*] v4.17.0修复:如果没有模板或模板没有配置核心字段,使用默认配置
                # 确保同一数据域+子类型的文件使用相同的核心字段配置
                from backend.services.deduplication_fields_config import (
                    get_default_deduplication_fields,
                )

                default_fields = get_default_deduplication_fields(
                    data_domain=catalog_file.data_domain or "",
                    sub_domain=normalized_sub_domain,
                )
                if default_fields:
                    deduplication_fields = default_fields
                    logger.info(
                        f"[DataSync] [v4.17.0] 模板未配置核心字段,使用默认配置: {deduplication_fields} "
                        f"(data_domain={catalog_file.data_domain}, sub_domain={normalized_sub_domain})"
                    )
                else:
                    logger.warning(
                        f"[DataSync] [v4.17.0] [WARN] 未找到数据域 {catalog_file.data_domain} 的默认核心字段配置,"
                        f"将使用所有业务字段计算data_hash(可能导致去重失败)"
                    )

            # [*] v4.17.0增强:记录使用的核心字段配置,便于排查data_hash计算一致性问题
            logger.info(
                f"[DataSync] [v4.17.0] 核心字段配置: "
                f"文件={catalog_file.file_name}, "
                f"模板={template.template_name if template else 'None'}, "
                f"核心字段={deduplication_fields}, "
                f"数据域={catalog_file.data_domain}, "
                f"子类型={normalized_sub_domain or 'None'}"
            )
            if not resolved_field_parse_rules and template:
                resolved_field_parse_rules = list(
                    getattr(template, "field_parse_rules", None) or []
                )
            logger.info(
                "[DataSync] field parse rules resolved: file=%s, template=%s, date_from=%s, date_to=%s, rules=%s",
                catalog_file.file_name,
                getattr(template, "template_name", None) if template else None,
                getattr(catalog_file, "date_from", None),
                getattr(catalog_file, "date_to", None),
                len(resolved_field_parse_rules or []),
            )

            # [*] DSS架构:不再需要字段映射检查,直接使用header_columns入库
            # 向后兼容:保留field_mapping参数(但可以为空)
            field_mapping = {}  # DSS架构不需要字段映射,但保留参数以兼容旧代码

            # 7. 调用DataIngestionService(直接函数调用,不通过HTTP)
            try:
                ingest_task_id = task_id if task_id else f"single_file_{file_id}"

                # [*] v4.16.0修复:优先从catalog_file获取sub_domain(因为template可能没有sub_domain)
                sub_domain_value = (
                    catalog_file.sub_domain if catalog_file.sub_domain else None
                )
                if not sub_domain_value and template:
                    sub_domain_value = getattr(template, "sub_domain", None)

                # [*] v4.16.0新增:验证services域必须有sub_domain
                if (
                    catalog_file.data_domain.lower() == "services"
                    and not sub_domain_value
                ):
                    error_msg = (
                        f"services域必须提供sub_domain,但文件{catalog_file.file_name}({file_id})的sub_domain为空。"
                        f"请检查catalog_files表中的sub_domain字段或创建包含sub_domain的模板。"
                    )
                    logger.error(f"[DataSync] [ERROR] {error_msg}")
                    catalog_file.status = "failed"
                    self._record_status(catalog_file, "failed", error_msg)
                    await self.db.commit()
                    return {
                        "success": False,
                        "file_id": file_id,
                        "file_name": catalog_file.file_name,
                        "status": "failed",
                        "message": error_msg,
                    }

                # [*] v4.16.0新增:无模板时的警告日志
                if not template:
                    logger.warning(
                        f"[DataSync] [v4.16.0] [WARN] 文件{catalog_file.file_name}({file_id})无模板,但继续处理: "
                        f"platform={catalog_file.platform_code}, domain={catalog_file.data_domain}, "
                        f"granularity={catalog_file.granularity}, sub_domain={sub_domain_value}"
                    )

                result = await self.ingestion_service.ingest_data(
                    file_id=file_id,
                    platform=catalog_file.platform_code
                    or catalog_file.source_platform
                    or "",
                    domain=catalog_file.data_domain or "",
                    mappings=field_mapping,  # 向后兼容:保留参数,但DSS架构不使用
                    header_columns=header_columns,  # [*] DSS架构:传递原始表头字段列表
                    header_row=header_row,
                    task_id=ingest_task_id,
                    extract_images=True,
                    deduplication_fields=deduplication_fields,  # [*] v4.14.0新增:传递核心去重字段
                    header_bindings=resolved_header_bindings
                    or (
                        getattr(template, "header_bindings", None) if template else None
                    ),
                    sub_domain=sub_domain_value,  # [*] v4.16.0修复:优先从catalog_file获取
                    template_id=getattr(template, "id", None),
                    field_parse_rules=resolved_field_parse_rules,
                )

                # 更新状态
                if result.get("success"):
                    # [*] v4.15.0增强:区分跳过原因(重复数据 vs 空文件)
                    skip_reason = result.get("skip_reason", "")
                    if result.get("skipped", False):
                        if skip_reason in [
                            "empty_file_no_data_rows",
                            "empty_file_no_data",
                            "empty_file_already_processed",
                        ]:
                            # 空文件:已在上层处理,这里只记录日志
                            self._mark_file_ingested(catalog_file)
                            self._record_status(
                                catalog_file, "success", f"文件为空,已标记为已处理"
                            )
                            logger.info(
                                f"[DataSync] [v4.15.0] [OK] 文件{catalog_file.file_name}({file_id})为空文件,"
                                f"已标记为已同步(ingested)"
                            )
                        else:
                            # [*] v4.16.0更新:在UPSERT策略下,重复数据应该被更新,而不是跳过
                            # 检查是否有更新统计信息
                            import_stats = result.get("import_stats", {})
                            updated_count = import_stats.get("updated", 0)

                            if updated_count > 0:
                                # UPSERT策略:有更新
                                self._mark_file_ingested(catalog_file)
                                self._record_status(
                                    catalog_file,
                                    "success",
                                    f"所有数据都已存在,已更新{updated_count}行(UPSERT策略)",
                                )
                                logger.info(
                                    f"[DataSync] [v4.16.0] [OK] 文件{catalog_file.file_name}({file_id})所有数据都已存在,"
                                    f"已更新{updated_count}行(UPSERT策略)"
                                )
                            else:
                                # 异常情况:标记为跳过(但应该不会发生)
                                self._mark_file_ingested(catalog_file)
                                self._record_status(
                                    catalog_file,
                                    "success",
                                    f"所有数据都已存在,已跳过重复数据",
                                )
                                logger.warning(
                                    f"[DataSync] [v4.16.0] [WARN] 文件{catalog_file.file_name}({file_id})所有数据都已存在,"
                                    f"但updated=0(异常情况,应该不会发生)"
                                )
                    elif result.get("quarantined", 0) > 0:
                        self._mark_file_ingested(catalog_file)  # 部分隔离也标记为已同步
                        self._record_status(
                            catalog_file, "quarantined", f"部分数据已隔离"
                        )
                    else:
                        self._mark_file_ingested(catalog_file)
                        self._record_status(catalog_file, "success", f"入库成功")
                else:
                    self._mark_file_failed(
                        catalog_file, result.get("message", "未知错误")
                    )
                    self._record_status(
                        catalog_file, "failed", result.get("message", "未知错误")
                    )

                await self.db.commit()

                return {
                    "success": result.get("success", False),
                    "file_id": file_id,
                    "file_name": catalog_file.file_name,
                    "status": "success" if result.get("success") else "failed",
                    "message": result.get("message")
                    or "数据入库失败(未提供错误信息)",  # [*] v4.15.0修复:确保有错误消息
                    "staged": result.get("staged", 0),
                    "imported": result.get("imported", 0),
                    "quarantined": result.get("quarantined", 0),
                    "skipped": result.get("skipped", False),  # [*] 新增:传递skipped标志
                    "import_stats": result.get(
                        "import_stats"
                    ),  # [*] v4.15.0新增:传递详细统计信息
                }

            except Exception as e:
                logger.error(f"[DataSync] 数据入库失败: {e}", exc_info=True)
                # [*] 修复:处理数据库事务回滚问题
                try:
                    await self.db.rollback()  # 先回滚,清除错误状态
                    self._mark_file_failed(catalog_file, f"ingest_failed: {str(e)}")
                    self._record_status(
                        catalog_file, "failed", f"ingest_failed: {str(e)}"
                    )
                    await self.db.commit()
                except Exception as commit_error:
                    logger.error(
                        f"[DataSync] 更新状态失败: {commit_error}", exc_info=True
                    )
                    # 如果commit失败,尝试重新获取session
                    try:
                        await self.db.rollback()
                        # 重新查询文件记录
                        result = await self.db.execute(
                            select(CatalogFile).where(CatalogFile.id == file_id)
                        )
                        catalog_file = result.scalar_one_or_none()
                        if catalog_file:
                            self._mark_file_failed(
                                catalog_file, f"ingest_failed: {str(e)}"
                            )
                            self._record_status(
                                catalog_file, "failed", f"ingest_failed: {str(e)}"
                            )
                            await self.db.commit()
                    except Exception as retry_error:
                        logger.error(
                            f"[DataSync] 重试更新状态失败: {retry_error}", exc_info=True
                        )

                return {
                    "success": False,
                    "file_id": file_id,
                    "file_name": (
                        catalog_file.file_name if catalog_file else f"文件{file_id}"
                    ),
                    "status": "failed",
                    "message": f"数据入库失败: {str(e)}",
                }

        except Exception as e:
            logger.error(f"[DataSync] 同步文件失败: {e}", exc_info=True)
            # [*] v4.15.0修复:处理数据库事务回滚问题(更健壮)
            try:
                # 检查是否是事务错误
                error_str = str(e)
                is_transaction_error = (
                    "InFailedSqlTransaction" in error_str
                    or "current transaction is aborted" in error_str.lower()
                    or "transaction" in error_str.lower()
                )

                if is_transaction_error:
                    logger.warning(f"[DataSync] 检测到事务错误,尝试回滚: {e}")
                    try:
                        await self.db.rollback()
                        # 尝试重新获取文件记录
                        result = await self.db.execute(
                            select(CatalogFile).where(CatalogFile.id == file_id)
                        )
                        catalog_file = result.scalar_one_or_none()
                        if catalog_file and catalog_file.status == "processing":
                            # 如果文件状态还是processing,更新为failed
                            self._mark_file_failed(
                                catalog_file, f"sync_failed: {str(e)}"
                            )
                            self._record_status(
                                catalog_file, "failed", f"sync_failed: {str(e)}"
                            )
                            await self.db.commit()
                    except Exception as retry_error:
                        logger.error(
                            f"[DataSync] 回滚后重试失败: {retry_error}", exc_info=True
                        )
                        # 如果重试也失败,尝试关闭会话
                        try:
                            await self.db.close()
                            # 注意:这里不能创建新会话,因为self.db是传入的
                            # 调用方需要处理会话失效的情况
                        except Exception:
                            pass
                else:
                    # 非事务错误,正常回滚
                    await self.db.rollback()
            except Exception as rollback_error:
                logger.error(f"[DataSync] 回滚失败: {rollback_error}", exc_info=True)
                # 尝试关闭会话(如果可能)
                try:
                    await self.db.close()
                except Exception:
                    pass

            # [*] v4.15.0修复:确保错误消息详细且有用
            error_message = f"同步失败: {str(e)}"
            # 如果是事务错误,添加更详细的说明
            error_str = str(e)
            if (
                "InFailedSqlTransaction" in error_str
                or "current transaction is aborted" in error_str.lower()
            ):
                error_message = (
                    f"数据库事务错误: {str(e)}(可能是并发冲突或数据库连接问题)"
                )

            return {
                "success": False,
                "file_id": file_id,
                "status": "failed",
                "message": error_message,
            }
