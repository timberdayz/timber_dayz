from backend.services.shopee_shop_id_resolver import resolve_shopee_platform_shop_id
from modules.components.base import ExecutionContext
from modules.platforms.shopee.components.shop_switch import ShopeeShopSwitch


def test_shopee_shop_id_resolver_maps_zewei_toys_store_name_to_confirmed_shop_id():
    resolved = resolve_shopee_platform_shop_id(
        platform="shopee",
        account_id="shopee_sg_zewei_toys_local",
        store_name="zewei_toys.sg",
        platform_shop_id="",
    )

    assert resolved == "1407964586"


def test_shopee_shop_id_resolver_maps_chenewei666_store_name_to_confirmed_shop_id():
    resolved = resolve_shopee_platform_shop_id(
        platform="shopee",
        account_id="shopee_sg_chenewei666_local",
        store_name="chenewei666.sg",
        platform_shop_id="",
    )

    assert resolved == "1227491331"


def test_shopee_shop_switch_prefers_confirmed_store_mapping_over_stale_config_shop_id():
    switch = ShopeeShopSwitch(
        ExecutionContext(
            platform="shopee",
            account={
                "account_id": "shopee_sg_zewei_toys_local",
                "store_name": "zewei_toys.sg",
                "shop_id": "1227491331",
            },
            config={
                "shop_name": "zewei_toys.sg",
                "shop_id": "1227491331",
            },
        )
    )

    assert switch._target_shop_id() == "1407964586"
