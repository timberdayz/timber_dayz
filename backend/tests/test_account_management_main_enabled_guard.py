from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_shop_enabled_toggle_does_not_write_main_account_enabled_state():
    text = (PROJECT_ROOT / "frontend/src/stores/accounts.js").read_text(encoding="utf-8")

    assert "mainPayload.enabled = data.enabled" not in text
