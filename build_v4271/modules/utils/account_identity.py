from __future__ import annotations

from typing import Any


def resolve_account_session_id(account: dict[str, Any] | None, fallback: str = "account") -> str:
    candidate = (
        (account or {}).get("account_id")
        or (account or {}).get("username")
        or (account or {}).get("store_name")
        or (account or {}).get("name")
        or (account or {}).get("label")
        or fallback
    )
    text = str(candidate or "").strip()
    return text or fallback


def resolve_account_display_label(account: dict[str, Any] | None, fallback: str = "unknown") -> str:
    candidate = (
        (account or {}).get("label")
        or (account or {}).get("store_name")
        or (account or {}).get("display_name")
        or (account or {}).get("menu_display_name")
        or (account or {}).get("username")
        or (account or {}).get("account_id")
        or fallback
    )
    text = str(candidate or "").strip()
    return text or fallback


def describe_account_identity(platform: str, account: dict[str, Any] | None) -> dict[str, str]:
    return {
        "platform": str(platform or "").strip().lower(),
        "session_id": resolve_account_session_id(account),
        "display_label": resolve_account_display_label(account),
    }
