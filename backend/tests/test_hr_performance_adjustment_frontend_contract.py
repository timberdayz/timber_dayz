from pathlib import Path


def test_api_index_exposes_hr_performance_adjustment_methods():
    text = Path("frontend/src/api/index.js").read_text(encoding="utf-8")

    assert "async getHrPerformanceAdjustments(params = {})" in text
    assert "async createHrPerformanceAdjustment(data)" in text
    assert "async updateHrPerformanceAdjustment(adjustmentId, data)" in text
    assert "async deleteHrPerformanceAdjustment(adjustmentId)" in text


def test_hr_performance_management_view_exposes_adjustment_panel():
    text = Path("frontend/src/domains/business/views/hr/PerformanceManagement.vue").read_text(encoding="utf-8")

    assert "adjustmentDialogVisible" in text
    assert "openCreateAdjustment" in text
    assert "adjustmentList" in text
    assert "loadAdjustmentList" in text
    assert "createHrPerformanceAdjustment" in text


def test_performance_views_expose_ranking_pool_and_alert_helpers():
    mgmt = Path("frontend/src/domains/business/views/hr/PerformanceManagement.vue").read_text(encoding="utf-8")
    display = Path("frontend/src/domains/business/views/hr/PerformanceDisplay.vue").read_text(encoding="utf-8")

    assert "rankingPoolText" in mgmt
    assert "performanceAlertText" in mgmt
    assert "poolFilter" in mgmt
    assert "alertFilter" in mgmt
    assert "filteredPerformanceData" in mgmt
    assert "rankingPoolText" in display
    assert "performanceAlertText" in display
    assert "poolFilter" in display
    assert "alertFilter" in display
    assert "filteredPerformanceData" in display
