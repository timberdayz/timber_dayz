from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from backend.services.currency_extractor import get_currency_extractor


SEMANTIC_FIELD_ALIASES: dict[str, list[str]] = {
    "order_id": ["order_id", "订单号", "订单编号", "order id"],
    "product_id": ["product_id", "产品id", "商品id", "产品ID", "商品ID", "product id"],
    "platform_sku": ["platform_sku", "平台sku", "平台 sku", "product_sku", "产品sku", "商品sku"],
    "sku_id": ["sku_id", "sku id", "SKU ID", "SKU编号"],
    "line_id": ["line_id", "order_line_id", "line id", "order line id"],
    "service_id": ["service_id", "service id", "服务ID", "服务编号"],
    "shop_id": ["shop_id", "店铺", "店铺ID", "shop id"],
    "product_name": ["product_name", "item_name", "product name", "item name", "商品", "商品名", "商品名称", "产品名称"],
    "item_status": ["item_status", "product_status", "listing_status", "item status", "product status", "发品状态", "商品状态"],
    "gmv_band": ["gmv_band", "gmv band", "gmv range", "GMV区间", "GMV 区间"],
    "warehouse_name": ["warehouse_name", "warehouse", "仓库", "仓库名称", "warehouse name"],
    "metric_date": ["metric_date", "日期", "统计日期", "data_date", "date"],
    "period_start_date": ["period_start_date", "开始日期", "周期开始日期"],
    "period_end_date": ["period_end_date", "结束日期", "周期结束日期"],
    "order_date": ["order_date", "下单日期", "订单日期", "下单时间"],
    "gmv": ["gmv", "GMV"],
    "sales_amount": ["sales_amount", "sales amount", "sales", "销售额", "销售金额"],
    "sales_volume": ["sales_volume", "sales volume", "units sold", "销量", "销售数量"],
    "order_count": ["order_count", "order count", "orders", "订单量", "订单数"],
}

SEMANTIC_FIELD_META: dict[str, dict[str, Any]] = {
    "order_id": {"kind": "identity", "hash_eligible": True, "default_hash": True, "required": True},
    "product_id": {"kind": "identity", "hash_eligible": True, "default_hash": True},
    "platform_sku": {"kind": "identity", "hash_eligible": True, "default_hash": True},
    "sku_id": {"kind": "identity", "hash_eligible": True, "default_hash": True},
    "line_id": {"kind": "identity", "hash_eligible": True, "default_hash": True},
    "service_id": {"kind": "identity", "hash_eligible": True, "default_hash": True},
    "shop_id": {"kind": "identity", "hash_eligible": True, "default_hash": False, "system_scope": True},
    "warehouse_name": {"kind": "dimension", "hash_eligible": True, "default_hash": True},
    "gmv_band": {"kind": "dimension", "hash_eligible": True, "default_hash": False},
    "metric_date": {"kind": "time", "hash_eligible": True, "default_hash": True},
    "period_start_date": {"kind": "time", "hash_eligible": True, "default_hash": True},
    "period_end_date": {"kind": "time", "hash_eligible": True, "default_hash": True},
    "order_date": {"kind": "time", "hash_eligible": True, "default_hash": False},
    "product_name": {
        "kind": "dimension",
        "hash_eligible": False,
        "default_hash": False,
        "identity_strength": "weak",
        "hash_warning": "商品名可能重名或改名，优先使用商品 ID / SKU。",
    },
    "item_status": {"kind": "attribute", "hash_eligible": False, "default_hash": False},
    "gmv": {"kind": "metric", "hash_eligible": False, "default_hash": False},
    "sales_amount": {"kind": "metric", "hash_eligible": False, "default_hash": False},
    "sales_volume": {"kind": "metric", "hash_eligible": False, "default_hash": False},
    "order_count": {"kind": "metric", "hash_eligible": False, "default_hash": False},
}

SEMANTIC_FIELD_DEFINITIONS: dict[str, dict[str, Any]] = {
    "order_id": {
        "label": "订单号",
        "kind": "identity",
        "domain": "common",
        "hash_eligible": True,
        "default_hash": True,
        "required": True,
        "aliases": ["订单号", "订单编号", "order id"],
    },
    "line_id": {
        "label": "订单明细行 ID",
        "kind": "identity",
        "domain": "common",
        "hash_eligible": True,
        "default_hash": True,
        "aliases": ["order_line_id", "line id", "order line id", "明细行ID"],
    },
    "product_id": {
        "label": "商品 ID",
        "kind": "identity",
        "domain": "common",
        "hash_eligible": True,
        "default_hash": True,
        "aliases": ["产品id", "商品id", "产品ID", "商品ID", "product id"],
    },
    "platform_sku": {
        "label": "平台 SKU",
        "kind": "identity",
        "domain": "common",
        "hash_eligible": True,
        "default_hash": True,
        "aliases": ["平台sku", "平台 sku", "product_sku", "产品sku", "商品sku"],
    },
    "sku_id": {
        "label": "SKU 编号",
        "kind": "identity",
        "domain": "common",
        "hash_eligible": True,
        "default_hash": True,
        "aliases": ["sku id", "SKU ID", "SKU编号"],
    },
    "service_id": {
        "label": "服务 ID",
        "kind": "identity",
        "domain": "common",
        "hash_eligible": True,
        "default_hash": True,
        "aliases": ["service id", "服务ID", "服务编号"],
    },
    "shop_id": {
        "label": "店铺 ID",
        "kind": "identity",
        "domain": "common",
        "hash_eligible": True,
        "default_hash": False,
        "system_scope": True,
        "aliases": ["店铺", "店铺ID", "shop id"],
    },
    "warehouse_name": {
        "label": "仓库",
        "kind": "dimension",
        "domain": "common",
        "hash_eligible": True,
        "default_hash": True,
        "aliases": ["warehouse", "仓库", "仓库名称", "warehouse name"],
    },
    "gmv_band": {
        "label": "GMV 区间",
        "kind": "dimension",
        "domain": "products",
        "hash_eligible": True,
        "default_hash": False,
        "aliases": ["gmv band", "gmv range", "GMV区间", "GMV 区间"],
    },
    "metric_date": {
        "label": "统计日期",
        "kind": "time",
        "domain": "common",
        "hash_eligible": True,
        "default_hash": True,
        "aliases": ["日期", "统计日期", "data_date", "date"],
    },
    "period_start_date": {
        "label": "周期开始日期",
        "kind": "time",
        "domain": "common",
        "hash_eligible": True,
        "default_hash": True,
        "aliases": ["开始日期", "周期开始日期", "date_from"],
    },
    "period_end_date": {
        "label": "周期结束日期",
        "kind": "time",
        "domain": "common",
        "hash_eligible": True,
        "default_hash": True,
        "aliases": ["结束日期", "周期结束日期", "date_to"],
    },
    "period_start_time": {
        "label": "周期开始时间",
        "kind": "time",
        "domain": "common",
        "hash_eligible": True,
        "default_hash": False,
        "aliases": ["开始时间", "小时", "时段", "hour", "time", "start time"],
    },
    "period_end_time": {
        "label": "周期结束时间",
        "kind": "time",
        "domain": "common",
        "hash_eligible": True,
        "default_hash": False,
        "aliases": ["结束时间", "结束小时", "end hour", "end time"],
    },
    "order_date": {
        "label": "下单日期",
        "kind": "time",
        "domain": "orders",
        "hash_eligible": True,
        "default_hash": False,
        "aliases": ["下单日期", "订单日期", "下单时间"],
    },
    "visitor_count": {
        "label": "访客数",
        "kind": "metric",
        "domain": "analytics",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["访客数", "visitors", "visitor count"],
    },
    "product_visitor_count": {
        "label": "商品访客数",
        "kind": "metric",
        "domain": "analytics",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["商品访客数", "product visitors", "product visitor count"],
    },
    "page_views": {
        "label": "浏览量",
        "kind": "metric",
        "domain": "analytics",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["浏览量", "pv", "page views", "views"],
    },
    "impressions": {
        "label": "曝光量",
        "kind": "metric",
        "domain": "analytics",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["曝光量", "曝光次数", "impression", "impressions"],
    },
    "clicks": {
        "label": "点击量",
        "kind": "metric",
        "domain": "analytics",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["点击量", "点击次数", "click", "clicks"],
    },
    "click_rate": {
        "label": "点击率",
        "kind": "metric",
        "domain": "analytics",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["点击率", "click rate", "ctr"],
    },
    "conversion_rate": {
        "label": "转化率",
        "kind": "metric",
        "domain": "analytics",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["转化率", "conversion rate", "cvr"],
    },
    "order_count": {
        "label": "订单量",
        "kind": "metric",
        "domain": "analytics",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["订单量", "订单数", "order count", "orders"],
    },
    "sku_order_count": {
        "label": "SKU 订单量",
        "kind": "metric",
        "domain": "analytics",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["SKU订单量", "sku orders", "sku order count"],
    },
    "gmv": {
        "label": "GMV",
        "kind": "metric",
        "domain": "common",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["GMV"],
    },
    "total_transaction_amount": {
        "label": "总交易金额",
        "kind": "metric",
        "domain": "analytics",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["总交易金额", "total transaction amount"],
    },
    "bounce_rate": {
        "label": "跳失率",
        "kind": "metric",
        "domain": "analytics",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["跳失率", "bounce rate"],
    },
    "sales_amount": {
        "label": "销售额",
        "kind": "metric",
        "domain": "orders",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["sales amount", "sales", "销售额", "销售金额"],
    },
    "sales_volume": {
        "label": "销量",
        "kind": "metric",
        "domain": "orders",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["sales volume", "units sold", "销量", "销售数量"],
    },
    "paid_amount": {
        "label": "实付金额",
        "kind": "metric",
        "domain": "orders",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["实付金额", "paid amount", "buyer paid amount"],
    },
    "profit": {
        "label": "利润",
        "kind": "metric",
        "domain": "orders",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["利润", "profit"],
    },
    "purchase_amount": {
        "label": "采购金额",
        "kind": "metric",
        "domain": "products",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["采购金额", "purchase amount"],
    },
    "platform_commission": {
        "label": "平台佣金",
        "kind": "metric",
        "domain": "orders",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["平台佣金", "platform commission", "commission"],
    },
    "live_gmv": {
        "label": "直播 GMV",
        "kind": "metric",
        "domain": "attribution",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["商家直播 GMV", "直播GMV", "live gmv"],
    },
    "live_attributed_gmv": {
        "label": "直播归因 GMV",
        "kind": "metric",
        "domain": "attribution",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["商家直播归因 GMV", "直播归因GMV", "live attributed gmv"],
    },
    "live_indirect_gmv": {
        "label": "直播间接 GMV",
        "kind": "metric",
        "domain": "attribution",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["商家直播间接 GMV", "直播间接GMV", "live indirect gmv"],
    },
    "video_gmv": {
        "label": "视频 GMV",
        "kind": "metric",
        "domain": "attribution",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["商家视频 GMV", "视频GMV", "video gmv"],
    },
    "video_attributed_gmv": {
        "label": "视频归因 GMV",
        "kind": "metric",
        "domain": "attribution",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["商家视频归因 GMV", "视频归因GMV", "video attributed gmv"],
    },
    "video_indirect_gmv": {
        "label": "视频间接 GMV",
        "kind": "metric",
        "domain": "attribution",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["商家视频间接 GMV", "视频间接GMV", "video indirect gmv"],
    },
    "product_name": {
        "label": "商品名称",
        "kind": "dimension",
        "domain": "products",
        "hash_eligible": False,
        "default_hash": False,
        "identity_strength": "weak",
        "hash_warning": "商品名可能重名或改名，优先使用商品 ID / SKU。",
        "aliases": ["item_name", "product name", "item name", "商品", "商品名", "商品名称", "产品名称"],
    },
    "item_status": {
        "label": "商品状态",
        "kind": "attribute",
        "domain": "products",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["product_status", "listing_status", "item status", "product status", "发品状态", "商品状态"],
    },
}

SEMANTIC_FIELD_ALIASES = {
    key: list(dict.fromkeys([key, *(definition.get("aliases") or [])]))
    for key, definition in SEMANTIC_FIELD_DEFINITIONS.items()
}

SEMANTIC_FIELD_META = {
    key: {meta_key: meta_value for meta_key, meta_value in definition.items() if meta_key != "aliases"}
    for key, definition in SEMANTIC_FIELD_DEFINITIONS.items()
}

SEMANTIC_HASH_IDENTITY_KEYS = {
    key for key, meta in SEMANTIC_FIELD_META.items() if meta.get("hash_eligible")
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


def get_semantic_field_meta(semantic_key: Optional[str]) -> dict[str, Any]:
    normalized = normalize_semantic_key(semantic_key)
    if not normalized:
        return {}
    meta = SEMANTIC_FIELD_META.get(normalized, {})
    return {"semantic_key": normalized, **meta} if meta else {}


def is_hash_eligible_semantic_key(value: Optional[str]) -> bool:
    normalized = normalize_semantic_key(value)
    return bool(normalized) and bool(SEMANTIC_FIELD_META.get(normalized, {}).get("hash_eligible"))


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
    meta = SEMANTIC_FIELD_META.get(normalized, {})
    return {
        "required": bool(meta.get("required", False)),
        "hash_participates": bool(meta.get("default_hash", False)),
        "hash_eligible": bool(meta.get("hash_eligible", False)),
        "semantic_kind": str(meta.get("kind", "")),
        "system_scope": bool(meta.get("system_scope", False)),
        "identity_strength": meta.get("identity_strength"),
        "hash_warning": meta.get("hash_warning"),
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
    return {variant for variant in variants if len(variant) > 1}


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
        source_header = str(binding.get("source_header") or "").strip()
        if source_header:
            candidate_names.append(source_header)
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

    row_lookup = {
        str(key).strip().lower(): key
        for key in row.keys()
        if str(key).strip()
    }
    for candidate in seen_names:
        matched_key = row_lookup.get(candidate.lower())
        if matched_key is not None:
            return row.get(matched_key), matched_key

    for key, value in row.items():
        key_variants = _normalize_key_variants(str(key))
        for candidate in seen_names:
            if any(candidate_variant in key_variants for candidate_variant in _normalize_key_variants(candidate)):
                return value, key
    return None, None
