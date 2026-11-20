from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_follow_investment_source_files_are_gone():
    for rel in (
        "backend/services/follow_investment_service.py",
        "backend/domains/business/routers/follow_investment.py",
        "backend/routers/follow_investment.py",
        "backend/schemas/follow_investment.py",
    ):
        assert not (REPO_ROOT / rel).exists(), f"{rel} 仍存在，跟投未下线"


def test_follow_investment_route_not_registered():
    source = (REPO_ROOT / "backend" / "domains" / "business" / "routes.py").read_text(
        encoding="utf-8-sig"
    )
    assert "follow_investment" not in source


def test_investor_role_and_permission_are_removed():
    role_source = (REPO_ROOT / "backend" / "services" / "system_role_service.py").read_text(
        encoding="utf-8-sig"
    )
    permission_source = (REPO_ROOT / "backend" / "services" / "permission_service.py").read_text(
        encoding="utf-8-sig"
    )
    assert '"investor"' not in role_source
    assert "my-follow-investment-income" not in permission_source


def test_settlement_service_no_longer_imports_follow_investment():
    source = (REPO_ROOT / "backend" / "services" / "monthly_profit_settlement_service.py").read_text(
        encoding="utf-8-sig"
    )
    assert "FollowInvestment" not in source
    assert "MonthlyProfitFollowDetail" not in source
