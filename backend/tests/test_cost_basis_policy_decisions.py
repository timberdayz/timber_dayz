"""成本基数的口径决策（业务已确认，2026-11）。

两条决策：

1. **绩效工资不计入成本基数**
   提成基数是「提成前利润」，绩效工资属于提成之后的支出。
   计进去等于同一笔钱扣两次（先压低基数、再算提成）。
2. **无归属人力成本必须二次分摊进各店**
   否则这笔钱既不消失也不归属任何人，等于让所有店利润虚高、提成虚高。
"""

from backend.services.labor_cost_policy_service import LaborCostPolicyService
from backend.services.labor_cost_projection_service import (
    LaborCostProjectionService,
)


def test_performance_salary_is_not_part_of_pre_commission_labor_cost():
    assert "performance_salary" not in LaborCostProjectionService.PRE_COMMISSION_FIELDS
    assert "performance_salary" in LaborCostPolicyService.EXCLUDED_COST_FIELDS
    assert "commission" in LaborCostPolicyService.EXCLUDED_COST_FIELDS


def test_cost_basis_includes_other_operating_cost_and_pre_commission_labor_cost():
    assert "other_a_class_cost_amount" in LaborCostPolicyService.INCLUDED_COST_FIELDS
    assert "pre_commission_labor_cost_amount" in LaborCostPolicyService.INCLUDED_COST_FIELDS


def test_shared_labor_cost_is_allocated_to_shops():
    assert LaborCostPolicyService.SHARED_LABOR_ALLOCATION_ENABLED is True


def test_cost_basis_rules_are_describable_in_business_language():
    rules = LaborCostPolicyService.describe_cost_basis_rules()
    assert rules["basis_version"] == LaborCostPolicyService.CURRENT_BASIS_VERSION
    assert "利润基数" in rules["formula"]
    assert rules["notes"]
    # 说明里必须把「绩效工资不进基数」讲清楚
    assert any("绩效工资" in note for note in rules["notes"])
    # 口径里不能同时出现「绩效工资」和「计入成本」
    assert not any(
        "绩效工资" in field and field in LaborCostPolicyService.INCLUDED_COST_FIELDS
        for field in LaborCostPolicyService.INCLUDED_COST_FIELDS
    )
