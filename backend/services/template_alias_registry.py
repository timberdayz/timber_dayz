from __future__ import annotations

from typing import Dict


_SHOPEE_PRODUCTS_STATUS_ALIASES = {
    "销售额（已确认订单）": "销售额（已付款订单）",
    "销售额（已确定订单）": "销售额（已付款订单）",
    "订单转化率（已确认订单）": "订单转化率（已付款订单）",
    "订单转化率（已确定订单）": "订单转化率（已付款订单）",
    "已确认订单": "已付款订单",
    "已确定订单": "已付款订单",
    "件数（已确认订单）": "件数（已付款订单）",
    "件数（已确定订单）": "件数（已付款订单）",
    "买家数（已确认订单）": "买家数（已付款订单）",
    "买家数（已确定订单）": "买家数（已付款订单）",
    "转化率（已确认订单）": "转化率（已付款订单）",
    "转化率（已确定订单）": "转化率（已付款订单）",
    "每笔订单销售额（已确认订单）": "每笔订单销售额（已付款订单）",
    "每笔订单销售额（已确定订单）": "每笔订单销售额（已付款订单）",
    "订单复购率（已确认订单）": "订单复购率（已付款订单）",
    "订单复购率（已确定订单）": "订单复购率（已付款订单）",
    "订单复购的平均天数（已确认订单）": "订单复购的平均天数（已付款订单）",
    "订单复购的平均天数（已确定订单）": "订单复购的平均天数（已付款订单）",
}


_ALIASES: dict[tuple[str, str, str], dict[str, str]] = {
    ("shopee", "products", "daily"): dict(_SHOPEE_PRODUCTS_STATUS_ALIASES),
    ("shopee", "products", "weekly"): dict(_SHOPEE_PRODUCTS_STATUS_ALIASES),
    ("shopee", "products", "monthly"): dict(_SHOPEE_PRODUCTS_STATUS_ALIASES),
}


def get_header_alias_mapping(platform: str, data_domain: str, granularity: str) -> Dict[str, str]:
    key = (
        str(platform or "").strip().lower(),
        str(data_domain or "").strip().lower(),
        str(granularity or "").strip().lower(),
    )
    return dict(_ALIASES.get(key, {}))
