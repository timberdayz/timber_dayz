from pathlib import Path


def test_user_store_uses_role_based_permission_resolution():
    text = Path("frontend/src/stores/user.js").read_text(encoding="utf-8")

    assert "hasPermissionForRoles" in text
    assert "hasAnyRole" in text
    assert "const hasPermission = (permission) => hasPermissionForRoles(roles.value, permission)" in text
    assert "const hasRole = (requiredRoles) => hasAnyRole(roles.value, requiredRoles)" in text


def test_financial_management_route_requires_finance_permission_and_roles():
    text = Path("frontend/src/router/index.js").read_text(encoding="utf-8")

    assert "path: '/financial-management'" in text
    assert "permission: 'financial-management'" in text
    assert "roles: ['admin', 'manager', 'finance']" in text


def test_role_permissions_grant_financial_management_to_manager_and_finance():
    text = Path("frontend/src/config/rolePermissions.js").read_text(encoding="utf-8")

    assert "'financial-management'" in text
    assert "manager:" in text
    assert "finance:" in text
