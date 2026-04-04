from backend.schemas.shop_discovery import ShopDiscoveryRunRequest
from backend.services.shop_discovery_service import ShopDiscoveryService


def test_extract_current_shop_context_prefers_url_shop_id():
    service = ShopDiscoveryService()

    result = service.extract_current_shop_context(
        platform="shopee",
        current_url="https://seller.example/path?shop_id=1227491331&region=SG",
        dom_snapshot={"store_name": "HongXi SG"},
    )

    assert result["detected_platform_shop_id"] == "1227491331"
    assert result["detected_region"] == "SG"
    assert result["detected_store_name"] == "HongXi SG"
    assert result["source"]["platform_shop_id"] == "url"
    assert result["confidence"] == 0.95


def test_extract_current_shop_context_falls_back_to_dom():
    service = ShopDiscoveryService()

    result = service.extract_current_shop_context(
        platform="shopee",
        current_url="https://seller.example/path",
        dom_snapshot={"store_name": "HongXi SG", "region": "SG"},
    )

    assert result["detected_platform_shop_id"] is None
    assert result["detected_region"] == "SG"
    assert result["detected_store_name"] == "HongXi SG"
    assert result["source"]["store_name"] == "dom"
    assert result["confidence"] == 0.8
