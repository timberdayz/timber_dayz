#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Shopee 平台契约测试（最小、无外网依赖）

目标：
- 导入统一登录服务与验证码处理器不产生导入期副作用
- 使用 FakePage 验证 LoginService.ensure_logged_in("shopee", ...) 的最小行为

运行方式：
    python modules/apps/shopee/contract_tests.py

成功标准：
- 全部断言通过且脚本退出码为 0
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict

# Ensure repository root is on sys.path when running as a script
_THIS_DIR = os.path.dirname(__file__)
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


# --------- Minimal fakes ---------
class FakeLocator:
    def __init__(self, page: "FakePage", selector: str) -> None:
        self.page = page
        self.selector = selector

    @property
    def first(self) -> "FakeLocator":
        return self

    def count(self) -> int:
        return 1 if self.page.is_present(self.selector) else 0

    # Playwright's locator.wait_for
    def wait_for(self, state: str = "visible", timeout: int = 500) -> None:  # noqa: ARG002
        # no-op for fake
        return None

    # Convenience used by some code that tries is_visible / is_enabled
    def is_visible(self) -> bool:
        return self.count() > 0

    def is_enabled(self) -> bool:
        return True

    def click(self) -> None:
        # Navigation simulation on clicking login/confirm/verify buttons
        if "button" in self.selector and (
            "登录" in self.selector or "Login" in self.selector or "确认" in self.selector or "验证" in self.selector
        ):
            self.page.url = "https://seller.shopee.cn/dashboard"

    def fill(self, value: str) -> None:
        # store typed value for this selector
        try:
            self.page._values[self.selector] = value
        except Exception:
            pass

    def type(self, value: str, delay: int = 0) -> None:  # noqa: ARG002
        try:
            prev = self.page._values.get(self.selector, "")
            self.page._values[self.selector] = prev + value
        except Exception:
            pass

    def input_value(self) -> str:
        try:
            return self.page._values.get(self.selector, "")
        except Exception:
            return ""


class FakeKeyboard:
    def __init__(self, page: "FakePage") -> None:
        self.page = page

    def press(self, key: str) -> None:  # noqa: ARG002
        # Pressing enter after filling form can also navigate away
        self.page.url = "https://seller.shopee.cn/dashboard"


class FakePage:
    def __init__(self, url: str) -> None:
        self.url = url
        self._present = {
            'input[name="loginKey"]': True,
            'input[name="password"]': True,
            'button:has-text("登录")': True,
        }
        self._values: Dict[str, str] = {}
        self.keyboard = FakeKeyboard(self)

    def is_present(self, selector: str) -> bool:
        return self._present.get(selector, False)

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(self, selector)

    def wait_for_timeout(self, ms: int) -> None:  # noqa: ARG002
        return None


# --------- Contract tests ---------

def test_imports_no_side_effects() -> None:
    # Should import without exceptions / side effects
    from modules.services.platform_login_service import LoginService  # noqa: F401
    from modules.utils.shopee_verification_handler import ShopeeVerificationHandler  # noqa: F401


def test_login_service_with_fake_page_success() -> None:
    from modules.services.platform_login_service import LoginService

    # Given a page that looks like a login page
    page = FakePage(url="https://shopee.cn/account/login")
    account: Dict[str, Any] = {
        "username": "user@example.com",
        "password": "secret123",
        "login_url": "https://shopee.cn/account/login",
    }

    svc = LoginService()
    ok = svc.ensure_logged_in("shopee", page, account)

    assert ok is True, "LoginService should report success with fake page"
    assert "login" not in page.url and "signin" not in page.url, "URL should navigate away from login"


def test_login_service_off_mode_stays_on_login() -> None:
    from modules.services.platform_login_service import LoginService

    page = FakePage(url="https://shopee.cn/account/login")
    account: Dict[str, Any] = {
        "username": "user@example.com",
        "password": "secret123",
        "login_url": "https://shopee.cn/account/login",
        "login_flags": {"shopee_verification_mode": "off"},
    }
    # Simulate missing login button to avoid navigation
    page._present['button:has-text("登录")'] = False

    svc = LoginService()
    ok = svc.ensure_logged_in("shopee", page, account)

    assert ok is False, "With verification mode=off and no navigation, should remain False"
    assert "login" in page.url or "signin" in page.url


def test_login_service_non_login_url_is_true() -> None:
    from modules.services.platform_login_service import LoginService

    page = FakePage(url="https://seller.shopee.cn/dashboard")
    # Make page look like a non-login context
    page._present['input[name="loginKey"]'] = False
    page._present['input[name="password"]'] = False
    page._present['button:has-text("登录")'] = False

    account: Dict[str, Any] = {"login_url": "https://shopee.cn/account/login"}

    svc = LoginService()
    ok = svc.ensure_logged_in("shopee", page, account)

    assert ok is True, "If not on login page, should be treated as already logged in"




def test_browser_mode_verification_flow() -> None:
    """In browser mode, with verification UI present and no Enter fallback,
    fallback handler should click confirm and navigate away from login.
    """
    from modules.services.platform_login_service import LoginService

    page = FakePage(url="https://shopee.cn/account/login")
    # Ensure login button missing so login button path won't navigate
    page._present['button:has-text("登录")'] = False
    # Present verification inputs and confirm buttons
    page._present["input[name*='otp']"] = True
    page._present["button:has-text('确认')"] = True
    page._present["button:has-text('验证')"] = True

    # Disable Enter fallback by overriding keyboard
    class _NoEnterKeyboard(FakeKeyboard):
        def press(self, key: str) -> None:  # type: ignore[override]
            return None

    page.keyboard = _NoEnterKeyboard(page)

    account: Dict[str, Any] = {
        "username": "user@example.com",
        "password": "secret123",
        "login_url": "https://shopee.cn/account/login",
        "login_flags": {"shopee_verification_mode": "browser"},
    }

    svc = LoginService()
    ok = svc.ensure_logged_in("shopee", page, account)

    assert ok is True
    assert "login" not in page.url and "signin" not in page.url

if __name__ == "__main__":
    try:
        test_imports_no_side_effects()
        test_login_service_with_fake_page_success()
        test_login_service_off_mode_stays_on_login()
        test_login_service_non_login_url_is_true()
        print("[contract-tests] all passed")
        sys.exit(0)
    except AssertionError as e:
        print(f"[contract-tests] assertion failed: {e}")
        sys.exit(1)
    except Exception as e:  # noqa: BLE001
        print(f"[contract-tests] unexpected error: {e}")
        sys.exit(2)

