from __future__ import annotations

from typing import Any, Dict, Iterable, Optional
from backend.services.currency_extractor import get_currency_extractor


SEMANTIC_FIELD_ALIASES: dict[str, list[str]] = {
    "order_id": ["order_id", "订单号", "订单编号", "order id"],
    "product_id": ["product_id", "产品id", "商品id", "product id"],
    "platform_sku": ["platform_sku", "平台sku", "平台 sku", "product_sku", "产品sku"],
    "sku_id": ["sku_id", "sku id", "sku编号", "sku id"],
    "shop_id": ["shop_id", "店铺", "店铺id", "shop id"],
    "metric_date": ["metric_date", "日期", "统计日期", "data_date", "date"],
    "period_start_date": ["period_start_date", "开始日期", "周期开始日期"],
    "period_end_date": ["period_end_date", "结束日期", "周期结束日期"],
    "order_date": ["order_date", "下单日期", "订单日期", "下单时间"],
}

SEMANTIC_FIELD_REQUIREMENTS: dict[str, dict[str, Any]] = {
    "order_id": {"required": True, "hash_participates": True},
    "product_id": {"required": False, "hash_participates": True},
    "platform_sku": {"required": False, "hash_participates": True},
    "sku_id": {"required": False, "hash_participates": True},
    "shop_id": {"required": False, "hash_participates": True},
    "metric_date": {"required": False, "hash_participates": True},
    "period_start_date": {"required": False, "hash_participates": False},
    "period_end_date": {"required": False, "hash_participates": False},
    "order_date": {"required": False, "hash_participates": True},
}

SEMANTIC_HASH_IDENTITY_KEYS = {"order_id", "product_id", "platform_sku", "sku_id", "shop_id"}


def normalize_semantic_key(value: Optional[str]) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    lowered = text.lower()
    if lowered in SEMANTIC_FIELD_ALIASES:
        return lowered

    for semantic_key, aliases in SEMANTIC_FIELD_ALIASES.items():
        if lowered == semantic_key:
            return semantic_key
        if any(lowered == str(alias).strip().lower() for alias in aliases):
            return semantic_key
    return lowered


def is_canonical_semantic_key(value: Optional[str]) -> bool:
    text = str(value or "").strip().lower()
    return bool(text) and text in SEMANTIC_FIELD_ALIASES


def is_hash_identity_semantic_key(value: Optional[str]) -> bool:
    normalized = normalize_semantic_key(value)
    return bool(normalized) and normalized in SEMANTIC_HASH_IDENTITY_KEYS


def infer_semantic_key(*values: Optional[str]) -> Optional[str]:
    for value in values:
        normalized = normalize_semantic_key(value)
        if normalized in SEMANTIC_FIELD_ALIASES:
            return normalized
    return None


def get_semantic_aliases(semantic_key: Optional[str]) -> list[str]:
    normalized = normalize_semantic_key(semantic_key)
    if not normalized:
        return []
    aliases = SEMANTIC_FIELD_ALIASES.get(normalized, [normalized])
    return list(dict.fromkeys([normalized, *aliases]))


def get_semantic_requirements(semantic_key: Optional[str]) -> dict[str, Any]:
    normalized = normalize_semantic_key(semantic_key)
    if not normalized:
        return {"required": False, "hash_participates": False}
    return {
        "required": bool(SEMANTIC_FIELD_REQUIREMENTS.get(normalized, {}).get("required", False)),
        "hash_participates": bool(
            SEMANTIC_FIELD_REQUIREMENTS.get(normalized, {}).get("hash_participates", False)
        ),
    }


def build_semantic_binding_lookup(header_bindings: Iterable[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for binding in header_bindings or []:
        raw_name = str(binding.get("raw_name", "")).strip()
        if raw_name:
            lookup[raw_name.lower()] = dict(binding)
    return lookup


def resolve_semantic_value(
    row: Dict[str, Any],
    semantic_key: str,
    header_bindings: Iterable[dict[str, Any]] | None = None,
) -> tuple[Optional[str], Optional[str]]:
    normalized_key = normalize_semantic_key(semantic_key)
    if not normalized_key:
        return None, None

    currency_extractor = get_currency_extractor()
    row_lookup = {str(key).strip().lower(): key for key in row.keys()}
    normalized_row_lookup = {}
    for key in row.keys():
        raw_key = str(key).strip()
        if not raw_key:
            continue
        normalized_key = currency_extractor.normalize_field_name(raw_key).strip().lower()
        if normalized_key and normalized_key not in normalized_row_lookup:
            normalized_row_lookup[normalized_key] = key
    binding_lookup = build_semantic_binding_lookup(header_bindings)

    for binding in binding_lookup.values():
        binding_semantic = normalize_semantic_key(
            binding.get("semantic_key") or binding.get("semantic_role") or binding.get("display_name")
        )
        if binding_semantic != normalized_key:
            continue
        raw_name = str(binding.get("raw_name", "")).strip()
        matched_key = row_lookup.get(raw_name.lower())
        if matched_key is None and raw_name:
            matched_key = normalized_row_lookup.get(
                currency_extractor.normalize_field_name(raw_name).strip().lower()
            )
        if matched_key is None:
            continue
        raw_value = row.get(matched_key)
        if raw_value is None or str(raw_value).strip() == "":
            continue
        return str(raw_value).strip(), matched_key

    for alias in get_semantic_aliases(normalized_key):
        matched_key = row_lookup.get(alias.lower())
        if matched_key is None:
            matched_key = normalized_row_lookup.get(
                currency_extractor.normalize_field_name(alias).strip().lower()
            )
        if matched_key is None:
            continue
        raw_value = row.get(matched_key)
        if raw_value is None or str(raw_value).strip() == "":
            continue
        return str(raw_value).strip(), matched_key

    return None, None
