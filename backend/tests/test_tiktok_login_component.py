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
        self.selector_map: dict[str, _FakeLocator] = {}
        self.text_map: dict[str, _FakeLocator] = {}

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

    def locator(self, selector: str) -> "_FakeLocator":
        return self.selector_map.get(selector, _FakeLocator(visible=False))

    def get_by_text(self, text: str, exact: bool = False) -> "_FakeLocator":
        return self.text_map.get(text, _FakeLocator(visible=False))

    def get_by_role(self, role: str, name=None) -> "_FakeLocator":
        key = f"{role}:{name.pattern if hasattr(name, 'pattern') else name}"
        return self.selector_map.get(key, _FakeLocator(visible=False))


class _FakeLocator:
    def __init__(self, *, visible: bool = True) -> None:
        self.visible = visible
        self.clicked = 0
        self.filled_values: list[str] = []

    @property
    def first(self) -> "_FakeLocator":
        return self

    async def is_visible(self, timeout: int | None = None) -> bool:
        return self.visible

    async def count(self) -> int:
        return 1 if self.visible else 0

    async def click(self, timeout: int | None = None) -> None:
        self.clicked += 1

    async def fill(self, value: str, timeout: int | None = None) -> None:
        self.filled_values.append(value)


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


@pytest.mark.asyncio
async def test_tiktok_login_homepage_dom_detection_uses_shop_region_signal() -> None:
    component = TiktokLogin(_ctx(config={"shop_region": "SG"}))
    page = _FakePage("https://seller.tiktokshopglobalselling.com/homepage?shop_region=SG")
    page.text_map["SG"] = _FakeLocator()

    assert await component._homepage_dom_looks_ready(page) is True


@pytest.mark.asyncio
async def test_tiktok_login_homepage_dom_detection_rejects_blank_homepage() -> None:
    component = TiktokLogin(_ctx(config={"shop_region": "SG"}))
    page = _FakePage("https://seller.tiktokshopglobalselling.com/homepage?shop_region=SG")

    assert await component._homepage_dom_looks_ready(page) is False


@pytest.mark.asyncio
async def test_tiktok_login_homepage_dom_detection_accepts_left_nav_signals_without_shop_region() -> None:
    component = TiktokLogin(_ctx(config={}))
    page = _FakePage("https://seller.tiktokshopglobalselling.com/homepage?shop_region=SG")
    page.text_map["首页"] = _FakeLocator()
    page.text_map["数据分析"] = _FakeLocator()

    assert await component._homepage_dom_looks_ready(page) is True


@pytest.mark.asyncio
async def test_tiktok_login_data_overview_dom_detection_accepts_probe_or_metric_text() -> None:
    component = TiktokLogin(_ctx(config={"params": {"login_success_target": "data_overview"}}))
    page = _FakePage("https://seller.tiktokshopglobalselling.com/compass/data-overview?shop_region=SG")
    page.selector_map["[role='grid'], table"] = _FakeLocator()

    assert await component._data_overview_dom_looks_ready(page) is True

    page = _FakePage("https://seller.tiktokshopglobalselling.com/compass/data-overview?shop_region=SG")
    page.text_map["GMV"] = _FakeLocator()

    assert await component._data_overview_dom_looks_ready(page) is True


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

    monkeypatch.setattr(component, "_is_otp_visible", AsyncMock(side_effect=[True, False]))
    monkeypatch.setattr(component, "_fill_otp", AsyncMock())
    monkeypatch.setattr(component, "_ensure_trust_device_checked", AsyncMock())

    async def _confirm(current_page) -> None:
        current_page.url = "https://seller.tiktokshopglobalselling.com/homepage"
        current_page.text_map["TikTok Shop"] = _FakeLocator()

    monkeypatch.setattr(component, "_confirm_otp", _confirm)
    monkeypatch.setattr(component, "_find_visible_otp_error", AsyncMock(return_value=None))

    result = await component.run(page)

    assert result.success is True
    assert result.message == "ok"


@pytest.mark.asyncio
async def test_tiktok_login_raises_manual_intervention_when_post_credentials_times_out(
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

    monkeypatch.setattr(component, "_wait_for_login_surface_ready", AsyncMock(return_value=True))
    monkeypatch.setattr(component, "_ensure_login_mode", AsyncMock())
    monkeypatch.setattr(component, "_fill_credentials", AsyncMock())
    monkeypatch.setattr(component, "_submit_credentials", AsyncMock())
    monkeypatch.setattr(component, "_wait_for_post_login_outcome", AsyncMock(return_value="timeout"))

    with pytest.raises(VerificationRequiredError) as exc_info:
        await component.run(page)

    assert exc_info.value.verification_type == "manual_intervention"
    assert page.screenshot_paths


@pytest.mark.asyncio
async def test_tiktok_login_submit_resumed_otp_raises_manual_intervention_when_homepage_never_stabilizes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    component = TiktokLogin(
        _ctx(
            config={
                "task": {"screenshot_dir": str(tmp_path)},
                "params": {"otp": "123456"},
            }
        )
    )
    page = _FakePage("https://seller.tiktokglobalshop.com/account/login")

    monkeypatch.setattr(component, "_is_otp_visible", AsyncMock(return_value=True))
    monkeypatch.setattr(component, "_ensure_trust_device_checked", AsyncMock())
    monkeypatch.setattr(component, "_fill_otp", AsyncMock())
    monkeypatch.setattr(component, "_confirm_otp", AsyncMock())
    monkeypatch.setattr(component, "_wait_for_post_login_outcome", AsyncMock(return_value="timeout"))

    with pytest.raises(VerificationRequiredError) as exc_info:
        await component.run(page)

    assert exc_info.value.verification_type == "manual_intervention"
    assert page.screenshot_paths


@pytest.mark.asyncio
async def test_tiktok_login_manual_completed_timeout_re_raises_manual_intervention(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    component = TiktokLogin(
        _ctx(
            config={
                "task": {"screenshot_dir": str(tmp_path)},
                "params": {"manual_completed": True},
            }
        )
    )
    page = _FakePage("https://seller.tiktokglobalshop.com/account/login")

    monkeypatch.setattr(component, "_is_otp_visible", AsyncMock(return_value=False))
    monkeypatch.setattr(component, "_wait_for_post_login_outcome", AsyncMock(return_value="timeout"))

    with pytest.raises(VerificationRequiredError) as exc_info:
        await component.run(page)

    assert exc_info.value.verification_type == "manual_intervention"
    assert page.screenshot_paths


@pytest.mark.asyncio
async def test_tiktok_login_submit_resumed_otp_checks_trust_device_before_filling_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component = TiktokLogin(_ctx(config={"params": {"otp": "123456"}}))
    page = _FakePage("https://seller.tiktokglobalshop.com/account/login")
    calls: list[str] = []

    async def _trust_device(current_page) -> None:
        calls.append("trust")

    async def _fill_otp(current_page, otp_value: str) -> None:
        calls.append("fill")

    async def _confirm(current_page) -> None:
        calls.append("confirm")

    monkeypatch.setattr(component, "_ensure_trust_device_checked", _trust_device)
    monkeypatch.setattr(component, "_fill_otp", _fill_otp)
    monkeypatch.setattr(component, "_confirm_otp", _confirm)
    monkeypatch.setattr(component, "_find_visible_otp_error", AsyncMock(return_value=None))
    monkeypatch.setattr(
        component,
        "_wait_for_post_login_outcome",
        AsyncMock(return_value="success"),
        raising=False,
    )

    result = await component._submit_resumed_otp(page, "123456")

    assert result.success is True
    assert calls == ["trust", "fill", "confirm"]


@pytest.mark.asyncio
async def test_tiktok_login_submit_resumed_otp_waits_for_post_login_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component = TiktokLogin(_ctx(config={"params": {"otp": "123456"}}))
    page = _FakePage("https://seller.tiktokglobalshop.com/account/login")
    wait_for_outcome = AsyncMock(return_value="success")

    monkeypatch.setattr(component, "_ensure_trust_device_checked", AsyncMock())
    monkeypatch.setattr(component, "_fill_otp", AsyncMock())
    monkeypatch.setattr(component, "_confirm_otp", AsyncMock())
    monkeypatch.setattr(component, "_find_visible_otp_error", AsyncMock(return_value=None))
    monkeypatch.setattr(component, "_wait_for_post_login_outcome", wait_for_outcome, raising=False)

    result = await component._submit_resumed_otp(page, "123456")

    assert result.success is True
    wait_for_outcome.assert_awaited_once()


@pytest.mark.asyncio
async def test_tiktok_login_post_credentials_wait_detects_delayed_otp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component = TiktokLogin(_ctx())
    page = _FakePage("https://seller.tiktokglobalshop.com/account/login")

    monkeypatch.setattr(component, "_find_visible_login_error", AsyncMock(return_value=None))
    monkeypatch.setattr(component, "_find_visible_otp_error", AsyncMock(return_value=None))
    monkeypatch.setattr(
        component,
        "_is_otp_visible",
        AsyncMock(side_effect=[False, False, True]),
    )

    outcome = await component._wait_for_post_login_outcome(
        page,
        phase="post_credentials",
        timeout_ms=10,
        poll_ms=1,
    )

    assert outcome == "otp"


@pytest.mark.asyncio
async def test_tiktok_login_is_otp_visible_accepts_textual_otp_signals_when_primary_locators_are_unstable() -> None:
    component = TiktokLogin(_ctx())
    page = _FakePage("https://seller.tiktokshopglobalselling.com/account/login")
    page.text_map["双重验证"] = _FakeLocator()
    page.text_map["在这台设备上不再询问"] = _FakeLocator()
    page.text_map["没有收到验证码"] = _FakeLocator()

    assert await component._is_otp_visible(page) is True


@pytest.mark.asyncio
async def test_tiktok_login_fill_otp_uses_accessible_textbox_fallback_when_css_locator_is_unstable() -> None:
    component = TiktokLogin(_ctx())
    page = _FakePage("https://seller.tiktokshopglobalselling.com/account/login")
    textbox = _FakeLocator()
    page.selector_map["textbox:验证码"] = textbox

    await component._fill_otp(page, "123456")

    assert textbox.filled_values == ["123456"]


@pytest.mark.asyncio
async def test_tiktok_login_post_otp_wait_supports_data_overview_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component = TiktokLogin(
        _ctx(
            config={
                "shop_region": "SG",
                "params": {"login_success_target": "data_overview"},
            }
        )
    )
    page = _FakePage("https://seller.tiktokglobalshop.com/account/login")

    monkeypatch.setattr(component, "_find_visible_login_error", AsyncMock(return_value=None))
    monkeypatch.setattr(component, "_find_visible_otp_error", AsyncMock(return_value=None))
    monkeypatch.setattr(component, "_is_otp_visible", AsyncMock(return_value=False))

    async def _advance_page(ms: int) -> None:
        page.timeout_calls.append(ms)
        if len(page.timeout_calls) >= 2:
            page.url = "https://seller.tiktokshopglobalselling.com/compass/data-overview?shop_region=SG"
            page.text_map["GMV"] = _FakeLocator()

    monkeypatch.setattr(page, "wait_for_timeout", _advance_page)

    outcome = await component._wait_for_post_login_outcome(
        page,
        phase="post_otp_submit",
        timeout_ms=10,
        poll_ms=1,
    )

    assert outcome == "success"


@pytest.mark.asyncio
async def test_tiktok_login_post_otp_wait_does_not_exit_early_when_otp_surface_lingers_briefly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component = TiktokLogin(
        _ctx(
            config={
                "shop_region": "SG",
                "params": {"login_success_target": "homepage"},
            }
        )
    )
    page = _FakePage("https://seller.tiktokshopglobalselling.com/account/login")

    monkeypatch.setattr(component, "_find_visible_login_error", AsyncMock(return_value=None))
    monkeypatch.setattr(component, "_find_visible_otp_error", AsyncMock(return_value=None))
    monkeypatch.setattr(component, "_is_otp_visible", AsyncMock(side_effect=[True, False, False]))

    async def _advance_page(ms: int) -> None:
        page.timeout_calls.append(ms)
        if len(page.timeout_calls) >= 2:
            page.url = "https://seller.tiktokshopglobalselling.com/homepage?shop_region=SG"
            page.text_map["SG"] = _FakeLocator()

    monkeypatch.setattr(page, "wait_for_timeout", _advance_page)

    outcome = await component._wait_for_post_login_outcome(
        page,
        phase="post_otp_submit",
        timeout_ms=10,
        poll_ms=1,
    )

    assert outcome == "success"


@pytest.mark.asyncio
async def test_tiktok_login_post_otp_wait_accepts_homepage_url_plus_left_nav_signals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component = TiktokLogin(_ctx(config={}))
    page = _FakePage("https://seller.tiktokshopglobalselling.com/account/login")

    monkeypatch.setattr(component, "_find_visible_login_error", AsyncMock(return_value=None))
    monkeypatch.setattr(component, "_find_visible_otp_error", AsyncMock(return_value=None))
    monkeypatch.setattr(component, "_is_otp_visible", AsyncMock(return_value=False))

    async def _advance_page(ms: int) -> None:
        page.timeout_calls.append(ms)
        if len(page.timeout_calls) >= 2:
            page.url = "https://seller.tiktokshopglobalselling.com/homepage?shop_region=SG"
            page.text_map["首页"] = _FakeLocator()
            page.text_map["数据分析"] = _FakeLocator()

    monkeypatch.setattr(page, "wait_for_timeout", _advance_page)

    outcome = await component._wait_for_post_login_outcome(
        page,
        phase="post_otp_submit",
        timeout_ms=10,
        poll_ms=1,
    )

    assert outcome == "success"


@pytest.mark.asyncio
async def test_tiktok_login_post_otp_wait_accepts_authenticated_shell_without_homepage_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component = TiktokLogin(_ctx(config={}))
    page = _FakePage("https://seller.tiktokglobalshop.com/account/login")

    monkeypatch.setattr(component, "_find_visible_login_error", AsyncMock(return_value=None))
    monkeypatch.setattr(component, "_find_visible_otp_error", AsyncMock(return_value=None))
    monkeypatch.setattr(component, "_is_otp_visible", AsyncMock(return_value=False))

    async def _advance_page(ms: int) -> None:
        page.timeout_calls.append(ms)
        if len(page.timeout_calls) >= 2:
            page.url = "https://seller.tiktokshopglobalselling.com/order/list?shop_region=SG"
            page.text_map["订单"] = _FakeLocator()
            page.text_map["商品"] = _FakeLocator()
            page.selector_map['a[href*="/order"]'] = _FakeLocator()
            page.selector_map['a[href*="/product"]'] = _FakeLocator()

    monkeypatch.setattr(page, "wait_for_timeout", _advance_page)

    outcome = await component._wait_for_post_login_outcome(
        page,
        phase="post_otp_submit",
        timeout_ms=10,
        poll_ms=1,
    )

    assert outcome == "success"


@pytest.mark.asyncio
async def test_tiktok_login_wait_for_login_surface_ready_handles_delayed_login_surface(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component = TiktokLogin(_ctx())
    page = _FakePage("https://seller.tiktokglobalshop.com/account/login")
    checks = {"count": 0}

    async def _fake_locator_is_visible(locator, timeout: int = 500):  # noqa: ANN001
        checks["count"] += 1
        return checks["count"] >= 3

    monkeypatch.setattr(component, "_locator_is_visible", _fake_locator_is_visible)

    assert await component._wait_for_login_surface_ready(page, timeout_ms=10, poll_ms=1) is True


@pytest.mark.asyncio
async def test_tiktok_login_ensure_login_mode_retries_when_switch_is_delayed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component = TiktokLogin(_ctx(account={"email": "demo@example.com", "password": "secret", "login_url": "https://seller.tiktokglobalshop.com/account/login"}))
    page = _FakePage("https://seller.tiktokglobalshop.com/account/login")
    switch = _FakeLocator(visible=True)

    monkeypatch.setattr(component, "_current_login_mode", AsyncMock(side_effect=["phone", "phone", "email"]))
    monkeypatch.setattr(component, "_email_login_switch_locator", lambda current_page: switch)
    monkeypatch.setattr(component, "_locator_is_visible", AsyncMock(side_effect=[False, True]))

    await component._ensure_login_mode(page, "email")

    assert switch.clicked == 1
