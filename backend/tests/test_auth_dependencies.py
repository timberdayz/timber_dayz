"""
Authentication dependency helper tests
"""

from types import SimpleNamespace

from backend.dependencies.auth import is_admin_user


def test_is_admin_user_accepts_superuser():
    user = SimpleNamespace(is_superuser=True, roles=[])

    assert is_admin_user(user) is True


def test_is_admin_user_accepts_admin_role_code():
    user = SimpleNamespace(
        is_superuser=False,
        roles=[SimpleNamespace(role_code="admin", role_name="whatever")],
    )

    assert is_admin_user(user) is True


def test_is_admin_user_accepts_admin_role_name():
    user = SimpleNamespace(
        is_superuser=False,
        roles=[SimpleNamespace(role_code="finance", role_name="admin")],
    )

    assert is_admin_user(user) is True


def test_is_admin_user_rejects_non_admin_user():
    user = SimpleNamespace(
        is_superuser=False,
        roles=[SimpleNamespace(role_code="finance", role_name="finance")],
    )

    assert is_admin_user(user) is False
