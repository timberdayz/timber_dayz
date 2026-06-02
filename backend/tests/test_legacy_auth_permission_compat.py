from backend.utils.auth import has_permission
from pathlib import Path


def test_legacy_has_permission_uses_explicit_permissions_payload_first():
    user = {
        "role": "manager",
        "permissions": ["finance-reports", "order-management"],
    }

    assert has_permission(user, "finance-reports") is True
    assert has_permission(user, "campaign:delete") is False


def test_legacy_has_permission_falls_back_to_current_system_role_defaults():
    manager = {"role": "manager"}
    investor = {"role": "investor"}

    assert has_permission(manager, "order-management") is True
    assert has_permission(manager, "sales-detail") is False
    assert has_permission(investor, "my-follow-investment-income") is True
    assert has_permission(investor, "personal-settings") is False


def test_legacy_has_permission_keeps_admin_override():
    admin = {"role": "admin"}

    assert has_permission(admin, "anything") is True


def test_legacy_auth_module_no_longer_keeps_standalone_role_permissions_table():
    source = Path("backend/utils/auth.py").read_text(encoding="utf-8")

    assert "ROLE_PERMISSIONS = {" not in source
