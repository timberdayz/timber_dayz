import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.routers.component_recorder import (
    _build_recorder_status_payload,
    recorder_session,
    resume_recorder_verification,
    start_recording,
)
from backend.schemas.component_recorder import RecorderResumeRequest, RecorderStartRequest
from modules.core.db import PlatformAccount


def test_build_recorder_status_payload_exposes_gate_fields():
    payload = _build_recorder_status_payload(
        state="failed_before_recording",
        gate_stage="login_gate",
        ready_to_record=False,
        active=True,
        platform="miaoshou",
        component_type="export",
        steps_count=0,
        started_at=None,
        error_message="login not confirmed",
    )

    assert payload["state"] == "failed_before_recording"
    assert payload["gate_stage"] == "login_gate"
    assert payload["ready_to_record"] is False
    assert payload["error_message"] == "login not confirmed"


@pytest.mark.asyncio
async def test_resume_recorder_verification_writes_response_file(tmp_path):
    status_path = tmp_path / "status.json"
    response_path = tmp_path / "verification_response.json"
    status_path.write_text(
        '{"state":"login_verification_pending","gate_stage":"login_gate","ready_to_record":false}',
        encoding="utf-8",
    )

    recorder_session.status_file = str(status_path)
    recorder_session.response_file = str(response_path)

    body = await resume_recorder_verification(
        RecorderResumeRequest(captcha_code="1234")
    )

    assert body["success"] is True
    assert response_path.exists()
    assert '"captcha_code": "1234"' in response_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_start_recording_returns_starting_not_ready(monkeypatch):
    class _FakeThread:
        def __init__(self, target=None, args=None, daemon=None):
            self.target = target
            self.args = args or ()
            self.daemon = daemon

        def start(self):
            return None

    monkeypatch.setattr(
        "backend.routers.component_recorder.threading.Thread",
        _FakeThread,
    )

    account = PlatformAccount(
        account_id="acc-1",
        platform="miaoshou",
        store_name="Miaoshou Test Store",
        username="user@example.com",
        password_encrypted="encrypted-password",
        login_url="https://erp.91miaoshou.com/login",
        capabilities={},
        enabled=True,
    )

    result = MagicMock()
    result.scalar_one_or_none.return_value = account
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)

    body = await start_recording(
        request=RecorderStartRequest(
            platform="miaoshou",
            component_type="export",
            account_id="acc-1",
        ),
        db=db,
    )

    assert body["success"] is True
    assert body["data"]["state"] == "starting"
    assert body["data"]["gate_stage"] == "login_gate"
    assert body["data"]["ready_to_record"] is False
