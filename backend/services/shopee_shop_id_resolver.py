from __future__ import annotations

from typing import Optional


SHOPEE_PLATFORM_SHOP_ID_OVERRIDES: dict[str, str] = {
    "shopee_my_xhkj1_local": "1540271739",
    "shopee_my_xhkj13_local": "1540271744",
    "shopee_ph_xhkj11_local": "1419169771",
    "shopee_ph_xhkj113_local": "1419165607",
    "shopee_sg_xhkj33_local": "1308200832",
    "shopee_sg_xhkj22_local": "1308200830",
    "shopee_sg_strawberries_store_local": "1391124224",
    "shopee_sg_hx_home_local": "1391124228",
    "shopee_sg_eternalbloom_local": "1292370001",
    "shopee_sg_zewei_toys_local": "1407964586",
    "shopee_sg_chenewei666_local": "1227491331",
}

SHOPEE_STORE_NAME_OVERRIDES: dict[str, str] = {
    "xhkj1.my": "1540271739",
    "xhkj13.my": "1540271744",
    "xhkj11.ph": "1419169771",
    "xhkj113.ph": "1419165607",
    "xhkj33.sg": "1308200832",
    "xhkj22.sg": "1308200830",
    "strawberries_store.sg": "1391124224",
    "hx_home.sg": "1391124228",
    "eternalbloom.sg": "1292370001",
    "zewei_toys.sg": "1407964586",
    "chenewei666.sg": "1227491331",
}


def normalize_shopee_platform_shop_id(value: object) -> str:
    text = str(value or "").strip()
    if text.isdigit():
        return text
    return ""


def resolve_shopee_platform_shop_id(
    *,
    platform: object,
    account_id: object = None,
    store_name: object = None,
    platform_shop_id: object = None,
    shop_id: object = None,
) -> str:
    if str(platform or "").strip().lower() != "shopee":
        return str(platform_shop_id or shop_id or "").strip()

    account_key = str(account_id or "").strip()
    if account_key and account_key in SHOPEE_PLATFORM_SHOP_ID_OVERRIDES:
        return SHOPEE_PLATFORM_SHOP_ID_OVERRIDES[account_key]

    store_key = str(store_name or "").strip().lower()
    if store_key and store_key in SHOPEE_STORE_NAME_OVERRIDES:
        return SHOPEE_STORE_NAME_OVERRIDES[store_key]

    normalized = normalize_shopee_platform_shop_id(platform_shop_id)
    if normalized:
        return normalized

    normalized = normalize_shopee_platform_shop_id(shop_id)
    if normalized:
        return normalized

    return ""
