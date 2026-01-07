#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
字段映射质量评分API端点（v4.13.0新增）
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pathlib import Path

from backend.models.database import get_db, get_async_db
from backend.services.excel_parser import ExcelParser
from backend.services.template_matcher import get_template_matcher
from backend.services.field_mapping_validator import calculate_mapping_quality_score
from backend.utils.api_response import success_response, error_response
from backend.utils.error_codes import ErrorCode, get_error_type
from modules.core.db import CatalogFile
from modules.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("/data-sync/mapping-quality")
async def get_mapping_quality(
    file_id: int = Query(..., description="文件ID"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    获取字段映射质量评分
    
    功能：
    - 计算字段映射质量评分（0-100分）
    - 识别映射问题
    - 提供改进建议
    """
    try:
        # 1. 获取文件记录
        catalog_file = db.execute(
            select(CatalogFile).where(CatalogFile.id == file_id)
        ).scalar_one_or_none()
        
        if not catalog_file:
            return error_response(
                code=ErrorCode.FILE_NOT_FOUND,
                message=f"文件{file_id}不存在",
                error_type=get_error_type(ErrorCode.FILE_NOT_FOUND),
                recovery_suggestion="请检查文件ID是否正确",
                status_code=404
            )
        
        # 2. 检查文件路径
        file_path = Path(catalog_file.file_path)
        if not file_path.exists():
            return error_response(
                code=ErrorCode.FILE_NOT_FOUND,
                message=f"文件不存在: {file_path}",
                error_type=get_error_type(ErrorCode.FILE_NOT_FOUND),
                recovery_suggestion="请检查文件路径",
                status_code=404
            )
        
        # 3. 获取字段映射配置（通过模板匹配器）
        template_matcher = get_template_matcher(db)
        # ⭐ v4.18.2：添加 await
        template = await template_matcher.find_best_template(
            platform=catalog_file.platform_code,
            data_domain=catalog_file.data_domain,
            granularity=catalog_file.granularity,
            sub_domain=catalog_file.sub_domain
        )
        
        if not template:
            return error_response(
                code=ErrorCode.FILE_NOT_FOUND,
                message=f"文件{file_id}没有找到匹配的字段映射模板",
                error_type=get_error_type(ErrorCode.FILE_NOT_FOUND),
                recovery_suggestion="请先创建字段映射模板",
                status_code=404
            )
        
        # 4. 读取文件数据（预览前100行用于评分）
        # ⭐ 修复：CatalogFile没有header_row字段，使用模板的header_row或默认0
        header_row = 0
        if template and hasattr(template, 'header_row') and template.header_row is not None:
            header_row = template.header_row
        
        df = ExcelParser.read_excel(
            str(file_path),
            header=header_row,
            nrows=100  # 只读取前100行用于评分
        )
        
        # 转换为字典列表
        all_rows = df.to_dict('records')
        
        # 5. 获取列名并应用字段映射
        columns = df.columns.tolist()
        # ⭐ v4.18.2：添加 await
        mappings = await template_matcher.apply_template_to_columns(template, columns)
        
        if not mappings:
            return error_response(
                code=ErrorCode.FILE_NOT_FOUND,
                message=f"文件{file_id}的字段映射配置为空",
                error_type=get_error_type(ErrorCode.FILE_NOT_FOUND),
                recovery_suggestion="请检查字段映射模板配置",
                status_code=404
            )
        
        # 6. 应用字段映射
        processed_mappings = {}
        for orig_col, mapping_info in mappings.items():
            if isinstance(mapping_info, dict):
                processed_mappings[orig_col] = mapping_info
            elif isinstance(mapping_info, str):
                processed_mappings[orig_col] = {"standard_field": mapping_info, "confidence": 0.95}
        
        mapped_rows = []
        for row in all_rows:
            mapped_row = {}
            for orig_col, value in row.items():
                mapping_info = processed_mappings.get(orig_col)
                if mapping_info and isinstance(mapping_info, dict):
                    standard_field = mapping_info.get("standard_field")
                    if standard_field and standard_field != "未映射":
                        mapped_row[standard_field] = value
                    else:
                        mapped_row[orig_col] = value
                else:
                    mapped_row[orig_col] = value
            mapped_rows.append(mapped_row)
        
        # 7. 计算质量评分
        result = calculate_mapping_quality_score(
            mapped_rows,
            catalog_file.data_domain or "products",
            processed_mappings
        )
        
        if not result.get("success"):
            return error_response(
                code=ErrorCode.DATABASE_QUERY_ERROR,
                message="计算字段映射质量评分失败",
                error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
                detail=result.get("error"),
                recovery_suggestion="请检查文件数据和字段映射配置",
                status_code=500
            )
        
        return success_response(
            data=result,
            message="字段映射质量评分完成"
        )
    
    except Exception as e:
        logger.error(f"[API] 获取字段映射质量评分失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取字段映射质量评分失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查文件ID和字段映射配置",
            status_code=500
        )
