from types import SimpleNamespace

from backend.services.shop_account_loader_service import ShopAccountLoaderService


def test_build_payload_returns_split_main_account_and_shop_context(monkeypatch):
    main_account = SimpleNamespace(
        id=1,
        platform="shopee",
        main_account_id="hongxikeji:main",
        username="demo-user",
        password_encrypted="encrypted",
        login_url="https://seller.shopee.cn",
        enabled=True,
        notes="shared login",
    )
    shop_account = SimpleNamespace(
        id=2,
        platform="shopee",
        shop_account_id="shopee_sg_hongxi_local",
        main_account_id="hongxikeji:main",
        store_name="HongXi SG",
        platform_shop_id="1227491331",
        platform_shop_id_status="manual_confirmed",
        shop_region="SG",
        shop_type="local",
        enabled=True,
        notes="shop note",
    )

    service = ShopAccountLoaderService()
    monkeypatch.setattr(service, "_decrypt_password", lambda encrypted: "plain-password")

    payload = service._build_payload(
        main_account,
        shop_account,
        {"orders": True, "products": False},
    )

    assert payload["main_account"]["main_account_id"] == "hongxikeji:main"
    assert payload["shop_context"]["shop_account_id"] == "shopee_sg_hongxi_local"
    assert payload["shop_context"]["platform_shop_id"] == "1227491331"
    assert payload["capabilities"] == {"orders": True, "products": False}
    assert payload["compat_account"]["account_id"] == "shopee_sg_hongxi_local"
    assert payload["compat_account"]["password"] == "plain-password"
