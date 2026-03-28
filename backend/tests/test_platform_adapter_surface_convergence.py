import pytest

from modules.components.base import ExecutionContext
from modules.platforms.miaoshou.adapter import MiaoshouAdapter
from modules.platforms.shopee.adapter import ShopeeAdapter
from modules.platforms.tiktok.adapter import TiktokAdapter


def _ctx(platform: str):
    return ExecutionContext(
        platform=platform,
        account={"username": "u"},
        logger=None,
        config={},
    )


def test_miaoshou_adapter_keeps_login_only_and_rejects_legacy_helper_slots():
    adapter = MiaoshouAdapter(_ctx("miaoshou"))

    assert adapter.login() is not None
    with pytest.raises(NotImplementedError):
        adapter.navigation()
    with pytest.raises(NotImplementedError):
        adapter.date_picker()
    with pytest.raises(NotImplementedError):
        adapter.exporter()


def test_shopee_adapter_rejects_legacy_default_slots_until_v2_migration():
    adapter = ShopeeAdapter(_ctx("shopee"))

    with pytest.raises(NotImplementedError):
        adapter.navigation()
    with pytest.raises(NotImplementedError):
        adapter.date_picker()
    with pytest.raises(NotImplementedError):
        adapter.exporter()


def test_tiktok_adapter_rejects_legacy_default_slots_until_v2_migration():
    adapter = TiktokAdapter(_ctx("tiktok"))

    with pytest.raises(NotImplementedError):
        adapter.navigation()
    with pytest.raises(NotImplementedError):
        adapter.date_picker()
    with pytest.raises(NotImplementedError):
        adapter.exporter()
    with pytest.raises(NotImplementedError):
        adapter.shop_selector()
