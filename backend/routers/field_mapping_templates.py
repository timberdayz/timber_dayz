#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
字段映射模板管理路由
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import get_async_db
from backend.schemas.field_mapping_template import (
    DefaultDeduplicationFieldsData,
    DefaultDeduplicationFieldsResponse,
    DetectHeaderChangesRequest,
    DetectHeaderChangesResponse,
    HeaderChangesPayload,
    TemplateApplyConfig,
    TemplateApplyRequest,
    TemplateApplyResponse,
    TemplateContextSummary,
    TemplateDeleteData,
    TemplateDeleteResponse,
    TemplateListData,
    TemplateListResponse,
    TemplateSaveRequest,
    TemplateSaveResponse,
    TemplateUpdateContextData,
    TemplateUpdateContextResponse,
)
from backend.services.field_mapping_template_service import get_template_service
from backend.utils.api_response import error_response
from backend.utils.error_codes import ErrorCode, get_error_type
from modules.core.db import FieldMappingTemplate
from modules.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()
DATE_TARGET_FIELDS = {"metric_date", "period_start_date", "period_end_date"}
FILE_DATE_SOURCE_COLUMNS = {"__file_date_from__", "__file_date_to__"}


async def _load_file_update_preview(
    db: AsyncSession,
    file_id: int,
    header_row: int,
) -> Dict[str, Any]:
    """Load current file header/sample context for template update review."""
    import asyncio

    from backend.services.excel_parser import ExcelParser
    from modules.core.db import CatalogFile
    from modules.core.path_manager import to_absolute_path

    file_result = await db.execute(select(CatalogFile).where(CatalogFile.id == file_id))
    catalog_file = file_result.scalar_one_or_none()

    if not catalog_file:
        raise ValueError(f"file_id={file_id} 对应的文件不存在")

    file_path = to_absolute_path(catalog_file.file_path)
    loop = asyncio.get_running_loop()
    file_exists = await loop.run_in_executor(None, lambda: file_path.exists())
    if not file_exists:
        raise ValueError(f"文件不存在: {catalog_file.file_path}")

    df = await loop.run_in_executor(None, ExcelParser.read_excel, file_path, header_row, 50)
    df.columns = [str(col).strip() for col in df.columns]
    df = df.dropna(how="all").fillna("")

    header_columns = df.columns.tolist()
    sample_data: Dict[str, str] = {}
    if len(df) > 0:
        first_row = df.iloc[0]
        for col in header_columns:
            sample_data[col] = str(first_row[col]) if first_row[col] is not None else ""

    return {
        "file": {
            "id": catalog_file.id,
            "file_name": catalog_file.file_name,
            "platform": catalog_file.platform_code,
            "domain": catalog_file.data_domain,
            "granularity": catalog_file.granularity,
            "sub_domain": catalog_file.sub_domain,
        },
        "header_columns": header_columns,
        "sample_data": sample_data,
        "preview_data": df.head(20).to_dict("records"),
    }


def _split_existing_deduplication_fields(
    existing_fields: list[str],
    current_header_columns: list[str],
) -> tuple[list[str], list[str]]:
    current_lookup = {str(field).lower(): field for field in current_header_columns}
    available: list[str] = []
    missing: list[str] = []

    for field in existing_fields:
        if str(field).lower() in current_lookup:
            available.append(field)
        else:
            missing.append(field)

    return available, missing


def _normalize_template_headers_for_domain(
    data_domain: str,
    header_columns: list[str],
) -> list[str]:
    # 模板存储必须保留原始表头，避免保存阶段污染 header_columns。
    # 货币/地区代码归一化只用于比较、匹配和同步入库，不用于模板本体。
    return list(header_columns)

def _extract_standard_field(mapping_info: Any) -> Optional[str]:
    if isinstance(mapping_info, dict):
        standard_field = mapping_info.get("standard_field")
        if isinstance(standard_field, str):
            return standard_field.strip()
        standard_value = mapping_info.get("standard")
        if isinstance(standard_value, str):
            return standard_value.strip()
        return None
    if isinstance(mapping_info, str):
        return mapping_info.strip()
    return None


def _normalize_field_parse_rules(request_rules: list[Any] | None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for rule in request_rules or []:
        if hasattr(rule, "model_dump"):
            normalized.append(rule.model_dump(exclude_none=True))
        elif isinstance(rule, dict):
            normalized.append({k: v for k, v in rule.items() if v is not None})
    return normalized


def _validate_field_parse_rules(
    mappings: dict[str, Any] | None,
    header_columns: list[str],
    field_parse_rules: list[dict[str, Any]],
) -> None:
    date_targets = {
        standard_field
        for standard_field in (
            _extract_standard_field(mapping_info)
            for mapping_info in (mappings or {}).values()
        )
        if standard_field in DATE_TARGET_FIELDS
    }
    if date_targets and not field_parse_rules:
        raise ValueError(
            "field_parse_rules is required when mappings include date targets: "
            + ", ".join(sorted(date_targets))
        )

    header_lookup = {str(column).lower(): str(column) for column in header_columns}
    rules_by_target = {
        str(rule.get("target_field", "")).strip(): rule
        for rule in field_parse_rules
        if str(rule.get("target_field", "")).strip()
    }
    for target_field, rule in rules_by_target.items():
        source_column = str(rule.get("source_column", "")).strip()
        if not source_column:
            raise ValueError(f"field_parse_rules for {target_field} must define source_column")
        if source_column not in FILE_DATE_SOURCE_COLUMNS and source_column.lower() not in header_lookup:
            raise ValueError(
                f"field_parse_rules for {target_field} references unknown source_column: {source_column}"
            )
        value_kind = str(rule.get("value_kind", "")).strip()
        if value_kind not in {"single_date", "date_range"}:
            raise ValueError(
                f"field_parse_rules for {target_field} must define value_kind as single_date or date_range"
            )
        date_format = str(rule.get("date_format", "")).strip()
        if not date_format:
            raise ValueError(f"field_parse_rules for {target_field} must define date_format")
        if value_kind == "date_range":
            range_pick = str(rule.get("range_pick", "")).strip()
            if range_pick not in {"start", "end"}:
                raise ValueError(
                    f"field_parse_rules for {target_field} must define range_pick as start or end"
                )

    if not date_targets:
        return

    missing_targets = sorted(target for target in date_targets if target not in rules_by_target)
    if missing_targets:
        raise ValueError(
            "field_parse_rules is missing required date targets: " + ", ".join(missing_targets)
        )

    for target_field in sorted(date_targets):
        if target_field not in rules_by_target:
            raise ValueError(
                "field_parse_rules is missing required date targets: " + ", ".join(missing_targets)
            )


@router.post("/templates/save", response_model=TemplateSaveResponse)
async def save_mapping_template(
    request: TemplateSaveRequest,
    db: AsyncSession = Depends(get_async_db),
):
    """保存模板，并将更新语义统一为创建新版本。"""
    try:
        template_service = get_template_service(db)

        if not request.platform:
            raise ValueError("platform参数必填")
        if not request.data_domain:
            raise ValueError("data_domain参数必填")

        header_columns = request.header_columns
        if not header_columns and request.mappings:
            mappings = request.mappings
            if isinstance(mappings, dict):
                header_columns = list(mappings.keys())
            else:
                header_columns = []

        if not header_columns:
            raise ValueError("header_columns参数必填(DSS架构:保存原始表头字段列表)")

        # 模板本体必须保留原始表头，避免保存阶段污染 header_columns。
        # 货币代码/地区代码归一化只用于“比较/匹配”逻辑，不用于模板存储。
        header_columns = list(header_columns)
        header_row = request.header_row
        field_parse_rules = _normalize_field_parse_rules(request.field_parse_rules)
        if not isinstance(header_row, int) or header_row < 0 or header_row > 100:
            raise ValueError(f"header_row必须在0-100之间, 当前值: {header_row}")

        deduplication_fields = request.deduplication_fields
        if deduplication_fields is None:
            from backend.services.deduplication_fields_config import get_default_deduplication_fields

            deduplication_fields = get_default_deduplication_fields(
                data_domain=request.data_domain,
                sub_domain=request.sub_domain,
            )
            logger.warning(
                f"[Template] [WARN] 保存模板时未提供deduplication_fields, 使用默认配置: {deduplication_fields}"
            )
        elif not isinstance(deduplication_fields, list):
            raise ValueError(f"deduplication_fields必须是列表, 当前值: {deduplication_fields}")
        elif len(deduplication_fields) == 0:
            raise ValueError("deduplication_fields不能为空列表, 至少需要选择1个核心字段")
        elif not all(isinstance(field, str) for field in deduplication_fields):
            raise ValueError("deduplication_fields列表中的元素必须是字符串")

        if header_columns:
            missing_fields = []
            for field in deduplication_fields:
                found = False
                for col in header_columns:
                    if col == field or col.lower() == field.lower():
                        found = True
                        break
                if not found:
                    missing_fields.append(field)

            if missing_fields:
                logger.warning(
                    f"[Template] [WARN] 以下核心字段不在表头中: {missing_fields}, 表头字段: {header_columns[:10]}..."
                )

        _validate_field_parse_rules(
            mappings=request.mappings,
            header_columns=header_columns,
            field_parse_rules=field_parse_rules,
        )

        save_result = await template_service.save_template(
            platform=request.platform,
            data_domain=request.data_domain,
            header_columns=header_columns,
            granularity=request.granularity,
            account=request.account,
            template_name=request.template_name,
            created_by=request.created_by,
            header_row=header_row,
            sub_domain=request.sub_domain,
            sheet_name=request.sheet_name,
            encoding=request.encoding,
            deduplication_fields=deduplication_fields,
            field_parse_rules=field_parse_rules,
            save_mode=request.save_mode,
            base_template_id=request.base_template_id,
        )

        logger.info(
            f"[Template] 保存成功: platform={request.platform}, domain={request.data_domain}, "
            f"template_id={save_result['template_id']}"
        )

        return TemplateSaveResponse(
            success=True,
            data=save_result,
            message="模板保存成功",
        )
    except ValueError as exc:
        logger.error(f"保存模板失败(参数错误): {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.PARAMETER_INVALID,
            message=f"保存模板失败: {str(exc)}",
            error_type=get_error_type(ErrorCode.PARAMETER_INVALID),
            detail=str(exc),
            recovery_suggestion="请检查请求参数是否正确",
            status_code=400,
        )
    except Exception as exc:
        logger.error(f"保存模板失败: {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message=f"保存模板失败: {str(exc)}",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(exc),
            recovery_suggestion="请检查数据库连接和权限, 或联系系统管理员",
            status_code=500,
        )


@router.get(
    "/templates/default-deduplication-fields",
    response_model=DefaultDeduplicationFieldsResponse,
)
async def get_default_deduplication_fields(
    data_domain: str = Query(..., description="数据域(如:orders, products, inventory)"),
    sub_domain: Optional[str] = Query(None, description="子类型(可选,如:ai_assistant)"),
    db: AsyncSession = Depends(get_async_db),
):
    """获取默认核心字段推荐。"""
    try:
        from backend.services.deduplication_fields_config import (
            get_default_deduplication_fields as get_default_deduplication_fields_config,
        )

        fields = get_default_deduplication_fields_config(data_domain, sub_domain)
        descriptions = {
            "orders": "订单数据的默认核心字段",
            "products": "产品数据的默认核心字段",
            "inventory": "库存数据的默认核心字段",
            "traffic": "流量数据的默认核心字段",
            "services": "服务数据的默认核心字段",
            "analytics": "分析数据的默认核心字段",
        }
        reasons = {
            "orders": "这些字段能够唯一标识订单级数据",
            "products": "这些字段能够唯一标识产品级数据",
            "inventory": "这些字段能够唯一标识库存级数据",
            "traffic": "这些字段能够唯一标识流量级数据",
            "services": "这些字段能够唯一标识服务级数据",
            "analytics": "这些字段能够唯一标识分析级数据",
        }

        description = descriptions.get(data_domain, f"{data_domain}数据的默认核心字段")
        if sub_domain:
            description = f"{sub_domain}子类型的{description}"

        return DefaultDeduplicationFieldsResponse(
            success=True,
            data=DefaultDeduplicationFieldsData(
                fields=fields,
                description=description,
                reason=reasons.get(data_domain, "这些字段能够唯一标识每行数据"),
            ),
            message="获取默认核心字段推荐成功",
        )
    except Exception as exc:
        logger.error(f"获取默认核心字段推荐失败: {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message=f"获取默认核心字段推荐失败: {str(exc)}",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(exc),
            recovery_suggestion="请检查数据域参数是否正确",
            status_code=500,
        )


@router.get(
    "/templates/{template_id}/update-context",
    response_model=TemplateUpdateContextResponse,
)
async def get_template_update_context(
    template_id: int,
    mode: str = Query("with-sample", description="更新模式(core-only 或 with-sample)"),
    file_id: Optional[int] = Query(None, description="用于更新模板的候选文件ID"),
    db: AsyncSession = Depends(get_async_db),
):
    """Return template update context for the dedicated update workbench."""
    from backend.services.deduplication_fields_config import (
        get_default_deduplication_fields as get_default_deduplication_fields_config,
    )
    from backend.services.template_matcher import get_template_matcher

    try:
        template_result = await db.execute(
            select(FieldMappingTemplate).where(FieldMappingTemplate.id == template_id)
        )
        template = template_result.scalar_one_or_none()
        if not template:
            return error_response(
                code=ErrorCode.NOT_FOUND,
                message="模板不存在",
                error_type=get_error_type(ErrorCode.NOT_FOUND),
                detail=f"模板ID {template_id} 不存在",
                recovery_suggestion="请检查模板ID是否正确",
                status_code=404,
            )

        template_header_columns = template.header_columns or []
        template_deduplication_fields = template.deduplication_fields or []
        response_data: Dict[str, Any] = {
            "template": TemplateContextSummary(
                id=template.id,
                platform=template.platform,
                data_domain=template.data_domain,
                granularity=template.granularity,
                sub_domain=template.sub_domain,
                header_row=template.header_row or 0,
                template_name=template.template_name,
                version=template.version,
                status=template.status,
                field_count=template.field_count or len(template_header_columns),
                deduplication_fields=template_deduplication_fields,
                field_parse_rules=template.field_parse_rules or [],
            ).model_dump(),
            "template_header_columns": template_header_columns,
            "current_file": None,
            "current_header_columns": [],
            "sample_data": {},
            "preview_data": [],
            "update_mode": mode,
            "header_source": "template" if mode == "core-only" else "sample-file",
            "header_changes": {
                "detected": False,
                "added_fields": [],
                "removed_fields": [],
                "match_rate": 100.0,
                "is_exact_match": True,
                "template_columns": template_header_columns,
                "current_columns": template_header_columns,
            },
            "match_rate": 100.0,
            "added_fields": [],
            "removed_fields": [],
            "existing_deduplication_fields_available": [],
            "existing_deduplication_fields_missing": [],
            "recommended_deduplication_fields": [],
            "update_semantics": "new_version",
            "recommended_save_mode": "new_version",
        }

        default_fields = get_default_deduplication_fields_config(
            template.data_domain,
            template.sub_domain,
        )

        if mode == "core-only":
            available_fields, missing_fields = _split_existing_deduplication_fields(
                template_deduplication_fields,
                template_header_columns,
            )
            recommended_fields = [
                field
                for field in default_fields
                if any(str(field).lower() == str(col).lower() for col in template_header_columns)
            ]
            response_data.update(
                {
                    "current_header_columns": template_header_columns,
                    "header_changes": {
                        "detected": False,
                        "added_fields": [],
                        "removed_fields": [],
                        "match_rate": 100.0,
                        "is_exact_match": True,
                        "template_columns": template_header_columns,
                        "current_columns": template_header_columns,
                    },
                    "existing_deduplication_fields_available": available_fields,
                    "existing_deduplication_fields_missing": missing_fields,
                    "recommended_deduplication_fields": recommended_fields,
                }
            )
        elif file_id is not None:
            file_preview = await _load_file_update_preview(db, file_id, template.header_row or 0)
            current_header_columns = file_preview["header_columns"]
            matcher = get_template_matcher(db)
            header_changes = await matcher.detect_header_changes(
                template_id,
                current_header_columns,
            )
            current_lookup = {str(field).lower(): field for field in current_header_columns}
            added_fields = header_changes.get("added_fields", [])
            removed_fields = header_changes.get("removed_fields", [])
            available_fields, missing_fields = _split_existing_deduplication_fields(
                template_deduplication_fields,
                current_header_columns,
            )
            recommended_fields = [
                field for field in default_fields if str(field).lower() in current_lookup
            ]
            response_data.update(
                {
                    "current_file": file_preview["file"],
                    "current_header_columns": current_header_columns,
                    "sample_data": file_preview.get("sample_data", {}),
                    "preview_data": file_preview.get("preview_data", []),
                    "header_changes": header_changes,
                    "match_rate": header_changes.get("match_rate", 0.0),
                    "added_fields": added_fields,
                    "removed_fields": removed_fields,
                    "existing_deduplication_fields_available": available_fields,
                    "existing_deduplication_fields_missing": missing_fields,
                    "recommended_deduplication_fields": recommended_fields,
                }
            )

        return TemplateUpdateContextResponse(
            success=True,
            data=TemplateUpdateContextData(**response_data),
            message="获取模板更新上下文成功",
        )
    except ValueError as exc:
        logger.error(f"获取模板更新上下文失败(参数错误): {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message="获取模板更新上下文失败",
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            detail=str(exc),
            recovery_suggestion="请检查模板和候选文件是否存在",
            status_code=400,
        )
    except Exception as exc:
        logger.error(f"获取模板更新上下文失败: {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取模板更新上下文失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(exc),
            recovery_suggestion="请检查数据库连接或候选文件状态",
            status_code=500,
        )


@router.get("/templates/list", response_model=TemplateListResponse)
async def list_mapping_templates(
    platform: Optional[str] = Query(None, description="平台代码"),
    data_domain: Optional[str] = Query(None, description="数据域"),
    db: AsyncSession = Depends(get_async_db),
):
    """列出模板。"""
    try:
        template_service = get_template_service(db)
        templates = await template_service.list_templates(platform or None, data_domain or None)
        return TemplateListResponse(
            success=True,
            data=TemplateListData(templates=templates, count=len(templates)),
        )
    except Exception as exc:
        logger.error(f"列出模板失败: {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="列出模板失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(exc),
            recovery_suggestion="请检查数据库连接和查询参数, 或联系系统管理员",
            status_code=500,
        )


@router.delete("/templates/{template_id}", response_model=TemplateDeleteResponse)
async def delete_mapping_template(
    template_id: int,
    db: AsyncSession = Depends(get_async_db),
):
    """删除模板。"""
    try:
        template_service = get_template_service(db)
        success = await template_service.delete_template(template_id)
        if success:
            return TemplateDeleteResponse(
                success=True,
                data=TemplateDeleteData(template_id=template_id),
                message="模板删除成功",
            )

        return error_response(
            code=ErrorCode.NOT_FOUND,
            message="模板不存在",
            error_type=get_error_type(ErrorCode.NOT_FOUND),
            detail=f"模板ID {template_id} 不存在",
            recovery_suggestion="请检查模板ID是否正确",
            status_code=404,
        )
    except Exception as exc:
        logger.error(f"删除模板失败: {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="删除模板失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(exc),
            recovery_suggestion="请检查数据库连接和权限, 或联系系统管理员",
            status_code=500,
        )


@router.post("/templates/apply", response_model=TemplateApplyResponse)
async def apply_mapping_template(
    request: TemplateApplyRequest,
    db: AsyncSession = Depends(get_async_db),
):
    """应用模板。"""
    try:
        template_service = get_template_service(db)
        result = await template_service.apply_template(
            template_id=request.template_id,
            current_columns=request.columns,
        )

        from backend.services.template_matcher import get_template_matcher

        matcher = get_template_matcher(db)
        config = await matcher.get_template_config(request.template_id)
        header_changes = await matcher.detect_header_changes(
            template_id=request.template_id,
            current_columns=request.columns,
        )

        return TemplateApplyResponse(
            success=True,
            mappings={},
            matched=result["matched"],
            unmatched=result["unmatched"],
            unmatched_columns=result["unmatched_columns"],
            match_rate=result["match_rate"],
            config=TemplateApplyConfig(
                header_row=config.get("header_row", 0),
                sub_domain=config.get("sub_domain"),
                sheet_name=config.get("sheet_name"),
                encoding=config.get("encoding", "utf-8"),
            ),
            template_name=config.get("template_name"),
            template_version=config.get("version"),
            header_columns=config.get("header_columns", []),
            header_changes=HeaderChangesPayload(**header_changes),
        )
    except Exception as exc:
        logger.error(f"应用模板失败: {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="应用模板失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(exc),
            recovery_suggestion="请检查数据库连接和权限, 或联系系统管理员",
            status_code=500,
        )


@router.post(
    "/templates/detect-header-changes",
    response_model=DetectHeaderChangesResponse,
)
async def detect_header_changes(
    request: DetectHeaderChangesRequest,
    db: AsyncSession = Depends(get_async_db),
):
    """检测表头变化。"""
    try:
        from backend.services.template_matcher import get_template_matcher

        matcher = get_template_matcher(db)
        header_changes = await matcher.detect_header_changes(
            template_id=request.template_id,
            current_columns=request.current_columns,
        )

        return DetectHeaderChangesResponse(
            success=True,
            header_changes=HeaderChangesPayload(**header_changes),
        )
    except Exception as exc:
        logger.error(f"检测表头变化失败: {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="检测表头变化失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(exc),
            recovery_suggestion="请检查数据库连接和权限, 或联系系统管理员",
            status_code=500,
        )
