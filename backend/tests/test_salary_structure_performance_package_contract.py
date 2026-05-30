from backend.schemas.hr import SalaryStructureCreate, SalaryStructureResponse, SalaryStructureUpdate


def test_salary_structure_contract_includes_performance_package_amount():
    assert "performance_package_amount" in SalaryStructureCreate.model_fields
    assert "performance_package_amount" in SalaryStructureResponse.model_fields
    assert "performance_package_amount" in SalaryStructureUpdate.model_fields
