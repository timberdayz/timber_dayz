from __future__ import annotations

from typing import Final


DOMAIN_PATHS: Final[dict[str, str]] = {
    "products": "/datacenter/product/performance",
    "services": "/datacenter/service/overview",
    "analytics": "/datacenter/traffic/overview",
}

DOMAIN_LABELS: Final[dict[str, str]] = {
    "products": "\u5546\u54c1",
    "services": "\u670d\u52a1",
    "analytics": "\u6d41\u91cf",
}

ALLOWED_PRESETS_BY_DOMAIN: Final[dict[str, list[str]]] = {
    "products": [
        "today_realtime",
        "yesterday",
        "last_7_days",
        "last_30_days",
    ],
    "services": [
        "today_realtime",
        "yesterday",
        "last_7_days",
        "last_30_days",
    ],
    "analytics": [
        "yesterday",
        "last_7_days",
        "last_30_days",
    ],
}

ALLOWED_GRANULARITIES: Final[set[str]] = {"daily", "weekly", "monthly"}

PRESET_LABELS: Final[dict[str, str]] = {
    "today_realtime": "\u4eca\u65e5\u5b9e\u65f6",
    "yesterday": "\u6628\u5929",
    "last_7_days": "\u8fc7\u53bb7\u5929",
    "last_30_days": "\u8fc7\u53bb30\u5929",
}

GRANULARITY_LABELS: Final[dict[str, str]] = {
    "daily": "\u6309\u65e5",
    "weekly": "\u6309\u5468",
    "monthly": "\u6309\u6708",
}


def build_domain_path(data_domain: str) -> str:
    normalized = str(data_domain or "").strip().lower()
    try:
        return DOMAIN_PATHS[normalized]
    except KeyError as exc:
        raise ValueError(f"unsupported shopee data_domain: {data_domain}") from exc


def allowed_presets_for_domain(data_domain: str) -> list[str]:
    normalized = str(data_domain or "").strip().lower()
    try:
        return list(ALLOWED_PRESETS_BY_DOMAIN[normalized])
    except KeyError as exc:
        raise ValueError(f"unsupported shopee data_domain: {data_domain}") from exc


def validate_time_request(data_domain: str, *, time_mode: str, value: str) -> None:
    normalized_domain = str(data_domain or "").strip().lower()
    normalized_mode = str(time_mode or "").strip().lower()
    normalized_value = str(value or "").strip().lower()

    if normalized_mode == "preset":
        allowed = allowed_presets_for_domain(normalized_domain)
        if normalized_value not in allowed:
            raise ValueError(
                f"unsupported preset {normalized_value!r} for shopee/{normalized_domain}"
            )
        return

    if normalized_mode == "granularity":
        if normalized_value not in ALLOWED_GRANULARITIES:
            raise ValueError(
                f"unsupported granularity {normalized_value!r} for shopee/{normalized_domain}"
            )
        return

    raise ValueError(f"unsupported time_mode {normalized_mode!r}")


def normalize_time_request(data_domain: str, *, time_mode: str, value: str) -> dict[str, str]:
    normalized_mode = str(time_mode or "").strip().lower()
    normalized_value = str(value or "").strip().lower()
    validate_time_request(data_domain, time_mode=normalized_mode, value=normalized_value)
    return {
        "time_mode": normalized_mode,
        "value": normalized_value,
    }


def preset_label(value: str) -> str:
    normalized = str(value or "").strip().lower()
    try:
        return PRESET_LABELS[normalized]
    except KeyError as exc:
        raise ValueError(f"unsupported preset {value!r}") from exc


def granularity_label(value: str) -> str:
    normalized = str(value or "").strip().lower()
    try:
        return GRANULARITY_LABELS[normalized]
    except KeyError as exc:
        raise ValueError(f"unsupported granularity {value!r}") from exc
