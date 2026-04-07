import pytest


def test_platform_login_entry_service_returns_shopee_shop_neutral_entry():
    from backend.services.platform_login_entry_service import get_platform_login_entry

    value = get_platform_login_entry("shopee")

    assert value.startswith("https://seller.shopee.cn/account/signin")
    assert "cnsc_shop_id=" not in value
    assert "shop_id=" not in value


def test_platform_login_entry_service_returns_miaoshou_shop_neutral_entry():
    from backend.services.platform_login_entry_service import get_platform_login_entry

    value = get_platform_login_entry("miaoshou")

    assert value == "https://erp.91miaoshou.com"


def test_platform_login_entry_service_returns_tiktok_shop_neutral_entry():
    from backend.services.platform_login_entry_service import get_platform_login_entry

    value = get_platform_login_entry("tiktok")

    assert "seller.tiktokshopglobalselling.com" in value
    assert "shop_id=" not in value
    assert "shop_region=" not in value


def test_platform_login_entry_service_rejects_unknown_platform():
    from backend.services.platform_login_entry_service import get_platform_login_entry

    with pytest.raises(ValueError, match="unsupported platform"):
        get_platform_login_entry("unknown")
