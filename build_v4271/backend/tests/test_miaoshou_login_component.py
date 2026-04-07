import sys
import types

import pytest

from modules.components.base import ExecutionContext
from modules.platforms.miaoshou.components.login import MiaoshouLogin


def _ctx():
    return ExecutionContext(
        platform="miaoshou",
        account={"username": "u", "password": "p", "login_url": "https://erp.91miaoshou.com"},
        logger=None,
        config={},
    )


def test_miaoshou_login_success_detection_accepts_dashboard_urls():
    component = MiaoshouLogin(_ctx())

    assert component._login_looks_successful("https://erp.91miaoshou.com/welcome") is True
    assert component._login_looks_successful("https://erp.91miaoshou.com/dashboard") is True


def test_miaoshou_login_success_detection_rejects_login_urls():
    component = MiaoshouLogin(_ctx())

    assert component._login_looks_successful("https://erp.91miaoshou.com/?redirect=%2Fwelcome") is False
    assert component._login_looks_successful("https://erp.91miaoshou.com/login") is False
    assert component._login_looks_successful("https://erp.91miaoshou.com/account/login") is False


def test_miaoshou_login_known_error_texts_include_graphical_captcha_failure():
    component = MiaoshouLogin(_ctx())

    assert "图形验证码不正确" in component._known_login_error_texts()


@pytest.mark.asyncio
async def test_miaoshou_login_cleanup_after_login_invokes_overlay_guard(monkeypatch):
    component = MiaoshouLogin(_ctx())
    calls = []

    class _FakeGuard:
        async def run(self, page, *, label=None):
            calls.append(label)
            return 1

    monkeypatch.setitem(
        sys.modules,
        "modules.platforms.miaoshou.components.overlay_guard",
        types.SimpleNamespace(OverlayGuard=_FakeGuard),
    )

    await component._cleanup_after_login(page=object())

    assert calls == ["post-login cleanup"]


@pytest.mark.asyncio
async def test_miaoshou_login_returns_success_when_goto_redirects_to_welcome(monkeypatch):
    component = MiaoshouLogin(_ctx())
    cleaned = []

    class _Page:
        def __init__(self):
            self.url = "about:blank"

        async def goto(self, url, wait_until="domcontentloaded", timeout=60000):
            self.url = "https://erp.91miaoshou.com/welcome"

        def get_by_text(self, text, exact=False):
            class _Locator:
                def __init__(self):
                    self.first = self

                async def is_visible(self, timeout=0):
                    return True

            return _Locator()

    async def _fake_cleanup(page):
        cleaned.append(str(getattr(page, "url", "")))

    monkeypatch.setattr(component, "_cleanup_after_login", _fake_cleanup)

    result = await component.run(_Page())

    assert result.success is True
    assert result.message == "ok"
    assert cleaned == ["https://erp.91miaoshou.com/welcome"]


def test_miaoshou_login_homepage_ready_texts_include_dashboard_signals():
    component = MiaoshouLogin(_ctx())

    markers = component._homepage_ready_texts()

    assert "待办事项" in markers
    assert "常用功能" in markers
