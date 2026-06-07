"""Save-time semantic coverage summary for template governance."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from backend.services.semantic_alias_registry import AliasRecord, SemanticAliasRegistryService
from backend.services.template_hash_policy import HashPolicyResult


PRODUCT_COVERAGE_FIELDS = [
    "product_id",
    "product_name",
    "item_status",
    "order_count",
    "sales_amount",
    "sales_volume",
]


class TemplateSemanticCoverageChecker:
    def __init__(self, alias_registry: Optional[SemanticAliasRegistryService] = None) -> None:
        self.alias_registry = alias_registry or SemanticAliasRegistryService()

    def build_summary(
        self,
        *,
        data_domain: str,
        platform_code: Optional[str],
        granularity: Optional[str],
        sample_data: Iterable[Dict[str, Any]] | None,
        confirmed_aliases: Iterable[AliasRecord],
        hash_policy_result: HashPolicyResult,
    ) -> Dict[str, Any]:
        if isinstance(sample_data, dict):
            sample_row = sample_data
        else:
            sample_rows = list(sample_data or [])
            sample_row = sample_rows[0] if sample_rows else {}
        fields = PRODUCT_COVERAGE_FIELDS if (data_domain or "").lower() == "products" else []
        coverage: Dict[str, Dict[str, Any]] = {}
        warnings: List[str] = list(hash_policy_result.warnings)

        for field in fields:
            value = self.alias_registry.resolve_alias_from_row(
                sample_row,
                data_domain=data_domain,
                standard_field=field,
                platform_code=platform_code,
                granularity=granularity,
                extra_aliases=confirmed_aliases,
            )
            coverage[field] = {"resolved": value is not None, "sample_has_value": value is not None}

        unresolved_required = [
            field
            for field in ["product_id", "product_name", "item_status"]
            if field in coverage and not coverage[field]["resolved"]
        ]
        if unresolved_required:
            warnings.append(f"字段标准化覆盖不足: {', '.join(unresolved_required)} 暂不可从样例行解析。")

        return {
            "hash_policy_status": "passed" if hash_policy_result.passed else "failed",
            "semantic_alias_coverage": coverage,
            "required_fields_resolved": [field for field, item in coverage.items() if item["resolved"]],
            "registered_aliases": list(confirmed_aliases),
            "warnings": warnings,
        }
