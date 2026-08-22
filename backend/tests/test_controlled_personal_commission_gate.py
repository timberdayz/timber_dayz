from backend.services.hr_income_calculation_service import HRIncomeCalculationService


def test_controlled_personal_commission_gate_blocks_partial_but_keeps_not_participating():
    allowed, blocked = HRIncomeCalculationService.partition_controlled_commission_codes(
        {
            "COMPLETE": {"calculation_status": "complete"},
            "PARTIAL": {"calculation_status": "partial"},
            "OUT": {"calculation_status": "not_participating"},
        }
    )

    assert allowed == {"COMPLETE", "OUT"}
    assert blocked == {"PARTIAL"}
