from __future__ import annotations

from typing import Dict, Iterable, Iterator, List, Optional, Tuple

from backend.services import component_name_utils

DATA_DOMAIN_SUB_TYPES = component_name_utils.DATA_DOMAIN_SUB_TYPES


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
