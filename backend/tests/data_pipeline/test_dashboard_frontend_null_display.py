from pathlib import Path


def test_business_overview_operational_metrics_no_longer_forces_nulls_to_zero():
    text = Path("frontend/src/views/BusinessOverview.vue").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "monthly_target: response.monthly_target || 0" not in text
    assert "today_sales: response.today_sales || 0" not in text
    assert "estimated_expenses: response.estimated_expenses || 0" not in text
    assert "operating_result: response.operating_result || 0" not in text


def test_annual_summary_view_uses_missing_display_instead_of_zero_fallback():
    text = Path("frontend/src/views/AnnualSummary.vue").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "kpiData.value[0].value = data.conversion_rate != null ? `${Number(data.conversion_rate).toFixed(2)}%` : '0.00%'" not in text
    assert "kpiData.value[1].value = visitorCount != null ? formatInteger(visitorCount) : '0'" not in text
    assert "kpiData.value[3].value = data.gmv != null ? formatCurrency(data.gmv) : '0.00'" not in text
    assert "target_gmv: tc.target_gmv ?? 0" not in text
    assert "target_orders: tc.target_orders ?? 0" not in text
