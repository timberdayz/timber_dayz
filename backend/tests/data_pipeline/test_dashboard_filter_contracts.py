from pathlib import Path


def test_business_overview_view_uses_single_platform_param():
    text = Path("frontend/src/domains/business/views/BusinessOverview.vue").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "platforms" not in text
    assert "platform: kpiPlatform.value" not in text
    assert "platform_code: kpiPlatform.value" in text


def test_dashboard_api_index_uses_platform_not_platforms_for_business_overview_routes():
    text = Path("frontend/src/api/index.js").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert 'if (params.platforms) queryParams.append("platforms", params.platforms);' not in text
    assert 'queryParams.append(\'platform\', params.platform)' not in text
    assert "queryParams.append('platform_code', params.platform_code)" in text


def test_dashboard_router_supports_platform_alias_for_shop_and_traffic_routes():
    text = Path("backend/routers/dashboard_api_postgresql.py").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "Business Overview API no longer accepts legacy query params." in text
    assert "platforms.split" not in text
