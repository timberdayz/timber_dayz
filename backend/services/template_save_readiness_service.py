from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

from backend.services.semantic_field_registry import (
    is_canonical_semantic_key,
    normalize_semantic_key,
)
from backend.services.template_hash_policy import HashPolicyResult, TemplateHashPolicyService
from backend.services.semantic_hash_policy_service import SemanticHashPolicyService


@dataclass(frozen=True)
class TemplateSaveReadinessResult:
    can_save: bool
    normalized_deduplication_fields: List[str]
    normalized_header_bindings: List[Dict[str, Any]]
    hash_policy: HashPolicyResult
    blocking_errors: List[str]
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
                "warnings": list(self.warnings),
                "normalized_deduplication_fields": list(self.normalized_deduplication_fields),
                "normalized_header_bindings": [dict(binding) for binding in self.normalized_header_bindings],
                "unresolved_deduplication_fields": list(self.unresolved_deduplication_fields),
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
                binding.get("semantic_key") or binding.get("semantic_role") or binding.get("display_name")
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
            binding.get("semantic_key") or binding.get("semantic_role") or binding.get("display_name")
        )
        if semantic_key:
            bindings_by_semantic.setdefault(semantic_key, []).append(binding)
    derived_semantic_keys = {
        semantic_key
        for semantic_key in (
            normalize_semantic_key(rule.get("target_field") or rule.get("semantic_key") or rule.get("field"))
            for rule in (field_parse_rules or [])
        )
        if semantic_key and is_canonical_semantic_key(semantic_key)
    }

    header_lookup = {str(column).strip().lower() for column in header_columns}
    invalid_fields: list[str] = []
    non_semantic_fields: list[str] = []

    for field in deduplication_fields:
        field_text = str(field).strip()
        field_key = field_text.lower()
        normalized_key = normalize_semantic_key(field_text)
        raw_binding = binding_by_raw.get(field_key)
        semantic_bindings = bindings_by_semantic.get(normalized_key or "", [])

        candidate_bindings = [binding for binding in [raw_binding, *semantic_bindings] if binding]
        non_semantic_binding = next(
            (
                binding
                for binding in candidate_bindings
                if binding.get("semantic_review_status") == "confirmed_non_semantic"
            ),
            None,
        )
        if non_semantic_binding:
            non_semantic_fields.append(str(non_semantic_binding.get("raw_name") or field_text).strip())
            continue

        confirmed_semantic_bindings = [
            binding
            for binding in semantic_bindings
            if binding.get("semantic_review_status") == "confirmed_semantic"
        ]
        if normalized_key and is_canonical_semantic_key(normalized_key) and confirmed_semantic_bindings:
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
            and raw_binding.get("semantic_review_status") == "confirmed_semantic"
            and raw_semantic_key
            and is_canonical_semantic_key(raw_semantic_key)
        ):
            continue
        invalid_fields.append(field_text)

    if non_semantic_fields:
        raise ValueError(
            "deduplication_fields包含已确认非核心语义字段，不能参与Hash: "
            + ", ".join(non_semantic_fields)
        )
    if invalid_fields:
        raise ValueError(
            "deduplication_fields必须能通过表头或语义绑定解析到真实字段: "
            + ", ".join(invalid_fields)
        )
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
        if next_binding.get("semantic_review_status") != "confirmed_semantic" or not semantic_key:
            next_binding["hash_participates"] = False
        else:
            next_binding["hash_participates"] = semantic_key in selected_hash_keys
        synced.append(next_binding)
    return synced


class TemplateSaveReadinessService:
    def __init__(self) -> None:
        self._hash_policy_service = TemplateHashPolicyService()
        self._semantic_hash_policy_service = SemanticHashPolicyService()

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
            prefix = "deduplication_fields必须能通过表头或语义绑定解析到真实字段: "
            if str(exc).startswith(prefix):
                unresolved_deduplication_fields = [
                    item.strip()
                    for item in str(exc)[len(prefix) :].split(",")
                    if item.strip()
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
        warnings = list(hash_policy.warnings)
        can_save = not blocking_errors and hash_policy.passed
        return TemplateSaveReadinessResult(
            can_save=can_save,
            normalized_deduplication_fields=normalized_deduplication_fields,
            normalized_header_bindings=normalized_header_bindings,
            hash_policy=hash_policy,
            blocking_errors=blocking_errors,
            warnings=warnings,
            unresolved_deduplication_fields=unresolved_deduplication_fields,
            hash_options=hash_options,
        )
