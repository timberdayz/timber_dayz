from modules.core.db import DimShop, PerformanceScore, SalaryStructure


def test_salary_structure_exposes_remark_field():
    assert "remark" in SalaryStructure.__table__.c


def test_performance_score_exposes_calculated_at_field():
    assert "calculated_at" in PerformanceScore.__table__.c


def test_dim_shop_exposes_is_active_field():
    assert "is_active" in DimShop.__table__.c
