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


def test_business_overview_frontend_traffic_ranking_embeds_changes_without_compare_columns():
    text = Path("frontend/src/domains/business/views/BusinessOverview.vue").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert 'label="\u5bf9\u6bd4\u671fUV"' not in text
    assert 'label="\u5bf9\u6bd4\u671fPV"' not in text
    assert "visitor_count_change_rate" in text
    assert "page_views_change_rate" in text
    assert "uv_conversion_rate_change_value" in text
    assert "pv_conversion_rate_change_value" in text
    assert "visitor_count_previous" in text
    assert "page_views_previous" in text
    assert "uv_conversion_rate_previous" in text
    assert "pv_conversion_rate_previous" in text
    assert "\u73af\u6bd4 {{" not in text
    assert "\u8f83\u4e0a\u671f {{" not in text
    assert "\u2191" in text
    assert "\u2193" in text


def test_business_overview_frontend_shop_racing_embeds_metric_changes_and_expands_layout():
    text = Path("frontend/src/domains/business/views/BusinessOverview.vue").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert '<el-col :xs="24" :lg="16">' in text
    assert '<el-col :xs="24" :lg="8">' in text
    assert '<el-col :xs="24" :lg="12">' in text
    assert "gmv_change_rate" in text
    assert "profit_change_rate" in text
    assert "order_count_change_rate" in text
    assert "achievement_rate_change_value" in text
    assert "gmv_previous" in text
    assert "profit_previous" in text
    assert "avg_order_value_previous" in text
    assert "profit_margin_previous" in text
    assert "order_count_previous" in text
    assert "achievement_rate_previous" in text
    assert "avg_order_value_change_rate" in text
    assert "profit_margin_change_value" in text
    assert "min-height: 400px" not in text


def test_business_overview_frontend_keeps_module_positions_and_uses_adaptive_table_widths():
    text = Path("frontend/src/domains/business/views/BusinessOverview.vue").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert '<div class="overview-pair-section overview-top-section">' in text
    assert '<el-row :gutter="16" class="overview-pair-row">' in text
    assert '<div class="overview-pair-section overview-rank-section">' in text
    assert '<el-row :gutter="16" class="overview-half-table-row">' in text
    assert '<el-col :xs="24" :lg="8">' in text
    assert '<el-col :xs="24" :lg="16">' in text
    assert text.count('<el-col :xs="24" :lg="12">') == 2
    assert '<div class="traffic-ranking-section">' not in text
    assert 'label="\u5bf9\u6bd4\u671fUV"' not in text
    assert 'label="\u5bf9\u6bd4\u671fPV"' not in text
    assert 'prop="visitor_count"\n            label="\u8bbf\u5ba2\u6570(UV)"\n            min-width="92"' in text
    assert 'prop="page_views"\n            label="\u6d4f\u89c8\u91cf(PV)"\n            min-width="92"' in text
    assert 'prop="gmv" label="\u9500\u552e\u989d" min-width="86"' in text
    assert 'prop="profit" label="\u5229\u6da6" min-width="86"' in text
    assert 'prop="profit_margin" min-width="60" align="right">' in text
    assert '<span>利润率</span>' in text
    assert 'prop="order_count" label="\u8ba2\u5355\u6570" min-width="72"' in text
    assert 'prop="avg_order_value" min-width="68" align="right">' in text
    assert '<span>客单价</span>' in text
    assert 'prop="achievement_rate" label="\u5b8c\u6210\u7387" min-width="96"' in text


def test_business_overview_frontend_compacts_spacing_and_controls():
    text = Path("frontend/src/domains/business/views/BusinessOverview.vue").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert '.overview-pair-section {\n  margin-bottom: 18px;' in text
    assert '.overview-pair-section :deep(.el-table .cell) {\n  padding: 0 6px;' in text
    assert '.header-controls {\n  display: flex;\n  align-items: center;\n  gap: 8px;' in text
    assert 'flex-wrap: wrap;' in text
    assert '.target-progress-section {\n  margin-bottom: 10px;\n  padding: 10px 12px;' in text
    assert '.comparison-table-container {\n  padding: 2px 0;' in text
    assert '.racing-table {\n  min-width: 762px;' in text
    assert '.metric-stack {\n  display: inline-flex;\n  flex-direction: column;\n  align-items: flex-end;\n  gap: 1px;' in text
    assert '.metric-previous {\n  color: #909399;\n  font-size: 9px;' in text
    assert '.metric-delta {\n  font-size: 10px;' in text


def test_business_overview_frontend_rank_cards_share_equal_height_scroll_area():
    text = Path("frontend/src/domains/business/views/BusinessOverview.vue").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert 'class="chart-card ranking-card"' in text
    assert '<div class="traffic-ranking-container" v-loading="loadingTrafficRanking">' in text
    assert '.overview-rank-section :deep(.el-col) {\n  display: flex;' in text
    assert '.ranking-card {\n  display: flex;\n  flex-direction: column;\n  width: 100%;\n  height: 100%;' in text
    assert '.racing-container,\n.traffic-ranking-container {\n  flex: 1;\n  min-height: 720px;\n  max-height: 720px;\n  overflow: auto;' in text
    assert "600px" in text


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
