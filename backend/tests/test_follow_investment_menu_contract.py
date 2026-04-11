from pathlib import Path


def test_menu_groups_use_financial_settlement_center_entry():
    text = Path("frontend/src/config/menuGroups.js").read_text(encoding="utf-8")

    assert "/my-follow-investment-income" in text
    assert "/financial-management" in text
    assert "财务结算中心" in text
    assert "我的跟投收益" in text
    assert "/financial-overview" not in text


def test_router_allows_investor_access_to_my_follow_investment_income():
    text = Path("frontend/src/router/index.js").read_text(encoding="utf-8")

    assert "path: '/my-follow-investment-income'" in text
    assert "permission: 'my-follow-investment-income'" in text
    assert "roles: ['admin', 'manager', 'operator', 'finance', 'investor']" in text
