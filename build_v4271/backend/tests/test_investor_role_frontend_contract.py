from pathlib import Path


def test_role_permissions_define_investor_role():
    text = Path("frontend/src/config/rolePermissions.js").read_text(encoding="utf-8")

    assert "investor:" in text
    assert "投资人" in text
    assert "'business-overview'" in text
    assert "'personal-settings'" in text


def test_router_allows_investor_access_to_basic_entry_points():
    text = Path("frontend/src/router/index.js").read_text(encoding="utf-8")

    assert "roles: ['admin', 'manager', 'operator', 'finance', 'tourist', 'investor']" in text
    assert "roles: ['admin', 'manager', 'operator', 'finance', 'investor']" in text
    assert "roles: ['admin', 'manager', 'operator', 'finance', 'tourist', 'investor']  // 全员可见" in text or "roles: ['admin', 'manager', 'operator', 'finance', 'tourist', 'investor']" in text

