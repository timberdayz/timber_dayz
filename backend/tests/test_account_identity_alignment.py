from __future__ import annotations


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
