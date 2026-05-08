from pathlib import Path

from modules.platforms.tiktok.components.shop_switch import TiktokShopSwitch


def test_tiktok_shop_switch_is_no_longer_a_wrapper_over_shop_selector():
    source = Path("modules/platforms/tiktok/components/shop_switch.py").read_text(encoding="utf-8")

    assert "from modules.platforms.tiktok.components.shop_selector import" not in source
    assert "class TiktokShopSwitch" in source
    assert "async def run(" in source


def test_tiktok_shop_switch_keeps_canonical_metadata():
    assert TiktokShopSwitch.platform == "tiktok"
    assert TiktokShopSwitch.component_type == "shop_switch"
    assert TiktokShopSwitch.data_domain is None
