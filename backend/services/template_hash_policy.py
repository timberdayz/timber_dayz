"""Hash identity policy for sync templates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Set

from backend.services.semantic_field_registry import (
    REVIEW_STATUS_CONFIRMED_SEMANTIC,
    is_canonical_semantic_key,
    is_confirmed_semantic_binding,
    is_hash_identity_semantic_key,
    normalize_semantic_key,
    parse_rule_provided_semantic_keys,
    resolve_semantic_value,
)
from backend.services.semantic_hash_policy_service import SemanticHashPolicyService


SYSTEM_SCOPE_FIELDS = ["platform_code", "shop_id", "data_domain", "granularity", "sub_domain"]
SYSTEM_SCOPE_FIELD_SET = set(SYSTEM_SCOPE_FIELDS)
FILE_DATE_SOURCE_COLUMNS = {"__file_date_from__", "__file_date_to__"}
HOUR_IDENTITY_KEYS = {"period_start_time", "period_end_time"}
DATE_IDENTITY_KEY_ORDER = [
    "metric_date",
    "period_start_date",
    "period_end_date",
    "period_start_time",
    "period_end_time",
]
DATE_IDENTITY_KEYS = set(DATE_IDENTITY_KEY_ORDER)


@dataclass(frozen=True)
class HashPolicyResult:
    passed: bool
    blocking_errors: List[str] = field(default_factory=list)
    blocking_messages: List[str] = field(default_factory=list)
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
            "blocking_messages": list(self.blocking_messages),
            "warnings": list(self.warnings),
            "resolved_keys": list(self.resolved_keys),
            "requirement_groups": [dict(group) for group in self.requirement_groups],
            "effective_components": dict(self.effective_components),
            "invalid_keys": list(self.invalid_keys),
            "missing_required_groups": [dict(group) for group in self.missing_required_groups],
            "sample_diagnostics": dict(self.sample_diagnostics),
        }


class TemplateHashPolicyService:
    PRODUCT_REQUIRED_IDENTITY_KEYS = ["product_id"]
    PRODUCT_STRONG_IDENTITY_KEYS = ["product_id", "platform_sku", "sku_id"]
    PRODUCT_IDENTITY_KEYS = [*PRODUCT_STRONG_IDENTITY_KEYS]
    PRODUCT_DAILY_DATE_KEYS = ["metric_date"]
    PERIOD_DATE_KEYS = ["metric_date", "period_start_date", "period_end_date"]
    PRODUCT_PERIOD_BOUNDARY_KEYS = ["period_start_date", "period_end_date"]
    ORDER_DETAIL_SUB_DOMAINS = {"detail", "details", "line", "lines", "order_detail", "order_lines"}
    # 店铺级服务报表：一份数据就是「一个店铺一个周期」，源文件里没有客服维度列
    # （表头形如 日期 / 服务的访客 / 已回答的问题 / …）。
    # 这类报表的行身份由「店铺 + 周期」承担：
    #   - 店铺 = ``shop_id``，属于系统范围字段，入库时自动进入 hash；
    #   - 周期 = 下面的 ``services_date`` 组（metric_date / 周期起止）。
    # 因此它们**不需要** service_id，也就不该被 ``services_identity`` 卡住。
    # ⚠️ 只豁免这两个子域；有客服维度列的服务报表（sub_domain 为空或别的值）照旧要求 service_id。
    SHOPI_LEVEL_SERVICES_SUB_DOMAINS = {"ai_assistant", "agent"}

    def __init__(self) -> None:
        self.semantic_hash_policy = SemanticHashPolicyService()

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
        auto_date_sources = self._auto_date_identity_sources(field_parse_rules)
        auto_date_keys = set(auto_date_sources)
        resolved_keys.update(auto_date_keys)
        derived_sources = self._file_companion_date_sources(
            deduplication_fields, field_parse_rules
        )
        derived_keys = set(derived_sources)
        invalid_keys = sorted(
            self._invalid_deduplication_keys(
                data_domain=domain,
                granularity=grain,
                sub_domain=sub_domain_key,
                deduplication_fields=deduplication_fields,
                header_bindings=header_bindings,
                field_parse_rules=field_parse_rules,
            )
        )

        errors: List[str] = []
        messages: List[str] = []
        warnings: List[str] = []
        requirement_groups: List[Dict[str, Any]] = []

        if invalid_keys:
            errors.append(
                "deduplication_fields must be confirmed semantic keys: "
                + ", ".join(invalid_keys)
            )
            messages.append(
                "去重字段必须是对应的语义键（需已确认映射）：" + "、".join(invalid_keys)
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
                "legacy_error": legacy_error,
            }
            requirement_groups.append(group)
            if not passed:
                errors.append(legacy_error or message)
                messages.append(message)

        def add_all_group(
            *,
            key: str,
            label: str,
            accepted_keys: List[str],
            message: str,
            legacy_error: str | None = None,
        ) -> None:
            selected_keys = [item for item in accepted_keys if item in resolved_keys]
            missing_keys = [item for item in accepted_keys if item not in resolved_keys]
            passed = not missing_keys
            group = {
                "key": key,
                "label": label,
                "severity": "blocking",
                "requirement_type": "all_of",
                "accepted_keys": list(accepted_keys),
                "selected_keys": selected_keys,
                "missing_keys": missing_keys,
                "passed": passed,
                "message": message,
                "legacy_error": legacy_error,
            }
            requirement_groups.append(group)
            if not passed:
                errors.append(legacy_error or message)
                messages.append(message)

        def add_satisfied_group(
            *,
            key: str,
            label: str,
            accepted_keys: List[str],
            message: str,
        ) -> None:
            """登记一个**天然满足**的要求组。

            用于「这类模板的行身份由系统范围字段（店铺）+ 周期承担」的场景：
            仍然要在 ``requirement_groups`` 里出现（前端面板要显示出来），
            但**不阻塞保存**，也不进 ``errors``。
            """
            requirement_groups.append(
                {
                    "key": key,
                    "label": label,
                    "severity": "blocking",
                    "requirement_type": "any_of",
                    "accepted_keys": list(accepted_keys),
                    "selected_keys": [],
                    "missing_keys": [],
                    "passed": True,
                    "message": message,
                    "legacy_error": None,
                }
            )

        if domain == "products" and grain == "daily":
            add_any_group(
                key="products_identity",
                label="商品主身份字段",
                accepted_keys=self.PRODUCT_REQUIRED_IDENTITY_KEYS,
                message="products daily 需要选择 product_id。",
                legacy_error=(
                    "products daily data requires product_id "
                    "as a semantic hash identity field."
                ),
            )
            add_any_group(
                key="products_metric_date",
                label="统计日期",
                accepted_keys=self.PRODUCT_DAILY_DATE_KEYS,
                message="products daily 需要选择 metric_date，避免不同日期互相覆盖。",
                legacy_error=(
                    "daily product metrics require product_id + "
                    "metric_date to avoid cross-date overwrites."
                ),
            )
        elif domain == "products" and grain in {"weekly", "monthly"}:
            add_any_group(
                key="products_identity",
                label="商品主身份字段",
                accepted_keys=self.PRODUCT_REQUIRED_IDENTITY_KEYS,
                message=f"products {grain} 需要选择 product_id。",
                legacy_error=(
                    "products period data requires product_id "
                    "as a semantic hash identity field."
                ),
            )
            if "metric_date" in derived_keys:
                requirement_groups.append(
                    {
                        "key": "products_period_date",
                        "label": "周期字段",
                        "severity": "blocking",
                        "requirement_type": "any_of",
                        "accepted_keys": ["metric_date", *self.PRODUCT_PERIOD_BOUNDARY_KEYS],
                        "selected_keys": ["metric_date"],
                        "missing_keys": [],
                        "passed": True,
                        "message": f"products {grain} uses metric_date as period identity.",
                        "legacy_error": None,
                    }
                )
            else:
                add_all_group(
                    key="products_period_date",
                    label="周期字段",
                    accepted_keys=self.PRODUCT_PERIOD_BOUNDARY_KEYS,
                    message=(
                        f"products {grain} 需要周期开始日期 period_start_date 和 "
                        "周期结束日期 period_end_date，避免不同周期互相覆盖。"
                    ),
                    legacy_error=(
                        "period product metrics require product_id + "
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
            if sub_domain_key in self.SHOPI_LEVEL_SERVICES_SUB_DOMAINS:
                # 店铺级报表：身份 = 店铺 + 周期，不需要 service_id。
                add_satisfied_group(
                    key="services_identity",
                    label="服务身份字段（店铺级）",
                    accepted_keys=["service_id"],
                    message=(
                        f"services {sub_domain_key} 是店铺级报表："
                        "行身份由「店铺 + 周期」承担（店铺是系统范围字段，"
                        "周期见下方统计日期），不需要 service_id。"
                    ),
                )
            else:
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

        if domain == "products":
            warnings.extend(self._product_identity_warnings(resolved_keys))
        warnings.extend(
            self._semantic_hash_policy_warnings(
                data_domain=domain,
                granularity=grain,
                sub_domain=sub_domain_key,
                deduplication_fields=deduplication_fields,
                header_bindings=header_bindings,
            )
        )

        effective_components = self._effective_components(
            data_domain=domain,
            granularity=grain,
            sub_domain=sub_domain_key,
            deduplication_fields=deduplication_fields,
            derived_keys=derived_keys,
            auto_date_keys=auto_date_keys,
        )
        sample_diagnostics, sample_warnings = self._sample_diagnostics(
            sample_rows=sample_rows,
            identity_fields=[
                *effective_components.get("user_identity_fields", []),
                *effective_components.get("auto_date_identity_fields", []),
            ],
            header_bindings=header_bindings,
            derived_sources={**auto_date_sources, **derived_sources},
            auto_date_sources=auto_date_sources,
        )
        warnings.extend(sample_warnings)
        missing_required_groups = [
            group for group in requirement_groups if group.get("severity") == "blocking" and not group.get("passed")
        ]

        return HashPolicyResult(
            passed=not errors,
            blocking_errors=errors,
            blocking_messages=messages,
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

    def _file_companion_date_sources(
        self,
        deduplication_fields: Iterable[str],
        field_parse_rules: Iterable[Dict[str, Any]],
    ) -> Dict[str, str]:
        """文件伴生日期派生的语义键。

        只有来源列是 ``__file_date_from__`` / ``__file_date_to__`` 的解析规则才算：
        这类日期来自文件名而不是行内数据，同一文件内所有行取值相同，
        因此只能作为"周期标识"，不能作为区分行的身份键。
        """
        selected_keys = {
            semantic_key
            for semantic_key in (normalize_semantic_key(field) for field in deduplication_fields or [])
            if semantic_key
        }
        derived_sources: Dict[str, str] = {}
        for rule in field_parse_rules or []:
            semantic_key = normalize_semantic_key(rule.get("target_field") or rule.get("semantic_key") or rule.get("field"))
            source_column = str(rule.get("source_column") or "").strip()
            if semantic_key in selected_keys and source_column in FILE_DATE_SOURCE_COLUMNS:
                derived_sources[semantic_key] = source_column
        return derived_sources

    def _parse_rule_provided_keys(
        self,
        field_parse_rules: Iterable[Dict[str, Any]],
    ) -> Set[str]:
        """解析规则能够提供数据来源的语义键（见 registry 的同名共享实现）。"""
        return parse_rule_provided_semantic_keys(field_parse_rules)

    def _auto_date_identity_sources(
        self,
        field_parse_rules: Iterable[Dict[str, Any]],
    ) -> Dict[str, str]:
        sources: Dict[str, str] = {}
        source_rank: Dict[str, int] = {}
        for rule in field_parse_rules or []:
            semantic_key = normalize_semantic_key(
                rule.get("target_field") or rule.get("semantic_key") or rule.get("field")
            )
            if semantic_key not in DATE_IDENTITY_KEYS or not is_hash_identity_semantic_key(semantic_key):
                continue
            source_column = str(rule.get("source_column") or "").strip()
            if not source_column:
                continue
            # Source file columns carry row identity; companion dates are lower priority fallbacks.
            rank = 1 if source_column in FILE_DATE_SOURCE_COLUMNS else 2
            if rank >= source_rank.get(semantic_key, 0):
                sources[semantic_key] = source_column
                source_rank[semantic_key] = rank
        return sources

    def _invalid_deduplication_keys(
        self,
        *,
        data_domain: str,
        granularity: str | None,
        sub_domain: str | None,
        deduplication_fields: Iterable[str],
        header_bindings: Iterable[Dict[str, Any]],
        field_parse_rules: Iterable[Dict[str, Any]],
    ) -> Set[str]:
        confirmed_semantic_keys = {
            normalize_semantic_key(binding.get("semantic_key"))
            for binding in header_bindings or []
            if is_confirmed_semantic_binding(binding)
        }
        confirmed_semantic_keys = {key for key in confirmed_semantic_keys if key}
        derived_semantic_keys = self._parse_rule_provided_keys(field_parse_rules)

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
            option = self.semantic_hash_policy.evaluate_option(
                data_domain=data_domain,
                granularity=granularity,
                sub_domain=sub_domain,
                semantic_key=semantic_key,
            )
            if not option.eligible:
                invalid.add(semantic_key)
                continue
            if semantic_key not in confirmed_semantic_keys and semantic_key not in derived_semantic_keys:
                invalid.add(field_text)
        return invalid

    def _effective_components(
        self,
        *,
        data_domain: str,
        granularity: str | None,
        sub_domain: str | None,
        deduplication_fields: Iterable[str],
        derived_keys: Set[str],
        auto_date_keys: Set[str],
    ) -> Dict[str, Any]:
        user_identity_fields: List[str] = []
        seen_user: Set[str] = set()
        for field in deduplication_fields or []:
            semantic_key = normalize_semantic_key(field)
            if (
                not semantic_key
                or semantic_key in SYSTEM_SCOPE_FIELD_SET
                or semantic_key in derived_keys
                or semantic_key in auto_date_keys
            ):
                continue
            option = self.semantic_hash_policy.evaluate_option(
                data_domain=data_domain,
                granularity=granularity,
                sub_domain=sub_domain,
                semantic_key=semantic_key,
            )
            if not option.eligible:
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
        auto_date_identity_fields = [
            field
            for field in DATE_IDENTITY_KEY_ORDER
            if field in auto_date_keys
        ]
        final_fields = [*SYSTEM_SCOPE_FIELDS, *user_identity_fields, *auto_date_identity_fields]
        return {
            "system_scope_fields": list(SYSTEM_SCOPE_FIELDS),
            "user_identity_fields": user_identity_fields,
            "auto_date_identity_fields": auto_date_identity_fields,
            "derived_identity_fields": derived_identity_fields,
            "final_fields": final_fields,
        }

    def _semantic_hash_policy_warnings(
        self,
        *,
        data_domain: str,
        granularity: str | None,
        sub_domain: str | None,
        deduplication_fields: Iterable[str],
        header_bindings: Iterable[Dict[str, Any]],
    ) -> List[str]:
        confirmed_keys = {
            normalize_semantic_key(binding.get("semantic_key"))
            for binding in header_bindings or []
            if is_confirmed_semantic_binding(binding)
        }
        confirmed_keys = {key for key in confirmed_keys if key}
        warnings: List[str] = []
        seen: Set[str] = set()
        for field in deduplication_fields or []:
            semantic_key = normalize_semantic_key(field)
            if not semantic_key or semantic_key in seen:
                continue
            if semantic_key not in confirmed_keys and semantic_key not in DATE_IDENTITY_KEYS:
                continue
            seen.add(semantic_key)
            option = self.semantic_hash_policy.evaluate_option(
                data_domain=data_domain,
                granularity=granularity,
                sub_domain=sub_domain,
                semantic_key=semantic_key,
            )
            if option.warning:
                warnings.append(option.warning)
        return warnings

    def _product_identity_warnings(self, resolved_keys: Set[str]) -> List[str]:
        required_keys = set(self.PRODUCT_REQUIRED_IDENTITY_KEYS)
        if "product_name" in resolved_keys and not (resolved_keys & required_keys):
            return [
                "products 当前仅使用 product_name 参与 Data Hash。商品名可能重名或改名，必须补充 product_id。"
            ]
        return []

    def _sample_diagnostics(
        self,
        *,
        sample_rows: Iterable[Dict[str, Any]] | None,
        identity_fields: List[str],
        header_bindings: Iterable[Dict[str, Any]],
        derived_sources: Dict[str, str] | None = None,
        auto_date_sources: Dict[str, str] | None = None,
    ) -> tuple[Dict[str, Any], List[str]]:
        rows = [row for row in (sample_rows or []) if isinstance(row, dict)]
        derived_sources = dict(derived_sources or {})
        auto_date_sources = dict(auto_date_sources or {})
        diagnostics: Dict[str, Any] = {
            "row_count": len(rows),
            "field_null_rates": {},
            "auto_date_fields": {
                field: {
                    "source_column": source_column,
                    "message": "由模板日期解析规则生成",
                }
                for field, source_column in auto_date_sources.items()
            },
            "derived_fields": {
                field: {
                    "source_column": source_column,
                    "message": "由文件伴生日期生成",
                }
                for field, source_column in derived_sources.items()
            },
            "hash_distinct_count": 0,
        }
        warnings: List[str] = []
        if not rows or not identity_fields:
            return diagnostics, warnings

        row_signatures: List[tuple[str, ...]] = []
        for field in identity_fields:
            if field in derived_sources:
                diagnostics["field_null_rates"][field] = 0.0
                continue
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
                if field in derived_sources:
                    parts.append(f"__derived__:{field}:{derived_sources[field]}")
                else:
                    value, _source = resolve_semantic_value(row, field, header_bindings)
                    parts.append("" if value is None else str(value).strip())
            row_signatures.append(tuple(parts))

        diagnostics["hash_distinct_count"] = len(set(row_signatures))
        if len(rows) > 1 and diagnostics["hash_distinct_count"] == 1:
            warnings.append(
                "sample hash distinct count is 1 for multiple rows; duplicate/upsert collision risk is high."
            )
        warnings.extend(
            self._hour_identity_warnings(
                rows=rows,
                row_signatures=row_signatures,
                selected_identity_fields=identity_fields,
                header_bindings=header_bindings,
            )
        )
        return diagnostics, warnings

    def _hour_identity_warnings(
        self,
        *,
        rows: List[Dict[str, Any]],
        row_signatures: List[tuple[str, ...]],
        selected_identity_fields: List[str],
        header_bindings: Iterable[Dict[str, Any]],
    ) -> List[str]:
        if len(rows) < 2:
            return []
        if len(set(row_signatures)) >= len(rows):
            return []

        selected = {
            semantic_key
            for semantic_key in (normalize_semantic_key(field) for field in selected_identity_fields)
            if semantic_key
        }
        confirmed_hour_keys = []
        seen: Set[str] = set()
        for binding in header_bindings or []:
            if not is_confirmed_semantic_binding(binding):
                continue
            semantic_key = normalize_semantic_key(binding.get("semantic_key"))
            if semantic_key not in HOUR_IDENTITY_KEYS or semantic_key in selected or semantic_key in seen:
                continue
            seen.add(semantic_key)
            confirmed_hour_keys.append(semantic_key)

        warnings: List[str] = []
        for semantic_key in confirmed_hour_keys:
            values = []
            for row in rows:
                value, _source = resolve_semantic_value(row, semantic_key, header_bindings)
                text = "" if value is None else str(value).strip()
                if text:
                    values.append(text)
            if len(set(values)) > 1:
                warnings.append(
                    f"当前 Hash 字段无法区分同日多小时数据，请将 {semantic_key} 加入 Data Hash。"
                )
        return warnings
