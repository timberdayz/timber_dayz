"""Hash identity policy for sync templates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Set

from backend.services.semantic_field_registry import (
    is_canonical_semantic_key,
    normalize_semantic_key,
)


@dataclass(frozen=True)
class HashPolicyResult:
    passed: bool
    blocking_errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    resolved_keys: List[str] = field(default_factory=list)


class TemplateHashPolicyService:
    PRODUCT_IDENTITY_KEYS = {"product_id", "platform_sku"}
    PRODUCT_DATE_KEYS = {"metric_date", "period_start_date"}
    PERIOD_DATE_KEYS = {"period_start_date", "period_end_date", "metric_date"}

    def validate(
        self,
        *,
        data_domain: str,
        granularity: str | None,
        deduplication_fields: Iterable[str],
        header_bindings: Iterable[Dict[str, Any]],
        field_parse_rules: Iterable[Dict[str, Any]],
    ) -> HashPolicyResult:
        domain = (data_domain or "").lower()
        grain = (granularity or "").lower()
        resolved_keys = self._resolved_semantic_keys(
            deduplication_fields,
            header_bindings,
            field_parse_rules,
        )
        errors: List[str] = []
        warnings: List[str] = []

        invalid_keys = self._invalid_deduplication_keys(
            deduplication_fields,
            header_bindings,
            field_parse_rules,
        )
        if invalid_keys:
            errors.append(
                "deduplication_fields must be confirmed semantic keys: "
                + ", ".join(sorted(invalid_keys))
            )

        if domain == "products" and grain == "daily":
            if not (resolved_keys & self.PRODUCT_IDENTITY_KEYS):
                errors.append(
                    "products daily data requires product_id or platform_sku as a semantic hash identity field."
                )
            if not (resolved_keys & self.PRODUCT_DATE_KEYS):
                errors.append(
                    "daily product metrics require product_id/platform_sku + metric_date to avoid cross-date overwrites."
                )
        elif domain == "products" and grain in {"weekly", "monthly"}:
            if not (resolved_keys & self.PRODUCT_IDENTITY_KEYS):
                errors.append(
                    "products period data requires product_id or platform_sku as a semantic hash identity field."
                )
            if not (resolved_keys & self.PERIOD_DATE_KEYS):
                errors.append(
                    "period product metrics require product_id/platform_sku + period date to avoid cross-period overwrites."
                )
        elif domain == "orders":
            if "order_id" not in resolved_keys:
                errors.append("orders data requires order_id as a semantic hash identity field.")
        elif domain in {"analytics", "traffic"}:
            if not (resolved_keys & self.PERIOD_DATE_KEYS):
                errors.append(
                    f"{domain} daily data requires metric_date as a semantic hash identity field."
                )
        elif domain == "inventory":
            has_date = bool(resolved_keys & self.PERIOD_DATE_KEYS)
            has_product = bool(resolved_keys & self.PRODUCT_IDENTITY_KEYS)
            has_warehouse = "warehouse_name" in resolved_keys
            if not has_date or not has_product or not has_warehouse:
                errors.append(
                    "inventory data requires product_id/platform_sku + warehouse_name + date as semantic hash identity fields."
                )

        return HashPolicyResult(
            passed=not errors,
            blocking_errors=errors,
            warnings=warnings,
            resolved_keys=sorted(resolved_keys),
        )

    def _resolved_semantic_keys(
        self,
        deduplication_fields: Iterable[str],
        header_bindings: Iterable[Dict[str, Any]],
        field_parse_rules: Iterable[Dict[str, Any]],
    ) -> Set[str]:
        keys = {
            normalize_semantic_key(str(field).strip()) or str(field).strip()
            for field in deduplication_fields or []
            if str(field).strip()
        }
        for binding in header_bindings or []:
            semantic_key = normalize_semantic_key(binding.get("semantic_key"))
            source_header = binding.get("source_header") or binding.get("raw_name") or binding.get("display_name")
            if semantic_key and semantic_key in keys:
                keys.add(str(semantic_key))
            if source_header in keys and semantic_key:
                keys.add(str(semantic_key))
        return keys

    def _invalid_deduplication_keys(
        self,
        deduplication_fields: Iterable[str],
        header_bindings: Iterable[Dict[str, Any]],
        field_parse_rules: Iterable[Dict[str, Any]],
    ) -> Set[str]:
        confirmed_semantic_keys = {
            normalize_semantic_key(binding.get("semantic_key"))
            for binding in header_bindings or []
            if binding.get("semantic_review_status") == "confirmed_semantic"
        }
        confirmed_semantic_keys = {key for key in confirmed_semantic_keys if key}
        derived_semantic_keys = {
            semantic_key
            for semantic_key in (
                normalize_semantic_key(rule.get("target_field") or rule.get("semantic_key") or rule.get("field"))
                for rule in field_parse_rules or []
            )
            if semantic_key and is_canonical_semantic_key(semantic_key)
        }

        invalid: Set[str] = set()
        for field in deduplication_fields or []:
            field_text = str(field).strip()
            if not field_text:
                continue
            semantic_key = normalize_semantic_key(field_text)
            if not semantic_key or not is_canonical_semantic_key(semantic_key):
                invalid.add(field_text)
                continue
            if semantic_key not in confirmed_semantic_keys and semantic_key not in derived_semantic_keys:
                invalid.add(field_text)
        return invalid
