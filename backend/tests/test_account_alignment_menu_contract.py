from pathlib import Path


def test_account_alignment_route_is_listed_in_account_management_menu_group():
    router_text = Path("frontend/src/router/index.js").read_text(encoding="utf-8")
    menu_text = Path("frontend/src/config/menuGroups.js").read_text(encoding="utf-8")

    assert "/account-alignment" in router_text
    assert "name: 'AccountAlignment'" in router_text
    assert "/account-alignment" in menu_text
