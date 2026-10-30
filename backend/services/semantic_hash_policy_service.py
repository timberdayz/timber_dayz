"""Data Hash eligibility policy for semantic fields."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from backend.services.semantic_field_registry import (
    get_semantic_field_meta,
    is_canonical_semantic_key,
    is_confirmed_semantic_binding,
    normalize_semantic_key,
)


# 域级身份字段限制：某些语义键虽然在全局层面可以作为 hash 身份键，
# 但在特定数据域里无法唯一标识一行，必须在"选择阶段"就拒绝。
DOMAIN_BLOCKED_SEMANTIC_KEYS: dict[str, set[str]] = {
    "inventory": {"product_name"},
}

DOMAIN_BLOCKED_REASON: dict[str, str] = {
    "inventory": (
        "inventory 域不接受 product_name 作为身份字段："
        "商品名可能重名或改名，请改用 product_id / platform_sku。"
    ),
}


@dataclass(frozen=True)
class SemanticHashOption:
    semantic_key: str
    label: str
    kind: str
    eligible: bool
    recommended: bool = False
    weak_identity: bool = False
    legacy_compatible: bool = False
    blocked_reason: str | None = None
    warning: str | None = None
    raw_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "semantic_key": self.semantic_key,
            "label": self.label,
            "kind": self.kind,
            "eligible": self.eligible,
            "recommended": self.recommended,
            "weak_identity": self.weak_identity,
            "legacy_compatible": self.legacy_compatible,
            "blocked_reason": self.blocked_reason,
            "warning": self.warning,
            "raw_name": self.raw_name,
        }


class SemanticHashPolicyService:
    """Separates row identity policy from semantic field definitions."""

    def evaluate_option(
        self,
        *,
        data_domain: str,
        granularity: str | None,
        sub_domain: str | None,
        semantic_key: str | None,
        raw_name: str | None = None,
    ) -> SemanticHashOption:
        del granularity, sub_domain
        normalized = normalize_semantic_key(semantic_key)
        if not normalized or not is_canonical_semantic_key(normalized):
            return SemanticHashOption(
                semantic_key=str(semantic_key or "").strip(),
                label=str(semantic_key or "").strip(),
                kind="unknown",
                eligible=False,
                blocked_reason="Unknown semantic key cannot participate in Data Hash.",
                raw_name=raw_name,
            )

        meta = get_semantic_field_meta(normalized)
        label = str(meta.get("label") or normalized)
        kind = str(meta.get("kind") or "")
        domain = str(data_domain or "").strip().lower()

        if normalized == "item_status" and domain == "products":
            return SemanticHashOption(
                semantic_key=normalized,
                label=label,
                kind=kind,
                eligible=True,
                recommended=False,
                weak_identity=True,
                legacy_compatible=True,
                warning=(
                    "item_status is allowed only for products template legacy compatibility; "
                    "prefer product_id/SKU for new templates."
                ),
                raw_name=raw_name,
            )

        if kind == "metric":
            return SemanticHashOption(
                semantic_key=normalized,
                label=label,
                kind=kind,
                eligible=False,
                blocked_reason="Metric fields are measures, not row identity fields.",
                raw_name=raw_name,
            )

        if bool(meta.get("system_scope")):
            return SemanticHashOption(
                semantic_key=normalized,
                label=label,
                kind=kind,
                eligible=False,
                blocked_reason="System scope fields are added automatically and cannot be selected manually.",
                raw_name=raw_name,
            )

        eligible = bool(meta.get("hash_eligible"))
        weak_identity = str(meta.get("identity_strength") or "").lower() == "weak"
        warning = str(meta.get("hash_warning") or "") or None if weak_identity else None

        domain_blocked = DOMAIN_BLOCKED_SEMANTIC_KEYS.get(domain, set())
        if eligible and normalized in domain_blocked:
            return SemanticHashOption(
                semantic_key=normalized,
                label=label,
                kind=kind,
                eligible=False,
                recommended=False,
                weak_identity=weak_identity,
                legacy_compatible=False,
                blocked_reason=DOMAIN_BLOCKED_REASON.get(
                    domain, f"{domain} 域不接受 {label} 作为身份字段。"
                ),
                warning=warning,
                raw_name=raw_name,
            )

        return SemanticHashOption(
            semantic_key=normalized,
            label=label,
            kind=kind,
            eligible=eligible,
            recommended=bool(eligible and meta.get("default_hash")),
            weak_identity=weak_identity,
            legacy_compatible=False,
            blocked_reason=None if eligible else "This semantic field is not configured as a Data Hash identity field.",
            warning=warning,
            raw_name=raw_name,
        )

    def build_options(
        self,
        *,
        data_domain: str,
        granularity: str | None,
        sub_domain: str | None,
        header_bindings: Iterable[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        options: list[dict[str, Any]] = []
        seen: set[str] = set()
        for binding in header_bindings or []:
            if not is_confirmed_semantic_binding(binding):
                continue
            semantic_key = normalize_semantic_key(binding.get("semantic_key"))
            if not semantic_key or semantic_key in seen:
                continue
            seen.add(semantic_key)
            raw_name = str(
                binding.get("raw_name")
                or binding.get("source_header")
                or binding.get("display_name")
                or ""
            ).strip() or None
            options.append(
                self.evaluate_option(
                    data_domain=data_domain,
                    granularity=granularity,
                    sub_domain=sub_domain,
                    semantic_key=semantic_key,
                    raw_name=raw_name,
                ).to_dict()
            )
        return options
