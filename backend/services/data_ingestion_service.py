#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据入库服务（Data Ingestion Service）

v4.12.0新增：
- 统一的数据入库服务，提取ingest_file的核心逻辑
- 复用data_importer函数，不重复实现
- 支持Raw -> Fact -> MV三层数据架构

v4.13.0 DSS架构重构：
- 移除字段映射应用（在Metabase中完成）
- 移除数据标准化（在Metabase中完成）
- 移除业务逻辑验证（在Metabase中完成）
- 移除数据隔离（DSS架构不隔离数据）

职责：
- 文件读取和解析
- 元数据补充（platform_code, shop_id）
- 去重处理（data_hash）
- 数据入库（RawDataImporter写入JSONB格式）
"""

from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pathlib import Path
from datetime import datetime, date
import re
import os
import asyncio

from modules.core.db import CatalogFile
from modules.core.logger import get_logger
from backend.services.excel_parser import ExcelParser
from backend.services.executor_manager import get_executor_manager  # v4.19.0新增：使用统一执行器管理器
from backend.services.data_importer import (
    stage_orders,
    stage_product_metrics,
    stage_inventory,
    upsert_orders,
    upsert_product_metrics,
)
from backend.services.operational_data_importer import (
    upsert_traffic,
    upsert_service,
    upsert_analytics,
)
# [*] v4.6.0 DSS架构：使用RawDataImporter写入JSONB格式
from backend.services.raw_data_importer import get_raw_data_importer
from backend.services.deduplication_service import DeduplicationService
from backend.services.currency_extractor import get_currency_extractor  # [*] v4.15.0新增
# [*] DSS架构：移除验证、标准化、隔离相关导入
# 这些功能在DSS架构下不再使用，数据处理在Metabase中完成
# from backend.services.data_validator import (
#     validate_orders,
#     validate_product_metrics,
#     validate_services,
#     validate_traffic,
#     validate_analytics,
# )
# from backend.services.enhanced_data_validator import (
#     validate_inventory,
# )
# from backend.services.data_standardizer import standardize_rows
# from backend.services.field_mapping_validator import validate_field_mapping, calculate_mapping_quality_score
# from backend.services.data_importer import quarantine_failed_data

logger = get_logger(__name__)


class DataIngestionService:
    """
    数据入库服务（仅支持异步）
    
    v4.18.2更新：支持 AsyncSession
    v4.19.0更新：移除同步/异步双模式支持，统一为异步架构
    
    职责：
    - 文件读取和解析
    - 字段映射应用
    - 数据标准化和验证
    - 数据入库（调用data_importer函数）
    - 数据隔离处理
    """
    
    def __init__(self, db: AsyncSession):
        """
        初始化数据入库服务
        
        Args:
            db: 异步数据库会话（AsyncSession）
        """
        self.db = db
    
    def _safe_resolve_path(self, file_path: str) -> str:
        """
        安全解析文件路径（增强版：兼容绝对路径和相对路径）
        
        Args:
            file_path: 文件路径
            
        Returns:
            解析后的安全路径
            
        支持：
        - 绝对路径存在：直接使用
        - 绝对路径不存在：尝试从路径中提取相对部分重新解析（兼容云端部署和环境迁移）
        - 相对路径：从项目根目录解析
        - 路径安全校验：限制在允许的根目录内
        """
        from modules.core.path_manager import get_project_root, get_data_input_dir, get_data_raw_dir
        
        project_root = get_project_root()
        path_obj = Path(file_path)
        
        # 允许的目录（使用统一路径管理）
        allowed_dirs_paths = [
            get_data_input_dir(),
            get_data_raw_dir(),
            project_root / "temp" / "outputs",
            project_root / "downloads",
        ]
        
        # 如果是绝对路径
        if path_obj.is_absolute():
            # 如果绝对路径存在，验证后直接使用
            if path_obj.exists():
                resolved = path_obj.resolve()
                # 验证路径在允许的目录中
                for allowed_dir_path in allowed_dirs_paths:
                    base_path = Path(allowed_dir_path).resolve()
                    try:
                        resolved.relative_to(base_path)
                        return str(resolved)
                    except ValueError:
                        continue
                
                # 额外检查：路径包含允许的目录名
                file_path_normalized = str(resolved).lower().replace("\\", "/")
                if any(key in file_path_normalized for key in ["data/raw", "data/input", "temp/outputs", "downloads"]):
                    logger.info(f"[SafePath] 绝对路径通过额外检查: {file_path}")
                    return str(resolved)
            
            # 绝对路径不存在，尝试从路径中提取相对部分（兼容旧数据和环境迁移）
            path_str = file_path.replace("\\", "/")
            key_paths = ["data/raw/", "data/input/", "downloads/", "temp/outputs/"]
            for key_path in key_paths:
                if key_path in path_str:
                    idx = path_str.find(key_path)
                    relative_path = path_str[idx:]
                    resolved_path = project_root / relative_path
                    if resolved_path.exists():
                        logger.info(f"[SafePath] 从绝对路径提取相对路径: {file_path} -> {resolved_path}")
                        return str(resolved_path.resolve())
            
            # 如果找不到关键路径，记录警告
            logger.warning(f"[SafePath] 绝对路径不存在且无法提取相对路径: {file_path}")
            # 仍然尝试解析，以便后续错误处理可以给出更好的提示
            resolved = path_obj.resolve() if path_obj.exists() else path_obj
        else:
            # 相对路径：从项目根目录解析
            resolved = (project_root / file_path).resolve()
        
        # 检查文件路径是否在允许的目录中
        for allowed_dir_path in allowed_dirs_paths:
            base_path = Path(allowed_dir_path).resolve()
            try:
                resolved.relative_to(base_path)
                return str(resolved)
            except ValueError:
                continue
        
        # 额外检查：如果路径包含允许的目录名（大小写不敏感，兼容路径拼写差异）
        file_path_lower = str(resolved).lower()
        file_path_normalized = file_path_lower.replace("\\", "/")
        
        for allowed_dir_path in allowed_dirs_paths:
            allowed_dir_str = str(allowed_dir_path)
            allowed_dir_normalized = allowed_dir_str.lower().replace("\\", "/")
            if allowed_dir_normalized in file_path_normalized:
                if project_root:
                    # v4.18.1修复：使用项目根目录名称动态获取，避免硬编码
                    project_root_name = project_root.name.lower()
                    project_key_parts = [project_root_name, "data", "downloads", "temp"]
                    if any(part in file_path_normalized for part in project_key_parts):
                        logger.info(f"[SafePath] 通过额外检查允许路径: {file_path} (允许目录: {allowed_dir_str})")
                        return str(resolved)
        
        allowed_dirs_str = [str(d) for d in allowed_dirs_paths]
        raise ValueError(f"[SafePath] 文件路径不在允许的目录中: {file_path} (项目根目录: {project_root}, 允许目录: {allowed_dirs_str})")
    
    async def ingest_data(
        self,
        file_id: int,
        platform: str,
        domain: str,
        mappings: Dict[str, Any],
        header_row: int = 0,
        task_id: Optional[str] = None,
        extract_images: bool = True,
        header_columns: Optional[List[str]] = None,  # [*] v4.6.0 DSS架构：原始表头字段列表
        deduplication_fields: Optional[List[str]] = None,  # [*] v4.14.0新增：核心去重字段列表
        sub_domain: Optional[str] = None,  # [*] v4.14.0新增：子类型
    ) -> Dict[str, Any]:
        """
        数据入库主方法
        
        Args:
            file_id: 文件ID
            platform: 平台代码
            domain: 数据域（orders/products/inventory/services等）
            mappings: 字段映射字典
            header_row: 表头行（0-based）
            task_id: 同步任务ID
            extract_images: 是否提取图片
            
        Returns:
            入库结果字典
        """
        try:
            # 1. 获取文件记录
            result = await self.db.execute(
                select(CatalogFile).where(CatalogFile.id == file_id)
            )
            file_record = result.scalar_one_or_none()
            if not file_record:
                raise ValueError(f"文件记录不存在: {file_id}")
            
            # 2. 从文件记录获取domain（二次确认）
            if not domain and file_record.data_domain:
                domain = file_record.data_domain
                logger.info(f"[Ingest] 从文件记录获取data_domain（二次确认）: {domain}")
            
            logger.info(f"[Ingest] 数据域: {domain}, header_row: {header_row} (0-based, Excel第{header_row+1}行)")
            
            # 3. 检查重复入库（全0文件和空文件）
            if file_record.status == "ingested":
                error_msg = file_record.error_message or ""
                if "[全0数据标识]" in error_msg:
                    return {
                        "success": True,
                        "message": "该文件已识别为全0数据文件，无需重复入库。",
                        "staged": 0,
                        "imported": 0,
                        "amount_imported": 0,
                        "quarantined": 0,
                        "skipped": True,
                        "skip_reason": "all_zero_data_already_processed"
                    }
                elif "[空文件标识]" in error_msg:
                    # [*] v4.15.0新增：检查空文件重复处理
                    return {
                        "success": True,
                        "message": "该文件已识别为空文件（有表头但无数据行），无需重复入库。",
                        "staged": 0,
                        "imported": 0,
                        "amount_imported": 0,
                        "quarantined": 0,
                        "skipped": True,
                        "skip_reason": "empty_file_already_processed"
                    }
            
            # 4. 读取完整文件
            safe_path = self._safe_resolve_path(file_record.file_path)
            
            # [*] v4.18.2修复：使用 run_in_executor 包装文件系统检查，避免阻塞事件循环
            loop = asyncio.get_running_loop()
            file_exists = await loop.run_in_executor(
                None,
                lambda: Path(safe_path).exists()
            )
            if not file_exists:
                raise ValueError(f"文件不存在: {file_record.file_path}")
            
            header_param = None if header_row < 0 else header_row
            logger.info(f"[Ingest] 实际使用的表头行: header_param={header_param}")
            
            # [*] v4.19.0更新：使用进程池执行CPU密集型操作（Excel读取），完全隔离事件循环
            executor_manager = get_executor_manager()
            df = await executor_manager.run_cpu_intensive(
                ExcelParser.read_excel,
                safe_path,
                header=header_param,  # 使用关键字参数
                nrows=None  # 读取完整文件（不限制行数）
            )
            
            # [*] v4.18.2修复：使用 run_in_executor 包装文件大小获取，避免阻塞事件循环
            loop = asyncio.get_running_loop()
            file_size_mb = await loop.run_in_executor(
                None,
                lambda: Path(safe_path).stat().st_size / (1024 * 1024)
            )
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
            
            # [*] v4.15.0新增：提前检测空文件（有表头但无数据行）
            if len(all_rows) == 0:
                # 情况：有表头但无数据行
                logger.warning(
                    f"[Ingest] [v4.15.0] 检测到空文件（有表头但无数据行）: "
                    f"file_id={file_id}, file_name={file_record.file_name}, "
                    f"表头列数={len(df.columns) if df is not None else 0}"
                )
                
                # 标记文件状态为已处理（避免重复处理）
                file_record.status = "ingested"
                file_record.error_message = "[空文件标识] 文件有表头但无数据行，无需入库"
                await self.db.commit()
                
                return {
                    "success": True,  # [*] 改为成功（空文件不是错误，是正常情况）
                    "message": "文件为空：有表头但无数据行，已标记为已处理",
                    "staged": 0,
                    "imported": 0,
                    "amount_imported": 0,
                    "quarantined": 0,
                    "skipped": True,
                    "skip_reason": "empty_file_no_data_rows",
                    "image_extraction_started": False,
                    "normalization_report": normalization_report if 'normalization_report' in locals() else {},
                }
            
            # [*] v4.6.0 DSS架构：优先使用传入的header_columns，否则使用从文件读取的列名
            # [*] v4.16.0修复：始终使用文件原始的列名（包含货币代码）用于追溯
            # 即使传入了归一化的header_columns（来自模板），也要使用文件原始列名
            file_original_columns = list(df.columns.tolist())  # 文件原始列名（包含货币代码）
            original_header_columns = file_original_columns  # 始终使用文件原始列名用于追溯
            
            # [*] DSS架构：跳过字段映射，直接使用原始数据
            # DSS架构原则：数据同步只做数据采集和存储，字段映射在Metabase中完成
            enhanced_rows = all_rows  # 直接使用原始数据，保留所有原始列名
            logger.info(f"[Ingest] [DSS] 跳过字段映射，直接使用原始数据: {len(enhanced_rows)}行，{len(original_header_columns)}个字段")
            
            # [*] 向后兼容：如果提供了mappings，记录日志但不使用（DSS架构不需要字段映射）
            if mappings:
                logger.info(f"[Ingest] [DSS] 检测到mappings参数（{len(mappings)}个），DSS架构将忽略，直接使用原始数据")
            
            # [*] v4.18.1优化：文件级别检查platform_code和shop_id（减少日志输出）
            # 从file_record获取一次，然后批量应用到所有行
            if file_record:
                # 文件级别确定platform_code
                file_platform_code = file_record.platform_code or platform or "unknown"
                if not file_record.platform_code and not platform:
                    logger.warning(f"[Ingest] [v4.18.1] 文件级别platform_code为空，使用unknown")
                
                # 文件级别确定shop_id（从伴生JSON文件获取，没有则为'none'）
                # [*] v4.18.1重构：shop_id完全从文件元数据获取，不再逐行检查
                file_shop_id = file_record.shop_id or 'none'
                if not file_record.shop_id:
                    logger.info(f"[Ingest] [v4.18.1] 文件级别shop_id为空，设为'none'（将使用Metabase关联账号管理表）")
                
                # 批量应用到所有行（静默处理，不逐行输出日志）
                for row in enhanced_rows:
                    if not row.get("platform_code"):
                        row["platform_code"] = file_platform_code
                    if not row.get("shop_id"):
                        row["shop_id"] = file_shop_id
            
            # [*] DSS架构：跳过数据标准化，保留原始数据
            # DSS架构原则：数据同步只做数据采集和存储，数据标准化在Metabase中完成
            # 如果需要数据类型转换，应在Metabase中通过字段映射或计算字段处理
            logger.info(f"[Ingest] [DSS] 跳过数据标准化，保留原始数据格式")
            # enhanced_rows 保持不变，直接使用原始数据
            
            # [*] DSS架构：移除特殊处理，保留原始数据
            # DSS架构原则：不修改原始数据，所有数据处理在Metabase中完成
            # 如果需要metric_date，应在Metabase中通过字段映射或计算字段处理
            logger.info(f"[Ingest] [DSS] 跳过特殊处理，保留原始数据完整性")
            
            # [*] DSS架构：跳过数据验证，直接使用所有数据
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
            
            # [*] DSS架构：使用所有数据（不筛选）
            valid_rows = enhanced_rows  # 直接使用所有数据，不做验证筛选
            
            # 11. 数据入库（使用RawDataImporter写入JSONB格式）[*] v4.6.0 DSS架构
            # [*] v4.12.2增强：添加数据丢失追踪日志
            logger.info(f"[Ingest] [DSS] 数据入库开始: file_id={file_id}, 总行数={len(valid_rows)}（DSS架构：跳过验证，所有数据入库）")
            
            staged = 0
            imported = 0
            amount_imported = 0
            
            if not task_id:
                task_id = f"single_file_{file_id}"
            
            if valid_rows:
                # [*] v4.6.0 DSS架构：使用RawDataImporter写入JSONB格式（保留原始中文表头）
                try:
                    # 获取RawDataImporter和DeduplicationService实例
                    raw_importer = get_raw_data_importer(self.db)
                    dedup_service = DeduplicationService(self.db)
                    
                    # 获取granularity（从file_record或默认daily）
                    granularity = getattr(file_record, 'granularity', None) or "daily"
                    
                    # [*] v4.14.0新增：获取核心去重字段（优先级：模板配置 > 默认配置 > 所有字段）
                    from backend.services.deduplication_fields_config import get_deduplication_fields
                    final_deduplication_fields = get_deduplication_fields(
                        data_domain=domain,
                        template_fields=deduplication_fields,
                        sub_domain=sub_domain
                    )
                    
                    if final_deduplication_fields:
                        logger.info(
                            f"[Ingest] [v4.14.0] 使用核心字段计算data_hash: {final_deduplication_fields} "
                            f"（数据行数={len(valid_rows)}）"
                        )
                    else:
                        logger.warning(
                            f"[Ingest] [v4.14.0] [WARN] 未配置核心字段，使用所有业务字段计算data_hash "
                            f"（数据行数={len(valid_rows)}）"
                        )
                    
                    # 计算data_hash（批量计算，支持核心字段）
                    logger.info(f"[Ingest] [DSS] 开始计算data_hash: {len(valid_rows)}行")
                    data_hashes = dedup_service.batch_calculate_data_hash(
                        valid_rows,
                        deduplication_fields=final_deduplication_fields
                    )
                    logger.info(f"[Ingest] [DSS] data_hash计算完成: {len(data_hashes)}个哈希")
                    
                    # 准备header_columns（原始表头字段列表）
                    # [*] v4.6.0 DSS架构：使用原始表头字段列表（保留中文表头）
                    # [*] v4.16.0修复：始终使用文件原始列名（包含货币代码）用于追溯和货币代码提取
                    # 注意：original_header_columns在函数作用域中定义，可以直接访问
                    header_columns_for_storage = original_header_columns  # 用于保存到数据库（原始列名，包含货币代码）
                    if not header_columns_for_storage and valid_rows:
                        # 如果无法获取原始表头，从第一行数据获取键（作为兜底）
                        header_columns_for_storage = list(valid_rows[0].keys())
                        logger.warning(f"[Ingest] [DSS] 无法获取原始表头，使用数据键作为header_columns")
                    
                    # [*] v4.15.0新增：货币代码提取和字段名归一化
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
                        
                        # [*] v4.16.0修复：提取货币代码时使用文件原始列名（row.keys()），而不是归一化的header_columns
                        # 原因：归一化的header_columns已经移除了货币代码，无法提取
                        # 使用 row.keys() 获取文件原始的字段名（包含货币代码）
                        currency_code = currency_extractor.extract_currency_from_row(
                            row,
                            header_columns=None  # [*] 修复：传入None，让方法使用row.keys()（原始字段名）
                        )
                        currency_codes.append(currency_code)
                    
                    logger.info(
                        f"[Ingest] [v4.15.0] 货币代码提取完成: "
                        f"提取到{sum(1 for c in currency_codes if c)}个货币代码，"
                        f"字段名归一化完成: {len(normalized_rows)}行"
                    )
                    
                    # 批量插入（使用RawDataImporter）
                    # [*] v4.16.0更新：获取sub_domain（services域必须提供）
                    sub_domain_value = sub_domain
                    if not sub_domain_value and file_record and hasattr(file_record, 'sub_domain'):
                        sub_domain_value = file_record.sub_domain
                    
                    # [*] v4.16.0修复：services域必须提供sub_domain，否则抛出详细错误
                    if domain.lower() == 'services' and not sub_domain_value:
                        file_name = file_record.file_name if file_record else f"文件{file_id}"
                        error_msg = (
                            f"services域必须提供sub_domain参数（ai_assistant或agent），"
                            f"但文件{file_name}({file_id})的sub_domain为空。"
                            f"请检查catalog_files表中的sub_domain字段或模板配置。"
                        )
                        logger.error(f"[Ingest] [ERROR] {error_msg}")
                        raise ValueError(error_msg)
                    
                    table_name_suffix = f"{domain}_{granularity}"
                    if sub_domain_value:
                        table_name_suffix = f"{domain}_{sub_domain_value}_{granularity}"
                    logger.info(f"[Ingest] [DSS] 开始批量插入到fact_raw_data_{table_name_suffix}表")
                    
                    # [*] v4.16.0修复：准备归一化的header_columns用于动态列管理
                    # 动态列应该使用归一化的列名（不包含货币代码），避免创建重复的列
                    normalized_header_columns = currency_extractor.normalize_field_list(header_columns_for_storage)
                    
                    # [*] v4.17.0修复：优先使用file_record.platform_code，确保表名正确
                    # 如果platform_code为空，会导致表名错误（如fact__inventory_snapshot）
                    platform_code_for_table = platform
                    if file_record and file_record.platform_code:
                        platform_code_for_table = file_record.platform_code
                    elif not platform_code_for_table or platform_code_for_table.strip() == '':
                        # 如果platform_code为空，使用"unknown"作为默认值
                        platform_code_for_table = "unknown"
                        logger.warning(
                            f"[Ingest] [v4.17.0] [WARN] platform_code为空，使用默认值: unknown "
                            f"(file_id={file_id}, file_name={file_record.file_name if file_record else 'unknown'}, "
                            f"platform_param={platform})"
                        )
                    
                    # [*] v4.19.0更新：统一使用异步操作
                    import_result = await raw_importer.async_batch_insert_raw_data(
                        rows=normalized_rows,  # [*] v4.15.0更新：使用归一化后的数据（字段名不含货币代码）
                        data_hashes=data_hashes,
                        data_domain=domain,
                        granularity=granularity,
                        platform_code=platform_code_for_table,  # [*] v4.17.0修复：使用正确的platform_code
                        shop_id=getattr(file_record, 'shop_id', None) if file_record else None,
                        file_id=file_id,
                        header_columns=normalized_header_columns,  # [*] v4.16.0修复：使用归一化的header_columns用于动态列管理（避免创建重复列）
                        currency_codes=currency_codes,  # [*] v4.15.0新增：货币代码列表
                        sub_domain=sub_domain_value,  # [*] v4.16.0新增：子类型（services域必须提供）
                        original_header_columns=header_columns_for_storage,  # [*] v4.16.0新增：原始header_columns（包含货币代码，用于保存到数据库）
                        template_id=None  # [*] v4.17.0新增：模板ID（暂时为None，后续从template获取）
                    )
                    
                    # [*] v4.15.0修改：处理新的返回值格式（字典）
                    if isinstance(import_result, dict):
                        imported = import_result.get('inserted', 0) + import_result.get('updated', 0)
                        updated = import_result.get('updated', 0)
                        skipped = import_result.get('skipped', 0)
                        
                        if updated > 0:
                            logger.info(
                                f"[Ingest] [DSS] [v4.15.0] UPSERT策略完成: "
                                f"新插入={import_result.get('inserted', 0)}行, "
                                f"更新={updated}行, "
                                f"总计={imported}行（表=fact_raw_data_{domain}_{granularity}）"
                            )
                        else:
                            logger.info(
                                f"[Ingest] [DSS] 批量插入完成: "
                                f"插入={import_result.get('inserted', 0)}行, "
                                f"跳过={skipped}行, "
                                f"总计={imported}行（表=fact_raw_data_{domain}_{granularity}）"
                            )
                    else:
                        # 兼容旧格式（整数）
                        imported = import_result
                        updated = 0
                        skipped = 0
                        logger.info(f"[Ingest] [DSS] 批量插入完成: {imported}行成功（表=fact_raw_data_{domain}_{granularity}）")
                    
                    # [*] 添加行数验证：验证导入行数与源文件行数匹配
                    if len(valid_rows) > 0:
                        loss_rate = (len(valid_rows) - imported) / len(valid_rows)
                        if loss_rate > 0.05:  # 超过5%的数据丢失
                            logger.warning(
                                f"[Ingest] [WARN] 警告：检测到显著数据丢失！"
                                f"源文件行数={len(valid_rows)}, "
                                f"导入行数={imported}, "
                                f"丢失率={loss_rate:.2%} "
                                f"（可能原因：核心字段配置不正确导致所有行产生相同的hash）"
                            )
                        elif imported == 1 and len(valid_rows) > 1:
                            logger.error(
                                f"[Ingest] [FAIL] 严重错误：只导入了1行，但源文件有{len(valid_rows)}行！"
                                f"这可能是因为所有行的data_hash都相同，导致去重失败。"
                                f"请检查核心字段配置是否正确。"
                            )
                    
                    # staged等于imported（DSS架构不再需要Staging层）
                    staged = imported
                    
                    # [*] v4.15.0新增：保存updated和skipped信息到结果中
                    # [*] v4.16.0修复：检查import_result是否存在（避免变量作用域错误）
                    if 'import_result' in locals() and isinstance(import_result, dict):
                        import_stats = {
                            'inserted': import_result.get('inserted', 0),
                            'updated': import_result.get('updated', 0),
                            'skipped': import_result.get('skipped', 0),
                        }
                    else:
                        # import_result不存在或不是字典格式，使用默认值
                        import_stats = {
                            'inserted': imported if 'imported' in locals() else 0,
                            'updated': 0,
                            'skipped': 0,
                        }
                    
                    # [*] v4.15.0新增：构建详细消息
                    # [*] v4.16.0更新：所有数据域都使用UPSERT策略，优先显示更新消息
                    if import_stats['updated'] > 0:
                        if import_stats['inserted'] > 0:
                            message = (
                                f"数据同步完成：新插入{import_stats['inserted']}行，"
                                f"更新{import_stats['updated']}行（UPSERT策略）"
                            )
                        else:
                            message = (
                                f"数据同步完成：所有{import_stats['updated']}行数据都已存在，"
                                f"已更新{import_stats['updated']}行（UPSERT策略）"
                            )
                    elif import_stats['inserted'] > 0:
                        message = f"数据同步完成：新插入{import_stats['inserted']}行"
                    elif import_stats['skipped'] > 0:
                        # [*] v4.16.0更新：UPSERT策略下不应该有skipped，但保留兼容性
                        message = (
                            f"数据同步完成：插入{import_stats['inserted']}行，"
                            f"跳过{import_stats['skipped']}行（重复数据）"
                        )
                    else:
                        message = f"数据入库成功：暂存{staged}行，入库{imported}行（DSS架构：跳过验证，所有数据入库）"
                    
                    # [*] v4.18.2移除：订单金额维度表功能已移除
                    # 原因：DSS架构下，数据已完整存储在 b_class.fact_raw_data_orders_* 表的 JSONB 字段中
                    # 货币代码已提取到 currency_code 系统字段，字段名已归一化
                    # 数据标准化应在 Metabase 中完成，该表属于"只写不读"的冗余数据
                    # 如需订单金额统计，请通过 Metabase 查询 b_class.fact_raw_data_orders_* 表
                    
                except Exception as e:
                    logger.error(f"[Ingest] [DSS] RawDataImporter入库失败: {e}", exc_info=True)
                    # 如果RawDataImporter失败，记录错误但不抛出异常（让后续流程继续）
                    imported = 0
                    staged = 0
                    import_result = None  # [*] v4.16.0修复：确保import_result被定义，避免后续访问错误
            
            # 12. 更新文件状态
            try:
                # [*] DSS架构：不再有验证错误，所有数据都成功入库
                file_record.status = "ingested"
                
                try:
                    setattr(file_record, "last_processed_at", datetime.now())
                except Exception:
                    file_record.last_processed = datetime.now()
                
                await self.db.commit()
            except Exception as commit_error:
                # [*] 修复：处理数据库事务回滚问题
                logger.error(f"[Ingest] 更新文件状态失败: {commit_error}", exc_info=True)
                try:
                    await self.db.rollback()
                    # 重新查询文件记录并更新
                    result = await self.db.execute(
                        select(CatalogFile).where(CatalogFile.id == file_id)
                    )
                    file_record = result.scalar_one_or_none()
                    if file_record:
                        # [*] DSS架构：不再有验证错误，所有数据都成功入库
                        file_record.status = "ingested"
                        try:
                            setattr(file_record, "last_processed_at", datetime.now())
                        except Exception:
                            file_record.last_processed = datetime.now()
                        await self.db.commit()
                except Exception as retry_error:
                    logger.error(f"[Ingest] 重试更新文件状态失败: {retry_error}", exc_info=True)
                    await self.db.rollback()
            
            # 13. 异步提取图片（可选）
            image_extraction_started = False
            if extract_images and imported > 0:
                try:
                    from backend.tasks.image_extraction import extract_product_images_task
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
                            f"[数据入库] Redis/Celery连接失败（{error_type}），跳过图片提取任务"
                        )
                    else:
                        logger.warning(
                            f"[数据入库] 图片提取任务调用失败（{error_type}），跳过"
                        )
                    image_extraction_started = True
                except Exception as img_err:
                    # 捕获所有异常（包括Redis连接错误），不影响主流程
                    error_type = type(img_err).__name__
                    if "OperationalError" in error_type or "ConnectionError" in error_type:
                        logger.warning(
                            f"[Ingest] Redis/Celery连接失败（{error_type}），跳过图片提取任务"
                        )
                    else:
                        logger.warning(f"[Ingest] 图片提取任务提交失败: {img_err}")
            
            # 14. 触发DATA_INGESTED事件（数据流转流程自动化）
            if imported > 0:
                try:
                    from backend.utils.events import DataIngestedEvent
                    from backend.services.event_listeners import event_listener
                    
                    event = DataIngestedEvent(
                        file_id=file_id,
                        platform_code=platform,
                        data_domain=domain,
                        granularity=getattr(file_record, 'granularity', None),
                        row_count=imported
                    )
                    event_listener.handle_data_ingested(event)
                    logger.info(f"[Ingest] 已触发DATA_INGESTED事件: domain={domain}, rows={imported}")
                except Exception as event_err:
                    # 事件触发失败不影响主流程
                    logger.warning(f"[Ingest] 触发DATA_INGESTED事件失败: {event_err}")
            
            # 15. 返回结果
            # [*] v4.15.0修复：区分"空文件"和"全部重复"的情况
            # 注意：空文件应该在上面的提前检测中已经处理，这里是兜底检测
            if imported == 0 and staged == 0:
                # 检查是否是空文件（兜底检测，正常情况下不应该到达这里）
                if not valid_rows or len(valid_rows) == 0:
                    # 空文件：标记为已处理（避免重复处理）
                    logger.warning(
                        f"[Ingest] [v4.15.0] 兜底检测：发现空文件（应该在提前检测中处理）: "
                        f"file_id={file_id}, file_name={file_record.file_name if file_record else 'unknown'}"
                    )
                    
                    if file_record:
                        file_record.status = "ingested"
                        file_record.error_message = "[空文件标识] 文件为空，无数据可入库"
                        await self.db.commit()
                    
                    # [*] v4.15.0修改：空文件返回成功（不是错误）
                    return {
                        "success": True,  # [*] 改为成功（空文件不是错误）
                        "message": "文件为空：无数据可入库，已标记为已处理",
                        "staged": 0,
                        "imported": 0,
                        "amount_imported": 0,
                        "quarantined": 0,
                        "skipped": True,
                        "skip_reason": "empty_file_no_data",
                        "image_extraction_started": False,
                        "normalization_report": normalization_report,
                    }
                else:
                    # [*] v4.16.0修复：有数据但入库0行的情况
                    # 在UPSERT策略下，即使所有数据都是重复的，也应该更新它们
                    # 如果imported == 0，可能是import_result格式问题，需要检查import_stats
                    # [*] v4.16.0修复：检查import_result是否存在（避免变量作用域错误）
                    if 'import_result' in locals() and isinstance(import_result, dict):
                        # 如果import_result是字典，应该已经有import_stats了
                        # 这种情况不应该到达这里，因为imported = inserted + updated
                        # 但如果到达这里，说明可能是异常情况
                        updated_count = import_result.get('updated', 0)
                        inserted_count = import_result.get('inserted', 0)
                        
                        if updated_count > 0:
                            # UPSERT策略：有更新，显示更新消息
                            logger.info(
                                f"[Ingest] [v4.16.0] UPSERT策略：所有{len(valid_rows)}行数据都已存在，"
                                f"已更新{updated_count}行（新插入{inserted_count}行）"
                            )
                            return {
                                "success": True,
                                "message": f"数据同步完成：所有{len(valid_rows)}行数据都已存在，已更新{updated_count}行",
                                "staged": updated_count + inserted_count,
                                "imported": updated_count + inserted_count,
                                "amount_imported": 0,
                                "quarantined": 0,
                                "skipped": False,  # [*] v4.16.0修复：UPSERT策略下不应该标记为跳过
                                "import_stats": {
                                    'inserted': inserted_count,
                                    'updated': updated_count,
                                    'skipped': 0,
                                },
                                "image_extraction_started": False,
                                "normalization_report": normalization_report,
                            }
                        else:
                            # 异常情况：有数据但updated和inserted都是0
                            logger.warning(
                                f"[Ingest] [v4.16.0] [WARN] 异常情况：有{len(valid_rows)}行数据，"
                                f"但imported=0, updated={updated_count}, inserted={inserted_count}"
                            )
                            return {
                                "success": True,
                                "message": f"数据同步完成：所有{len(valid_rows)}行数据都已存在，已更新0行（异常情况）",
                                "staged": 0,
                                "imported": 0,
                                "amount_imported": 0,
                                "quarantined": 0,
                                "skipped": False,
                                "import_stats": {
                                    'inserted': inserted_count,
                                    'updated': updated_count,
                                    'skipped': 0,
                                },
                                "image_extraction_started": False,
                                "normalization_report": normalization_report,
                            }
                    elif 'import_result' in locals() and import_result is not None:
                        # [*] v4.16.0修复：import_result不是字典格式（旧格式兼容，但排除None）
                        # 在UPSERT策略下，这种情况不应该发生，但为了兼容性保留
                        # 注意：只有当import_result不是None时才处理（None表示异常，已在上面处理）
                        logger.warning(
                            f"[Ingest] [v4.16.0] [WARN] import_result不是字典格式（旧格式）: "
                            f"type={type(import_result)}, value={import_result}"
                        )
                        # [*] v4.16.0更新：在UPSERT策略下，即使import_result是旧格式（整数），
                        # 也应该假设数据被更新了，而不是跳过
                        from backend.services.deduplication_fields_config import get_deduplication_strategy
                        strategy = get_deduplication_strategy(domain)
                        if strategy == 'UPSERT':
                            # UPSERT策略：假设所有数据都被更新了
                            logger.info(
                                f"[Ingest] [v4.16.0] UPSERT策略（旧格式兼容）："
                                f"所有{len(valid_rows)}行数据都已存在，假设已更新"
                            )
                            return {
                                "success": True,
                                "message": f"数据同步完成：所有{len(valid_rows)}行数据都已存在，已更新{len(valid_rows)}行",
                                "staged": len(valid_rows),
                                "imported": len(valid_rows),
                                "amount_imported": 0,
                                "quarantined": 0,
                                "skipped": False,  # [*] v4.16.0修复：UPSERT策略下不应该标记为跳过
                                "import_stats": {
                                    'inserted': 0,
                                    'updated': len(valid_rows),
                                    'skipped': 0,
                                },
                                "image_extraction_started": False,
                                "normalization_report": normalization_report,
                            }
                        else:
                            # INSERT策略：跳过重复数据（旧逻辑，保留兼容性）
                            logger.info(
                                f"[Ingest] [OK] 所有数据都已存在（重复数据），已跳过: "
                                f"准备入库{len(valid_rows)}行，实际入库0行（全部重复，这是正常情况）"
                            )
                            return {
                                "success": True,
                                "message": f"数据同步完成：所有{len(valid_rows)}行数据都已存在，已跳过重复数据",
                                "staged": 0,
                                "imported": 0,
                                "amount_imported": 0,
                                "quarantined": 0,
                                "skipped": True,
                                "import_stats": {
                                    'inserted': 0,
                                    'updated': 0,
                                    'skipped': len(valid_rows),
                                },
                                "image_extraction_started": False,
                                "normalization_report": normalization_report,
                            }
                    else:
                        # [*] v4.16.0修复：import_result不存在的情况（异常发生在batch_insert_raw_data之前）
                        logger.error(
                            f"[Ingest] [v4.16.0] [WARN] 严重错误：有{len(valid_rows)}行数据，"
                            f"但import_result未定义（可能异常发生在batch_insert_raw_data之前）"
                        )
                        return {
                            "success": False,
                            "message": f"数据入库失败：RawDataImporter异常，import_result未定义",
                            "staged": 0,
                            "imported": 0,
                            "amount_imported": 0,
                            "quarantined": 0,
                            "skipped": False,
                            "import_stats": {
                                'inserted': 0,
                                'updated': 0,
                                'skipped': 0,
                            },
                            "image_extraction_started": False,
                            "normalization_report": normalization_report,
                        }
            
            # [*] v4.16.0修复：确保import_stats被定义（避免变量作用域错误）
            if 'import_stats' not in locals():
                import_stats = {
                    'inserted': imported if 'imported' in locals() else 0,
                    'updated': 0,
                    'skipped': 0,
                }
            
            return {
                "success": True,
                "message": message if 'message' in locals() else f"数据入库成功：暂存{staged}行，入库{imported}行（DSS架构：跳过验证，所有数据入库）",
                "staged": staged,
                "imported": imported,
                "amount_imported": amount_imported,
                "quarantined": quarantined_count,  # [*] DSS架构：始终为0，保留字段以兼容API
                "skipped": False,
                "image_extraction_started": image_extraction_started,
                "normalization_report": normalization_report,
                "import_stats": import_stats,  # [*] v4.15.0新增：详细统计信息
            }
            
        except Exception as e:
            logger.error(f"[Ingest] 数据入库失败: {e}", exc_info=True)
            # [*] 修复：确保异常时回滚事务，避免"transaction has been rolled back"错误
            try:
                await self.db.rollback()
            except Exception as rollback_error:
                logger.warning(f"[Ingest] 回滚事务失败: {rollback_error}")
            raise

