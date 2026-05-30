import modules.core.db as core_db


EmployeePerformanceInput = getattr(core_db, "EmployeePerformanceInput", None)


def test_employee_performance_input_model_exists_with_required_fields():
    assert EmployeePerformanceInput is not None, "EmployeePerformanceInput model is missing from modules.core.db"

    columns = EmployeePerformanceInput.__table__.c
    assert "employee_code" in columns
    assert "year_month" in columns
    assert "metric_code" in columns
    assert "target_value" in columns
    assert "achieved_value" in columns
    assert "max_score" in columns
    assert "metric_direction" in columns
