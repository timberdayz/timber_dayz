from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from backend.services.currency_extractor import get_currency_extractor


SEMANTIC_FIELD_ALIASES: dict[str, list[str]] = {
    "order_id": ["order_id", "订单号", "订单编号", "order id"],
    "product_id": ["product_id", "产品id", "商品id", "product id"],
    "platform_sku": ["platform_sku", "平台sku", "平台 sku", "product_sku", "产品sku"],
    "sku_id": ["sku_id", "sku id", "sku编号", "sku id"],
    "shop_id": ["shop_id", "店铺", "店铺id", "shop id"],
    "warehouse_name": ["warehouse_name", "warehouse", "仓库", "仓库名称", "warehouse name"],
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
    "warehouse_name": {"required": False, "hash_participates": True},
    "metric_date": {"required": False, "hash_participates": True},
    "period_start_date": {"required": False, "hash_participates": False},
    "period_end_date": {"required": False, "hash_participates": False},
    "order_date": {"required": False, "hash_participates": True},
}

SEMANTIC_HASH_IDENTITY_KEYS = {
    "order_id",
    "product_id",
    "platform_sku",
    "sku_id",
    "shop_id",
    "warehouse_name",
}


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


def _normalize_key_variants(key: str) -> set[str]:
    lowered = key.strip().lower()
    variants = {lowered}
    extractor = get_currency_extractor()
    normalized = extractor.normalize_field_name(key)
    variants.add(normalized.lower())
    variants.add(lowered.replace(" ", ""))
    variants.add(lowered.replace("_", ""))
    variants.add(normalized.lower().replace("_", ""))
    return {variant for variant in variants if variant}


def resolve_semantic_value(
    row: Dict[str, Any],
    semantic_key: str,
    header_bindings: Optional[Iterable[Dict[str, Any]]] = None,
) -> tuple[Any, Optional[str]]:
    normalized_key = normalize_semantic_key(semantic_key)
    if not normalized_key:
        return None, None

    candidate_names: list[str] = []
    binding_candidates = list(header_bindings or [])
    for binding in binding_candidates:
        binding_semantic_key = normalize_semantic_key(binding.get("semantic_key"))
        if binding_semantic_key != normalized_key:
            continue
        raw_name = str(binding.get("raw_name") or "").strip()
        if raw_name:
            candidate_names.append(raw_name)
        display_name = str(binding.get("display_name") or "").strip()
        if display_name:
            candidate_names.append(display_name)
        for alias in binding.get("aliases") or []:
            alias_text = str(alias or "").strip()
            if alias_text:
                candidate_names.append(alias_text)

    candidate_names.extend(get_semantic_aliases(normalized_key))
    seen_names: list[str] = []
    seen_set = set()
    for name in candidate_names:
        lowered = str(name).strip().lower()
        if not lowered or lowered in seen_set:
            continue
        seen_set.add(lowered)
        seen_names.append(str(name).strip())

    for key, value in row.items():
        key_variants = _normalize_key_variants(str(key))
        for candidate in seen_names:
            if any(candidate_variant in key_variants for candidate_variant in _normalize_key_variants(candidate)):
                return value, key
    return None, None
