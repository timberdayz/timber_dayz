from pathlib import Path


def test_verify_system_role_integrity_script_supports_repair_mode():
    text = Path("scripts/verify_system_role_integrity.py").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "--repair" in text
    assert "ensure_system_roles" in text
    assert "system_role_integrity=ok" in text
    assert "empty_permission_roles" in text
