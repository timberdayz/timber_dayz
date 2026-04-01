from __future__ import annotations

from pathlib import Path


def test_account_identity_helper_prefers_explicit_account_id() -> None:
    from modules.utils.account_identity import resolve_account_session_id

    result = resolve_account_session_id(
        {
            "account_id": "Tiktok 2店",
            "username": "user@example.com",
            "store_name": "TikTok Store",
        }
    )

    assert result == "Tiktok 2店"


def test_account_identity_helper_falls_back_to_username_then_store_name() -> None:
    from modules.utils.account_identity import resolve_account_session_id

    assert resolve_account_session_id({"username": "user@example.com", "store_name": "Store A"}) == "user@example.com"
    assert resolve_account_session_id({"store_name": "Store A"}) == "Store A"


def test_collection_center_files_use_account_identity_helper_for_session_namespace() -> None:
    app_source = Path("modules/apps/collection_center/app.py").read_text(encoding="utf-8")
    handlers_source = Path("modules/apps/collection_center/handlers.py").read_text(encoding="utf-8")

    assert "resolve_account_session_id" in app_source
    assert "resolve_account_session_id" in handlers_source
