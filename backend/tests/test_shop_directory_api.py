from types import SimpleNamespace


def test_shop_directory_response_prefers_alias_then_canonical_then_shop_id():
    from backend.domains.platform.routers.reference import _serialize_shop_directory_item

    aliased = _serialize_shop_directory_item(
        SimpleNamespace(
            platform="shopee",
            platform_shop_id="shop-1",
            shop_account_id="shopee_sg_shop_1",
            main_account_id="main-1",
            store_name="HongXi Singapore Local",
            shop_region="SG",
            enabled=True,
        ),
        "新加坡1店",
    )
    assert aliased.display_name == "新加坡1店"
    assert aliased.canonical_name == "HongXi Singapore Local"
    assert aliased.shop_id == "shop-1"

    canonical = _serialize_shop_directory_item(
        SimpleNamespace(
            platform="shopee",
            platform_shop_id="shop-2",
            shop_account_id="shopee_sg_shop_2",
            main_account_id="main-1",
            store_name="HongXi Singapore 2",
            shop_region="SG",
            enabled=True,
        ),
        None,
    )
    assert canonical.display_name == "HongXi Singapore 2"

    fallback = _serialize_shop_directory_item(
        SimpleNamespace(
            platform="shopee",
            platform_shop_id=None,
            shop_account_id="shopee_sg_shop_3",
            main_account_id="main-1",
            store_name="",
            shop_region="SG",
            enabled=True,
        ),
        None,
    )
    assert fallback.display_name == "shopee_sg_shop_3"


def test_shop_directory_route_is_registered_in_production_runtime(monkeypatch):
    import importlib
    import backend.main as main_module

    monkeypatch.setenv("APP_RUNTIME_MODE", "production")
    module = importlib.reload(main_module)
    paths = {route.path for route in module.app.routes if hasattr(route, "path")}

    assert "/api/reference/shop-directory" in paths
