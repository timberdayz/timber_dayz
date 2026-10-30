from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

from backend.services.semantic_field_registry import (
    REVIEW_STATUS_CONFIRMED_NON_SEMANTIC,
    REVIEW_STATUS_CONFIRMED_SEMANTIC,
    is_canonical_semantic_key,
    is_confirmed_semantic_binding,
    normalize_semantic_key,
    parse_rule_provided_semantic_keys,
    resolve_binding_review_status,
)
from backend.services.template_hash_policy import (
    SYSTEM_SCOPE_FIELD_SET,
    HashPolicyResult,
    TemplateHashPolicyService,
)
from backend.services.semantic_hash_policy_service import SemanticHashPolicyService


UNRESOLVED_DEDUPLICATION_FIELDS_PREFIX = (
    "deduplication_fields must resolve to confirmed semantic bindings or parse rules: "
)


@dataclass(frozen=True)
class TemplateSaveReadinessResult:
    can_save: bool
    normalized_deduplication_fields: List[str]
    normalized_header_bindings: List[Dict[str, Any]]
    hash_policy: HashPolicyResult
    blocking_errors: List[str]
    blocking_messages: List[str]
    warnings: List[str]
    unresolved_deduplication_fields: List[str]
    hash_options: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        payload = self.hash_policy.to_dict()
        payload.update(
            {
                "passed": self.can_save,
                "can_save": self.can_save,
                "blocking_errors": list(self.blocking_errors),
                "blocking_messages": list(self.blocking_messages),
                "warnings": list(self.warnings),
                "normalized_deduplication_fields": list(
                    self.normalized_deduplication_fields
                ),
                "normalized_header_bindings": [
                    dict(binding) for binding in self.normalized_header_bindings
                ],
                "unresolved_deduplication_fields": list(
                    self.unresolved_deduplication_fields
                ),
                "hash_options": [dict(option) for option in self.hash_options],
            }
        )
        return payload


def normalize_deduplication_fields_for_template(
    deduplication_fields: list[str] | None,
    header_bindings: list[dict[str, Any]] | None,
) -> list[str]:
    normalized_fields: list[str] = []
    binding_by_raw = {
        str(binding.get("raw_name", "")).strip().lower(): binding
        for binding in (header_bindings or [])
        if str(binding.get("raw_name", "")).strip()
    }
    seen = set()

    for field in deduplication_fields or []:
        if is_canonical_semantic_key(field):
            normalized_field = normalize_semantic_key(field) or str(field).strip()
        else:
            normalized_field = str(field).strip()
        binding = binding_by_raw.get(str(field).strip().lower())
        if binding:
            candidate_semantic_key = normalize_semantic_key(
                binding.get("semantic_key")
                or binding.get("semantic_role")
                or binding.get("display_name")
            )
            if is_canonical_semantic_key(candidate_semantic_key):
                normalized_field = candidate_semantic_key or normalized_field
        lowered = normalized_field.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        normalized_fields.append(normalized_field)
    return normalized_fields


def validate_deduplication_fields_against_bindings(
    deduplication_fields: list[str],
    header_columns: list[str],
    header_bindings: list[dict[str, Any]],
    field_parse_rules: list[dict[str, Any]] | None = None,
) -> list[str]:
    binding_by_raw = {
        str(binding.get("raw_name", "")).strip().lower(): binding
        for binding in header_bindings
        if str(binding.get("raw_name", "")).strip()
    }
    bindings_by_semantic: dict[str, list[dict[str, Any]]] = {}
    for binding in header_bindings:
        semantic_key = normalize_semantic_key(
            binding.get("semantic_key")
            or binding.get("semantic_role")
            or binding.get("display_name")
        )
        if semantic_key:
            bindings_by_semantic.setdefault(semantic_key, []).append(binding)
    derived_semantic_keys = parse_rule_provided_semantic_keys(field_parse_rules)

    header_lookup = {str(column).strip().lower() for column in header_columns}
    invalid_fields: list[str] = []
    non_semantic_diagnostics: list[str] = []

    for field in deduplication_fields:
        field_text = str(field).strip()
        field_key = field_text.lower()
        normalized_key = normalize_semantic_key(field_text)
        # 系统范围字段由后端自动追加到 hash，不需要用户确认映射，
        # 与 hash 闸门（template_hash_policy）保持同一口径。
        if normalized_key and normalized_key in SYSTEM_SCOPE_FIELD_SET:
            continue
        raw_binding = binding_by_raw.get(field_key)
        semantic_bindings = bindings_by_semantic.get(normalized_key or "", [])
        candidate_bindings = [
            binding for binding in [raw_binding, *semantic_bindings] if binding
        ]
        for binding in candidate_bindings:
            if (
                resolve_binding_review_status(binding)
                == REVIEW_STATUS_CONFIRMED_NON_SEMANTIC
            ):
                raw_name = str(binding.get("raw_name") or field_text).strip()
                if raw_name and raw_name not in non_semantic_diagnostics:
                    non_semantic_diagnostics.append(raw_name)

        confirmed_semantic_bindings = [
            binding
            for binding in semantic_bindings
            if is_confirmed_semantic_binding(binding)
        ]
        if (
            normalized_key
            and is_canonical_semantic_key(normalized_key)
            and confirmed_semantic_bindings
        ):
            continue
        if normalized_key and normalized_key in derived_semantic_keys:
            continue
        raw_semantic_key = None
        if raw_binding:
            raw_semantic_key = normalize_semantic_key(
                raw_binding.get("semantic_key") or raw_binding.get("semantic_role")
            )
        if (
            field_key in header_lookup
            and raw_binding
            and is_confirmed_semantic_binding(raw_binding)
            and raw_semantic_key
            and is_canonical_semantic_key(raw_semantic_key)
        ):
            continue
        invalid_fields.append(normalized_key or field_text)

    if invalid_fields:
        message = UNRESOLVED_DEDUPLICATION_FIELDS_PREFIX + ", ".join(invalid_fields)
        if non_semantic_diagnostics:
            message += "; non-semantic source fields are diagnostic only: " + ", ".join(
                non_semantic_diagnostics
            )
        raise ValueError(message)
    return invalid_fields


def sync_hash_participation_from_deduplication_fields(
    header_bindings: list[dict[str, Any]],
    deduplication_fields: list[str],
) -> list[dict[str, Any]]:
    selected_hash_keys = {
        normalize_semantic_key(field)
        for field in deduplication_fields or []
        if normalize_semantic_key(field)
    }
    synced: list[dict[str, Any]] = []
    for binding in header_bindings or []:
        next_binding = dict(binding)
        semantic_key = normalize_semantic_key(next_binding.get("semantic_key"))
        if not is_confirmed_semantic_binding(next_binding) or not semantic_key:
            next_binding["hash_participates"] = False
        else:
            next_binding["hash_participates"] = semantic_key in selected_hash_keys
        synced.append(next_binding)
    return synced


class TemplateSaveReadinessService:
    def __init__(self) -> None:
        self._hash_policy_service = TemplateHashPolicyService()
        self._semantic_hash_policy_service = SemanticHashPolicyService()

    def build_workbench_effective_deduplication_fields(
        self,
        *,
        data_domain: str,
        granularity: str | None = None,
        sub_domain: str | None = None,
        deduplication_fields: Iterable[str] | None = None,
        header_bindings: Iterable[Dict[str, Any]] | None = None,
        field_parse_rules: Iterable[Dict[str, Any]] | None = None,
    ) -> List[str]:
        """算出「走到工作台提交那一刻，真正会被提交的去重字段」。

        为什么需要这个
        --------------
        模板里**存量**的去重字段 ≠ 提交时提交的去重字段：

        - 工作台会把**未确认的表头列**剔除（用户没点过确认 ⇒ 不进 hash）；
        - 工作台会剔除**由解析规则派生**的字段（如 metric_date）；
        - 工作台会剔除**不可参与 hash**的语义键（度量字段、system_scope）；
        - 工作台会自动**补齐**该数据域必需的身份键（前提是文件里认得出这一列）。

        也就是说：同一个模板，"直接拿库里的配置去评估" 和 "走一遍工作台再评估"
        会得到**两个不同的结论**。体检脚本要回答的是后者
        （源文件一变，用户去工作台更新模板，到底能不能存下来），
        所以这里把工作台的规则在后端**等价实现**一遍。

        与前端的对应关系（改一边必须改另一边）：

        - ``frontend/src/domains/data_platform/utils/deduplicationSelection.js``
          的 ``normalizeDeduplicationSelection`` → 剔除未确认列 / 派生字段 / 不可参与 hash 的键；
        - ``frontend/src/components/dataSync/TemplateUpdateWorkbenchDrawer.vue``
          的 ``mergeRecommendedIdentityFields`` → 补齐域必需身份键。
        """
        bindings = [item for item in (header_bindings or []) if isinstance(item, dict)]
        binding_by_raw: Dict[str, Dict[str, Any]] = {}
        confirmed_keys: set[str] = set()
        for binding in bindings:
            raw_name = str(binding.get("raw_name") or "").strip()
            if raw_name:
                binding_by_raw.setdefault(raw_name.lower(), binding)
            semantic_key = normalize_semantic_key(
                binding.get("semantic_key") or binding.get("semantic_role")
            )
            if semantic_key and is_confirmed_semantic_binding(binding):
                confirmed_keys.add(semantic_key)

        derived_keys = {
            key
            for key in (
                normalize_semantic_key(
                    rule.get("target_field")
                    or rule.get("semantic_key")
                    or rule.get("field")
                )
                for rule in (field_parse_rules or [])
                if isinstance(rule, dict)
            )
            if key
        }

        eligible_keys = {
            option["semantic_key"]
            for option in self._semantic_hash_policy_service.build_options(
                data_domain=data_domain,
                granularity=granularity,
                sub_domain=sub_domain,
                header_bindings=bindings,
            )
            if option.get("eligible")
        }

        effective: List[str] = []
        seen: set[str] = set()

        def push(value: str) -> None:
            text = str(value or "").strip()
            if not text:
                return
            lowered = text.lower()
            if lowered in seen:
                return
            seen.add(lowered)
            effective.append(text)

        for raw_field in deduplication_fields or []:
            field_text = str(raw_field or "").strip()
            if not field_text:
                continue
            binding = binding_by_raw.get(field_text.lower())
            if binding is not None:
                # 用户选的是原始表头名：必须落到已确认的语义绑定上才允许提交。
                if (
                    resolve_binding_review_status(binding)
                    != REVIEW_STATUS_CONFIRMED_SEMANTIC
                ):
                    continue
                semantic_key = normalize_semantic_key(
                    binding.get("semantic_key") or binding.get("semantic_role")
                )
                if semantic_key and eligible_keys and semantic_key not in eligible_keys:
                    continue
                if semantic_key:
                    push(semantic_key)
                continue

            normalized = normalize_semantic_key(field_text)
            if normalized and normalized in derived_keys:
                # 由解析规则派生（文件伴生日期等），不作为去重字段提交。
                continue
            if normalized and normalized in confirmed_keys:
                if eligible_keys and normalized not in eligible_keys:
                    continue
                push(normalized)
                continue
            # 当前绑定集里找不到该字段的已确认绑定：保留并汇报（前端同样保留）。
            push(field_text)

        # 自动补齐域必需身份键（只在文件里认得出这一列时补）。
        for key in self._hash_policy_service.required_identity_keys(
            data_domain, sub_domain
        ):
            if key in confirmed_keys:
                push(key)

        return effective

    def assess(
        self,
        *,
        data_domain: str,
        granularity: str | None,
        sub_domain: str | None,
        deduplication_fields: list[str],
        header_columns: list[str],
        header_bindings: list[dict[str, Any]],
        field_parse_rules: list[dict[str, Any]],
        sample_rows: Iterable[dict[str, Any]] | None = None,
    ) -> TemplateSaveReadinessResult:
        normalized_deduplication_fields = normalize_deduplication_fields_for_template(
            deduplication_fields,
            header_bindings,
        )
        unresolved_deduplication_fields: list[str] = []
        binding_errors: list[str] = []
        try:
            validate_deduplication_fields_against_bindings(
                normalized_deduplication_fields,
                header_columns,
                header_bindings,
                field_parse_rules,
            )
        except ValueError as exc:
            binding_errors.append(str(exc))
            prefix = UNRESOLVED_DEDUPLICATION_FIELDS_PREFIX
            if str(exc).startswith(prefix):
                unresolved_text = str(exc)[len(prefix) :].split(";", 1)[0]
                unresolved_deduplication_fields = [
                    item.strip() for item in unresolved_text.split(",") if item.strip()
                ]

        normalized_header_bindings = sync_hash_participation_from_deduplication_fields(
            header_bindings,
            normalized_deduplication_fields,
        )
        hash_options = self._semantic_hash_policy_service.build_options(
            data_domain=data_domain,
            granularity=granularity,
            sub_domain=sub_domain,
            header_bindings=normalized_header_bindings,
        )
        hash_policy = self._hash_policy_service.validate(
            data_domain=data_domain,
            granularity=granularity,
            sub_domain=sub_domain,
            deduplication_fields=normalized_deduplication_fields,
            header_bindings=normalized_header_bindings,
            field_parse_rules=field_parse_rules,
            sample_rows=sample_rows,
        )
        blocking_errors = [*binding_errors, *list(hash_policy.blocking_errors)]
        blocking_messages: list[str] = []
        if unresolved_deduplication_fields:
            blocking_messages.append(
                "去重字段无法解析到已确认的语义映射，请先确认映射："
                + "、".join(unresolved_deduplication_fields)
            )
        blocking_messages.extend(list(hash_policy.blocking_messages))
        warnings = list(hash_policy.warnings)
        can_save = not blocking_errors and hash_policy.passed
        return TemplateSaveReadinessResult(
            can_save=can_save,
            normalized_deduplication_fields=normalized_deduplication_fields,
            normalized_header_bindings=normalized_header_bindings,
            hash_policy=hash_policy,
            blocking_errors=blocking_errors,
            blocking_messages=blocking_messages,
            warnings=warnings,
            unresolved_deduplication_fields=unresolved_deduplication_fields,
            hash_options=hash_options,
        )
