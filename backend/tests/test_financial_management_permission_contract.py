from pathlib import Path


def test_user_store_resolves_permission_from_backend_permission_list():
    """权限判定口径：后端下发的 permissions 列表 + admin 兜底（不再是纯角色推导）。

    佐证：commit b458b8a7 "feat:准备上线" 把
    ``hasPermissionForRoles(roles.value, permission)`` 改成
    「admin 直通 + ``permissions`` 列表包含」；后端登录响应已下发
    ``permissions`` 载荷（见 backend/tests/test_rbac_auth_payload_contract.py）。
    """
    text = Path("frontend/src/stores/user.js").read_text(encoding="utf-8")

    assert "hasAnyRole" in text
    assert "const hasPermission = (permission) => {" in text
    assert "if (hasAnyRole(roles.value, ['admin'])) return true" in text
    assert "return permissions.value.includes(permission)" in text
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
