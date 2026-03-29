from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from modules.apps.collection_center.executor_v2 import VerificationRequiredError
from modules.components.base import ExecutionContext
from modules.platforms.shopee.components.login import ShopeeLogin


def _ctx(
    account: dict | None = None,
    config: dict | None = None,
) -> ExecutionContext:
    return ExecutionContext(
        platform="shopee",
        account=account
        or {
            "username": "user",
            "password": "pass",
            "login_url": "https://seller.shopee.cn/account/signin?next=%2F",
        },
        logger=None,
        config=config or {},
    )


class _FakeLocator:
    def __init__(self, *, visible: bool = True) -> None:
        self.visible = visible
        self.clicked = False
        self.filled_values: list[str] = []
        self.children: dict[str, "_FakeLocator"] = {}

    @property
    def first(self) -> "_FakeLocator":
        return self

    async def count(self) -> int:
        return 1 if self.visible else 0

    async def is_visible(self, timeout: int | None = None) -> bool:
        return self.visible

    async def click(self, timeout: int | None = None) -> None:
        self.clicked = True

    async def fill(self, value: str, timeout: int | None = None) -> None:
        self.filled_values.append(value)

    def locator(self, selector: str) -> "_FakeLocator":
        return self.children.get(selector, _FakeLocator(visible=False))


class _FakePage:
    def __init__(self, url: str = "about:blank") -> None:
        self.url = url
        self.goto_calls: list[str] = []
        self.timeout_calls: list[int] = []
        self.screenshot_paths: list[str] = []
        self.text_map: dict[str, _FakeLocator] = {}
        self.selector_map: dict[str, _FakeLocator] = {}

    async def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int = 60000) -> None:
        self.goto_calls.append(url)
        self.url = url

    async def wait_for_timeout(self, ms: int) -> None:
        self.timeout_calls.append(ms)

    async def screenshot(self, path: str, timeout: int = 5000) -> None:
        self.screenshot_paths.append(path)

    def locator(self, selector: str) -> _FakeLocator:
        return self.selector_map.get(selector, _FakeLocator(visible=False))

    def get_by_text(self, text: str, exact: bool = False) -> _FakeLocator:
        return self.text_map.get(text, _FakeLocator(visible=False))

    def get_by_role(self, role: str, name=None) -> _FakeLocator:
        key = f"{role}:{name.pattern if hasattr(name, 'pattern') else name}"
        return self.selector_map.get(key, _FakeLocator(visible=False))


def test_shopee_login_success_detection_accepts_homepage_urls() -> None:
    component = ShopeeLogin(_ctx())

    assert component._login_looks_successful("https://seller.shopee.cn/?cnsc_shop_id=1") is True
    assert component._login_looks_successful("https://seller.shopee.cn/portal/sale/order") is True


def test_shopee_login_homepage_detection_rejects_non_homepage_urls() -> None:
    component = ShopeeLogin(_ctx())

    assert component._homepage_looks_ready("https://seller.shopee.cn/?cnsc_shop_id=1") is True
    assert component._homepage_looks_ready("https://seller.shopee.cn/datacenter/home?cnsc_shop_id=1") is False
    assert component._homepage_looks_ready("https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1") is False


def test_shopee_login_success_detection_rejects_signin_urls() -> None:
    component = ShopeeLogin(_ctx())

    assert component._login_looks_successful("https://seller.shopee.cn/account/signin") is False
    assert component._login_looks_successful("https://seller.shopee.cn/account/signin?next=%2F") is False


def test_shopee_login_otp_mode_from_title_distinguishes_phone_and_email() -> None:
    component = ShopeeLogin(_ctx())

    assert component._otp_mode_from_title("验证电话号码") == "phone"
    assert component._otp_mode_from_title("邮箱验证") == "email"
    assert component._otp_mode_from_title("其他验证") is None


@pytest.mark.asyncio
async def test_shopee_login_requires_login_url() -> None:
    component = ShopeeLogin(_ctx(account={"username": "user", "password": "pass"}))

    result = await component.run(_FakePage("https://seller.shopee.cn/account/signin"))

    assert result.success is False
    assert result.message == "login_url is required in account"


@pytest.mark.asyncio
async def test_shopee_login_already_logged_in_short_circuits(monkeypatch: pytest.MonkeyPatch) -> None:
    component = ShopeeLogin(_ctx())
    page = _FakePage("https://seller.shopee.cn/?cnsc_shop_id=1227491331")
    cleaned: list[str] = []

    async def _fake_cleanup(current_page) -> None:
        cleaned.append(str(current_page.url))

    monkeypatch.setattr(component, "_cleanup_after_login", _fake_cleanup)

    result = await component.run(page)

    assert result.success is True
    assert result.message == "already logged in"
    assert cleaned == ["https://seller.shopee.cn/?cnsc_shop_id=1227491331"]


@pytest.mark.asyncio
async def test_shopee_login_ensure_phone_otp_mode_clicks_switch_from_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component = ShopeeLogin(_ctx())
    switch = _FakeLocator()

    monkeypatch.setattr(component, "_otp_mode", AsyncMock(side_effect=["email", "phone"]))
    monkeypatch.setattr(component, "_phone_otp_switch_locator", lambda page: switch)

    await component._ensure_phone_otp_mode(_FakePage("https://seller.shopee.cn/account/signin"))

    assert switch.clicked is True


@pytest.mark.asyncio
async def test_shopee_login_raises_verification_required_when_otp_is_needed_without_value(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    component = ShopeeLogin(
        _ctx(
            config={
                "task": {"screenshot_dir": str(tmp_path)},
                "params": {},
            }
        )
    )
    page = _FakePage("https://seller.shopee.cn/account/signin")

    monkeypatch.setattr(component, "_fill_credentials", AsyncMock())
    monkeypatch.setattr(component, "_submit_credentials", AsyncMock())
    monkeypatch.setattr(component, "_find_visible_login_error", AsyncMock(return_value=None))
    monkeypatch.setattr(component, "_is_otp_visible", AsyncMock(return_value=True))
    monkeypatch.setattr(component, "_ensure_phone_otp_mode", AsyncMock())

    with pytest.raises(VerificationRequiredError) as exc_info:
        await component.run(page)

    assert exc_info.value.verification_type == "otp"
    assert page.screenshot_paths


@pytest.mark.asyncio
async def test_shopee_login_raises_slide_captcha_when_slider_verification_is_visible(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    component = ShopeeLogin(
        _ctx(
            config={
                "task": {"screenshot_dir": str(tmp_path)},
                "params": {},
            }
        )
    )
    page = _FakePage("https://seller.shopee.cn/account/signin")

    monkeypatch.setattr(component, "_fill_credentials", AsyncMock())
    monkeypatch.setattr(component, "_submit_credentials", AsyncMock())
    monkeypatch.setattr(component, "_find_visible_login_error", AsyncMock(return_value=None))
    monkeypatch.setattr(component, "_is_otp_visible", AsyncMock(return_value=False))
    monkeypatch.setattr(component, "_is_slide_captcha_visible", AsyncMock(return_value=True))

    with pytest.raises(VerificationRequiredError) as exc_info:
        await component.run(page)

    assert exc_info.value.verification_type == "slide_captcha"
    assert page.screenshot_paths


@pytest.mark.asyncio
async def test_shopee_login_resume_with_runtime_otp_reaches_homepage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component = ShopeeLogin(
        _ctx(
            config={
                "params": {"otp": "123456"},
            }
        )
    )
    page = _FakePage("https://seller.shopee.cn/account/signin")
    cleaned: list[str] = []

    monkeypatch.setattr(component, "_is_otp_visible", AsyncMock(return_value=True))
    monkeypatch.setattr(component, "_ensure_phone_otp_mode", AsyncMock())
    monkeypatch.setattr(component, "_fill_otp", AsyncMock())
    monkeypatch.setattr(component, "_confirm_otp", AsyncMock(side_effect=lambda current_page: setattr(current_page, "url", "https://seller.shopee.cn/?cnsc_shop_id=1227491331")))
    monkeypatch.setattr(component, "_find_visible_otp_error", AsyncMock(return_value=None))

    async def _fake_cleanup(current_page) -> None:
        cleaned.append(str(current_page.url))

    monkeypatch.setattr(component, "_cleanup_after_login", _fake_cleanup)

    result = await component.run(page)

    assert result.success is True
    assert result.message == "ok"
    assert cleaned == ["https://seller.shopee.cn/?cnsc_shop_id=1227491331"]


@pytest.mark.asyncio
async def test_shopee_login_fresh_submit_does_not_treat_non_homepage_url_as_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component = ShopeeLogin(_ctx())
    page = _FakePage("about:blank")

    async def _fake_submit(current_page) -> None:
        current_page.url = "https://seller.shopee.cn/datacenter/home?cnsc_shop_id=1227491331"

    monkeypatch.setattr(component, "_fill_credentials", AsyncMock())
    monkeypatch.setattr(component, "_submit_credentials", AsyncMock(side_effect=_fake_submit))
    monkeypatch.setattr(component, "_find_visible_login_error", AsyncMock(return_value=None))
    monkeypatch.setattr(component, "_is_otp_visible", AsyncMock(return_value=False))

    result = await component.run(page)

    assert result.success is False
    assert result.message == "login did not reach homepage or otp step"
