from __future__ import annotations

import json
from pathlib import Path

from modules.utils.sessions.session_manager import SessionManager


def _read_session(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_manual_seeded_session_is_not_downgraded_by_lower_quality_auto_save(tmp_path: Path) -> None:
    manager = SessionManager(base_path=tmp_path / "sessions")
    platform = "miaoshou"
    account_id = "acc-1"

    manual_state = {
        "cookies": [
            {"name": "JSESSIONID", "domain": "erp.example.com", "path": "/"},
            {"name": "token", "domain": "erp.example.com", "path": "/"},
            {"name": "SESSION", "domain": "erp.example.com", "path": "/"},
            {"name": "extra", "domain": "erp.example.com", "path": "/"},
            {"name": "extra2", "domain": "erp.example.com", "path": "/"},
            {"name": "extra3", "domain": "erp.example.com", "path": "/"},
            {"name": "extra4", "domain": "erp.example.com", "path": "/"},
            {"name": "extra5", "domain": "erp.example.com", "path": "/"},
        ],
        "origins": [{"origin": "https://erp.example.com", "localStorage": [{"name": "a", "value": "1"}]}],
    }
    auto_state = {
        "cookies": [
            {"name": "JSESSIONID", "domain": "erp.example.com", "path": "/"},
        ],
        "origins": [],
    }

    assert manager.save_session(
        platform,
        account_id,
        manual_state,
        metadata={"quality_source": "manual", "manual_seeded": True, "protected": True},
    )
    assert manager.save_session(platform, account_id, auto_state, metadata={"quality_source": "automatic"})

    payload = _read_session(manager.get_session_path(platform, account_id))
    assert payload["storage_state"] == manual_state
    assert payload["metadata"]["protected"] is True
    assert payload["metadata"]["manual_seeded"] is True
    assert payload["metadata"]["quality_source"] == "manual"


def test_automatic_save_can_upgrade_existing_session_quality(tmp_path: Path) -> None:
    manager = SessionManager(base_path=tmp_path / "sessions")
    platform = "tiktok"
    account_id = "acc-1"

    low_state = {
        "cookies": [
            {"name": "ttwid", "domain": ".tiktokshopglobalselling.com", "path": "/"},
            {"name": "i18next", "domain": "seller.tiktokshopglobalselling.com", "path": "/"},
        ],
        "origins": [],
    }
    high_state = {
        "cookies": [
            {"name": "sessionid", "domain": ".tiktokshopglobalselling.com", "path": "/"},
            {"name": "sid_tt", "domain": ".tiktokshopglobalselling.com", "path": "/"},
            {"name": "passport_csrf_token", "domain": ".tiktokshopglobalselling.com", "path": "/"},
            {"name": "user_oec_info", "domain": "seller.tiktokshopglobalselling.com", "path": "/"},
            {"name": "global_seller_id_unified_seller_env", "domain": ".tiktokshopglobalselling.com", "path": "/"},
            {"name": "app_id_unified_seller_env", "domain": ".tiktokshopglobalselling.com", "path": "/"},
            {"name": "oec_seller_id_unified_seller_env", "domain": ".tiktokshopglobalselling.com", "path": "/"},
            {"name": "ttwid", "domain": ".tiktokshopglobalselling.com", "path": "/"},
            {"name": "i18next", "domain": "seller.tiktokshopglobalselling.com", "path": "/"},
            {"name": "ATLAS_LANG", "domain": "seller.tiktokshopglobalselling.com", "path": "/"},
            {"name": "msToken", "domain": "seller.tiktokshopglobalselling.com", "path": "/"},
            {"name": "passport_auth_status", "domain": ".tiktokshopglobalselling.com", "path": "/"},
        ],
        "origins": [{"origin": "https://seller.tiktokshopglobalselling.com", "localStorage": [{"name": "a", "value": "1"}]}],
    }

    assert manager.save_session(platform, account_id, low_state, metadata={"quality_source": "automatic"})
    assert manager.save_session(platform, account_id, high_state, metadata={"quality_source": "automatic"})

    payload = _read_session(manager.get_session_path(platform, account_id))
    cookie_names = {item["name"] for item in payload["storage_state"]["cookies"]}
    assert "sessionid" in cookie_names
    assert payload["metadata"]["quality_gate_passed"] is True
