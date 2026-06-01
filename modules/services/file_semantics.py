from __future__ import annotations

from dataclasses import dataclass

from backend.services.component_name_utils import DATA_DOMAIN_SUB_TYPES


@dataclass(frozen=True)
class SemanticValidationResult:
    is_valid: bool
    normalized_platform: str
    normalized_sub_domain: str
    reason: str = ""


_SERVICE_ALLOWED_SUBDOMAINS = {
    str(item).strip().lower()
    for item in DATA_DOMAIN_SUB_TYPES.get("services", [])
}


def validate_file_semantics(
    *,
    source_platform: str | None,
    data_domain: str | None,
    granularity: str | None,
    sub_domain: str | None,
) -> SemanticValidationResult:
    platform = str(source_platform or "").strip().lower()
    domain = str(data_domain or "").strip().lower()
    _ = str(granularity or "").strip().lower()
    normalized_sub_domain = str(sub_domain or "").strip().lower()

    if domain == "services":
        if not normalized_sub_domain or normalized_sub_domain in _SERVICE_ALLOWED_SUBDOMAINS:
            return SemanticValidationResult(
                is_valid=True,
                normalized_platform=platform,
                normalized_sub_domain=normalized_sub_domain,
            )
        return SemanticValidationResult(
            is_valid=False,
            normalized_platform=platform,
            normalized_sub_domain=normalized_sub_domain,
            reason="services_invalid_subdomain",
        )

    if domain in {"products", "analytics", "inventory", "finance"} and normalized_sub_domain:
        return SemanticValidationResult(
            is_valid=False,
            normalized_platform=platform,
            normalized_sub_domain=normalized_sub_domain,
            reason="nonsvc_should_not_have_subdomain",
        )

    if domain == "orders" and normalized_sub_domain:
        return SemanticValidationResult(
            is_valid=False,
            normalized_platform=platform,
            normalized_sub_domain=normalized_sub_domain,
            reason="orders_subdomain_not_allowed",
        )

    return SemanticValidationResult(
        is_valid=True,
        normalized_platform=platform,
        normalized_sub_domain=normalized_sub_domain,
    )


def is_catalog_file_semantically_valid(catalog_file) -> bool:
    result = validate_file_semantics(
        source_platform=getattr(catalog_file, "source_platform", None) or getattr(catalog_file, "platform_code", None),
        data_domain=getattr(catalog_file, "data_domain", None),
        granularity=getattr(catalog_file, "granularity", None),
        sub_domain=getattr(catalog_file, "sub_domain", None),
    )
    return result.is_valid
