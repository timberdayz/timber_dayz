from pathlib import Path


def test_role_seed_scripts_do_not_create_empty_permissions():
    targets = [
        "scripts/bootstrap_production.py",
        "scripts/ensure_all_roles.py",
        "scripts/create_admin_user.py",
    ]

    for path_str in targets:
        text = Path(path_str).read_text(encoding="utf-8", errors="replace")
        assert 'permissions="[]"' not in text
        assert "permissions='[]'" not in text


def test_role_seed_scripts_reference_system_role_defaults():
    for path_str in (
        "scripts/bootstrap_production.py",
        "scripts/ensure_all_roles.py",
        "scripts/create_admin_user.py",
    ):
        text = Path(path_str).read_text(encoding="utf-8", errors="replace")
        assert "DEFAULT_SYSTEM_ROLES" in text
