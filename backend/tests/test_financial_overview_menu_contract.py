from pathlib import Path


def test_financial_overview_route_is_not_listed_in_finance_menu_group():
    text = Path("frontend/src/config/menuGroups.js").read_text(encoding="utf-8")

    assert "/financial-overview" not in text


def test_financial_management_route_display_name_is_financial_settlement_center():
    text = Path("frontend/src/config/menuGroups.js").read_text(encoding="utf-8")

    assert "'/financial-management': '财务结算中心'" in text
