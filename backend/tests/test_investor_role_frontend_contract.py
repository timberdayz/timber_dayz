from pathlib import Path


def test_role_permissions_define_investor_role():
    text = Path("frontend/src/config/rolePermissions.js").read_text(encoding="utf-8")
    investor_block = text.split("investor:", 1)[1].split("tourist:", 1)[0]

    assert "investor:" in text
    assert "投资人" in text
    assert "'business-overview'" in investor_block
    assert "'my-follow-investment-income'" in investor_block
    assert "'personal-settings'" not in investor_block


def test_router_allows_investor_access_to_basic_entry_points():
    text = Path("frontend/src/router/index.js").read_text(encoding="utf-8")

    assert "roles: ['admin', 'manager', 'operator', 'finance', 'tourist', 'investor']" in text
    assert "roles: ['admin', 'manager', 'operator', 'finance', 'investor']" in text
