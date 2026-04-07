from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

from backend.services import component_name_utils

DATA_DOMAIN_SUB_TYPES = component_name_utils.DATA_DOMAIN_SUB_TYPES

TIME_PRESET_TO_GRANULARITY: Dict[str, str] = {
    "today": "daily",
    "yesterday": "daily",
    "last_7_days": "weekly",
    "last_30_days": "monthly",
}

DEFAULT_CONFIG_DATA_DOMAINS: List[str] = [
    "orders",
    "products",
    "analytics",
    "finance",
    "services",
    "inventory",
]

DEFAULT_GRANULARITY_DATE_RANGE_TYPE: Dict[str, str] = {
    "daily": "yesterday",
    "weekly": "last_7_days",
    "monthly": "last_30_days",
}


def get_default_shop_capabilities(shop_type: str | None) -> Dict[str, bool]:
    defaults = {
        "orders": True,
        "products": True,
        "services": True,
        "analytics": True,
        "finance": True,
        "inventory": True,
    }
    if str(shop_type or "").strip().lower() == "global":
        defaults["services"] = False
    return defaults


def resolve_shop_capabilities(
    capabilities: Optional[Dict[str, bool]],
    *,
    shop_type: str | None = None,
) -> Dict[str, bool]:
    if capabilities is None:
        return get_default_shop_capabilities(shop_type)

    normalized: Dict[str, bool] = {}
    for domain in DEFAULT_CONFIG_DATA_DOMAINS:
        normalized[domain] = bool(capabilities.get(domain, False))
    return normalized


def get_recommended_config_domains(
    capabilities: Optional[Dict[str, bool]],
    *,
    shop_type: str | None = None,
) -> List[str]:
    effective = resolve_shop_capabilities(capabilities, shop_type=shop_type)
    return sorted([domain for domain, enabled in effective.items() if enabled])


def build_default_sub_domains(
    data_domains: List[str],
) -> Dict[str, List[str]]:
    result: Dict[str, List[str]] = {}
    for domain in data_domains or []:
        allowed_subtypes = _allowed_subtype_mapping().get(domain, [])
        if allowed_subtypes:
            result[domain] = list(allowed_subtypes)
    return result


def _normalize_date_like(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


def get_supported_config_data_domains(platform: str | None) -> List[str]:
    return list(DEFAULT_CONFIG_DATA_DOMAINS)


def normalize_time_selection(
    *,
    time_selection: Optional[Dict[str, Any]] = None,
    time_mode: Optional[str] = None,
    date_preset: Optional[str] = None,
    start_date: Any = None,
    end_date: Any = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    date_range_type: Optional[str] = None,
    custom_date_start: Any = None,
    custom_date_end: Any = None,
    date_range: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    raw: Dict[str, Any] = dict(time_selection or {})
    explicit_preset = str(raw.get("preset") or date_preset or date_range_type or "").strip().lower()
    explicit_start = (
        raw.get("start_date")
        or _normalize_date_like(start_date)
        or _normalize_date_like(custom_date_start)
        or _normalize_date_like((date_range or {}).get("start_date"))
        or _normalize_date_like((date_range or {}).get("start"))
        or _normalize_date_like((date_range or {}).get("date_from"))
    )
    explicit_end = (
        raw.get("end_date")
        or _normalize_date_like(end_date)
        or _normalize_date_like(custom_date_end)
        or _normalize_date_like((date_range or {}).get("end_date"))
        or _normalize_date_like((date_range or {}).get("end"))
        or _normalize_date_like((date_range or {}).get("date_to"))
    )
    has_custom_fields = bool(explicit_start or explicit_end)

    mode = str(
        raw.get("mode")
        or time_mode
        or ("preset" if explicit_preset and explicit_preset != "custom" else "")
        or ("custom" if has_custom_fields else "")
        or ("preset" if date_range_type and date_range_type != "custom" else "")
        or ("custom" if date_range_type == "custom" else "")
    ).strip().lower()

    if not mode:
        return {}

    if mode == "preset":
        if has_custom_fields:
            raise ValueError("preset time selection cannot include custom range fields")
        preset = explicit_preset
        if preset not in TIME_PRESET_TO_GRANULARITY:
            raise ValueError(f"invalid date preset: {preset or 'empty'}")
        return {
            "mode": "preset",
            "preset": preset,
        }

    if mode == "custom":
        if explicit_preset and explicit_preset != "custom":
            raise ValueError("custom time selection cannot include preset fields")
        start = explicit_start
        end = explicit_end
        if not start or not end:
            raise ValueError("custom time selection requires start_date and end_date")
        return {
            "mode": "custom",
            "start_date": start,
            "end_date": end,
            "start_time": str(raw.get("start_time") or start_time or "00:00:00").strip(),
            "end_time": str(raw.get("end_time") or end_time or "23:59:59").strip(),
        }

    raise ValueError(f"invalid time mode: {mode}")


def derive_granularity_from_time_selection(
    time_selection: Dict[str, Any],
    granularity: Optional[str] = None,
) -> str:
    normalized = normalize_time_selection(time_selection=time_selection)
    mode = normalized["mode"]
    if mode == "preset":
        return TIME_PRESET_TO_GRANULARITY[normalized["preset"]]
    if mode == "custom":
        granularity_norm = str(granularity or "").strip().lower()
        if not granularity_norm:
            raise ValueError("granularity is required for custom time selection")
        return granularity_norm
    raise ValueError(f"unsupported time selection mode: {mode}")


def build_date_range_from_time_selection(
    time_selection: Dict[str, Any],
    *,
    today: Optional[date] = None,
) -> Dict[str, str]:
    normalized = normalize_time_selection(time_selection=time_selection)
    if normalized["mode"] == "custom":
        start = normalized["start_date"]
        end = normalized["end_date"]
    else:
        target = today or date.today()
        preset = normalized["preset"]
        if preset == "today":
            start = end = target.isoformat()
        elif preset == "yesterday":
            y = target - timedelta(days=1)
            start = end = y.isoformat()
        elif preset == "last_7_days":
            start = (target - timedelta(days=6)).isoformat()
            end = target.isoformat()
        elif preset == "last_30_days":
            start = (target - timedelta(days=29)).isoformat()
            end = target.isoformat()
        else:
            raise ValueError(f"unsupported preset: {preset}")

    return {
        "start_date": start,
        "end_date": end,
        "date_from": start,
        "date_to": end,
    }


def build_legacy_collection_date_fields(
    time_selection: Dict[str, Any],
) -> Dict[str, Any]:
    normalized = normalize_time_selection(time_selection=time_selection)
    if normalized["mode"] == "preset":
        return {
            "date_range_type": normalized["preset"],
            "custom_date_start": None,
            "custom_date_end": None,
        }

    return {
        "date_range_type": "custom",
        "custom_date_start": date.fromisoformat(normalized["start_date"]),
        "custom_date_end": date.fromisoformat(normalized["end_date"]),
    }


def _allowed_subtype_mapping() -> Dict[str, List[str]]:
    return getattr(component_name_utils, "DATA_DOMAIN_SUB_TYPES", DATA_DOMAIN_SUB_TYPES)


def _as_string_list(raw: object) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, Iterable) and not isinstance(raw, (bytes, bytearray, dict)):
        values = list(raw)
    else:
        return []

    normalized: List[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return normalized


def normalize_domain_subtypes(
    *,
    data_domains: List[str],
    domain_subtypes: Optional[Dict[str, List[str]]] = None,
    sub_domains: Optional[Dict[str, List[str]] | List[str]] = None,
) -> Dict[str, List[str]]:
    normalized: Dict[str, List[str]] = {}
    raw_mapping: Dict[str, object] = {}

    if isinstance(domain_subtypes, dict):
        raw_mapping.update(domain_subtypes)
    elif isinstance(sub_domains, dict):
        raw_mapping.update(sub_domains)

    legacy_values = _as_string_list(sub_domains) if not isinstance(sub_domains, dict) else []

    for domain in data_domains or []:
        allowed_subtypes = _allowed_subtype_mapping().get(domain, [])
        if not allowed_subtypes:
            continue

        requested = _as_string_list(raw_mapping.get(domain)) if domain in raw_mapping else legacy_values
        filtered = [item for item in requested if item in allowed_subtypes]
        if filtered:
            normalized[domain] = filtered

    return normalized


def iter_domain_targets(
    data_domains: List[str],
    domain_subtypes: Optional[Dict[str, List[str]]] = None,
) -> Iterator[Tuple[str, Optional[str], str]]:
    normalized = normalize_domain_subtypes(
        data_domains=data_domains or [],
        domain_subtypes=domain_subtypes,
    )
    for domain in data_domains or []:
        subtypes = normalized.get(domain) or [None]
        for subtype in subtypes:
            key = f"{domain}:{subtype}" if subtype else domain
            yield domain, subtype, key


def count_collection_targets(
    data_domains: List[str],
    domain_subtypes: Optional[Dict[str, List[str]]] = None,
) -> int:
    return sum(1 for _ in iter_domain_targets(data_domains or [], domain_subtypes))


def normalize_collection_date_range(
    date_range: Optional[Dict[str, str]],
) -> Dict[str, str]:
    source = dict(date_range or {})
    if source.get("time_selection"):
        normalized = build_date_range_from_time_selection(source["time_selection"])
        normalized["time_selection"] = normalize_time_selection(time_selection=source["time_selection"])
        return normalized

    start_date = source.get("start_date") or source.get("start") or source.get("date_from") or ""
    end_date = source.get("end_date") or source.get("end") or source.get("date_to") or ""

    normalized: Dict[str, str] = {}
    if start_date:
        normalized["start_date"] = start_date
        normalized["date_from"] = start_date
    if end_date:
        normalized["end_date"] = end_date
        normalized["date_to"] = end_date
    return normalized


def summarize_shop_scopes(
    shop_scopes: List[Dict[str, Any]] | List[Any],
) -> Dict[str, Any]:
    account_ids: List[str] = []
    data_domains: List[str] = []
    domain_seen: set[str] = set()
    merged_sub_domains: Dict[str, List[str]] = {}

    for raw_scope in shop_scopes or []:
        scope = (
            raw_scope.model_dump(exclude_none=True)
            if hasattr(raw_scope, "model_dump")
            else dict(raw_scope or {})
        )
        if not bool(scope.get("enabled", True)):
            continue

        shop_account_id = str(scope.get("shop_account_id") or "").strip()
        if shop_account_id:
            account_ids.append(shop_account_id)

        normalized_domains = _as_string_list(scope.get("data_domains"))
        normalized_mapping = normalize_domain_subtypes(
            data_domains=normalized_domains,
            sub_domains=scope.get("sub_domains"),
        )
        for domain in normalized_domains:
            if domain not in domain_seen:
                domain_seen.add(domain)
                data_domains.append(domain)

        for domain, subtypes in normalized_mapping.items():
            merged = merged_sub_domains.setdefault(domain, [])
            for subtype in subtypes:
                if subtype not in merged:
                    merged.append(subtype)

    return {
        "account_ids": account_ids,
        "data_domains": data_domains,
        "sub_domains": merged_sub_domains or None,
    }
