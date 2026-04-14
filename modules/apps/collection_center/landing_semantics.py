from __future__ import annotations


def resolve_business_granularity(
    data_domain: str,
    task_granularity: str,
    component_hint: str | None = None,
) -> str:
    normalized_domain = str(data_domain or "").strip().lower()
    normalized_granularity = str(task_granularity or "").strip().lower()

    if normalized_domain == "inventory":
        return "snapshot"

    return normalized_granularity or "daily"
