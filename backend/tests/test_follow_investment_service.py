from datetime import date

import pytest

from backend.services.follow_investment_service import FollowInvestmentService


def test_calculate_occupied_days_in_month():
    service = FollowInvestmentService(db=None)

    assert service.calculate_occupied_days(
        year_month="2026-03",
        contribution_date=date(2026, 3, 1),
        withdraw_date=None,
    ) == 31
    assert service.calculate_occupied_days(
        year_month="2026-03",
        contribution_date=date(2026, 3, 16),
        withdraw_date=None,
    ) == 16
    assert service.calculate_occupied_days(
        year_month="2026-03",
        contribution_date=date(2026, 2, 20),
        withdraw_date=date(2026, 3, 10),
    ) == 10


def test_calculate_settlement_detail_ratios():
    service = FollowInvestmentService(db=None)

    rows = [
        {
            "investor_user_id": 101,
            "contribution_amount": 50000,
            "contribution_date": date(2026, 3, 1),
            "withdraw_date": None,
        },
        {
            "investor_user_id": 102,
            "contribution_amount": 30000,
            "contribution_date": date(2026, 3, 16),
            "withdraw_date": None,
        },
    ]

    details = service.build_settlement_details(
        year_month="2026-03",
        distributable_amount=32000,
        investments=rows,
    )

    assert len(details) == 2
    assert details[0]["occupied_days"] == 31
    assert details[1]["occupied_days"] == 16
    assert details[0]["weighted_capital"] == pytest.approx(1550000)
    assert details[1]["weighted_capital"] == pytest.approx(480000)
    assert details[0]["share_ratio"] == pytest.approx(1550000 / 2030000, rel=1e-4)
    assert details[1]["share_ratio"] == pytest.approx(480000 / 2030000, rel=1e-4)
    assert details[0]["estimated_income"] + details[1]["estimated_income"] == pytest.approx(32000, abs=0.01)


def test_calculate_distributable_details_with_no_investments():
    service = FollowInvestmentService(db=None)

    details = service.build_settlement_details(
        year_month="2026-03",
        distributable_amount=32000,
        investments=[],
    )

    assert details == []
