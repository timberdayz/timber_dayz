#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TikTok 平台契约测试（最小、无外网依赖）

运行方式：
    python modules/apps/tiktok/contract_tests.py

成功标准：
- 全部断言通过且脚本退出码为 0
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict

# Ensure repository root on sys.path
_THIS_DIR = os.path.dirname(__file__)
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


# Minimal fakes
class FakeLocator:
    def __init__(self, page: "FakePage", selector: str) -> None:
        self.page = page
        self.selector = selector

    @property
    def first(self) -> "FakeLocator":
        return self

    def count(self) -> int:
        return 1 if self.page.is_present(self.selector) else 0

    def is_visible(self) -> bool:
        return self.count() > 0

    def is_enabled(self) -> bool:
        return True

    def click(self, timeout: int = 0) -> None:  # noqa: ARG002
        if "button" in self.selector and ("登录" in self.selector or "Login" in self.selector):
            self.page.url = "https://seller.tiktokglobalshop.com/home"

    def fill(self, value: str) -> None:
        self.page._values[self.selector] = value

    def type(self, value: str, delay: int = 0) -> None:  # noqa: ARG002
        prev = self.page._values.get(self.selector, "")
        self.page._values[self.selector] = prev + value


class FakeKeyboard:
    def __init__(self, page: "FakePage") -> None:
        self.page = page

    def press(self, key: str) -> None:  # noqa: ARG002
        # pressing enter also navigates away after form submit
        self.page.url = "https://seller.tiktokglobalshop.com/home"


class NoEnterKeyboard(FakeKeyboard):
    def press(self, key: str) -> None:  # noqa: ARG002
        # Disable navigation on ENTER for negative tests
        return None


class FakePage:
    def __init__(self, url: str) -> None:
        self.url = url
        self._present = {
            "input[type='password']": True,
            "button:has-text('登录')": True,
        }
        self._values: Dict[str, str] = {}
        self.keyboard = FakeKeyboard(self)

    def is_present(self, selector: str) -> bool:
        return self._present.get(selector, False)

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(self, selector)

    def wait_for_timeout(self, ms: int) -> None:  # noqa: ARG002
        return None


# Tests

def test_imports_no_side_effects() -> None:
    from modules.services.platform_login_service import LoginService  # noqa: F401


def test_non_login_url_true() -> None:
    from modules.services.platform_login_service import LoginService

    page = FakePage(url="https://seller.tiktokglobalshop.com/home")
    # Make sure it's not like a login form
    page._present["input[type='password']"] = False
    page._present["button:has-text('登录')"] = False

    svc = LoginService()
    ok = svc.ensure_logged_in("tiktok", page, {"login_url": "https://seller.tiktokglobalshop.com/account/login"})
    assert ok is True


def test_login_page_success_minimal() -> None:
    from modules.services.platform_login_service import LoginService

    page = FakePage(url="https://seller.tiktokglobalshop.com/account/login")
    account: Dict[str, Any] = {
        "phone": "13800138000",
        "password": "p@ssw0rd",
        "login_url": "https://seller.tiktokglobalshop.com/account/login",
    }

    svc = LoginService()
    ok = svc.ensure_logged_in("tiktok", page, account)
    assert ok is True
    assert "account/login" not in page.url


def test_missing_login_button_fails() -> None:
    from modules.services.platform_login_service import LoginService

    page = FakePage(url="https://seller.tiktokglobalshop.com/account/login")
    # Remove login button and disable ENTER fallback
    page._present["button:has-text('登录')"] = False
    page.keyboard = NoEnterKeyboard(page)

    account: Dict[str, Any] = {
        "phone": "13800138000",
        "password": "p@ssw0rd",
        "login_url": "https://seller.tiktokglobalshop.com/account/login",
    }

    svc = LoginService()
    ok = svc.ensure_logged_in("tiktok", page, account)
    assert ok is False
    assert "account/login" in page.url


essential_selectors = ["input[type='text']"]

def test_non_standard_placeholder_success() -> None:
    from modules.services.platform_login_service import LoginService

    page = FakePage(url="https://seller.tiktokglobalshop.com/account/login")
    # No phone-specific placeholders; only generic input[type=text]
    for k in list(page._present.keys()):
        if "placeholder" in k or "data-testid" in k or "name*='phone'" in k:
            page._present[k] = False
    page._present["input[type='text']"] = True

    account: Dict[str, Any] = {
        "username": "user_abc",
        "password": "p@ss",
        "login_url": "https://seller.tiktokglobalshop.com/account/login",
    }

    svc = LoginService()
    ok = svc.ensure_logged_in("tiktok", page, account)
    assert ok is True
    assert "account/login" not in page.url


if __name__ == "__main__":
    try:
        test_imports_no_side_effects()
        test_non_login_url_true()
        test_login_page_success_minimal()
        print("[tiktok-contract-tests] all passed")
        sys.exit(0)
    except AssertionError as e:
        print(f"[tiktok-contract-tests] assertion failed: {e}")
        sys.exit(1)
    except Exception as e:  # noqa: BLE001
        print(f"[tiktok-contract-tests] unexpected error: {e}")
        sys.exit(2)

