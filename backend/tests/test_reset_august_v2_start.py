import importlib.util
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).parents[2] / "scripts" / "reset_august_v2_start.py"


def load_script():
    spec = importlib.util.spec_from_file_location("reset_august_v2_start", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_august_reset_accepts_only_an_unlocked_month_without_settlement():
    script = load_script()
    report = {
        "period_month": "2026-08",
        "locked_basis_rows": 0,
        "v2_basis_rows": 0,
        "payroll_statuses": [],
        "settlement_rows": 0,
    }

    script.validate_reset_report(report)

    with pytest.raises(script.AugustV2ResetSafetyError, match="locked"):
        script.validate_reset_report({**report, "locked_basis_rows": 1})
    with pytest.raises(script.AugustV2ResetSafetyError, match="payroll"):
        script.validate_reset_report({**report, "payroll_statuses": ["confirmed"]})
    with pytest.raises(script.AugustV2ResetSafetyError, match="settlement"):
        script.validate_reset_report({**report, "settlement_rows": 1})
    with pytest.raises(script.AugustV2ResetSafetyError, match="V2"):
        script.validate_reset_report({**report, "v2_basis_rows": 1})


def test_august_reset_contract_preserves_source_tables_and_uses_shared_v2_flow():
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert 'PERIOD_MONTH = "2026-08"' in source
    assert "V2MonthlyRefreshService" in source
    assert "export_backup" in source
    assert "fact_audit_logs" in source
    for derived_table in (
        "finance.shop_profit_basis",
        "finance.employee_labor_cost_allocations",
        "c_class.employee_commissions",
        "c_class.employee_performance",
        "c_class.shop_commissions",
        "a_class.payroll_records",
    ):
        assert derived_table in source
    for source_table in (
        "b_class",
        "a_class.operating_costs",
        "a_class.employee_shop_assignments",
        "a_class.salary_structures",
        "a_class.employee_performance_inputs",
        "a_class.employee_performance_adjustments",
    ):
        assert f"DELETE FROM {source_table}" not in source


def test_backend_image_includes_the_one_time_august_reset_tool():
    dockerfile = Path(__file__).parents[2] / "Dockerfile.backend"
    source = dockerfile.read_text(encoding="utf-8")

    assert "COPY scripts/reset_august_v2_start.py /app/scripts/reset_august_v2_start.py" in source
