from pathlib import Path


def test_business_overview_view_uses_single_platform_param():
    text = Path("frontend/src/views/BusinessOverview.vue").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "params.platforms = kpiPlatform.value" not in text
    assert "params.platform = kpiPlatform.value" in text
    assert "platform: kpiPlatform.value || undefined" in text


def test_dashboard_api_index_uses_platform_not_platforms_for_business_overview_routes():
    text = Path("frontend/src/api/index.js").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert 'if (params.platforms) queryParams.append("platforms", params.platforms);' not in text
    assert 'if (params.platform) queryParams.append("platform", params.platform);' in text


def test_dashboard_router_supports_platform_alias_for_shop_and_traffic_routes():
    text = Path("backend/routers/dashboard_api_postgresql.py").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert 'platform: Optional[str] = Query(None, description="single platform code")' in text
    assert 'effective_platform = platform or (platforms.split(",")[0].strip() if platforms else None)' in text
