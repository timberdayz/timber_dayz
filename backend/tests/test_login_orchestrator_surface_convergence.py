import pytest

from modules.utils.login_orchestrator import LoginOrchestrator


def test_login_orchestrator_only_advertises_miaoshou_by_default():
    orchestrator = LoginOrchestrator(browser=None)

    assert orchestrator.supported_platforms == ["miaoshou", "miaoshou_erp"]


def test_login_orchestrator_rejects_shopee_and_tiktok_legacy_platform_keys():
    orchestrator = LoginOrchestrator(browser=None)

    with pytest.raises(ValueError):
        orchestrator._get_platform_key("shopee")

    with pytest.raises(ValueError):
        orchestrator._get_platform_key("tiktok")
