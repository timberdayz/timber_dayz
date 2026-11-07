from pathlib import Path


def test_api_index_exposes_hr_performance_adjustment_methods():
    text = Path("frontend/src/api/index.js").read_text(encoding="utf-8")

    assert "async getHrPerformanceAdjustments(params = {})" in text
    assert "async createHrPerformanceAdjustment(data)" in text
    assert "async updateHrPerformanceAdjustment(adjustmentId, data)" in text
    assert "async deleteHrPerformanceAdjustment(adjustmentId)" in text
    assert "async getHrPerformanceInputs(params = {})" in text
    assert "async createHrPerformanceInput(data)" in text
    assert "async updateHrPerformanceInput(inputId, data)" in text
    assert "async deleteHrPerformanceInput(inputId)" in text
    assert "async getHrPerformanceInputTemplates(params = {})" in text
    assert "async applyHrPerformanceInputTemplate(data)" in text


def test_hr_performance_management_view_exposes_adjustment_panel():
    text = Path("frontend/src/domains/business/views/hr/PerformanceManagement.vue").read_text(encoding="utf-8")

    assert "adjustmentDialogVisible" in text
    assert "openCreateAdjustment" in text
    assert "adjustmentList" in text
    assert "loadAdjustmentList" in text
    assert "createHrPerformanceAdjustment" in text
    assert "inputDialogVisible" in text
    assert "openCreateInput" in text
    assert "inputList" in text
    assert "loadInputList" in text
    assert "createHrPerformanceInput" in text
    assert "openApplyTemplate" in text
    assert "applyHrPerformanceInputTemplate" in text
    assert "templateDialogVisible" in text


def test_employee_salary_view_mentions_stale_payroll_warning():
    text = Path("frontend/src/domains/business/views/hr/EmployeeSalary.vue").read_text(encoding="utf-8")

    assert "is_stale_against_latest_calc" in text
    assert "结果已过期" in text


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
    assert "personal_input_items" in display
    assert "performance_source_type" in display


def test_person_target_page_marks_boundary_with_performance_inputs():
    text = Path("frontend/src/domains/business/views/target/TargetPersonManagement.vue").read_text(encoding="utf-8")

    # 人员绩效输入入口：按钮文案 + 跳转目标（commit a12d49bf 把这个入口搬到本页面）
    assert "人员绩效输入" in text
    assert "goToPerformancePerson" in text
    assert "/hr-performance-management/person" in text
    # 员工目标已统一为「共同承接店铺目标」(commit 8c042d71)，本页面只读、不再创建员工目标
    assert "getHrEmployeeTargetSummary" in text
    assert "createHrEmployeeTarget" not in text


def test_legacy_target_management_page_is_downgraded_to_split_entry():
    text = Path("frontend/src/domains/business/views/target/TargetManagement.vue").read_text(encoding="utf-8")

    assert "历史入口" in text
    assert "/target-management/shop" in text
    assert "/target-management/person" in text
    assert "/target-management/operation" in text
    # 人员绩效输入项入口已随个人绩效工作台搬到个人目标页 (commit a12d49bf)，
    # 历史页不再重复挂载；该入口仍由菜单组提供（见 frontend/scripts/targetRouteSplit.test.mjs）。
    assert "/hr-performance-management/person" not in text


def test_income_audit_route_and_view_exist():
    router_text = Path("frontend/src/router/index.js").read_text(encoding="utf-8")
    menu_text = Path("frontend/src/config/menuGroups.js").read_text(encoding="utf-8")
    view_text = Path("frontend/src/domains/business/views/hr/IncomeAudit.vue").read_text(encoding="utf-8")

    assert "/hr-income-audit" in router_text
    assert "/hr-income-audit" in menu_text
    assert "员工月度收入审计" in view_text
    assert "getHrIncomeAudit" in view_text
