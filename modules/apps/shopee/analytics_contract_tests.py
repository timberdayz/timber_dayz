#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import sys

_THIS_DIR = os.path.dirname(__file__)
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def test_analytics_domain_path_contract() -> None:
    from modules.platforms.shopee.components.business_analysis_common import build_domain_path

    assert build_domain_path("analytics") == "/datacenter/traffic/overview"


def test_analytics_export_metadata_contract() -> None:
    from modules.components.base import ExecutionContext
    from modules.platforms.shopee.components.analytics_export import ShopeeAnalyticsExport

    assert ShopeeAnalyticsExport.platform == "shopee"
    assert ShopeeAnalyticsExport.component_type == "export"
    assert ShopeeAnalyticsExport.data_domain == "analytics"

    export_component = ShopeeAnalyticsExport(
        ExecutionContext(platform="shopee", account={}, config={})
    )
    assert export_component.sel.overview_path == "/datacenter/traffic/overview"


def test_analytics_rejects_today_realtime_contract() -> None:
    from modules.components.base import ExecutionContext
    from modules.platforms.shopee.components.analytics_export import ShopeeAnalyticsExport

    export_component = ShopeeAnalyticsExport(
        ExecutionContext(platform="shopee", account={}, config={})
    )

    try:
        export_component._target_date_label({"preset": "today_realtime"})
    except ValueError as exc:
        assert "today_realtime" in str(exc)
        return

    raise AssertionError("analytics export should reject today_realtime preset")


if __name__ == "__main__":
    try:
        test_analytics_domain_path_contract()
        test_analytics_export_metadata_contract()
        test_analytics_rejects_today_realtime_contract()
        print("[analytics-contract-tests] all passed")
        sys.exit(0)
    except AssertionError as exc:
        print(f"[analytics-contract-tests] assertion failed: {exc}")
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        print(f"[analytics-contract-tests] unexpected error: {exc}")
        sys.exit(2)
