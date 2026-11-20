from pathlib import Path


def test_financial_overview_route_is_not_listed_in_finance_menu_group():
    text = Path("frontend/src/config/menuGroups.js").read_text(encoding="utf-8")

    assert "/financial-overview" not in text


def test_financial_management_route_display_name_is_monthly_profit_dashboard():
    """财务菜单项显示名随「财务结算中心」→「月度利润看板」改名（2026-11-21）。"""
    text = Path("frontend/src/config/menuGroups.js").read_text(encoding="utf-8")

    assert "'/financial-management': '月度利润看板'" in text
    assert "财务结算中心" not in text
