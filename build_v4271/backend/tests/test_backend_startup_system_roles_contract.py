from pathlib import Path


def test_backend_startup_ensures_system_roles():
    text = Path("backend/main.py").read_text(encoding="utf-8")

    assert "ensure_system_roles" in text
    assert "系统角色补齐完成" in text
