from types import SimpleNamespace

from backend.services.operation_performance_shop_scope_service import (
    OperationPerformanceShopScopeService,
)


def test_build_candidates_only_includes_enabled_operating_accounts_with_exact_keys():
    candidates, unresolved = OperationPerformanceShopScopeService.build_candidates(
        accounts=[
            SimpleNamespace(
                id=1,
                platform="shopee",
                platform_shop_id="S001",
                shop_account_id="shop-account-1",
                store_name="新加坡旗舰店",
                enabled=True,
                business_role="operating_store",
            ),
            SimpleNamespace(
                id=2,
                platform="shopee",
                platform_shop_id="S002",
                shop_account_id="shop-account-2",
                store_name="停用店",
                enabled=False,
                business_role="operating_store",
            ),
            SimpleNamespace(
                id=3,
                platform="miaoshou",
                platform_shop_id="snapshot_1",
                shop_account_id="collector-1",
                store_name="采集来源",
                enabled=True,
                business_role="collection_source",
            ),
            SimpleNamespace(
                id=4,
                platform="amazon",
                platform_shop_id=None,
                shop_account_id="amazon-fallback",
                store_name="待对齐店",
                enabled=True,
                business_role="operating_store",
            ),
        ],
        dim_shop_keys={("shopee", "S001")},
        aliases_by_account={1: ["xhkj11.sg", "SG 主店"], 4: ["US backup"]},
    )

    assert candidates == [
        {
            "source_shop_account_id": 1,
            "platform_code": "shopee",
            "shop_id": "S001",
            "standard_name": "新加坡旗舰店",
            "aliases": ["xhkj11.sg", "SG 主店"],
        }
    ]
    assert unresolved == [
        {
            "source_shop_account_id": 4,
            "platform_code": "amazon",
            "standard_name": "待对齐店",
            "aliases": ["US backup"],
            "raw_platform_shop_id": None,
            "raw_shop_account_id": "amazon-fallback",
        }
    ]
