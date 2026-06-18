from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.exc import OperationalError

from modules.core.db import CatalogFile
from backend.services.template_family_service import get_template_resolver
from backend.services.template_matcher import get_template_matcher


class DataSyncTemplateStatusService:
    def __init__(self, db):
        self.db = db
        self.template_matcher = get_template_matcher(db)
        self.template_resolver = get_template_resolver(db)

    async def evaluate_catalog_file(
        self,
        catalog_file: CatalogFile,
        *,
        template=None,
        current_columns: Optional[list[str]] = None,
        sample_rows: Optional[list[dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        resolver_result = None
        try:
            resolver_result = await self.template_resolver.resolve(
                platform=catalog_file.platform_code,
                data_domain=catalog_file.data_domain,
                granularity=catalog_file.granularity,
                sub_domain=catalog_file.sub_domain if catalog_file.sub_domain else None,
                header_columns=current_columns or [],
                sample_rows=sample_rows or [],
            )
        except OperationalError:
            resolver_result = None

        normalized_sub_domain = catalog_file.sub_domain if catalog_file.sub_domain else None
        template = template or await self.template_matcher.find_best_template(
            platform=catalog_file.platform_code,
            data_domain=catalog_file.data_domain,
            granularity=catalog_file.granularity,
            sub_domain=normalized_sub_domain,
        )

        if not template:
            governance_status = (
                resolver_result.get("governance_status", "missing_family")
                if resolver_result
                else "missing_family"
            )
            active_version = resolver_result.get("active_version") if resolver_result else None
            return {
                "template_status": "missing_variant" if governance_status == "missing_variant" else "missing",
                "governance_status": governance_status,
                "has_template": governance_status == "missing_variant",
                "template_name": active_version.get("template_name") if active_version else None,
                "template_header_row": None,
                "template_update_required": False,
                "update_reason": None,
                "error_code": "MISSING_VARIANT" if governance_status == "missing_variant" else "NO_TEMPLATE",
                "should_auto_sync": False,
                "exact_match": False,
                "semantic_match": False,
                "shadow_compare": resolver_result.get("shadow_compare") if resolver_result else None,
            }

        if current_columns is None:
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
                "shadow_compare": resolver_result.get("shadow_compare") if resolver_result else None,
            }

        header_changes = await self.template_matcher.detect_header_changes(
            template.id,
            current_columns,
        )

        blocking_changes = header_changes.get("blocking_changes")
        if not isinstance(blocking_changes, list):
            blocking_changes = []
        non_blocking_changes = header_changes.get("non_blocking_changes")
        if not isinstance(non_blocking_changes, list):
            non_blocking_changes = []

        if header_changes.get("is_exact_match", False):
            status = "ready"
            governance_status = "ready"
            should_auto_sync = True
            update_required = False
        elif header_changes.get("is_semantic_match", False) or (
            header_changes.get("detected", False)
            and not blocking_changes
            and bool(non_blocking_changes)
        ):
            status = "alias_only"
            governance_status = "non_breaking_drift"
            should_auto_sync = True
            update_required = False
        else:
            status = "update_required"
            governance_status = "breaking_drift"
            should_auto_sync = False
            update_required = True

        return {
            "template_status": status,
            "governance_status": governance_status,
            "has_template": True,
            "template_name": template.template_name,
            "template_header_row": getattr(template, "header_row", None),
            "template_update_required": update_required,
            "update_reason": None if status in {"ready", "alias_only"} else "header_changed",
            "error_code": None if status in {"ready", "alias_only"} else "HEADER_CHANGED",
            "should_auto_sync": should_auto_sync,
            "exact_match": header_changes.get("is_exact_match", False),
            "semantic_match": header_changes.get("is_semantic_match", False),
            "semantic_contract_status": header_changes.get("semantic_contract_status"),
            "missing_required_keys": header_changes.get("missing_required_keys", []),
            "missing_optional_keys": header_changes.get("missing_optional_keys", []),
            "resolved_required_keys": header_changes.get("resolved_required_keys", []),
            "resolved_optional_keys": header_changes.get("resolved_optional_keys", []),
            "extra_raw_fields": header_changes.get("extra_raw_fields", []),
            "impact_descriptions": header_changes.get("impact_descriptions", []),
            "header_changes": header_changes,
            "shadow_compare": resolver_result.get("shadow_compare") if resolver_result else None,
        }
