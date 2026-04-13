from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from modules.components.base import ExecutionContext
from modules.platforms.shopee.components.login import ShopeeLogin


class _FakeShopeeLoginPage:
    def __init__(self) -> None:
        self.url = "about:blank"
        self._wait_calls = 0

    async def goto(self, url: str, **_: object) -> None:
        self.url = "https://seller.shopee.cn/account/signin?next=%2Fportal%2Fproduct%2Flist"

    async def wait_for_timeout(self, _ms: int) -> None:
        self._wait_calls += 1
        if self._wait_calls >= 2:
            self.url = "https://seller.shopee.cn/portal/product/list?cnsc_shop_id=1227491331"


@pytest.mark.asyncio
async def test_shopee_login_waits_for_reused_session_redirect_before_filling_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = ExecutionContext(
        platform="shopee",
        account={
            "username": "chenewei666:main",
            "password": "secret",
            "login_url": "https://seller.shopee.cn/account/signin?next=%2Fportal%2Fproduct%2Flist",
        },
        config={"params": {"reused_session": True}},
    )
    component = ShopeeLogin(ctx)
    page = _FakeShopeeLoginPage()

    fill_credentials = AsyncMock()
    cleanup_after_login = AsyncMock()

    monkeypatch.setattr(component, "_fill_credentials", fill_credentials, raising=False)
    monkeypatch.setattr(component, "_cleanup_after_login", cleanup_after_login, raising=False)
    monkeypatch.setattr(component, "_is_otp_visible", AsyncMock(return_value=False), raising=False)
    monkeypatch.setattr(component, "_wait_for_post_login_outcome", AsyncMock(return_value="timeout"), raising=False)

    result = await component.run(page)

    assert result.success is True
    assert result.message == "ok"
    fill_credentials.assert_not_awaited()
    cleanup_after_login.assert_awaited_once()


class _FakeStableShellPage:
    def __init__(self) -> None:
        self.url = "https://seller.shopee.cn/portal/merchant/setting?cnsc_shop_id=1227491331"
        self.wait_for_timeout = AsyncMock()


@pytest.mark.asyncio
async def test_shopee_login_treats_stable_logged_in_shell_page_as_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = ExecutionContext(
        platform="shopee",
        account={"username": "chenewei666:main"},
        config={},
    )
    component = ShopeeLogin(ctx)
    page = _FakeStableShellPage()

    monkeypatch.setattr(component, "_find_visible_login_error", AsyncMock(return_value=None), raising=False)
    monkeypatch.setattr(component, "_homepage_dom_looks_ready", AsyncMock(return_value=False), raising=False)
    monkeypatch.setattr(component, "_is_otp_visible", AsyncMock(return_value=False), raising=False)
    monkeypatch.setattr(component, "_is_slide_captcha_visible", AsyncMock(return_value=False), raising=False)
    monkeypatch.setattr(
        component,
        "_session_shell_looks_ready",
        AsyncMock(side_effect=[True, True]),
        raising=False,
    )

    result = await component._wait_for_post_login_outcome(
        page,
        phase="post_manual_verification",
        timeout_ms=50,
        poll_ms=10,
    )

    assert result == "success"


@pytest.mark.asyncio
async def test_shopee_login_waits_for_shell_to_stabilize_before_declaring_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = ExecutionContext(
        platform="shopee",
        account={"username": "chenewei666:main"},
        config={},
    )
    component = ShopeeLogin(ctx)
    page = _FakeStableShellPage()

    monkeypatch.setattr(component, "_find_visible_login_error", AsyncMock(return_value=None), raising=False)
    monkeypatch.setattr(component, "_homepage_dom_looks_ready", AsyncMock(return_value=False), raising=False)
    monkeypatch.setattr(component, "_is_otp_visible", AsyncMock(return_value=False), raising=False)
    monkeypatch.setattr(component, "_is_slide_captcha_visible", AsyncMock(return_value=False), raising=False)
    monkeypatch.setattr(
        component,
        "_session_shell_looks_ready",
        AsyncMock(side_effect=[False, True, True]),
        raising=False,
    )

    result = await component._wait_for_post_login_outcome(
        page,
        phase="post_manual_verification",
        timeout_ms=80,
        poll_ms=10,
    )

    assert result == "success"
    assert page.wait_for_timeout.await_count >= 2
