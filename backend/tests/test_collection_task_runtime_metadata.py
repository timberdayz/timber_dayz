from __future__ import annotations

from types import SimpleNamespace

from backend.routers.collection_tasks import _extract_runtime_metadata_from_logs


def test_extract_runtime_metadata_from_logs_uses_latest_runtime_log() -> None:
    logs = [
        SimpleNamespace(
            details={
                "step_id": "login_gate_probe",
                "actual_execution_mode": "headed",
                "runtime_session_mode": "persistent_profile",
                "login_gate_ready": True,
                "login_gate_reason": "login confirmed",
                "login_gate_url": "https://seller.tiktok.com/homepage",
            }
        ),
        SimpleNamespace(
            details={
                "step_id": "login_gate_probe",
                "actual_execution_mode": "headless",
                "runtime_session_mode": "persistent_profile",
                "login_gate_ready": False,
                "login_gate_reason": "login not confirmed",
                "login_gate_url": "https://seller.tiktok.com/account/login",
            }
        ),
    ]

    metadata = _extract_runtime_metadata_from_logs(logs)

    assert metadata["actual_execution_mode"] == "headed"
    assert metadata["runtime_session_mode"] == "persistent_profile"
    assert metadata["login_gate_ready"] is True
    assert metadata["login_gate_reason"] == "login confirmed"
    assert metadata["login_gate_url"] == "https://seller.tiktok.com/homepage"


def test_extract_runtime_metadata_from_logs_preserves_session_diagnostics() -> None:
    logs = [
        SimpleNamespace(
            details={
                "step_id": "login_gate_probe",
                "actual_execution_mode": "headless",
                "runtime_session_mode": "persistent_profile",
                "login_gate_ready": True,
                "login_gate_reason": "login confirmed",
                "login_gate_url": "https://seller.tiktok.com/homepage",
                "session_owner_id": "main-1",
                "shop_account_id": "shop-1",
                "persistent_profile_path": "profiles/tiktok/main-1",
                "profile_contains_state": True,
                "runtime_strategy_reason": "storage_state_available",
                "session_source": "storage_state",
                "user_agent": "Mozilla/5.0 Chrome/136.0.0.0",
                "runtime_locale": "en-SG",
                "runtime_timezone": "Asia/Singapore",
                "runtime_accept_language": "en-SG,en;q=0.9",
                "session_quality_score": 33,
                "session_quality_gate_passed": True,
                "session_quality_source": "manual",
                "session_manual_seeded": True,
                "session_protected": True,
                "probe_urls": [
                    "https://seller.tiktok.com/homepage",
                    "https://seller.tiktok.com/account/login",
                ],
            }
        )
    ]

    metadata = _extract_runtime_metadata_from_logs(logs)

    assert metadata["session_owner_id"] == "main-1"
    assert metadata["shop_account_id"] == "shop-1"
    assert metadata["persistent_profile_path"] == "profiles/tiktok/main-1"
    assert metadata["profile_contains_state"] is True
    assert metadata["runtime_strategy_reason"] == "storage_state_available"
    assert metadata["session_source"] == "storage_state"
    assert metadata["user_agent"] == "Mozilla/5.0 Chrome/136.0.0.0"
    assert metadata["runtime_locale"] == "en-SG"
    assert metadata["runtime_timezone"] == "Asia/Singapore"
    assert metadata["runtime_accept_language"] == "en-SG,en;q=0.9"
    assert metadata["session_quality_score"] == 33
    assert metadata["session_quality_gate_passed"] is True
    assert metadata["session_quality_source"] == "manual"
    assert metadata["session_manual_seeded"] is True
    assert metadata["session_protected"] is True
    assert metadata["probe_urls"] == [
        "https://seller.tiktok.com/homepage",
        "https://seller.tiktok.com/account/login",
    ]
