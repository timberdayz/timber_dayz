#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import sys

_THIS_DIR = os.path.dirname(__file__)
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def test_analytics_config_contract() -> None:
    from modules.platforms.shopee.components.analytics_config import AnalyticsSelectors

    selectors = AnalyticsSelectors()

    assert selectors.overview_path == "/datacenter/traffic/overview"

    preset_labels = selectors.preset_labels
    assert set(preset_labels) == {"yesterday", "last_7_days", "last_30_days"}

    granularity_labels = selectors.granularity_labels
    assert set(granularity_labels) == {"daily", "weekly", "monthly"}


def test_analytics_export_metadata_contract() -> None:
    from modules.platforms.shopee.components.analytics_export import ShopeeAnalyticsExport

    assert ShopeeAnalyticsExport.platform == "shopee"
    assert ShopeeAnalyticsExport.component_type == "export"
    assert ShopeeAnalyticsExport.data_domain == "analytics"


if __name__ == "__main__":
    try:
        test_analytics_config_contract()
        test_analytics_export_metadata_contract()
        print("[analytics-contract-tests] all passed")
        sys.exit(0)
    except AssertionError as exc:
        print(f"[analytics-contract-tests] assertion failed: {exc}")
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        print(f"[analytics-contract-tests] unexpected error: {exc}")
        sys.exit(2)
