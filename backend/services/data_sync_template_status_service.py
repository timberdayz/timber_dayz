from __future__ import annotations

from typing import Any, Dict, Optional

from modules.core.db import CatalogFile
from backend.services.template_matcher import get_template_matcher


class DataSyncTemplateStatusService:
    def __init__(self, db):
        self.db = db
        self.template_matcher = get_template_matcher(db)

    async def evaluate_catalog_file(
        self,
        catalog_file: CatalogFile,
        *,
        template=None,
        current_columns: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        normalized_sub_domain = catalog_file.sub_domain if catalog_file.sub_domain else None
        template = template or await self.template_matcher.find_best_template(
            platform=catalog_file.platform_code,
            data_domain=catalog_file.data_domain,
            granularity=catalog_file.granularity,
            sub_domain=normalized_sub_domain,
        )

        if not template:
            return {
                "template_status": "missing",
                "has_template": False,
                "template_name": None,
                "template_header_row": None,
                "template_update_required": False,
                "update_reason": None,
                "error_code": "NO_TEMPLATE",
                "should_auto_sync": False,
                "exact_match": False,
                "semantic_match": False,
            }

        if current_columns is None:
            return {
                "template_status": "ready",
                "has_template": True,
                "template_name": template.template_name,
                "template_header_row": getattr(template, "header_row", None),
                "template_update_required": False,
                "update_reason": None,
                "error_code": None,
                "should_auto_sync": True,
                "exact_match": True,
                "semantic_match": True,
            }

        header_changes = await self.template_matcher.detect_header_changes(
            template.id,
            current_columns,
        )

        if header_changes.get("is_exact_match", False):
            status = "ready"
            should_auto_sync = True
            update_required = False
        elif header_changes.get("is_semantic_match", False):
            status = "alias_only"
            should_auto_sync = True
            update_required = False
        else:
            status = "update_required"
            should_auto_sync = False
            update_required = True

        return {
            "template_status": status,
            "has_template": True,
            "template_name": template.template_name,
            "template_header_row": getattr(template, "header_row", None),
            "template_update_required": update_required,
            "update_reason": None if status in {"ready", "alias_only"} else "header_changed",
            "error_code": None if status in {"ready", "alias_only"} else "HEADER_CHANGED",
            "should_auto_sync": should_auto_sync,
            "exact_match": header_changes.get("is_exact_match", False),
            "semantic_match": header_changes.get("is_semantic_match", False),
            "header_changes": header_changes,
        }
