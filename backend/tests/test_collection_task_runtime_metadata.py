from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from backend.routers.collection_tasks import (
    _build_task_response_payload_with_runtime_metadata,
    _extract_runtime_metadata_from_logs,
)
from backend.schemas.collection import TaskResponse

# [Task 8] profile 是登录态的唯一载体之后，这 5 个「质量分 / 人工播种 / 保护」
# 字段整体失去意义，诊断与任务响应里都不得再出现。
LEGACY_SESSION_DIAGNOSTIC_FIELDS = (
    "session_quality_score",
    "session_quality_gate_passed",
    "session_quality_source",
    "session_manual_seeded",
    "session_protected",
)

# [Task 8] 旧字段名同样不得复活（改名后的新名字见断言）。
LEGACY_PROFILE_FIELD_NAMES = (
    "persistent_profile_path",
    "profile_contains_state",
)


def _runtime_details(**overrides) -> dict:
    details = {
        "step_id": "login_gate_probe",
        "actual_execution_mode": "headless",
        "runtime_session_mode": "persistent_profile",
        "login_gate_ready": True,
        "login_gate_reason": "login confirmed",
        "login_gate_url": "https://seller.tiktok.com/homepage",
    }
    details.update(overrides)
    return details


def _fake_task() -> SimpleNamespace:
    now = datetime(2026, 11, 3, 10, 0, 0)
    return SimpleNamespace(
        id=1,
        task_id="task-1",
        platform="tiktok",
        account="acc-1",
        status="completed",
        progress=100,
        current_step=None,
        files_collected=1,
        trigger_type="manual",
        config_id=None,
        data_domains=None,
        sub_domains=None,
        granularity="day",
        date_range=None,
        time_selection=None,
        total_domains=1,
        completed_domains=None,
        failed_domains=None,
        current_domain=None,
        debug_mode=False,
        error_message=None,
        duration_seconds=1,
        created_at=now,
        updated_at=now,
        started_at=now,
        completed_at=now,
        verification_type=None,
        verification_screenshot=None,
    )


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
    """[Task 8] 诊断字段收敛为 profile 载体语义：路径 / 是否复用 / 来源 / 代理。"""
    logs = [
        SimpleNamespace(
            details=_runtime_details(
                session_owner_id="main-1",
                shop_account_id="shop-1",
                session_profile_path="profiles/tiktok/main-1",
                session_reused=True,
                runtime_strategy_reason="persistent_profile_ready",
                session_source="profile",
                session_proxy="http://proxy.example.com:8080",
                user_agent="Mozilla/5.0 Chrome/136.0.0.0",
                runtime_locale="en-SG",
                runtime_timezone="Asia/Singapore",
                runtime_accept_language="en-SG,en;q=0.9",
                probe_urls=[
                    "https://seller.tiktok.com/homepage",
                    "https://seller.tiktok.com/account/login",
                ],
            )
        )
    ]

    metadata = _extract_runtime_metadata_from_logs(logs)

    assert metadata["session_owner_id"] == "main-1"
    assert metadata["shop_account_id"] == "shop-1"
    assert metadata["session_profile_path"] == "profiles/tiktok/main-1"
    assert metadata["session_reused"] is True
    assert metadata["runtime_strategy_reason"] == "persistent_profile_ready"
    assert metadata["session_source"] == "profile"
    assert metadata["session_proxy"] == "http://proxy.example.com:8080"
    assert metadata["user_agent"] == "Mozilla/5.0 Chrome/136.0.0.0"
    assert metadata["runtime_locale"] == "en-SG"
    assert metadata["runtime_timezone"] == "Asia/Singapore"
    assert metadata["runtime_accept_language"] == "en-SG,en;q=0.9"
    assert metadata["probe_urls"] == [
        "https://seller.tiktok.com/homepage",
        "https://seller.tiktok.com/account/login",
    ]


def test_extract_runtime_metadata_from_logs_drops_legacy_session_fields() -> None:
    """[Task 8] 旧诊断字段不得再出现在任务响应里（反向断言比存在断言抗回归）。"""
    logs = [
        SimpleNamespace(
            details=_runtime_details(
                session_profile_path="profiles/tiktok/main-1",
                session_reused=True,
                session_source="profile",
                persistent_profile_path="profiles/tiktok/main-1",
                profile_contains_state=True,
                session_quality_score=33,
                session_quality_gate_passed=True,
                session_quality_source="manual",
                session_manual_seeded=True,
                session_protected=True,
            )
        )
    ]

    metadata = _extract_runtime_metadata_from_logs(logs)

    for legacy_field in LEGACY_SESSION_DIAGNOSTIC_FIELDS + LEGACY_PROFILE_FIELD_NAMES:
        assert legacy_field not in metadata, f"任务响应里仍存在旧字段 {legacy_field}"


def test_task_payload_promotes_profile_diagnostics_to_top_level() -> None:
    """[Task 8] 新字段必须提升到**顶层** —— 前端读的是顶层，不是 runtime_metadata 嵌套。"""
    metadata = {
        "actual_execution_mode": "headless",
        "runtime_session_mode": "persistent_profile",
        "login_gate_ready": True,
        "login_gate_reason": "login confirmed",
        "login_gate_url": "https://seller.tiktok.com/homepage",
        "session_owner_id": "main-1",
        "shop_account_id": "shop-1",
        "session_profile_path": "profiles/tiktok/main-1",
        "session_reused": True,
        "runtime_strategy_reason": "persistent_profile_ready",
        "session_source": "profile",
        "session_proxy": "http://proxy.example.com:8080",
    }

    payload = _build_task_response_payload_with_runtime_metadata(
        _fake_task(),
        runtime_metadata=metadata,
    )

    assert payload["session_profile_path"] == "profiles/tiktok/main-1"
    assert payload["session_reused"] is True
    assert payload["session_source"] == "profile"
    assert payload["session_proxy"] == "http://proxy.example.com:8080"

    for legacy_field in LEGACY_SESSION_DIAGNOSTIC_FIELDS + LEGACY_PROFILE_FIELD_NAMES:
        assert legacy_field not in payload, f"任务响应顶层仍存在旧字段 {legacy_field}"


def test_task_response_schema_keeps_profile_diagnostics() -> None:
    """[Task 8] ``TaskResponse`` 必须声明新字段，否则 ``response_model`` 会把它们丢掉。"""
    metadata = {
        "actual_execution_mode": "headless",
        "runtime_session_mode": "persistent_profile",
        "login_gate_ready": True,
        "login_gate_reason": "login confirmed",
        "login_gate_url": "https://seller.tiktok.com/homepage",
        "session_profile_path": "profiles/tiktok/main-1",
        "session_reused": True,
        "session_source": "profile",
        "session_proxy": "http://proxy.example.com:8080",
    }

    payload = _build_task_response_payload_with_runtime_metadata(
        _fake_task(),
        runtime_metadata=metadata,
    )
    response = TaskResponse.model_validate(payload)

    assert response.session_profile_path == "profiles/tiktok/main-1"
    assert response.session_reused is True
    assert response.session_source == "profile"
    assert response.session_proxy == "http://proxy.example.com:8080"


def test_task_payload_keeps_session_proxy_none_without_proxy() -> None:
    """[Task 8] 没有代理时 ``session_proxy`` 是 None（前端显示 "-"）。"""
    metadata = {
        "actual_execution_mode": "headless",
        "runtime_session_mode": "persistent_profile",
        "login_gate_ready": True,
        "login_gate_reason": "login confirmed",
        "login_gate_url": "https://seller.tiktok.com/homepage",
        "session_profile_path": "profiles/tiktok/main-1",
        "session_reused": False,
        "session_source": "profile",
        "session_proxy": None,
    }

    payload = _build_task_response_payload_with_runtime_metadata(
        _fake_task(),
        runtime_metadata=metadata,
    )

    assert payload["session_proxy"] is None
    assert payload["session_reused"] is False
