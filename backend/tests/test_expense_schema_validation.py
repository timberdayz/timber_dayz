import pytest
from pydantic import ValidationError

from backend.schemas.expense import ExpenseCreateRequest, ExpenseUpdateRequest


def test_expense_create_rejects_blank_shop_id():
    with pytest.raises(ValidationError):
        ExpenseCreateRequest(
            platform_code="shopee",
            shop_id="   ",
            year_month="2026-05",
        )


def test_expense_create_rejects_blank_platform_code():
    with pytest.raises(ValidationError):
        ExpenseCreateRequest(
            platform_code="   ",
            shop_id="shop-1",
            year_month="2026-05",
        )


def test_expense_update_rejects_blank_platform_code_when_provided():
    model = ExpenseUpdateRequest(platform_code=" ")

    assert model.platform_code is None


def test_expense_create_rejects_all_zero_empty_payload():
    with pytest.raises(ValidationError):
        ExpenseCreateRequest(
            platform_code="shopee",
            shop_id="shop-1",
            year_month="2026-05",
            rent=0,
            marketing_fee=0,
            utilities=0,
            ai_token_cost=0,
            labor_cost=0,
            other_costs=0,
            note=None,
            attachments=[],
        )


def test_expense_update_rejects_all_zero_empty_payload():
    with pytest.raises(ValidationError):
        ExpenseUpdateRequest(
            platform_code="shopee",
            rent=0,
            marketing_fee=0,
            utilities=0,
            ai_token_cost=0,
            labor_cost=0,
            other_costs=0,
            note="",
            attachments=[],
        )


def test_expense_create_accepts_labor_cost_only_payload():
    model = ExpenseCreateRequest(
        platform_code="shopee",
        shop_id="shop-1",
        year_month="2026-05",
        labor_cost=100,
    )

    assert model.labor_cost == 100


def test_expense_update_accepts_labor_cost_only_payload():
    model = ExpenseUpdateRequest(labor_cost=100)

    assert model.labor_cost == 100


def test_expense_create_rejects_negative_labor_cost():
    with pytest.raises(ValidationError):
        ExpenseCreateRequest(
            platform_code="shopee",
            shop_id="shop-1",
            year_month="2026-05",
            labor_cost=-1,
        )
