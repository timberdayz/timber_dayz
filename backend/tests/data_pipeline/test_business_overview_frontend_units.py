from pathlib import Path


def test_business_overview_frontend_no_longer_marks_raw_amounts_as_w():
    text = Path("frontend/src/domains/business/views/BusinessOverview.vue").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "(w)" not in text
    assert 'const targetUnit = ref("")' in text


def test_business_overview_frontend_shows_explicit_pv_uv_kpi_cards():
    text = Path("frontend/src/domains/business/views/BusinessOverview.vue").read_text(
        encoding="utf-8",
        errors="replace",
    )

    for label in (
        "曝光量",
        "浏览量(PV)",
        "访客数(UV)",
        "访问率",
        "浏览深度",
        "UV转化率",
        "PV转化率",
    ):
        assert label in text

    assert "客流量" not in text
    assert "uv_conversion_rate" in text
    assert "pv_conversion_rate" in text
