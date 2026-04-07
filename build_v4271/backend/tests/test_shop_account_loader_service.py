from types import SimpleNamespace

from backend.services.shop_account_loader_service import ShopAccountLoaderService


def test_shop_account_loader_service_normalizes_login_url_to_origin():
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

    assert payload["compat_account"]["login_url"] == "https://seller.shopee.cn"
    assert payload["main_account"]["login_url"] == "https://seller.shopee.cn"
