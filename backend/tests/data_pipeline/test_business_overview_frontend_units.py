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


def test_business_overview_frontend_traffic_ranking_shows_pv_uv_conversion_columns():
    text = Path("frontend/src/domains/business/views/BusinessOverview.vue").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert 'prop="uv_conversion_rate"' in text
    assert 'label="UV\u8f6c\u5316\u7387"' in text
    assert 'prop="pv_conversion_rate"' in text
    assert 'label="PV\u8f6c\u5316\u7387"' in text
    assert "order_count: row.order_count" in text
    assert "uv_conversion_rate: row.uv_conversion_rate" in text
    assert "pv_conversion_rate: row.pv_conversion_rate" in text


def test_business_overview_frontend_groups_kpis_and_allows_wrapping():
    text = Path("frontend/src/domains/business/views/BusinessOverview.vue").read_text(
        encoding="utf-8",
        errors="replace",
    )

    for marker in (
        "kpi-compact-grid",
        "kpi-strip-card",
        "coreKpiCards",
        "exposure_order_rate",
    ):
        assert marker in text

    for legacy_marker in (
        "kpi-row-primary",
        "kpi-row-funnel",
        "kpi-flow-group",
        "kpi-rate-group",
    ):
        assert legacy_marker not in text

    assert "flex-wrap: nowrap" not in text


def test_business_overview_frontend_expense_tooltip_includes_labor_cost():
    text = Path("frontend/src/domains/business/views/BusinessOverview.vue").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "人力费用" in text
