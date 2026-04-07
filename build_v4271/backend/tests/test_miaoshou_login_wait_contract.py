from __future__ import annotations

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


@pytest.mark.asyncio
async def test_miaoshou_login_wait_for_outcome_tolerates_delayed_homepage(monkeypatch):
    component = MiaoshouLogin(_ctx())
    seen = {"count": 0}

    class _Page:
        url = "https://erp.91miaoshou.com/welcome"

    async def _fake_find_error(page):
        return None

    async def _fake_home_ready(page):
        seen["count"] += 1
        return seen["count"] >= 3

    monkeypatch.setattr(component, "_find_visible_login_error", _fake_find_error)
    monkeypatch.setattr(component, "_homepage_ready", _fake_home_ready)

    outcome = await component._wait_for_login_outcome(_Page(), timeout_ms=2000, poll_ms=10)

    assert outcome == "success"


@pytest.mark.asyncio
async def test_miaoshou_login_wait_for_outcome_attempts_cleanup_after_welcome_redirect(monkeypatch):
    component = MiaoshouLogin(_ctx())
    calls = {"home": 0, "cleanup": 0}

    class _Page:
        url = "https://erp.91miaoshou.com/welcome"

        async def wait_for_load_state(self, state, timeout=0):
            return None

    async def _fake_find_error(page):
        return None

    async def _fake_home_ready(page):
        calls["home"] += 1
        return calls["home"] >= 2

    async def _fake_cleanup(page):
        calls["cleanup"] += 1

    monkeypatch.setattr(component, "_find_visible_login_error", _fake_find_error)
    monkeypatch.setattr(component, "_homepage_ready", _fake_home_ready)
    monkeypatch.setattr(component, "_cleanup_after_login", _fake_cleanup)

    outcome = await component._wait_for_login_outcome(_Page(), timeout_ms=2000, poll_ms=10)

    assert outcome == "success"
    assert calls["cleanup"] >= 1
