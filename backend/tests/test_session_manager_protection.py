from __future__ import annotations

import json
import time
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


def test_automatic_save_does_not_override_manual_seeded_session_even_if_new_state_is_higher_quality(
    tmp_path: Path,
) -> None:
    manager = SessionManager(base_path=tmp_path / "sessions")
    platform = "tiktok"
    account_id = "acc-1"

    manual_state = {
        "cookies": [
            {"name": "ttwid", "domain": ".tiktokshopglobalselling.com", "path": "/"},
        ],
        "origins": [],
    }
    auto_high_state = {
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

    assert manager.save_session(
        platform,
        account_id,
        manual_state,
        metadata={"quality_source": "manual", "manual_seeded": True, "protected": True},
    )
    assert manager.save_session(platform, account_id, auto_high_state, metadata={"quality_source": "automatic"})

    payload = _read_session(manager.get_session_path(platform, account_id))
    assert payload["storage_state"] == manual_state
    assert payload["metadata"]["manual_seeded"] is True
    assert payload["metadata"]["protected"] is True
    assert payload["metadata"]["quality_source"] == "manual"


def test_resaving_session_refreshes_expiration_window(tmp_path: Path) -> None:
    manager = SessionManager(base_path=tmp_path / "sessions")
    platform = "shopee"
    account_id = "acc-1"
    state = {
        "cookies": [
            {"name": "csrftoken", "domain": "seller.example.com", "path": "/"},
            {"name": "session", "domain": "seller.example.com", "path": "/"},
            {"name": "token", "domain": "seller.example.com", "path": "/"},
        ],
        "origins": [{"origin": "https://seller.example.com", "localStorage": []}],
    }

    stale_time = 1_700_000_000.0
    fresh_time = stale_time + 60 * 86400

    original_time = time.time
    try:
        time.time = lambda: stale_time
        assert manager.save_session(platform, account_id, state, metadata={"quality_source": "manual"})

        time.time = lambda: fresh_time
        assert manager.save_session(platform, account_id, state, metadata={"quality_source": "manual"})

        session = manager.load_session(platform, account_id, max_age_days=30)
        assert session is not None
        payload = _read_session(manager.get_session_path(platform, account_id))
        assert payload["last_used_at"] >= fresh_time
        assert payload["metadata"]["saved_at"] >= fresh_time
    finally:
        time.time = original_time


def test_session_info_age_uses_latest_saved_time(tmp_path: Path) -> None:
    manager = SessionManager(base_path=tmp_path / "sessions")
    platform = "miaoshou"
    account_id = "acc-2"
    state = {
        "cookies": [
            {"name": "JSESSIONID", "domain": "erp.example.com", "path": "/"},
            {"name": "token", "domain": "erp.example.com", "path": "/"},
            {"name": "SESSION", "domain": "erp.example.com", "path": "/"},
        ],
        "origins": [{"origin": "https://erp.example.com", "localStorage": []}],
    }

    stale_time = 1_700_000_000.0
    fresh_time = stale_time + 45 * 86400
    inspect_time = fresh_time + 5 * 86400

    original_time = time.time
    try:
        time.time = lambda: stale_time
        assert manager.save_session(platform, account_id, state, metadata={"quality_source": "automatic"})

        time.time = lambda: fresh_time
        assert manager.save_session(platform, account_id, state, metadata={"quality_source": "automatic"})

        time.time = lambda: inspect_time
        info = manager.get_session_info(platform, account_id)
        assert info["exists"] is True
        assert info["age_days"] < 10
    finally:
        time.time = original_time


def test_freshness_uses_saved_at_only():
    """新鲜度必须以 saved_at 为准，last_used_at 不得参与。"""
    from modules.utils.sessions.session_manager import _session_freshness_timestamp

    session = {
        "metadata": {"saved_at": 1000.0},
        "last_used_at": 9_999_999.0,
        "created_at": 500.0,
    }
    assert _session_freshness_timestamp(session) == 1000.0


def test_freshness_falls_back_to_created_at():
    """saved_at 缺失时才回退 created_at（护栏：修复后仍须成立）。"""
    from modules.utils.sessions.session_manager import _session_freshness_timestamp

    session = {"metadata": {}, "created_at": 500.0}
    assert _session_freshness_timestamp(session) == 500.0


def test_protected_session_keeps_saved_at_when_overwritten(tmp_path):
    """protected 人工会话被自动 state 覆盖时，saved_at 不得被刷新（spec D7）。"""
    import json
    import time

    from modules.utils.sessions.session_manager import SessionManager

    manager = SessionManager(base_path=tmp_path / "data" / "sessions")
    manager.save_session(
        "shopee",
        "acct",
        {"cookies": [{"name": "sid", "value": "v"}], "origins": []},
        metadata={"manual_seeded": True, "protected": True},
    )
    path = manager.get_session_path("shopee", "acct")
    saved_at = json.loads(path.read_text(encoding="utf-8"))["metadata"]["saved_at"]

    time.sleep(0.05)
    # 自动来源、质量更低的 state 覆盖 -> 保留旧 state，且 saved_at 不得刷新
    manager.save_session("shopee", "acct", {"cookies": [], "origins": []})

    after = json.loads(path.read_text(encoding="utf-8"))
    assert after["metadata"]["saved_at"] == saved_at, "protected 会话的 saved_at 被自动回写刷新了"


def test_expired_session_is_rejected_even_when_recently_read(tmp_path):
    """saved_at 过期时，即使 last_used_at 是现在，也必须判为过期。"""
    import json
    import time

    from modules.utils.sessions.session_manager import SessionManager

    manager = SessionManager(base_path=tmp_path / "data" / "sessions")
    manager.save_session(
        "shopee",
        "acct",
        {"cookies": [{"name": "sid", "value": "v"}], "origins": []},
    )
    path = manager.get_session_path("shopee", "acct")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["metadata"]["saved_at"] = time.time() - 40 * 86400
    payload["last_used_at"] = time.time()
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    assert manager.load_session("shopee", "acct", max_age_days=30) is None
