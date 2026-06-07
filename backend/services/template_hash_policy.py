"""Lightweight hash identity policy for sync templates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Set


@dataclass(frozen=True)
class HashPolicyResult:
    passed: bool
    blocking_errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    resolved_keys: List[str] = field(default_factory=list)


class TemplateHashPolicyService:
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
        resolved_keys = self._resolved_semantic_keys(deduplication_fields, header_bindings, field_parse_rules)
        errors: List[str] = []

        warnings: List[str] = []

        if domain == "products" and grain == "daily":
            has_product_identity = bool(resolved_keys & {"product_id", "platform_sku"})
            if has_product_identity and not (resolved_keys & self.PRODUCT_DATE_KEYS):
                errors.append("日级商品指标需要 product_id + metric_date，否则不同日期同商品会互相覆盖。")
            elif not has_product_identity:
                warnings.append("日级商品指标建议确认 product_id 或 platform_sku 作为商品身份字段。")
        elif domain == "products" and grain in {"weekly", "monthly"}:
            has_product_identity = bool(resolved_keys & {"product_id", "platform_sku"})
            if has_product_identity and not (resolved_keys & self.PERIOD_DATE_KEYS):
                errors.append("周期商品指标需要 product_id + period_start_date，否则不同周期同商品会互相覆盖。")
            elif not has_product_identity:
                warnings.append("周期商品指标建议确认 product_id 或 platform_sku 作为商品身份字段。")
        elif domain == "orders":
            if "order_id" not in resolved_keys:
                errors.append("订单数据需要 order_id 作为去重身份字段。")
        elif domain == "analytics":
            missing = {"metric_date", "shop_id"} - resolved_keys
            if missing:
                warnings.append("经营分析数据建议使用 metric_date + shop_id 作为去重身份字段。")
        elif domain == "inventory":
            has_date = bool(resolved_keys & self.PERIOD_DATE_KEYS)
            has_product = bool(resolved_keys & {"product_id", "platform_sku"})
            if not has_date or not has_product:
                errors.append("库存数据需要日期字段 + product_id 或 platform_sku 作为去重身份字段。")

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
        keys = {str(field).strip() for field in deduplication_fields or [] if str(field).strip()}
        for binding in header_bindings or []:
            semantic_key = binding.get("semantic_key")
            source_header = binding.get("source_header") or binding.get("raw_name") or binding.get("display_name")
            if semantic_key and semantic_key in keys:
                keys.add(str(semantic_key))
            if source_header in keys and semantic_key:
                keys.add(str(semantic_key))
        for rule in field_parse_rules or []:
            target = rule.get("target_field") or rule.get("semantic_key") or rule.get("field")
            if target:
                keys.add(str(target))
        return keys
