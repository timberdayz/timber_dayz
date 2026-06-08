from pathlib import Path


def test_business_overview_platform_filter_refreshes_platform_dependent_modules():
    text = Path("frontend/src/domains/business/views/BusinessOverview.vue").read_text(
        encoding="utf-8",
        errors="replace",
    )

    marker = "const onKpiFilterChange = async () => {"
    start = text.index(marker)
    body = text[start : text.index("}\n\n//", start)]

    for call in (
        "loadKPIData()",
        "loadComparisonData()",
        "loadOperationalMetrics()",
        "loadShopRacingData()",
        "loadTrafficRanking()",
    ):
        assert call in body
