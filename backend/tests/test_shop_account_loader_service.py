from types import SimpleNamespace

from backend.services.shop_account_loader_service import ShopAccountLoaderService


def test_shop_account_loader_service_uses_platform_login_entry():
    service = ShopAccountLoaderService()
    service._decrypt_password = lambda encrypted: "plain-password"

    payload = service._build_payload(
        SimpleNamespace(
            id=1,
            platform="shopee",
            main_account_id="chenewei666:main",
            username="demo-user",
            password_encrypted="enc",
            login_url="https://seller.shopee.cn/account/signin?next=%2Fportal%2Fproduct%2Flist%2Fall%3Fcnsc_shop_id%3D1407964586%26page%3D1",
            enabled=True,
            notes="",
        ),
        SimpleNamespace(
            id=2,
            platform="shopee",
            shop_account_id="shopee_sg_chenewei666_local",
            main_account_id="chenewei666:main",
            store_name="chenewei666.sg",
            platform_shop_id="1227491331",
            platform_shop_id_status="confirmed",
            shop_region="SG",
            shop_type="local",
            enabled=True,
            notes="",
        ),
        {"analytics": True},
    )

    assert (
        payload["compat_account"]["login_url"]
        == "https://seller.shopee.cn/account/signin?next=%2Fportal%2Fhome"
    )
    assert (
        payload["main_account"]["login_url"]
        == "https://seller.shopee.cn/account/signin?next=%2Fportal%2Fhome"
    )


def test_shop_account_loader_service_fills_missing_shopee_shop_id_from_override():
    service = ShopAccountLoaderService()
    service._decrypt_password = lambda encrypted: "plain-password"

    payload = service._build_payload(
        SimpleNamespace(
            id=1,
            platform="shopee",
            main_account_id="hongxikeji:main",
            username="demo-user",
            password_encrypted="enc",
            login_url="https://seller.shopee.cn/account/signin?next=%2Fportal%2Fhome",
            enabled=True,
            notes="",
        ),
        SimpleNamespace(
            id=2,
            platform="shopee",
            shop_account_id="shopee_my_xhkj13_local",
            main_account_id="hongxikeji:main",
            store_name="xhkj13.my",
            platform_shop_id="",
            platform_shop_id_status="missing",
            shop_region="MY",
            shop_type="local",
            enabled=True,
            notes="",
        ),
        {"products": True},
    )

    assert payload["compat_account"]["shop_id"] == "1540271744"
    assert payload["shop_context"]["platform_shop_id"] == "1540271744"
