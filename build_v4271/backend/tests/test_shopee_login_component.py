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
        self.checked = False
        self.check_calls = 0
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

    async def is_checked(self) -> bool:
        return self.checked

    async def check(self, timeout: int | None = None) -> None:
        self.checked = True
        self.check_calls += 1

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
    assert component._login_looks_successful("https://seller.shopee.cn/datacenter/home") is True


def test_shopee_login_homepage_detection_rejects_non_homepage_urls() -> None:
    component = ShopeeLogin(_ctx())

    assert component._homepage_looks_ready("https://seller.shopee.cn/?cnsc_shop_id=1") is True
    assert component._homepage_looks_ready("https://seller.shopee.cn/datacenter/home?cnsc_shop_id=1") is False
    assert component._homepage_looks_ready("https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1") is False


@pytest.mark.asyncio
async def test_shopee_login_homepage_dom_detection_requires_navigation_signals() -> None:
    component = ShopeeLogin(_ctx())
    page = _FakePage("https://seller.shopee.cn/?cnsc_shop_id=1227491331")
    page.selector_map['a[href*="/datacenter/"]'] = _FakeLocator()
    page.selector_map['a[href*="/portal/sale/order"]'] = _FakeLocator()

    assert await component._homepage_dom_looks_ready(page) is True


@pytest.mark.asyncio
async def test_shopee_login_post_otp_wait_requires_stable_homepage_dom(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component = ShopeeLogin(_ctx(config={"params": {"otp": "123456"}}))
    page = _FakePage("https://seller.shopee.cn/?cnsc_shop_id=1227491331")

    monkeypatch.setattr(component, "_find_visible_login_error", AsyncMock(return_value=None))
    monkeypatch.setattr(component, "_find_visible_otp_error", AsyncMock(return_value=None))
    monkeypatch.setattr(component, "_is_otp_visible", AsyncMock(return_value=False))
    monkeypatch.setattr(component, "_is_slide_captcha_visible", AsyncMock(return_value=False))
    monkeypatch.setattr(
        component,
        "_homepage_dom_looks_ready",
        AsyncMock(side_effect=[False, True, True]),
    )

    outcome = await component._wait_for_post_login_outcome(
        page,
        phase="post_otp_submit",
        timeout_ms=100,
        poll_ms=1,
    )

    assert outcome == "success"


@pytest.mark.asyncio
async def test_shopee_login_post_otp_submit_does_not_fail_while_otp_modal_is_still_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component = ShopeeLogin(_ctx(config={"params": {"otp": "123456"}}))
    page = _FakePage("https://seller.shopee.cn/account/signin")

    monkeypatch.setattr(component, "_find_visible_login_error", AsyncMock(return_value=None))
    monkeypatch.setattr(component, "_find_visible_otp_error", AsyncMock(return_value=None))
    monkeypatch.setattr(component, "_is_slide_captcha_visible", AsyncMock(return_value=False))
    homepage_checks = {"count": 0}

    async def _fake_homepage_dom_ready(*args, **kwargs):
        homepage_checks["count"] += 1
        return homepage_checks["count"] >= 2 and page.url.startswith(
            "https://seller.shopee.cn/?cnsc_shop_id="
        )

    monkeypatch.setattr(
        component,
        "_homepage_dom_looks_ready",
        AsyncMock(side_effect=_fake_homepage_dom_ready),
    )
    otp_checks = {"count": 0}

    async def _fake_is_otp_visible(*args, **kwargs):
        otp_checks["count"] += 1
        return otp_checks["count"] <= 2

    monkeypatch.setattr(component, "_is_otp_visible", AsyncMock(side_effect=_fake_is_otp_visible))

    async def _advance_page(*args, **kwargs):
        if len(page.timeout_calls) >= 2:
            page.url = "https://seller.shopee.cn/?cnsc_shop_id=1227491331"
        await _FakePage.wait_for_timeout(page, kwargs.get("ms", args[0] if args else 0))

    monkeypatch.setattr(page, "wait_for_timeout", _advance_page)

    outcome = await component._wait_for_post_login_outcome(
        page,
        phase="post_otp_submit",
        timeout_ms=20,
        poll_ms=1,
    )

    assert outcome == "success"


@pytest.mark.asyncio
async def test_shopee_login_detects_post_login_special_page_as_manual_intervention(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    component = ShopeeLogin(
        _ctx(
            account={
                "username": "huangjiajumain",
                "password": "pass",
                "login_url": "https://seller.shopee.cn/account/signin?next=%2F",
            },
            config={
                "task": {"screenshot_dir": str(tmp_path)},
                "params": {"otp": "123456"},
            },
        )
    )
    page = _FakePage("https://seller.shopee.cn/portal/merchant/setting")

    monkeypatch.setattr(component, "_find_visible_login_error", AsyncMock(return_value=None))
    monkeypatch.setattr(component, "_find_visible_otp_error", AsyncMock(return_value=None))
    monkeypatch.setattr(component, "_is_slide_captcha_visible", AsyncMock(return_value=False))
    monkeypatch.setattr(component, "_is_otp_visible", AsyncMock(return_value=False))
    monkeypatch.setattr(component, "_homepage_dom_looks_ready", AsyncMock(return_value=False))
    monkeypatch.setattr(component, "_session_shell_looks_ready", AsyncMock(return_value=True))

    with pytest.raises(VerificationRequiredError) as exc_info:
        await component._submit_resumed_otp(page, "123456")

    assert exc_info.value.verification_type == "manual_intervention"
    assert page.screenshot_paths


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
async def test_shopee_login_uses_platform_default_login_entry_when_account_login_url_missing() -> None:
    component = ShopeeLogin(_ctx(account={"username": "user", "password": "pass"}))
    page = _FakePage("about:blank")

    result = await component.run(page)

    assert page.goto_calls[0].startswith("https://seller.shopee.cn/account/signin")
    assert result.success is False


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
async def test_shopee_login_treats_authenticated_shell_as_already_logged_in(monkeypatch: pytest.MonkeyPatch) -> None:
    component = ShopeeLogin(_ctx())
    page = _FakePage("https://seller.shopee.cn/datacenter/home")
    cleaned: list[str] = []

    async def _fake_cleanup(current_page) -> None:
        cleaned.append(str(current_page.url))

    monkeypatch.setattr(component, "_cleanup_after_login", _fake_cleanup)

    result = await component.run(page)

    assert result.success is True
    assert result.message == "already logged in"
    assert cleaned == ["https://seller.shopee.cn/datacenter/home"]


@pytest.mark.asyncio
async def test_shopee_login_treats_post_goto_authenticated_shell_as_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component = ShopeeLogin(_ctx())
    page = _FakePage("about:blank")
    cleaned: list[str] = []

    async def _fake_goto(url: str, wait_until: str = "domcontentloaded", timeout: int = 60000) -> None:
        page.goto_calls.append(url)
        page.url = "https://seller.shopee.cn/datacenter/home"

    async def _fake_cleanup(current_page) -> None:
        cleaned.append(str(current_page.url))

    monkeypatch.setattr(page, "goto", _fake_goto)
    monkeypatch.setattr(component, "_cleanup_after_login", _fake_cleanup)

    result = await component.run(page)

    assert result.success is True
    assert result.message == "ok"
    assert cleaned == ["https://seller.shopee.cn/datacenter/home"]


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
async def test_shopee_login_ensure_remember_me_checked_checks_checkbox_when_unchecked() -> None:
    component = ShopeeLogin(_ctx())
    page = _FakePage("https://seller.shopee.cn/account/signin")
    checkbox = _FakeLocator()
    checkbox.checked = False

    page.selector_map['input[type="checkbox"], [role="checkbox"]'] = checkbox

    await component._ensure_remember_me_checked(page)

    assert checkbox.check_calls == 1
    assert checkbox.checked is True


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
async def test_shopee_login_detects_puzzle_verification_modal_signals() -> None:
    component = ShopeeLogin(_ctx())
    page = _FakePage("https://seller.shopee.cn/account/signin")
    page.text_map["Verification"] = _FakeLocator()
    page.text_map["请滑动以完成拼图"] = _FakeLocator()

    assert await component._is_slide_captcha_visible(page) is True


@pytest.mark.asyncio
async def test_shopee_login_does_not_treat_plain_otp_prompt_as_otp_error() -> None:
    component = ShopeeLogin(_ctx())
    page = _FakePage("https://seller.shopee.cn/account/signin")
    page.text_map["OTP"] = _FakeLocator()

    assert await component._find_visible_otp_error(page) is None


@pytest.mark.asyncio
async def test_shopee_login_first_submit_prefers_slide_before_otp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component = ShopeeLogin(_ctx())
    page = _FakePage("https://seller.shopee.cn/account/signin")

    monkeypatch.setattr(component, "_find_visible_login_error", AsyncMock(return_value=None))
    monkeypatch.setattr(component, "_find_visible_otp_error", AsyncMock(return_value=None))
    monkeypatch.setattr(component, "_is_slide_captcha_visible", AsyncMock(return_value=True))
    monkeypatch.setattr(component, "_is_otp_visible", AsyncMock(return_value=True))

    outcome = await component._wait_for_post_login_outcome(page, phase="post_credentials")

    assert outcome == "slide_captcha"


@pytest.mark.asyncio
async def test_shopee_login_after_manual_verification_prefers_otp_before_slide(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component = ShopeeLogin(_ctx(config={"params": {"manual_completed": True}}))
    page = _FakePage("https://seller.shopee.cn/account/signin")

    monkeypatch.setattr(component, "_find_visible_login_error", AsyncMock(return_value=None))
    monkeypatch.setattr(component, "_find_visible_otp_error", AsyncMock(return_value=None))
    monkeypatch.setattr(component, "_is_slide_captcha_visible", AsyncMock(return_value=True))
    monkeypatch.setattr(component, "_is_otp_visible", AsyncMock(return_value=True))

    outcome = await component._wait_for_post_login_outcome(page, phase="post_manual_verification")

    assert outcome == "otp"


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
    monkeypatch.setattr(component, "_confirm_otp", AsyncMock())
    async def _fake_wait_for_post_login_outcome(*args, **kwargs):
        page.url = "https://seller.shopee.cn/?cnsc_shop_id=1227491331"
        return "success"
    monkeypatch.setattr(component, "_wait_for_post_login_outcome", AsyncMock(side_effect=_fake_wait_for_post_login_outcome))

    async def _fake_cleanup(current_page) -> None:
        cleaned.append(str(current_page.url))

    monkeypatch.setattr(component, "_cleanup_after_login", _fake_cleanup)

    result = await component.run(page)

    assert result.success is True
    assert result.message == "ok"
    assert cleaned == ["https://seller.shopee.cn/?cnsc_shop_id=1227491331"]


@pytest.mark.asyncio
async def test_shopee_login_manual_completed_advances_to_otp_without_restarting_login(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    component = ShopeeLogin(
        _ctx(
            config={
                "task": {"screenshot_dir": str(tmp_path)},
                "params": {"manual_completed": True},
            }
        )
    )
    page = _FakePage("https://seller.shopee.cn/account/signin")

    fill_credentials = AsyncMock()
    submit_credentials = AsyncMock()
    ensure_phone_mode = AsyncMock()

    monkeypatch.setattr(component, "_fill_credentials", fill_credentials)
    monkeypatch.setattr(component, "_submit_credentials", submit_credentials)
    monkeypatch.setattr(component, "_is_otp_visible", AsyncMock(return_value=False))
    monkeypatch.setattr(component, "_wait_for_post_login_outcome", AsyncMock(return_value="otp"))
    monkeypatch.setattr(component, "_ensure_phone_otp_mode", ensure_phone_mode)

    with pytest.raises(VerificationRequiredError) as exc_info:
        await component.run(page)

    assert exc_info.value.verification_type == "otp"
    assert page.goto_calls == []
    fill_credentials.assert_not_awaited()
    submit_credentials.assert_not_awaited()
    ensure_phone_mode.assert_awaited_once()
    assert page.screenshot_paths


@pytest.mark.asyncio
async def test_shopee_login_existing_otp_page_without_code_raises_otp_without_restarting_login(
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
    ensure_phone_mode = AsyncMock()

    monkeypatch.setattr(component, "_is_otp_visible", AsyncMock(return_value=True))
    monkeypatch.setattr(component, "_ensure_phone_otp_mode", ensure_phone_mode)

    with pytest.raises(VerificationRequiredError) as exc_info:
        await component.run(page)

    assert exc_info.value.verification_type == "otp"
    assert page.goto_calls == []
    ensure_phone_mode.assert_awaited_once()
    assert page.screenshot_paths


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
