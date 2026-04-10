import importlib

import pytest

from modules.apps.collection_center.popup_handler import UniversalPopupHandler


class _FakeLocator:
    def __init__(self, *, visible: bool = False) -> None:
        self._visible = visible
        self.first = self
        self.click_count = 0

    async def is_visible(self, timeout: int = 0) -> bool:  # noqa: ARG002
        return self._visible

    async def count(self) -> int:
        return 1 if self._visible else 0

    async def click(self, timeout: int = 0) -> None:  # noqa: ARG002
        self.click_count += 1


class _FakePage:
    def __init__(self, locator_map: dict[str, _FakeLocator]) -> None:
        self._locator_map = locator_map
        self.frames = []
        self.keyboard = self
        self.esc_count = 0

    def locator(self, selector: str) -> _FakeLocator:
        return self._locator_map.setdefault(selector, _FakeLocator())

    async def press(self, key: str) -> None:
        if key == "Escape":
            self.esc_count += 1


def test_platform_popup_configs_expose_safe_notice_contract() -> None:
    for module_name in (
        "modules.platforms.miaoshou.popup_config",
        "modules.platforms.shopee.popup_config",
        "modules.platforms.tiktok.popup_config",
    ):
        module = importlib.import_module(module_name)
        assert hasattr(module, "get_safe_notice_close_selectors")
        assert hasattr(module, "get_safe_notice_overlay_selectors")
        assert hasattr(module, "get_safe_notice_exclusion_selectors")
        assert hasattr(module, "get_poll_strategy")


def test_miaoshou_popup_config_exposes_non_empty_safe_notice_rules() -> None:
    module = importlib.import_module("modules.platforms.miaoshou.popup_config")

    close_selectors = module.get_safe_notice_close_selectors()
    overlay_selectors = module.get_safe_notice_overlay_selectors()

    assert close_selectors
    assert overlay_selectors


@pytest.mark.asyncio
async def test_close_safe_notices_clicks_platform_close_selector(monkeypatch) -> None:
    handler = UniversalPopupHandler()
    close_locator = _FakeLocator(visible=True)
    page = _FakePage({"safe-close": close_locator})

    monkeypatch.setattr(
        handler,
        "_load_platform_config",
        lambda platform: {  # noqa: ARG005
            "safe_notice_close_selectors": ["safe-close"],
            "safe_notice_overlay_selectors": ["safe-overlay"],
            "safe_notice_exclusion_selectors": [],
            "poll_strategy": {"max_rounds": 1, "interval_ms": 1, "watch_ms": 5},
        },
    )

    closed = await handler.close_safe_notices(page, platform="miaoshou")

    assert closed == 1
    assert close_locator.click_count == 1


@pytest.mark.asyncio
async def test_close_safe_notices_skips_when_exclusion_selector_is_visible(monkeypatch) -> None:
    handler = UniversalPopupHandler()
    close_locator = _FakeLocator(visible=True)
    exclusion_locator = _FakeLocator(visible=True)
    page = _FakePage(
        {
            "safe-close": close_locator,
            "critical-dialog": exclusion_locator,
        }
    )

    monkeypatch.setattr(
        handler,
        "_load_platform_config",
        lambda platform: {  # noqa: ARG005
            "safe_notice_close_selectors": ["safe-close"],
            "safe_notice_overlay_selectors": ["safe-overlay"],
            "safe_notice_exclusion_selectors": ["critical-dialog"],
            "poll_strategy": {"max_rounds": 1, "interval_ms": 1, "watch_ms": 5},
        },
    )

    closed = await handler.close_safe_notices(page, platform="miaoshou")

    assert closed == 0
    assert close_locator.click_count == 0
