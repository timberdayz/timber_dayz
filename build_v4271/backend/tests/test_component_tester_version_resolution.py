import types

import pytest

from tools.test_component import ComponentTester


class _FakePage:
    def __init__(self):
        self.url = "about:blank"

    async def wait_for_timeout(self, ms: int):
        return None

    async def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int = 30000):
        self.url = url

    async def wait_for_load_state(self, state: str, timeout: int = 10000):
        return None


@pytest.mark.asyncio
async def test_component_tester_auto_login_prefers_versioned_login_component(monkeypatch):
    tester = ComponentTester(
        platform="miaoshou",
        account_id="acc-1",
        account_info={
            "account_id": "acc-1",
            "platform": "miaoshou",
            "username": "user@example.com",
            "password": "plain-password",
            "login_url": "https://erp.91miaoshou.com",
        },
    )
    page = _FakePage()
    calls = []

    class _Adapter:
        async def login(self, page):
            calls.append("login")
            page.url = "https://erp.91miaoshou.com/welcome"
            return types.SimpleNamespace(success=True, message="ok")

    monkeypatch.setattr(
        tester,
        "_resolve_versioned_component_class",
        lambda component_name, component_type: object() if component_name == "miaoshou/login" else None,
    )
    monkeypatch.setattr(
        "tools.test_component.create_adapter",
        lambda **kwargs: _Adapter(),
    )
    monkeypatch.setattr(
        tester.component_loader,
        "load",
        lambda path: (_ for _ in ()).throw(AssertionError("should not use canonical load path")),
    )

    ok = await tester._execute_auto_login(page, tester.get_account_info())

    assert ok is True
    assert calls == ["login"]
    assert page.url.endswith("/welcome")


@pytest.mark.asyncio
async def test_component_tester_navigation_prefers_versioned_navigation_component(monkeypatch):
    tester = ComponentTester(
        platform="miaoshou",
        account_id="acc-1",
        account_info={
            "account_id": "acc-1",
            "platform": "miaoshou",
            "username": "user@example.com",
            "password": "plain-password",
            "login_url": "https://erp.91miaoshou.com",
        },
    )
    page = _FakePage()
    calls = []

    class _Adapter:
        async def navigate(self, page, target_page):
            calls.append(target_page)
            page.url = f"https://erp.91miaoshou.com/{target_page}"
            return types.SimpleNamespace(success=True, message="ok")

    monkeypatch.setattr(
        tester,
        "_resolve_versioned_component_class",
        lambda component_name, component_type: object() if component_name == "miaoshou/navigation" else None,
    )
    monkeypatch.setattr(
        "tools.test_component.create_adapter",
        lambda **kwargs: _Adapter(),
    )
    monkeypatch.setattr(
        tester.component_loader,
        "load",
        lambda path: (_ for _ in ()).throw(AssertionError("should not use canonical load path")),
    )

    ok = await tester._navigate_to_test_page(
        page,
        {"test_data_domain": "orders"},
        tester.get_account_info(),
    )

    assert ok is True
    assert calls == ["orders"]
    assert page.url.endswith("/orders")
