from __future__ import annotations

import pytest

from modules.platforms.shopee.components.business_analysis_common import (
    allowed_presets_for_domain,
    build_domain_path,
    normalize_time_request,
    validate_time_request,
)


def test_build_domain_path_returns_expected_products_route() -> None:
    assert build_domain_path("products") == "/datacenter/product/overview"


def test_build_domain_path_returns_expected_services_route() -> None:
    assert build_domain_path("services") == "/datacenter/service/overview"


def test_build_domain_path_returns_expected_analytics_route() -> None:
    assert build_domain_path("analytics") == "/datacenter/traffic/overview"


def test_allowed_presets_for_analytics_excludes_today_realtime() -> None:
    assert allowed_presets_for_domain("analytics") == [
        "yesterday",
        "last_7_days",
        "last_30_days",
    ]


def test_validate_time_request_rejects_today_realtime_for_analytics() -> None:
    with pytest.raises(ValueError, match="today_realtime"):
        validate_time_request("analytics", time_mode="preset", value="today_realtime")


def test_normalize_time_request_accepts_monthly_granularity() -> None:
    assert normalize_time_request("products", time_mode="granularity", value="monthly") == {
        "time_mode": "granularity",
        "value": "monthly",
    }
