"""采集侧「页面归位」：错误页 ≠ 没登录 —— 先导航回平台入口，再探测身份。

背景
----
持久 profile 启动后，Chromium 会**恢复上次会话停着的标签页**。2026-11-07 实测
恢复到的是 ``https://seller.shopee.cn/404?cnsc_shop_id=1391124228``：
会话失效 / 深链过期时平台会跳到 404，而下一次开箱就把它原样恢复了出来。

**关键认知**：404 页**不等于「没登录」** —— 登录态其实还在，只是页面停错了地方。
所以修复**不是**把 404 判成「未登录」（那会让采集器白跑一遍重新登录、甚至弹验证码），
而是**把页面导航回平台入口**，让平台自己导回带店铺编号的正常页。

本测试守四件事
--------------
1. 正常页面**一次额外导航都不加** ⇒ 采集流程零影响；
2. 错误页会被导航回平台入口，归位成功后能读到**真实**店铺编号；
3. 归位失败 ⇒ 记「探测失败」，**绝不**拿错误页上的残留编号当探测结果；
4. 平台身份探测的判据仍是**唯一实现**（迁移与采集侧逐条一致）。
"""

from __future__ import annotations

from typing import Any, Optional

import pytest

from modules.apps.collection_center import runtime_session
from modules.apps.collection_center.executor_v2 import (
    _ERROR_PAGE_PATH_SEGMENTS,
    _extract_platform_shop_context,
    _is_platform_error_page,
    _record_platform_shop_discovery_async,
)
from modules.apps.collection_center.platform_error_page import (
    ERROR_PAGE_PATH_SEGMENTS,
    is_platform_error_page,
)
from modules.apps.collection_center.runtime_session import (
    PlatformLandingOutcome,
    ensure_platform_landing_page,
)


SHOPEE_ERROR_URL = "https://seller.shopee.cn/404?cnsc_shop_id=1391124228"
SHOPEE_LOGIN_ENTRY = "https://seller.shopee.cn/account/signin?next=%2Fportal%2Fhome"
SHOPEE_LANDED_URL = "https://seller.shopee.cn/?cnsc_shop_id=1227491331"


class _FakePage:
    """最小 page 替身：记录 goto 调用，goto 后把 URL 切到落地页。"""

    def __init__(
        self,
        url: str,
        *,
        landing_url: Optional[str] = None,
        goto_error: Optional[Exception] = None,
    ) -> None:
        self.url = url
        self.goto_calls: list[str] = []
        self._landing_url = landing_url
        self._goto_error = goto_error

    async def goto(self, url: str, wait_until: str = "", timeout: int = 0) -> None:
        self.goto_calls.append(url)
        if self._goto_error is not None:
            raise self._goto_error
        if self._landing_url is not None:
            self.url = self._landing_url


@pytest.fixture(autouse=True)
def _no_wait(monkeypatch):
    """页面稳定等待与本测试无关，去掉它避免每次白等几秒。"""

    async def _fake_wait(**_kwargs):
        return None

    monkeypatch.setattr(
        runtime_session, "wait_for_runtime_page_stable", _fake_wait, raising=True
    )


async def test_normal_page_is_never_navigated():
    """正常页面**一次额外导航都不加** —— 采集流程零影响。"""
    page = _FakePage("https://seller.shopee.cn/datacenter/home?cnsc_shop_id=1227491331")

    outcome = await ensure_platform_landing_page(
        page=page, platform="shopee", account={"login_url": SHOPEE_LOGIN_ENTRY}
    )

    assert outcome.navigated is False
    assert outcome.ready is True
    assert outcome.reason == "already_on_landing_page"
    assert page.goto_calls == []


async def test_error_page_is_navigated_back_to_platform_entry():
    """错误页 ⇒ 导航回平台入口（会话有效时平台会自己导回正常页）。"""
    page = _FakePage(SHOPEE_ERROR_URL, landing_url=SHOPEE_LANDED_URL)

    outcome = await ensure_platform_landing_page(
        page=page, platform="shopee", account={"login_url": SHOPEE_LOGIN_ENTRY}
    )

    assert outcome.navigated is True
    assert outcome.ready is True
    assert outcome.current_url == SHOPEE_LANDED_URL
    assert page.goto_calls == [SHOPEE_LOGIN_ENTRY]


async def test_error_page_without_navigable_page_is_reported():
    """没有 goto 的 page（测试替身）⇒ 明确报「不可归位」，不静默。"""

    class _NoGotoPage:
        url = SHOPEE_ERROR_URL

    outcome = await ensure_platform_landing_page(
        page=_NoGotoPage(), platform="shopee", account={"login_url": SHOPEE_LOGIN_ENTRY}
    )

    assert outcome.navigated is False
    assert outcome.ready is False
    assert outcome.reason == "page_not_navigable"


async def test_error_page_landing_to_another_error_page_is_reported():
    """归位后仍停在错误页 ⇒ 明确报「归位失败」，不静默。"""
    page = _FakePage(SHOPEE_ERROR_URL, landing_url=SHOPEE_ERROR_URL)

    outcome = await ensure_platform_landing_page(
        page=page, platform="shopee", account={"login_url": SHOPEE_LOGIN_ENTRY}
    )

    assert outcome.navigated is True
    assert outcome.ready is False
    assert outcome.reason == "landed_on_error_page"


async def test_error_page_goto_exception_is_reported():
    """导航抛异常 ⇒ 明确报失败，不抛给采集流程。"""
    page = _FakePage(SHOPEE_ERROR_URL, goto_error=RuntimeError("net down"))

    outcome = await ensure_platform_landing_page(
        page=page, platform="shopee", account={"login_url": SHOPEE_LOGIN_ENTRY}
    )

    assert outcome.navigated is False
    assert outcome.ready is False
    assert outcome.reason.startswith("goto_failed:")


async def test_error_page_without_login_entry_is_reported():
    """平台没有入口 URL ⇒ 明确报失败（不猜一个 URL 导航过去）。"""
    page = _FakePage(SHOPEE_ERROR_URL)

    # 未知平台：``get_platform_login_entry`` 会抛 ValueError ⇒ 必须被兜住
    outcome = await ensure_platform_landing_page(
        page=page, platform="not_a_platform", account={}
    )

    assert outcome.navigated is False
    assert outcome.ready is False
    assert outcome.reason == "no_platform_login_entry"
    assert page.goto_calls == []


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


class _FakeDiscoveryService:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def record_runtime_discovery(self, db, **kwargs):
        self.calls.append(kwargs)
        return None


@pytest.fixture
def _capture_discovery(monkeypatch):
    """把落库动作换成内存捕获。"""
    service = _FakeDiscoveryService()
    monkeypatch.setattr(
        "backend.models.database.AsyncSessionLocal", lambda: _FakeSession()
    )
    monkeypatch.setattr(
        "backend.services.platform_shop_discovery_service.get_platform_shop_discovery_service",
        lambda: service,
    )
    return service


async def test_discovery_records_real_identity_after_landing(
    monkeypatch, _capture_discovery
):
    """归位成功 ⇒ 记**真实**身份（不再是无意义的「探测失败」）。"""

    async def _fake_landing(**_kwargs):
        return PlatformLandingOutcome(
            navigated=True,
            ready=True,
            current_url=SHOPEE_LANDED_URL,
            reason="landed",
        )

    monkeypatch.setattr(
        runtime_session, "ensure_platform_landing_page", _fake_landing, raising=True
    )

    page = _FakePage(SHOPEE_ERROR_URL)
    await _record_platform_shop_discovery_async(
        platform="shopee",
        page=page,
        params={"main_account_id": "main_1", "shop_account_id": "shop_1"},
        account={"store_name": "demo"},
    )

    assert len(_capture_discovery.calls) == 1
    call = _capture_discovery.calls[0]
    assert call["detected_platform_shop_id"] == "1227491331"
    assert call["probe_failed"] is False
    assert call["raw_payload"]["current_url"] == SHOPEE_LANDED_URL


async def test_discovery_records_probe_failure_when_landing_fails(
    monkeypatch, _capture_discovery
):
    """归位失败 ⇒ 记「探测失败」，残留编号**不许**当成探测结果。"""

    async def _fake_landing(**_kwargs):
        return PlatformLandingOutcome(
            navigated=True,
            ready=False,
            current_url=SHOPEE_ERROR_URL,
            reason="landed_on_error_page",
        )

    monkeypatch.setattr(
        runtime_session, "ensure_platform_landing_page", _fake_landing, raising=True
    )

    page = _FakePage(SHOPEE_ERROR_URL)
    await _record_platform_shop_discovery_async(
        platform="shopee",
        page=page,
        params={"main_account_id": "main_1", "shop_account_id": "shop_1"},
        account={"store_name": "demo"},
    )

    assert len(_capture_discovery.calls) == 1
    call = _capture_discovery.calls[0]
    assert call["detected_platform_shop_id"] is None
    assert call["probe_failed"] is True
    assert call["detected_store_name"] is None


async def test_discovery_does_not_navigate_on_normal_page(
    monkeypatch, _capture_discovery
):
    """正常页面 ⇒ 探测链路**一次导航都不加**。"""
    landing_calls: list[dict[str, Any]] = []

    async def _fake_landing(**kwargs):
        landing_calls.append(kwargs)
        return PlatformLandingOutcome(
            navigated=True, ready=True, current_url="", reason="landed"
        )

    monkeypatch.setattr(
        runtime_session, "ensure_platform_landing_page", _fake_landing, raising=True
    )

    page = _FakePage(SHOPEE_LANDED_URL)
    await _record_platform_shop_discovery_async(
        platform="shopee",
        page=page,
        params={"main_account_id": "main_1", "shop_account_id": "shop_1"},
        account={"store_name": "demo"},
    )

    assert landing_calls == []
    assert len(_capture_discovery.calls) == 1
    assert _capture_discovery.calls[0]["detected_platform_shop_id"] == "1227491331"
    assert _capture_discovery.calls[0]["probe_failed"] is False


def test_error_page_criteria_is_a_single_implementation():
    """判据只有一个实现 —— 迁移守护测试与采集侧必须指向同一套口径。"""
    assert is_platform_error_page(SHOPEE_ERROR_URL) is True
    assert _is_platform_error_page(SHOPEE_ERROR_URL) is True
    assert _ERROR_PAGE_PATH_SEGMENTS is ERROR_PAGE_PATH_SEGMENTS
    assert "404" in ERROR_PAGE_PATH_SEGMENTS
    assert "signin" in ERROR_PAGE_PATH_SEGMENTS


def test_extract_context_marks_error_page_and_keeps_residual_id():
    """错误页上**确实**带着残留编号 —— 这正是不能拿它当探测结果的原因。"""
    payload = _extract_platform_shop_context("shopee", SHOPEE_ERROR_URL)

    assert payload["is_error_page"] is True
    assert payload["detected_platform_shop_id"] == "1391124228"
