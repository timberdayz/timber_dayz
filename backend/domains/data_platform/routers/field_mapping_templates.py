#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
字段映射模板管理路由
"""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import get_async_db
from backend.schemas.field_mapping_template import (
    DefaultDeduplicationFieldsData,
    DefaultDeduplicationFieldsResponse,
    DetectHeaderChangesRequest,
    DetectHeaderChangesResponse,
    HashPolicyPreviewData,
    HashPolicyPreviewRequest,
    HashPolicyPreviewResponse,
    HeaderChangesPayload,
    TemplateApplyConfig,
    TemplateApplyRequest,
    TemplateApplyResponse,
    TemplateContextSummary,
    TemplateDeleteData,
    TemplateDeleteResponse,
    TemplateFamilyListData,
    TemplateFamilyListResponse,
    TemplateFamilyVersionsData,
    TemplateFamilyVersionsResponse,
    TemplateListData,
    TemplateListResponse,
    TemplateResolveData,
    TemplateResolveRequest,
    TemplateResolveResponse,
    TemplateSaveRequest,
    TemplateSaveResponse,
    TemplateUpdateContextData,
    TemplateUpdateContextResponse,
    TemplateUpdatePreviewData,
    TemplateUpdatePreviewResponse,
    TemplateUpdateBindingsData,
    TemplateUpdateBindingsResponse,
    TemplateVariantCreateContextData,
    TemplateVariantCreateContextResponse,
    TemplateVersionVariantsData,
    TemplateVersionVariantsResponse,
)
from backend.services.template_family_service import (
    get_template_family_service,
    get_template_resolver,
)
from backend.services.field_mapping_template_service import get_template_service
from backend.services.semantic_field_registry import (
    get_semantic_aliases,
    get_semantic_requirements,
    infer_semantic_key,
    is_canonical_semantic_key,
    normalize_semantic_key,
)
from backend.services.semantic_hash_policy_service import SemanticHashPolicyService
from backend.services.semantic_alias_registry import SemanticAliasRegistryService
from backend.services.template_save_readiness_service import (
    TemplateSaveReadinessService,
    normalize_deduplication_fields_for_template as service_normalize_deduplication_fields_for_template,
    sync_hash_participation_from_deduplication_fields as service_sync_hash_participation_from_deduplication_fields,
    validate_deduplication_fields_against_bindings as service_validate_deduplication_fields_against_bindings,
)
from backend.services.template_semantic_coverage_checker import TemplateSemanticCoverageChecker
from backend.utils.api_response import error_response
from backend.utils.error_codes import ErrorCode, get_error_type
from modules.core.db import FieldMappingTemplate
from modules.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()
DATE_TARGET_FIELDS = {
    "metric_date",
    "period_start_date",
    "period_end_date",
    "period_start_time",
    "period_end_time",
}
FILE_DATE_SOURCE_COLUMNS = {"__file_date_from__", "__file_date_to__"}
DATE_PARSE_VALUE_KINDS = {
    "single_date",
    "single_datetime",
    "time_of_day",
    "date_range",
    "datetime_range",
    "time_range",
}
DATE_PARSE_RANGE_VALUE_KINDS = {"date_range", "datetime_range", "time_range"}
SYSTEM_HASH_SCOPE_KEYS = {"platform_code", "shop_id", "data_domain", "granularity", "sub_domain"}


class TemplateFamilyHashKeyMismatch(ValueError):
    def __init__(self, message: str, payload: dict[str, Any]) -> None:
        super().__init__(message)
        self.payload = payload


def _normalize_dimension_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in {"n/a", "na", "none", "null"}:
        return None
    return text or None


def _binding_lookup_by_source(header_bindings: list[dict[str, Any]] | None) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for binding in header_bindings or []:
        if binding.get("semantic_review_status") != "confirmed_semantic":
            continue
        semantic_key = normalize_semantic_key(
            binding.get("semantic_key") or binding.get("semantic_role") or binding.get("display_name")
        )
        if not semantic_key or not is_canonical_semantic_key(semantic_key):
            continue
        for source in (
            binding.get("raw_name"),
            binding.get("source_header"),
            binding.get("display_name"),
        ):
            source_text = str(source or "").strip()
            if source_text:
                lookup[source_text.lower()] = semantic_key
    return lookup


def _canonical_user_hash_key_set(
    fields: list[str] | None,
    header_bindings: list[dict[str, Any]] | None = None,
) -> set[str]:
    keys: set[str] = set()
    binding_lookup = _binding_lookup_by_source(header_bindings)
    for field in fields or []:
        field_text = str(field or "").strip()
        semantic_key = normalize_semantic_key(field_text)
        if not semantic_key or not is_canonical_semantic_key(semantic_key):
            semantic_key = binding_lookup.get(field_text.lower())
        if not semantic_key or semantic_key in SYSTEM_HASH_SCOPE_KEYS:
            continue
        if is_canonical_semantic_key(semantic_key):
            keys.add(semantic_key)
    return keys


def _hash_source_by_semantic_key(
    fields: list[str] | None,
    header_bindings: list[dict[str, Any]] | None,
) -> dict[str, str]:
    binding_lookup = _binding_lookup_by_source(header_bindings)
    source_by_key: dict[str, str] = {}
    for field in fields or []:
        field_text = str(field or "").strip()
        semantic_key = normalize_semantic_key(field_text)
        if not semantic_key or not is_canonical_semantic_key(semantic_key):
            semantic_key = binding_lookup.get(field_text.lower())
        if semantic_key and semantic_key not in SYSTEM_HASH_SCOPE_KEYS and semantic_key not in source_by_key:
            source_by_key[semantic_key] = field_text
    for binding in header_bindings or []:
        semantic_key = normalize_semantic_key(binding.get("semantic_key"))
        if not semantic_key or semantic_key in source_by_key:
            continue
        raw_name = str(binding.get("raw_name") or binding.get("source_header") or binding.get("display_name") or "").strip()
        if raw_name:
            source_by_key[semantic_key] = raw_name
    return source_by_key


def _family_hash_change_payload(
    *,
    existing_template: FieldMappingTemplate,
    existing_keys: set[str],
    current_keys: set[str],
    current_deduplication_fields: list[str],
    current_header_bindings: list[dict[str, Any]],
    data_domain: str,
) -> dict[str, Any]:
    existing_sources = _hash_source_by_semantic_key(
        existing_template.deduplication_fields or [],
        existing_template.header_bindings or [],
    )
    current_sources = _hash_source_by_semantic_key(
        current_deduplication_fields,
        current_header_bindings,
    )
    source_field_changes = []
    for semantic_key in sorted(existing_keys & current_keys):
        family_raw_name = existing_sources.get(semantic_key)
        current_raw_name = current_sources.get(semantic_key)
        if family_raw_name and current_raw_name and family_raw_name != current_raw_name:
            source_field_changes.append(
                {
                    "semantic_key": semantic_key,
                    "family_raw_name": family_raw_name,
                    "current_raw_name": current_raw_name,
                }
            )
    semantic_hash_key_changes = [
        {"change": "missing", "semantic_key": key}
        for key in sorted(existing_keys - current_keys)
    ] + [
        {"change": "added", "semantic_key": key}
        for key in sorted(current_keys - existing_keys)
    ]
    suggested_action = "save_allowed"
    if semantic_hash_key_changes:
        suggested_action = (
            "migrate_family_hash_keys"
            if data_domain == "products" and "product_name" in existing_keys and "product_id" in current_keys
            else "create_new_family"
        )
    return {
        "family_hash_keys": sorted(existing_keys),
        "current_hash_keys": sorted(current_keys),
        "source_field_changes": source_field_changes,
        "semantic_hash_key_changes": semantic_hash_key_changes,
        "suggested_action": suggested_action,
    }


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
        "header_bindings": _normalize_header_bindings(None, header_columns, sample_data),
        "sample_data": sample_data,
        "preview_data": df.head(20).to_dict("records"),
    }


async def _load_file_update_summary(
    db: AsyncSession,
    file_id: int,
    header_row: int,
) -> Dict[str, Any]:
    """Load lightweight header context for first-paint template update review."""
    import asyncio

    from backend.services.excel_parser import ExcelParser
    from modules.core.db import CatalogFile
    from modules.core.path_manager import to_absolute_path

    file_result = await db.execute(select(CatalogFile).where(CatalogFile.id == file_id))
    catalog_file = file_result.scalar_one_or_none()

    if not catalog_file:
        raise ValueError(f"file_id={file_id} 瀵瑰簲鐨勬枃浠朵笉瀛樺湪")

    file_path = to_absolute_path(catalog_file.file_path)
    loop = asyncio.get_running_loop()
    file_exists = await loop.run_in_executor(None, lambda: file_path.exists())
    if not file_exists:
        raise ValueError(f"鏂囦欢涓嶅瓨鍦? {catalog_file.file_path}")

    # First-paint only needs headers plus one sample row for lightweight semantic hints.
    df = await loop.run_in_executor(None, ExcelParser.read_excel, file_path, header_row, 1)
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
        "header_bindings": _normalize_header_bindings(None, header_columns, sample_data),
    }


def _filter_bindings_for_manual_review(
    header_bindings: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    bindings = list(header_bindings or [])
    if not bindings:
        return []

    semantic_counts: dict[str, int] = {}
    for binding in bindings:
        semantic_key = normalize_semantic_key(binding.get("semantic_key"))
        if semantic_key:
            semantic_counts[semantic_key] = semantic_counts.get(semantic_key, 0) + 1

    filtered: list[dict[str, Any]] = []
    for binding in bindings:
        semantic_key = normalize_semantic_key(binding.get("semantic_key"))
        review_status = str(binding.get("semantic_review_status") or "").strip()
        if not review_status:
            review_status = "confirmed_semantic" if semantic_key else "pending"
        has_conflict = bool(semantic_key and semantic_counts.get(semantic_key, 0) > 1)
        is_key_review_candidate = bool(
            binding.get("required")
            or binding.get("hash_participates")
            or binding.get("hash_eligible")
            or semantic_key
        )
        if review_status == "confirmed_non_semantic" and not has_conflict:
            continue
        if (review_status == "pending" and is_key_review_candidate) or has_conflict:
            filtered.append({**binding, "semantic_review_status": review_status})
    return filtered


def _split_existing_deduplication_fields(
    existing_fields: list[str],
    current_header_columns: list[str],
    current_header_bindings: list[dict[str, Any]] | None = None,
    existing_header_bindings: list[dict[str, Any]] | None = None,
    *,
    data_domain: str = "",
    granularity: Optional[str] = None,
    sub_domain: Optional[str] = None,
) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    current_lookup = {str(field).strip().lower(): field for field in current_header_columns}
    current_bindings = list(current_header_bindings or [])
    existing_bindings = list(existing_header_bindings or [])

    def binding_semantic_key(binding: dict[str, Any] | None) -> Optional[str]:
        if not binding:
            return None
        semantic_key = normalize_semantic_key(
            binding.get("semantic_key") or binding.get("semantic_role") or binding.get("display_name")
        )
        return semantic_key if semantic_key and is_canonical_semantic_key(semantic_key) else None

    def binding_field_name(binding: dict[str, Any] | None) -> Optional[str]:
        if not binding:
            return None
        for key in ("raw_name", "source_header", "display_name"):
            value = str(binding.get(key) or "").strip()
            if value:
                return value
        return None

    def raw_binding_lookup(bindings: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        lookup: dict[str, dict[str, Any]] = {}
        for binding in bindings:
            for key in ("raw_name", "source_header", "display_name"):
                value = str(binding.get(key) or "").strip()
                if value:
                    lookup.setdefault(value.lower(), binding)
        return lookup

    existing_binding_by_raw = raw_binding_lookup(existing_bindings)
    current_binding_by_raw = raw_binding_lookup(current_bindings)
    current_binding_by_semantic: dict[str, dict[str, Any]] = {}
    for binding in current_bindings:
        semantic_key = binding_semantic_key(binding)
        if semantic_key:
            current_binding_by_semantic.setdefault(semantic_key, binding)

    available: list[str] = []
    missing: list[str] = []
    matches: list[dict[str, Any]] = []
    seen_available: set[str] = set()
    hash_policy = SemanticHashPolicyService()

    for field in existing_fields:
        requested_field = str(field).strip()
        requested_key = requested_field.lower()
        old_binding = existing_binding_by_raw.get(requested_key)
        old_semantic_key = binding_semantic_key(old_binding)
        normalized_semantic_key = normalize_semantic_key(requested_field)
        if not old_semantic_key and normalized_semantic_key and is_canonical_semantic_key(normalized_semantic_key):
            old_semantic_key = normalized_semantic_key

        current_binding = current_binding_by_semantic.get(old_semantic_key or "")
        current_field = binding_field_name(current_binding)
        match_type = "semantic_key" if current_binding and old_semantic_key else ""

        if not current_binding and requested_key in current_lookup:
            current_field = current_lookup[requested_key]
            current_binding = current_binding_by_raw.get(requested_key)
            current_semantic_key = binding_semantic_key(current_binding)
            if current_semantic_key:
                old_semantic_key = old_semantic_key or current_semantic_key
            match_type = "raw_header"

        if current_field:
            hash_option = (
                hash_policy.evaluate_option(
                    data_domain=data_domain,
                    granularity=granularity,
                    sub_domain=sub_domain,
                    semantic_key=old_semantic_key,
                )
                if old_semantic_key
                else None
            )
            hash_eligible = bool(hash_option and hash_option.eligible)
            if hash_eligible:
                status = "matched_hashable"
                available_field = old_semantic_key or requested_field
                if available_field.lower() not in seen_available:
                    seen_available.add(available_field.lower())
                    available.append(available_field)
            elif old_semantic_key:
                status = "matched_non_hashable"
            else:
                status = "matched_raw_header"
                if requested_field.lower() not in seen_available:
                    seen_available.add(requested_field.lower())
                    available.append(requested_field)

            matches.append(
                {
                    "requested_field": requested_field,
                    "semantic_key": old_semantic_key,
                    "current_field": current_field,
                    "match_type": match_type,
                    "hash_eligible": hash_eligible,
                    "status": status,
                }
            )
        else:
            missing.append(requested_field)
            matches.append(
                {
                    "requested_field": requested_field,
                    "semantic_key": old_semantic_key,
                    "current_field": None,
                    "match_type": "missing",
                    "hash_eligible": False,
                    "status": "missing",
                }
            )

    return available, missing, matches


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


def _looks_like_unnamed_header(column_name: str) -> bool:
    return str(column_name).strip().lower().startswith("unnamed:")


def _looks_like_date_value(raw_value: Any) -> bool:
    text = str(raw_value or "").strip()
    if not text:
        return False
    candidates = [text, text.replace("/", "-")]
    for candidate in candidates:
        iso_candidate = candidate.replace("Z", "+00:00")
        try:
            datetime.fromisoformat(iso_candidate)
            return True
        except ValueError:
            pass
        if re.match(r"^\d{4}-\d{1,2}-\d{1,2}( \d{1,2}:\d{2}(:\d{2})?)?$", candidate):
            return True
    return False


def _looks_like_number_value(raw_value: Any) -> bool:
    text = str(raw_value or "").strip()
    if not text:
        return False
    try:
        float(text.replace(",", ""))
        return True
    except ValueError:
        return False


def _normalize_header_bindings(
    request_bindings: list[Any] | None,
    header_columns: list[str],
    sample_data: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    sample_data = sample_data or {}
    requested_by_raw: dict[str, dict[str, Any]] = {}
    for binding in request_bindings or []:
        if hasattr(binding, "model_dump"):
            binding_dict = binding.model_dump(exclude_none=True)
        elif isinstance(binding, dict):
            binding_dict = {k: v for k, v in binding.items() if v is not None}
        else:
            continue
        raw_name = str(binding_dict.get("raw_name", "")).strip()
        if raw_name:
            requested_by_raw[raw_name] = binding_dict

    normalized: list[dict[str, Any]] = []
    for position, raw_name in enumerate(header_columns):
        requested = requested_by_raw.get(raw_name, {})
        sample_value = sample_data.get(raw_name)
        sample_type = requested.get("sample_type")
        confidence = requested.get("confidence")
        if not sample_type:
            if _looks_like_date_value(sample_value):
                sample_type = "date"
                confidence = confidence if confidence is not None else 0.98
            elif _looks_like_number_value(sample_value):
                sample_type = "number"
                confidence = confidence if confidence is not None else 0.7
            else:
                sample_type = "string"
                confidence = confidence if confidence is not None else 0.5

        display_name = str(requested.get("display_name", "")).strip() or raw_name
        semantic_key = requested.get("semantic_key")
        semantic_role = requested.get("semantic_role")
        aliases = [str(alias).strip() for alias in requested.get("aliases", []) if str(alias).strip()]
        inferred_semantic_key = infer_semantic_key(
            semantic_key,
            semantic_role,
            display_name,
            raw_name,
            *aliases,
        )
        semantic_requirements = get_semantic_requirements(inferred_semantic_key)
        requested_review_status = str(requested.get("semantic_review_status") or "").strip()
        if requested_review_status not in {
            "pending",
            "confirmed_semantic",
            "confirmed_non_semantic",
        }:
            requested_review_status = ""
        if requested_review_status == "confirmed_non_semantic":
            inferred_semantic_key = None
            semantic_role = None
            aliases = []
            semantic_requirements = {"required": False, "hash_participates": False}
        if _looks_like_unnamed_header(raw_name) and sample_type == "date":
            if display_name == raw_name:
                display_name = "日期"
            if not semantic_role:
                semantic_role = "metric_date"
            inferred_semantic_key = inferred_semantic_key or "metric_date"
            semantic_requirements = get_semantic_requirements(inferred_semantic_key)
            aliases = list(dict.fromkeys([display_name, "日期", "统计日期", *aliases, *get_semantic_aliases(inferred_semantic_key)]))
        elif display_name != raw_name:
            aliases = list(dict.fromkeys([display_name, *aliases, *get_semantic_aliases(inferred_semantic_key)]))
        elif inferred_semantic_key:
            aliases = list(dict.fromkeys([*aliases, *get_semantic_aliases(inferred_semantic_key)]))

        if requested_review_status:
            semantic_review_status = requested_review_status
        elif inferred_semantic_key:
            semantic_review_status = "confirmed_semantic"
        else:
            semantic_review_status = "pending"

        if semantic_review_status == "confirmed_non_semantic":
            inferred_semantic_key = None
            semantic_role = None
            aliases = []
            semantic_requirements = {"required": False, "hash_participates": False}

        required = bool(requested.get("required", semantic_requirements["required"]))
        hash_participates = bool(requested.get("hash_participates", semantic_requirements["hash_participates"]))
        if semantic_review_status == "confirmed_non_semantic":
            required = False
            hash_participates = False

        normalized.append(
            {
                "raw_name": raw_name,
                "display_name": display_name,
                "semantic_key": inferred_semantic_key,
                "semantic_role": semantic_role,
                "aliases": aliases,
                "required": required,
                "hash_participates": hash_participates,
                "semantic_review_status": semantic_review_status,
                "position": requested.get("position", position),
                "sample_type": sample_type,
                "confidence": confidence,
            }
        )
    return normalized


def _apply_mapping_semantics_to_header_bindings(
    header_bindings: list[dict[str, Any]],
    mappings: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not mappings:
        return header_bindings

    mapping_by_raw = {
        str(raw_name).strip(): _extract_standard_field(mapping_info)
        for raw_name, mapping_info in mappings.items()
        if str(raw_name).strip()
    }
    if not mapping_by_raw:
        return header_bindings

    enriched: list[dict[str, Any]] = []
    for binding in header_bindings:
        raw_name = str(binding.get("raw_name", "")).strip()
        standard_field = mapping_by_raw.get(raw_name)
        semantic_key = normalize_semantic_key(standard_field) if standard_field else None
        if semantic_key and is_canonical_semantic_key(semantic_key):
            semantic_requirements = get_semantic_requirements(semantic_key)
            enriched.append(
                {
                    **binding,
                    "semantic_key": semantic_key,
                    "semantic_role": "metric_date" if semantic_key == "metric_date" else binding.get("semantic_role"),
                    "aliases": list(
                        dict.fromkeys(
                            [
                                *(binding.get("aliases") or []),
                                *get_semantic_aliases(semantic_key),
                            ]
                        )
                    ),
                    "required": bool(binding.get("required") or semantic_requirements["required"]),
                    "hash_participates": bool(
                        binding.get("hash_participates") or semantic_requirements["hash_participates"]
                    ),
                    "semantic_review_status": "confirmed_semantic",
                }
            )
            continue
        enriched.append(binding)

    return enriched


def _validate_deduplication_fields_against_bindings(
    deduplication_fields: list[str],
    header_columns: list[str],
    header_bindings: list[dict[str, Any]],
    field_parse_rules: list[dict[str, Any]] | None = None,
) -> None:
    service_validate_deduplication_fields_against_bindings(
        deduplication_fields,
        header_columns,
        header_bindings,
        field_parse_rules,
    )


def _sync_hash_participation_from_deduplication_fields(
    header_bindings: list[dict[str, Any]],
    deduplication_fields: list[str],
) -> list[dict[str, Any]]:
    return service_sync_hash_participation_from_deduplication_fields(
        header_bindings,
        deduplication_fields,
    )


def _extract_semantic_key_sets(
    deduplication_fields: list[str] | None,
    header_bindings: list[dict[str, Any]] | None,
) -> tuple[list[str], list[str]]:
    required_keys: list[str] = []
    hash_keys: list[str] = []
    seen_required: set[str] = set()
    seen_hash: set[str] = set()

    for field in deduplication_fields or []:
        semantic_key = normalize_semantic_key(field)
        if semantic_key and is_canonical_semantic_key(semantic_key) and semantic_key not in seen_hash:
            seen_hash.add(semantic_key)
            hash_keys.append(semantic_key)

    for binding in header_bindings or []:
        semantic_key = normalize_semantic_key(
            binding.get("semantic_key") or binding.get("semantic_role") or binding.get("display_name")
        )
        if not semantic_key:
            continue
        if binding.get("required") and semantic_key not in seen_required:
            seen_required.add(semantic_key)
            required_keys.append(semantic_key)
        if binding.get("hash_participates") and semantic_key not in seen_hash:
            seen_hash.add(semantic_key)
            hash_keys.append(semantic_key)

    return required_keys, hash_keys


def _normalize_deduplication_fields_for_template(
    deduplication_fields: list[str] | None,
    header_bindings: list[dict[str, Any]] | None,
) -> list[str]:
    return service_normalize_deduplication_fields_for_template(
        deduplication_fields,
        header_bindings,
    )


def _recommended_deduplication_fields(
    default_fields: list[str],
    header_columns: list[str],
    header_bindings: list[dict[str, Any]] | None,
) -> list[str]:
    current_lookup = {str(field).lower() for field in header_columns}
    binding_semantic_keys = {
        normalize_semantic_key(
            binding.get("semantic_key") or binding.get("semantic_role") or binding.get("display_name")
        )
        for binding in (header_bindings or [])
    }

    recommended: list[str] = []
    seen: set[str] = set()
    for field in default_fields:
        semantic_key = normalize_semantic_key(field)
        if not semantic_key:
            continue
        if semantic_key in binding_semantic_keys or str(field).lower() in current_lookup:
            if semantic_key in seen:
                continue
            seen.add(semantic_key)
            recommended.append(semantic_key)
    return recommended


def _build_template_save_readiness(
    *,
    data_domain: str,
    granularity: str | None,
    sub_domain: str | None,
    header_columns: list[str],
    deduplication_fields: list[str],
    header_bindings: list[dict[str, Any]],
    field_parse_rules: list[dict[str, Any]],
    sample_rows: list[dict[str, Any]] | None = None,
):
    return TemplateSaveReadinessService().assess(
        data_domain=data_domain,
        granularity=granularity,
        sub_domain=sub_domain,
        header_columns=header_columns,
        deduplication_fields=deduplication_fields,
        header_bindings=header_bindings,
        field_parse_rules=field_parse_rules,
        sample_rows=sample_rows,
    )


def _enrich_field_parse_rules(
    field_parse_rules: list[dict[str, Any]],
    header_bindings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    bindings_by_raw = {
        str(binding.get("raw_name", "")).strip(): binding
        for binding in header_bindings or []
        if str(binding.get("raw_name", "")).strip()
    }
    enriched: list[dict[str, Any]] = []
    for rule in field_parse_rules or []:
        source_column = str(rule.get("source_column", "")).strip()
        binding = bindings_by_raw.get(source_column)
        enriched_rule = dict(rule)
        if binding:
            if binding.get("display_name") and not enriched_rule.get("source_label"):
                enriched_rule["source_label"] = binding["display_name"]
            if binding.get("aliases") and not enriched_rule.get("source_aliases"):
                enriched_rule["source_aliases"] = list(binding["aliases"])
            if binding.get("semantic_role") and not enriched_rule.get("source_semantic_role"):
                enriched_rule["source_semantic_role"] = binding["semantic_role"]
        enriched.append(enriched_rule)
    return enriched


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
        if value_kind not in DATE_PARSE_VALUE_KINDS:
            raise ValueError(
                f"field_parse_rules for {target_field} must define a supported value_kind"
            )
        date_format = str(rule.get("date_format", "")).strip()
        if not date_format:
            raise ValueError(f"field_parse_rules for {target_field} must define date_format")
        date_anchor = str(rule.get("date_anchor", "") or "").strip()
        if date_anchor and date_anchor not in FILE_DATE_SOURCE_COLUMNS and date_anchor.lower() not in header_lookup:
            raise ValueError(
                f"field_parse_rules for {target_field} references unknown date_anchor: {date_anchor}"
            )
        if value_kind in DATE_PARSE_RANGE_VALUE_KINDS:
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


async def _validate_template_family_hash_keys(
    db: AsyncSession,
    *,
    platform: str,
    data_domain: str,
    granularity: Optional[str],
    sub_domain: Optional[str],
    account: Optional[str],
    deduplication_fields: list[str],
    header_bindings: list[dict[str, Any]],
) -> None:
    current_keys = _canonical_user_hash_key_set(deduplication_fields, header_bindings)
    result = await db.execute(
        select(FieldMappingTemplate).where(
            and_(
                FieldMappingTemplate.platform == platform,
                FieldMappingTemplate.data_domain == data_domain,
                FieldMappingTemplate.granularity == _normalize_dimension_value(granularity),
                FieldMappingTemplate.sub_domain == _normalize_dimension_value(sub_domain),
                FieldMappingTemplate.account == _normalize_dimension_value(account),
                FieldMappingTemplate.status == "published",
            )
        )
    )
    existing_templates = list(result.scalars().all())
    if not existing_templates:
        return

    existing = sorted(
        existing_templates,
        key=lambda item: (item.version or 0, item.id or 0),
        reverse=True,
    )[0]
    existing_keys = _canonical_user_hash_key_set(
        existing.deduplication_fields or [],
        existing.header_bindings or [],
    )
    if not existing_keys:
        return

    missing_keys = sorted(existing_keys - current_keys)
    extra_keys = sorted(current_keys - existing_keys)
    if not missing_keys and not extra_keys:
        return

    payload = _family_hash_change_payload(
        existing_template=existing,
        existing_keys=existing_keys,
        current_keys=current_keys,
        current_deduplication_fields=deduplication_fields,
        current_header_bindings=header_bindings,
        data_domain=data_domain,
    )
    details: list[str] = []
    if missing_keys:
        details.append("缺少必要 hash 语义字段: " + ", ".join(missing_keys))
    if extra_keys:
        details.append("新增 hash 语义字段: " + ", ".join(extra_keys))
    message = (
        "; ".join(details)
        + "。同一模板家族必须保持同一套 data_hash 语义字段；"
        + "如业务行粒度不同，请迁移模板家族 Hash 口径，或拆分 sub_domain / 模板家族。"
    )
    if payload["suggested_action"] == "migrate_family_hash_keys":
        message = (
            "Hash口径升级: "
            + message
            + " Historical family hash uses product_name while current selection uses product_id."
        )
    raise TemplateFamilyHashKeyMismatch(message, payload)

    details: list[str] = []
    if missing_keys:
        details.append("缺少必要 hash 语义字段: " + ", ".join(missing_keys))
    if extra_keys:
        details.append("新增 hash 语义字段: " + ", ".join(extra_keys))
    raise ValueError(
        "; ".join(details)
        + "。同一模板家族必须保持同一套 data_hash 语义字段；如业务行粒度不同，请拆分 sub_domain 或模板家族。"
    )


@router.post(
    "/templates/hash-policy-preview",
    response_model=HashPolicyPreviewResponse,
)
async def preview_template_hash_policy(
    request: HashPolicyPreviewRequest,
    db: AsyncSession = Depends(get_async_db),
):
    del db
    preview_header_columns = [
        str(binding.raw_name).strip()
        for binding in request.header_bindings
        if str(binding.raw_name).strip()
    ]
    header_bindings = _normalize_header_bindings(
        request.header_bindings,
        preview_header_columns,
        {},
    )
    field_parse_rules = _enrich_field_parse_rules(
        _normalize_field_parse_rules(request.field_parse_rules),
        header_bindings,
    )
    readiness = _build_template_save_readiness(
        data_domain=request.data_domain,
        granularity=request.granularity,
        sub_domain=request.sub_domain,
        header_columns=preview_header_columns,
        deduplication_fields=request.deduplication_fields,
        header_bindings=header_bindings,
        field_parse_rules=field_parse_rules,
        sample_rows=request.sample_rows,
    )
    return HashPolicyPreviewResponse(
        success=True,
        data=HashPolicyPreviewData(**readiness.to_dict()),
    )


@router.post("/templates/save", response_model=TemplateSaveResponse)
async def save_mapping_template(
    request: TemplateSaveRequest,
    header_row: Optional[int] = Query(
        None,
        description="Optional override header row for current file preview (0=Excel第1行)",
    ),
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
        header_bindings = _normalize_header_bindings(
            request.header_bindings,
            header_columns,
            request.sample_data,
        )
        header_bindings = _apply_mapping_semantics_to_header_bindings(
            header_bindings,
            request.mappings,
        )
        field_parse_rules = _enrich_field_parse_rules(
            _normalize_field_parse_rules(request.field_parse_rules),
            header_bindings,
        )
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
        readiness = _build_template_save_readiness(
            data_domain=request.data_domain,
            granularity=request.granularity,
            sub_domain=request.sub_domain,
            header_columns=header_columns,
            deduplication_fields=deduplication_fields,
            header_bindings=header_bindings,
            field_parse_rules=field_parse_rules,
            sample_rows=[request.sample_data] if request.sample_data else [],
        )
        deduplication_fields = readiness.normalized_deduplication_fields
        header_bindings = readiness.normalized_header_bindings

        if header_columns:
            missing_fields = []
            for field in deduplication_fields:
                found = False
                normalized_field = normalize_semantic_key(field)
                if normalized_field:
                    found = any(
                        normalize_semantic_key(
                            binding.get("semantic_key") or binding.get("semantic_role") or binding.get("display_name")
                        )
                        == normalized_field
                        for binding in header_bindings
                    )
                    if found:
                        continue
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
        hash_policy_result = readiness.hash_policy
        if not readiness.can_save:
            message = "; ".join(readiness.blocking_errors)
            return error_response(
                code=ErrorCode.PARAMETER_INVALID,
                message=f"保存模板失败: {message}",
                error_type=get_error_type(ErrorCode.PARAMETER_INVALID),
                detail=message,
                recovery_suggestion="请补齐 Data Hash 必需的语义字段后再保存",
                status_code=400,
                data={"hash_policy": readiness.to_dict()},
            )

        try:
            await _validate_template_family_hash_keys(
                db,
                platform=request.platform,
                data_domain=request.data_domain,
                granularity=request.granularity,
                sub_domain=request.sub_domain,
                account=request.account,
                deduplication_fields=deduplication_fields,
                header_bindings=header_bindings,
            )
        except TemplateFamilyHashKeyMismatch as exc:
            hash_policy_payload = readiness.to_dict()
            hash_policy_payload.update(exc.payload)
            family_group = {
                "key": "template_family_hash_keys",
                "label": "模板家族 Data Hash 字段一致性",
                "severity": "blocking",
                "requirement_type": "same_as_family",
                "accepted_keys": hash_policy_payload.get("family_hash_keys", []),
                "selected_keys": hash_policy_payload.get("current_hash_keys", []),
                "missing_keys": [],
                "passed": False,
                "message": str(exc),
            }
            hash_policy_payload["blocking_errors"] = [
                *hash_policy_payload.get("blocking_errors", []),
                str(exc),
            ]
            hash_policy_payload["requirement_groups"] = [
                *hash_policy_payload.get("requirement_groups", []),
                family_group,
            ]
            hash_policy_payload["missing_required_groups"] = [
                *hash_policy_payload.get("missing_required_groups", []),
                family_group,
            ]
            hash_policy_payload["passed"] = False
            hash_policy_payload["can_save"] = False
            return error_response(
                code=ErrorCode.PARAMETER_INVALID,
                message=f"保存模板失败: {str(exc)}",
                error_type=get_error_type(ErrorCode.PARAMETER_INVALID),
                detail=str(exc),
                recovery_suggestion="请保持同一模板家族的 Data Hash 语义字段一致",
                status_code=400,
                data={"hash_policy": hash_policy_payload},
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
            header_bindings=header_bindings,
            field_parse_rules=field_parse_rules,
            save_mode=request.save_mode,
            base_template_id=request.base_template_id,
        )
        alias_registry = SemanticAliasRegistryService()
        alias_summary = await alias_registry.upsert_template_confirmed_aliases(
            db,
            data_domain=request.data_domain,
            platform_code=request.platform,
            granularity=request.granularity,
            header_bindings=header_bindings,
        )
        governance_checks = TemplateSemanticCoverageChecker(alias_registry).build_summary(
            data_domain=request.data_domain,
            platform_code=request.platform,
            granularity=request.granularity,
            sample_data=request.sample_data,
            confirmed_aliases=alias_summary.aliases,
            hash_policy_result=hash_policy_result,
        )
        save_result["governance_checks"] = governance_checks

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
    header_row: Optional[int] = Query(
        None,
        description="可选：覆盖当前文件预览使用的表头行(0=Excel第1行)",
    ),
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
        effective_header_row = header_row if header_row is not None else (template.header_row or 0)
        normalized_template_bindings = _normalize_header_bindings(
            template.header_bindings,
            template_header_columns,
            {},
        )
        required_semantic_keys, hash_participating_semantic_keys = _extract_semantic_key_sets(
            template_deduplication_fields,
            normalized_template_bindings,
        )
        response_data: Dict[str, Any] = {
            "resolved_object_type": "template_update",
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
                required_semantic_keys=required_semantic_keys,
                hash_participating_semantic_keys=hash_participating_semantic_keys,
                header_bindings=normalized_template_bindings,
                field_parse_rules=template.field_parse_rules or [],
            ).model_dump(),
            "template_header_columns": template_header_columns,
            "current_file": None,
            "current_header_columns": [],
            "current_header_row": effective_header_row,
            "sample_data": {},
            "preview_data": [],
            "current_header_bindings": [],
            "review_header_bindings": [],
            "full_header_bindings": [],
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
            "existing_deduplication_field_matches": [],
            "recommended_deduplication_fields": [],
            "hash_options": [],
            "required_semantic_keys": required_semantic_keys,
            "hash_participating_semantic_keys": hash_participating_semantic_keys,
            "update_semantics": "new_version",
            "recommended_save_mode": "new_version",
        }

        default_fields = get_default_deduplication_fields_config(
            template.data_domain,
            template.sub_domain,
        )

        if mode == "with-sample" and file_id is None:
            raise ValueError("file_id is required when mode is with-sample")

        if mode == "core-only":
            available_fields, missing_fields, field_matches = _split_existing_deduplication_fields(
                template_deduplication_fields,
                template_header_columns,
                normalized_template_bindings,
                existing_header_bindings=normalized_template_bindings,
                data_domain=template.data_domain,
                granularity=template.granularity,
                sub_domain=template.sub_domain,
            )
            recommended_fields = _recommended_deduplication_fields(
                default_fields,
                template_header_columns,
                normalized_template_bindings,
            )
            response_data.update(
                {
                    "current_header_columns": template_header_columns,
                    "current_header_bindings": normalized_template_bindings,
                    "review_header_bindings": _filter_bindings_for_manual_review(normalized_template_bindings),
                    "full_header_bindings": normalized_template_bindings,
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
                    "existing_deduplication_field_matches": field_matches,
                    "recommended_deduplication_fields": recommended_fields,
                    "hash_options": SemanticHashPolicyService().build_options(
                        data_domain=template.data_domain,
                        granularity=template.granularity,
                        sub_domain=template.sub_domain,
                        header_bindings=normalized_template_bindings,
                    ),
                }
            )
        elif file_id is not None:
            file_summary = await _load_file_update_summary(db, file_id, effective_header_row)
            current_header_columns = file_summary["header_columns"]
            current_header_bindings = _normalize_header_bindings(
                file_summary.get("header_bindings", []),
                current_header_columns,
                {},
            )
            matcher = get_template_matcher(db)
            header_changes = await matcher.detect_header_changes(
                template_id,
                current_header_columns,
            )
            current_lookup = {str(field).lower(): field for field in current_header_columns}
            added_fields = header_changes.get("added_fields", [])
            removed_fields = header_changes.get("removed_fields", [])
            available_fields, missing_fields, field_matches = _split_existing_deduplication_fields(
                template_deduplication_fields,
                current_header_columns,
                current_header_bindings,
                existing_header_bindings=normalized_template_bindings,
                data_domain=template.data_domain,
                granularity=template.granularity,
                sub_domain=template.sub_domain,
            )
            recommended_fields = _recommended_deduplication_fields(
                default_fields,
                current_header_columns,
                current_header_bindings,
            )
            response_data.update(
                {
                    "current_file": file_summary["file"],
                    "current_header_columns": current_header_columns,
                    "current_header_bindings": current_header_bindings,
                    "review_header_bindings": _filter_bindings_for_manual_review(current_header_bindings),
                    "full_header_bindings": current_header_bindings,
                    "current_header_row": effective_header_row,
                    "sample_data": {},
                    "preview_data": [],
                    "header_changes": header_changes,
                    "match_rate": header_changes.get("match_rate", 0.0),
                    "added_fields": added_fields,
                    "removed_fields": removed_fields,
                    "existing_deduplication_fields_available": available_fields,
                    "existing_deduplication_fields_missing": missing_fields,
                    "existing_deduplication_field_matches": field_matches,
                    "recommended_deduplication_fields": recommended_fields,
                    "hash_options": SemanticHashPolicyService().build_options(
                        data_domain=template.data_domain,
                        granularity=template.granularity,
                        sub_domain=template.sub_domain,
                        header_bindings=current_header_bindings,
                    ),
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


@router.get(
    "/templates/{template_id}/update-preview",
    response_model=TemplateUpdatePreviewResponse,
)
async def get_template_update_preview(
    template_id: int,
    file_id: int = Query(..., description="鐢ㄤ簬鏇存柊妯℃澘鐨勫€欓€夋枃浠禝D"),
    header_row: Optional[int] = Query(None, description="鍙€夎鐩栬〃澶磋"),
    db: AsyncSession = Depends(get_async_db),
):
    try:
        template_result = await db.execute(
            select(FieldMappingTemplate).where(FieldMappingTemplate.id == template_id)
        )
        template = template_result.scalar_one_or_none()
        if not template:
            return error_response(
                code=ErrorCode.NOT_FOUND,
                message="妯℃澘涓嶅瓨鍦?",
                error_type=get_error_type(ErrorCode.NOT_FOUND),
                detail=f"妯℃澘ID {template_id} 涓嶅瓨鍦?",
                recovery_suggestion="璇锋鏌ユā鏉縄D鏄惁姝ｇ‘",
                status_code=404,
            )

        effective_header_row = header_row if header_row is not None else (template.header_row or 0)
        file_preview = await _load_file_update_preview(db, file_id, effective_header_row)
        return TemplateUpdatePreviewResponse(
            success=True,
            data=TemplateUpdatePreviewData(
                current_file=file_preview["file"],
                current_header_columns=file_preview.get("header_columns", []),
                current_header_row=effective_header_row,
                sample_data=file_preview.get("sample_data", {}),
                preview_data=file_preview.get("preview_data", []),
            ),
            message="鑾峰彇妯℃澘鏇存柊棰勮鎴愬姛",
        )
    except ValueError as exc:
        logger.error(f"鑾峰彇妯℃澘鏇存柊棰勮澶辫触(鍙傛暟閿欒): {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message="鑾峰彇妯℃澘鏇存柊棰勮澶辫触",
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            detail=str(exc),
            recovery_suggestion="璇锋鏌ユā鏉垮拰鍊欓€夋枃浠舵槸鍚﹀瓨鍦?",
            status_code=400,
        )
    except Exception as exc:
        logger.error(f"鑾峰彇妯℃澘鏇存柊棰勮澶辫触: {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="鑾峰彇妯℃澘鏇存柊棰勮澶辫触",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(exc),
            recovery_suggestion="璇锋鏌ユ暟鎹簱杩炴帴鎴栧€欓€夋枃浠剁姸鎬?",
            status_code=500,
        )


@router.get(
    "/templates/{template_id}/update-bindings",
    response_model=TemplateUpdateBindingsResponse,
)
async def get_template_update_bindings(
    template_id: int,
    file_id: int = Query(..., description="鐢ㄤ簬鏇存柊妯℃澘鐨勫€欓€夋枃浠禝D"),
    header_row: Optional[int] = Query(None, description="鍙€夎鐩栬〃澶磋"),
    db: AsyncSession = Depends(get_async_db),
):
    try:
        template_result = await db.execute(
            select(FieldMappingTemplate).where(FieldMappingTemplate.id == template_id)
        )
        template = template_result.scalar_one_or_none()
        if not template:
            return error_response(
                code=ErrorCode.NOT_FOUND,
                message="妯℃澘涓嶅瓨鍦?",
                error_type=get_error_type(ErrorCode.NOT_FOUND),
                detail=f"妯℃澘ID {template_id} 涓嶅瓨鍦?",
                recovery_suggestion="璇锋鏌ユā鏉縄D鏄惁姝ｇ‘",
                status_code=404,
            )

        effective_header_row = header_row if header_row is not None else (template.header_row or 0)
        file_preview = await _load_file_update_preview(db, file_id, effective_header_row)
        current_header_bindings = _normalize_header_bindings(
            file_preview.get("header_bindings", []),
            file_preview.get("header_columns", []),
            file_preview.get("sample_data", {}),
        )
        required_semantic_keys, hash_participating_semantic_keys = _extract_semantic_key_sets(
            template.deduplication_fields or [],
            current_header_bindings,
        )
        return TemplateUpdateBindingsResponse(
            success=True,
            data=TemplateUpdateBindingsData(
                current_file=file_preview["file"],
                current_header_columns=file_preview.get("header_columns", []),
                current_header_row=effective_header_row,
                current_header_bindings=current_header_bindings,
                review_header_bindings=_filter_bindings_for_manual_review(current_header_bindings),
                full_header_bindings=current_header_bindings,
                required_semantic_keys=required_semantic_keys,
                hash_participating_semantic_keys=hash_participating_semantic_keys,
            ),
            message="鑾峰彇妯℃澘鏇存柊璇箟缁戝畾鎴愬姛",
        )
    except ValueError as exc:
        logger.error(f"鑾峰彇妯℃澘鏇存柊璇箟缁戝畾澶辫触(鍙傛暟閿欒): {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message="鑾峰彇妯℃澘鏇存柊璇箟缁戝畾澶辫触",
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            detail=str(exc),
            recovery_suggestion="璇锋鏌ユā鏉垮拰鍊欓€夋枃浠舵槸鍚﹀瓨鍦?",
            status_code=400,
        )
    except Exception as exc:
        logger.error(f"鑾峰彇妯℃澘鏇存柊璇箟缁戝畾澶辫触: {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="鑾峰彇妯℃澘鏇存柊璇箟缁戝畾澶辫触",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(exc),
            recovery_suggestion="璇锋鏌ユ暟鎹簱杩炴帴鎴栧€欓€夋枃浠剁姸鎬?",
            status_code=500,
        )


@router.get(
    "/template-families/{family_id}/variant-create-context",
    response_model=TemplateVariantCreateContextResponse,
)
async def get_template_variant_create_context(
    family_id: int,
    file_id: int = Query(..., description="候选样本文件 ID"),
    header_row: Optional[int] = Query(None, description="可选覆盖表头行"),
    db: AsyncSession = Depends(get_async_db),
):
    try:
        family_service = get_template_family_service(db)
        family, versions = await family_service.get_family_versions(family_id)
        active_version = next((item for item in versions if item["status"] == "active"), None)
        if active_version is None:
            raise ValueError(f"template family {family_id} has no active version")

        _version_payload, variants = await family_service.get_version_variants(active_version["id"])
        legacy_template_ids = list(active_version.get("legacy_template_ids") or [])
        if not legacy_template_ids:
            raise ValueError(f"template family {family_id} has no compatible legacy template")

        template_result = await db.execute(
            select(FieldMappingTemplate).where(FieldMappingTemplate.id == legacy_template_ids[0])
        )
        template = template_result.scalar_one_or_none()
        if not template:
            raise ValueError(f"legacy template {legacy_template_ids[0]} not found")

        effective_header_row = header_row if header_row is not None else (template.header_row or 0)
        file_preview = await _load_file_update_preview(db, file_id, effective_header_row)
        current_header_columns = file_preview["header_columns"]
        current_header_bindings = file_preview.get("header_bindings", [])
        required_semantic_keys, hash_participating_semantic_keys = _extract_semantic_key_sets(
            list(active_version.get("deduplication_fields") or []),
            current_header_bindings,
        )

        resolver = get_template_resolver(db)
        resolve_data = await resolver.resolve(
            platform=family["platform"],
            data_domain=family["data_domain"],
            granularity=family["granularity"],
            sub_domain=family["sub_domain"],
            header_row=effective_header_row,
            header_columns=current_header_columns,
            sample_rows=file_preview.get("preview_data", [])[:3],
        )
        recommended_variant = resolve_data.get("variant")
        recommended_variant_key = (
            recommended_variant.get("variant_key")
            if recommended_variant
            else f"{family['granularity'] or 'generic'}_custom"
        )
        recommended_parse_profile = (
            dict(recommended_variant.get("parse_profile") or {})
            if recommended_variant
            else {}
        )

        return TemplateVariantCreateContextResponse(
            success=True,
            data=TemplateVariantCreateContextData(
                family=family,
                active_version=active_version,
                existing_variants=variants,
                current_file=file_preview["file"],
                current_header_columns=current_header_columns,
                current_header_row=effective_header_row,
                sample_data=file_preview.get("sample_data", {}),
                preview_data=file_preview.get("preview_data", []),
                current_header_bindings=current_header_bindings,
                required_semantic_keys=required_semantic_keys,
                hash_participating_semantic_keys=hash_participating_semantic_keys,
                recommended_variant_key=recommended_variant_key,
                recommended_parse_profile=recommended_parse_profile,
            ),
            message="获取变体创建上下文成功",
        )
    except ValueError as exc:
        logger.error(f"获取变体创建上下文失败(参数错误): {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message="获取变体创建上下文失败",
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            detail=str(exc),
            recovery_suggestion="请检查模板族和样本文件是否存在",
            status_code=400,
        )
    except Exception as exc:
        logger.error(f"获取变体创建上下文失败: {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取变体创建上下文失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(exc),
            recovery_suggestion="请检查数据库连接或样本文件状态",
            status_code=500,
        )


@router.get("/template-families", response_model=TemplateFamilyListResponse)
async def list_template_families(
    platform: Optional[str] = Query(None, description="平台代码"),
    data_domain: Optional[str] = Query(None, description="数据域"),
    db: AsyncSession = Depends(get_async_db),
):
    try:
        families = await get_template_family_service(db).list_families(
            platform=platform or None,
            data_domain=data_domain or None,
        )
        return TemplateFamilyListResponse(
            success=True,
            data=TemplateFamilyListData(families=families, count=len(families)),
        )
    except Exception as exc:
        logger.error(f"列出模板族失败: {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="列出模板族失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(exc),
            recovery_suggestion="请检查数据库连接",
            status_code=500,
        )


@router.get(
    "/template-families/{family_id}/versions",
    response_model=TemplateFamilyVersionsResponse,
)
async def list_template_family_versions(
    family_id: int,
    db: AsyncSession = Depends(get_async_db),
):
    try:
        family, versions = await get_template_family_service(db).get_family_versions(family_id)
        return TemplateFamilyVersionsResponse(
            success=True,
            data=TemplateFamilyVersionsData(family=family, versions=versions),
        )
    except ValueError as exc:
        return error_response(
            code=ErrorCode.NOT_FOUND,
            message="模板族不存在",
            error_type=get_error_type(ErrorCode.NOT_FOUND),
            detail=str(exc),
            recovery_suggestion="请检查模板族 ID",
            status_code=404,
        )
    except Exception as exc:
        logger.error(f"列出模板族版本失败: {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="列出模板族版本失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(exc),
            recovery_suggestion="请检查数据库连接",
            status_code=500,
        )


@router.get(
    "/template-versions/{version_id}/variants",
    response_model=TemplateVersionVariantsResponse,
)
async def list_template_version_variants(
    version_id: int,
    db: AsyncSession = Depends(get_async_db),
):
    try:
        version, variants = await get_template_family_service(db).get_version_variants(version_id)
        return TemplateVersionVariantsResponse(
            success=True,
            data=TemplateVersionVariantsData(version=version, variants=variants),
        )
    except ValueError as exc:
        return error_response(
            code=ErrorCode.NOT_FOUND,
            message="模板版本不存在",
            error_type=get_error_type(ErrorCode.NOT_FOUND),
            detail=str(exc),
            recovery_suggestion="请检查模板版本 ID",
            status_code=404,
        )
    except Exception as exc:
        logger.error(f"列出模板变体失败: {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="列出模板变体失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(exc),
            recovery_suggestion="请检查数据库连接",
            status_code=500,
        )


@router.post("/template-resolve", response_model=TemplateResolveResponse)
async def resolve_template_candidate(
    request: TemplateResolveRequest,
    db: AsyncSession = Depends(get_async_db),
):
    try:
        data = await get_template_resolver(db).resolve(
            platform=request.platform,
            data_domain=request.data_domain,
            granularity=request.granularity,
            sub_domain=request.sub_domain,
            account=request.account,
            header_row=request.header_row,
            sheet_name=request.sheet_name,
            header_columns=request.header_columns,
            sample_rows=request.sample_rows,
        )
        return TemplateResolveResponse(success=True, data=TemplateResolveData(**data))
    except Exception as exc:
        logger.error(f"解析模板候选失败: {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="解析模板候选失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(exc),
            recovery_suggestion="请检查请求参数和数据库连接",
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
