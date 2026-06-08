"""Hash identity policy for sync templates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Set

from backend.services.semantic_field_registry import (
    is_canonical_semantic_key,
    is_hash_identity_semantic_key,
    normalize_semantic_key,
    resolve_semantic_value,
)


SYSTEM_SCOPE_FIELDS = ["platform_code", "shop_id", "data_domain", "granularity", "sub_domain"]
SYSTEM_SCOPE_FIELD_SET = set(SYSTEM_SCOPE_FIELDS)
FILE_DATE_SOURCE_COLUMNS = {"__file_date_from__", "__file_date_to__"}


@dataclass(frozen=True)
class HashPolicyResult:
    passed: bool
    blocking_errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    resolved_keys: List[str] = field(default_factory=list)
    requirement_groups: List[Dict[str, Any]] = field(default_factory=list)
    effective_components: Dict[str, Any] = field(default_factory=dict)
    invalid_keys: List[str] = field(default_factory=list)
    missing_required_groups: List[Dict[str, Any]] = field(default_factory=list)
    sample_diagnostics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "blocking_errors": list(self.blocking_errors),
            "warnings": list(self.warnings),
            "resolved_keys": list(self.resolved_keys),
            "requirement_groups": [dict(group) for group in self.requirement_groups],
            "effective_components": dict(self.effective_components),
            "invalid_keys": list(self.invalid_keys),
            "missing_required_groups": [dict(group) for group in self.missing_required_groups],
            "sample_diagnostics": dict(self.sample_diagnostics),
        }


class TemplateHashPolicyService:
    PRODUCT_IDENTITY_KEYS = ["product_id", "platform_sku"]
    PRODUCT_DAILY_DATE_KEYS = ["metric_date"]
    PERIOD_DATE_KEYS = ["metric_date", "period_start_date", "period_end_date"]
    ORDER_DETAIL_SUB_DOMAINS = {"detail", "details", "line", "lines", "order_detail", "order_lines"}

    def validate(
        self,
        *,
        data_domain: str,
        granularity: str | None,
        deduplication_fields: Iterable[str],
        header_bindings: Iterable[Dict[str, Any]],
        field_parse_rules: Iterable[Dict[str, Any]],
        sub_domain: str | None = None,
        sample_rows: Iterable[Dict[str, Any]] | None = None,
    ) -> HashPolicyResult:
        domain = (data_domain or "").lower()
        grain = (granularity or "").lower()
        sub_domain_key = (sub_domain or "").lower()
        resolved_keys = self._resolved_semantic_keys(
            deduplication_fields,
            header_bindings,
            field_parse_rules,
        )
        derived_keys = self._derived_selected_keys(deduplication_fields, field_parse_rules)
        invalid_keys = sorted(
            self._invalid_deduplication_keys(
                deduplication_fields,
                header_bindings,
                field_parse_rules,
            )
        )

        errors: List[str] = []
        warnings: List[str] = []
        requirement_groups: List[Dict[str, Any]] = []

        if invalid_keys:
            errors.append(
                "deduplication_fields must be confirmed semantic keys: "
                + ", ".join(invalid_keys)
            )

        def add_any_group(
            *,
            key: str,
            label: str,
            accepted_keys: List[str],
            message: str,
            legacy_error: str | None = None,
        ) -> None:
            selected_keys = [item for item in accepted_keys if item in resolved_keys]
            passed = bool(selected_keys)
            group = {
                "key": key,
                "label": label,
                "severity": "blocking",
                "requirement_type": "any_of",
                "accepted_keys": list(accepted_keys),
                "selected_keys": selected_keys,
                "missing_keys": [] if passed else list(accepted_keys),
                "passed": passed,
                "message": message,
            }
            requirement_groups.append(group)
            if not passed:
                errors.append(legacy_error or message)

        if domain == "products" and grain == "daily":
            add_any_group(
                key="products_identity",
                label="商品身份字段",
                accepted_keys=self.PRODUCT_IDENTITY_KEYS,
                message="products daily 需要选择 product_id 或 platform_sku。",
                legacy_error=(
                    "products daily data requires product_id or platform_sku "
                    "as a semantic hash identity field."
                ),
            )
            add_any_group(
                key="products_metric_date",
                label="统计日期",
                accepted_keys=self.PRODUCT_DAILY_DATE_KEYS,
                message="products daily 需要选择 metric_date，避免不同日期互相覆盖。",
                legacy_error=(
                    "daily product metrics require product_id/platform_sku + "
                    "metric_date to avoid cross-date overwrites."
                ),
            )
        elif domain == "products" and grain in {"weekly", "monthly"}:
            add_any_group(
                key="products_identity",
                label="商品身份字段",
                accepted_keys=self.PRODUCT_IDENTITY_KEYS,
                message=f"products {grain} 需要选择 product_id 或 platform_sku。",
                legacy_error=(
                    "products period data requires product_id or platform_sku "
                    "as a semantic hash identity field."
                ),
            )
            add_any_group(
                key="products_period_date",
                label="周期字段",
                accepted_keys=self.PERIOD_DATE_KEYS,
                message=(
                    f"products {grain} 需要选择 metric_date、period_start_date 或 "
                    "period_end_date，避免不同周期互相覆盖。"
                ),
                legacy_error=(
                    "period product metrics require product_id/platform_sku + "
                    "period date to avoid cross-period overwrites."
                ),
            )
        elif domain == "orders":
            add_any_group(
                key="orders_identity",
                label="订单身份字段",
                accepted_keys=["order_id"],
                message="orders 需要选择 order_id。",
                legacy_error="orders data requires order_id as a semantic hash identity field.",
            )
            if sub_domain_key in self.ORDER_DETAIL_SUB_DOMAINS:
                add_any_group(
                    key="orders_line_identity",
                    label="订单明细身份字段",
                    accepted_keys=["line_id", "sku_id"],
                    message="orders detail 需要选择 line_id 或 sku_id，避免订单明细互相覆盖。",
                )
        elif domain in {"analytics", "traffic"}:
            add_any_group(
                key=f"{domain}_date",
                label="统计日期",
                accepted_keys=self.PERIOD_DATE_KEYS,
                message=f"{domain} 需要选择 metric_date、period_start_date 或 period_end_date。",
                legacy_error=(
                    f"{domain} daily data requires metric_date as a semantic hash identity field."
                ),
            )
        elif domain == "inventory":
            add_any_group(
                key="inventory_product_identity",
                label="商品身份字段",
                accepted_keys=self.PRODUCT_IDENTITY_KEYS,
                message="inventory 需要选择 product_id 或 platform_sku。",
            )
            add_any_group(
                key="inventory_warehouse",
                label="仓库字段",
                accepted_keys=["warehouse_name"],
                message="inventory 需要选择 warehouse_name。",
            )
            add_any_group(
                key="inventory_date",
                label="快照日期",
                accepted_keys=self.PERIOD_DATE_KEYS,
                message="inventory 需要选择 metric_date、period_start_date 或 period_end_date。",
            )
        elif domain == "services":
            add_any_group(
                key="services_identity",
                label="服务身份字段",
                accepted_keys=["service_id"],
                message="services 需要选择 service_id。",
            )
            add_any_group(
                key="services_date",
                label="统计日期",
                accepted_keys=self.PERIOD_DATE_KEYS,
                message="services 需要选择 metric_date、period_start_date 或 period_end_date。",
            )

        effective_components = self._effective_components(
            deduplication_fields=deduplication_fields,
            derived_keys=derived_keys,
        )
        sample_diagnostics, sample_warnings = self._sample_diagnostics(
            sample_rows=sample_rows,
            identity_fields=[
                *effective_components.get("user_identity_fields", []),
                *effective_components.get("derived_identity_fields", []),
            ],
            header_bindings=header_bindings,
        )
        warnings.extend(sample_warnings)
        missing_required_groups = [
            group for group in requirement_groups if group.get("severity") == "blocking" and not group.get("passed")
        ]

        return HashPolicyResult(
            passed=not errors,
            blocking_errors=errors,
            warnings=warnings,
            resolved_keys=sorted(resolved_keys),
            requirement_groups=requirement_groups,
            effective_components=effective_components,
            invalid_keys=invalid_keys,
            missing_required_groups=missing_required_groups,
            sample_diagnostics=sample_diagnostics,
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

    def _derived_selected_keys(
        self,
        deduplication_fields: Iterable[str],
        field_parse_rules: Iterable[Dict[str, Any]],
    ) -> Set[str]:
        selected_keys = {
            semantic_key
            for semantic_key in (normalize_semantic_key(field) for field in deduplication_fields or [])
            if semantic_key
        }
        derived_keys: Set[str] = set()
        for rule in field_parse_rules or []:
            semantic_key = normalize_semantic_key(rule.get("target_field") or rule.get("semantic_key") or rule.get("field"))
            source_column = str(rule.get("source_column") or "").strip()
            if semantic_key in selected_keys and source_column in FILE_DATE_SOURCE_COLUMNS:
                derived_keys.add(semantic_key)
        return derived_keys

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
            if semantic_key in SYSTEM_SCOPE_FIELD_SET:
                continue
            if not is_hash_identity_semantic_key(semantic_key):
                invalid.add(semantic_key)
                continue
            if semantic_key not in confirmed_semantic_keys and semantic_key not in derived_semantic_keys:
                invalid.add(field_text)
        return invalid

    def _effective_components(
        self,
        *,
        deduplication_fields: Iterable[str],
        derived_keys: Set[str],
    ) -> Dict[str, Any]:
        user_identity_fields: List[str] = []
        seen_user: Set[str] = set()
        for field in deduplication_fields or []:
            semantic_key = normalize_semantic_key(field)
            if (
                not semantic_key
                or semantic_key in SYSTEM_SCOPE_FIELD_SET
                or semantic_key in derived_keys
                or not is_hash_identity_semantic_key(semantic_key)
            ):
                continue
            if semantic_key in seen_user:
                continue
            seen_user.add(semantic_key)
            user_identity_fields.append(semantic_key)

        derived_identity_fields = [
            field
            for field in (normalize_semantic_key(item) for item in deduplication_fields or [])
            if field in derived_keys
        ]
        derived_identity_fields = list(dict.fromkeys(derived_identity_fields))
        final_fields = [*SYSTEM_SCOPE_FIELDS, *user_identity_fields, *derived_identity_fields]
        return {
            "system_scope_fields": list(SYSTEM_SCOPE_FIELDS),
            "user_identity_fields": user_identity_fields,
            "derived_identity_fields": derived_identity_fields,
            "final_fields": final_fields,
        }

    def _sample_diagnostics(
        self,
        *,
        sample_rows: Iterable[Dict[str, Any]] | None,
        identity_fields: List[str],
        header_bindings: Iterable[Dict[str, Any]],
    ) -> tuple[Dict[str, Any], List[str]]:
        rows = [row for row in (sample_rows or []) if isinstance(row, dict)]
        diagnostics: Dict[str, Any] = {
            "row_count": len(rows),
            "field_null_rates": {},
            "hash_distinct_count": 0,
        }
        warnings: List[str] = []
        if not rows or not identity_fields:
            return diagnostics, warnings

        row_signatures: List[tuple[str, ...]] = []
        for field in identity_fields:
            null_count = 0
            values: List[str] = []
            for row in rows:
                value, _source = resolve_semantic_value(row, field, header_bindings)
                text = "" if value is None else str(value).strip()
                if not text:
                    null_count += 1
                values.append(text)
            null_rate = null_count / len(rows)
            diagnostics["field_null_rates"][field] = null_rate
            if null_rate > 0.3:
                warnings.append(
                    f"sample hash field {field} null rate {null_rate:.0%} exceeds 30%; verify semantic binding."
                )

        for row in rows:
            parts: List[str] = []
            for field in identity_fields:
                value, _source = resolve_semantic_value(row, field, header_bindings)
                parts.append("" if value is None else str(value).strip())
            row_signatures.append(tuple(parts))

        diagnostics["hash_distinct_count"] = len(set(row_signatures))
        if len(rows) > 1 and diagnostics["hash_distinct_count"] == 1:
            warnings.append(
                "sample hash distinct count is 1 for multiple rows; duplicate/upsert collision risk is high."
            )
        return diagnostics, warnings
