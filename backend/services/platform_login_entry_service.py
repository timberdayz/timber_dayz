from __future__ import annotations


PLATFORM_LOGIN_ENTRIES = {
    "shopee": "https://seller.shopee.cn/account/signin?next=%2Fportal%2Fhome",
    "miaoshou": "https://erp.91miaoshou.com",
    "tiktok": "https://seller.tiktokshopglobalselling.com/account/login",
    "amazon": "https://sellercentral.amazon.com",
}


def get_platform_login_entry(platform: str) -> str:
    key = str(platform or "").strip().lower()
    value = PLATFORM_LOGIN_ENTRIES.get(key)
    if not value:
        raise ValueError(f"unsupported platform: {platform}")
    return value


def normalize_main_account_login_url(platform: str, login_url: str | None) -> str:
    # In the current test environment, runtime login entry is fully platform-owned.
    # Persist the platform-standard login entry regardless of historical shop-bound input.
    return get_platform_login_entry(platform)
