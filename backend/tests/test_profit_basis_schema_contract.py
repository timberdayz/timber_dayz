from backend.schemas.profit_basis import ProfitBasisResponse
from modules.core.db import ShopProfitBasis


def test_profit_basis_response_exposes_v2_cost_breakdown_without_removing_legacy_total():
    payload = ProfitBasisResponse(
        period_month="2026-09",
        platform_code="shopee",
        shop_id="shop-1",
        orders_profit_amount=4000,
        a_class_cost_amount=2000,
        other_a_class_cost_amount=1500,
        pre_commission_labor_cost_amount=500,
        b_class_cost_amount=0,
        profit_basis_amount=2000,
        basis_version="A_PRE_COMMISSION_LABOR_V2",
        cost_status="projected",
    )

    assert payload.model_dump()["a_class_cost_amount"] == 2000
    assert payload.model_dump()["other_a_class_cost_amount"] == 1500
    assert payload.model_dump()["pre_commission_labor_cost_amount"] == 500
    assert payload.model_dump()["cost_status"] == "projected"


def test_shop_profit_basis_persists_v2_cost_breakdown_for_locked_audit():
    columns = ShopProfitBasis.__table__.c

    assert "other_a_class_cost_amount" in columns
    assert "pre_commission_labor_cost_amount" in columns
    assert "cost_status" in columns
