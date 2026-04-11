from pathlib import Path


def test_api_index_exposes_hr_performance_adjustment_methods():
    text = Path("frontend/src/api/index.js").read_text(encoding="utf-8")

    assert "async getHrPerformanceAdjustments(params = {})" in text
    assert "async createHrPerformanceAdjustment(data)" in text
    assert "async updateHrPerformanceAdjustment(adjustmentId, data)" in text
    assert "async deleteHrPerformanceAdjustment(adjustmentId)" in text


def test_hr_performance_management_view_exposes_adjustment_panel():
    text = Path("frontend/src/views/hr/PerformanceManagement.vue").read_text(encoding="utf-8")

    assert "adjustmentDialogVisible" in text
    assert "openCreateAdjustment" in text
    assert "adjustmentList" in text
    assert "loadAdjustmentList" in text
    assert "createHrPerformanceAdjustment" in text
