#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import sys

_THIS_DIR = os.path.dirname(__file__)
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from modules.apps.shopee.analytics_smoke import classify_environment_state


def test_classify_login_page() -> None:
    state = classify_environment_state(
        url="https://seller.shopee.cn/account/signin?next=%2Fdatacenter%2Ftraffic%2Foverview",
        title="Shopee",
        body_text="login form",
    )
    assert state == "login_required"


def test_classify_loading_shell() -> None:
    state = classify_environment_state(
        url="https://seller.shopee.cn/datacenter/traffic/overview",
        title="Shopee",
        body_text="S",
    )
    assert state == "loading_blocked"


def test_classify_script_only_shell_as_loading() -> None:
    state = classify_environment_state(
        url="https://seller.shopee.cn/datacenter/traffic/overview",
        title="",
        body_text="window.__performanceBodyScriptStartTime = Date.now();window.__performanceFrameworkScriptStartTime = Date.now();",
    )
    assert state == "loading_blocked"


def test_classify_business_page() -> None:
    state = classify_environment_state(
        url="https://seller.shopee.cn/datacenter/traffic/overview?cnsc_shop_id=1",
        title="Shopee",
        body_text="GMT+08 下载数据 流量",
    )
    assert state == "business_ready"


if __name__ == "__main__":
    try:
        test_classify_login_page()
        test_classify_loading_shell()
        test_classify_script_only_shell_as_loading()
        test_classify_business_page()
        print("[analytics-smoke-contract-tests] all passed")
        raise SystemExit(0)
    except AssertionError as exc:
        print(f"[analytics-smoke-contract-tests] assertion failed: {exc}")
        raise SystemExit(1)
    except Exception as exc:  # noqa: BLE001
        print(f"[analytics-smoke-contract-tests] unexpected error: {exc}")
        raise SystemExit(2)
