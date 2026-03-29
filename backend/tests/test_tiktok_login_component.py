from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from modules.apps.collection_center.executor_v2 import VerificationRequiredError
from modules.components.base import ExecutionContext
from modules.platforms.tiktok.components.login import TiktokLogin


def _ctx(
    account: dict | None = None,
    config: dict | None = None,
) -> ExecutionContext:
    return ExecutionContext(
        platform="tiktok",
        account=account
        or {
            "username": "chenzeweinbnb@163.com",
            "password": "secret",
            "phone": "18876067809",
            "login_url": "https://seller.tiktokglobalshop.com/account/login",
        },
        logger=None,
        config=config or {},
    )


class _FakePage:
    def __init__(self, url: str = "about:blank") -> None:
        self.url = url
        self.goto_calls: list[str] = []
        self.timeout_calls: list[int] = []
        self.screenshot_paths: list[str] = []

    async def goto(
        self,
        url: str,
        wait_until: str = "domcontentloaded",
        timeout: int = 60000,
    ) -> None:
        self.goto_calls.append(url)
        self.url = url

    async def wait_for_timeout(self, ms: int) -> None:
        self.timeout_calls.append(ms)

    async def screenshot(self, path: str, timeout: int = 5000) -> None:
        self.screenshot_paths.append(path)


def test_tiktok_login_success_detection_accepts_non_login_seller_urls() -> None:
    component = TiktokLogin(_ctx())

    assert (
        component._login_looks_successful("https://seller.tiktokshopglobalselling.com/homepage")
        is True
    )
    assert (
        component._login_looks_successful("https://seller.tiktokglobalshop.com/orders")
        is True
    )


def test_tiktok_login_success_detection_rejects_login_urls() -> None:
    component = TiktokLogin(_ctx())

    assert (
        component._login_looks_successful("https://seller.tiktokshopglobalselling.com/account/login")
        is False
    )
    assert component._login_looks_successful("https://seller.tiktokglobalshop.com/account/login") is False


def test_tiktok_login_prefers_phone_for_phone_mode() -> None:
    component = TiktokLogin(_ctx())

    assert (
        component._credential_value_for_mode(
            {
                "phone": "18876067809",
                "email": "demo@example.com",
                "username": "fallback@example.com",
            },
            "phone",
        )
        == "18876067809"
    )


def test_tiktok_login_prefers_email_for_email_mode() -> None:
    component = TiktokLogin(_ctx())

    assert (
        component._credential_value_for_mode(
            {
                "phone": "18876067809",
                "email": "demo@example.com",
                "username": "fallback@example.com",
            },
            "email",
        )
        == "demo@example.com"
    )


@pytest.mark.asyncio
async def test_tiktok_login_requires_login_url() -> None:
    component = TiktokLogin(_ctx(account={"username": "user", "password": "pass"}))

    result = await component.run(_FakePage("https://seller.tiktokglobalshop.com/account/login"))

    assert result.success is False
    assert result.message == "login_url is required in account"


@pytest.mark.asyncio
async def test_tiktok_login_already_logged_in_short_circuits() -> None:
    component = TiktokLogin(_ctx())
    page = _FakePage("https://seller.tiktokshopglobalselling.com/homepage")

    result = await component.run(page)

    assert result.success is True
    assert result.message == "already logged in"


@pytest.mark.asyncio
async def test_tiktok_login_raises_verification_required_when_otp_is_needed_without_value(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    component = TiktokLogin(
        _ctx(
            config={
                "task": {"screenshot_dir": str(tmp_path)},
                "params": {},
            }
        )
    )
    page = _FakePage("https://seller.tiktokglobalshop.com/account/login")

    monkeypatch.setattr(component, "_ensure_login_mode", AsyncMock())
    monkeypatch.setattr(component, "_fill_credentials", AsyncMock())
    monkeypatch.setattr(component, "_submit_credentials", AsyncMock())
    monkeypatch.setattr(component, "_find_visible_login_error", AsyncMock(return_value=None))
    monkeypatch.setattr(component, "_is_otp_visible", AsyncMock(return_value=True))
    monkeypatch.setattr(component, "_ensure_trust_device_checked", AsyncMock())

    with pytest.raises(VerificationRequiredError) as exc_info:
        await component.run(page)

    assert exc_info.value.verification_type == "otp"
    assert page.screenshot_paths


@pytest.mark.asyncio
async def test_tiktok_login_resume_with_runtime_otp_reaches_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component = TiktokLogin(
        _ctx(
            config={
                "params": {"otp": "123456"},
            }
        )
    )
    page = _FakePage("https://seller.tiktokglobalshop.com/account/login")

    monkeypatch.setattr(component, "_is_otp_visible", AsyncMock(return_value=True))
    monkeypatch.setattr(component, "_fill_otp", AsyncMock())
    monkeypatch.setattr(component, "_ensure_trust_device_checked", AsyncMock())

    async def _confirm(current_page) -> None:
        current_page.url = "https://seller.tiktokshopglobalselling.com/homepage"

    monkeypatch.setattr(component, "_confirm_otp", _confirm)
    monkeypatch.setattr(component, "_find_visible_otp_error", AsyncMock(return_value=None))

    result = await component.run(page)

    assert result.success is True
    assert result.message == "ok"
