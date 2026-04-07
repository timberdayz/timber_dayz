from pathlib import Path


def test_backend_startup_checks_legacy_shop_session_artifacts():
    text = Path("backend/main.py").read_text(encoding="utf-8")

    assert "collect_legacy_shop_artifacts_for_active_shops" in text
    assert "legacy shop artifact" in text
