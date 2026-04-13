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
