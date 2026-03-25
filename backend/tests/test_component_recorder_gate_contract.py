import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.routers.component_recorder import (
    _build_recorder_status_payload,
    get_recording_steps,
    recorder_session,
    resume_recorder_verification,
    start_recording,
    validate_segment,
)
from backend.schemas.component_recorder import (
    RecorderResumeRequest,
    RecorderStartRequest,
    RecorderValidateSegmentRequest,
)
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


@pytest.mark.asyncio
async def test_get_recording_steps_reads_latest_steps_file_when_recording_active(tmp_path):
    steps_path = tmp_path / "steps.json"
    steps_path.write_text(
        '{"mode":"steps","steps":[{"id":1,"action":"click","selector":"button[title=\\"export\\"]"}]}',
        encoding="utf-8",
    )

    recorder_session.active = True
    recorder_session.steps = [{"id": 99, "action": "wait"}]
    recorder_session.steps_file = str(steps_path)

    body = await get_recording_steps()

    assert body["success"] is True
    assert body["data"]["steps"][0]["action"] == "click"
    assert body["data"]["steps"][0]["selector"] == 'button[title="export"]'


@pytest.mark.asyncio
async def test_validate_segment_returns_structured_validation_payload(monkeypatch):
    class _FakeValidator:
        async def validate(self, request, db=None):
            return {
                "success": True,
                "data": {
                    "passed": True,
                    "resolved_signal": "navigation_ready",
                    "step_start": request.step_start,
                    "step_end": request.step_end,
                    "validated_steps": len(request.steps),
                    "current_url": "https://example.com/orders",
                    "failure_step_id": None,
                    "failure_phase": None,
                    "error_message": None,
                    "screenshot_url": None,
                    "suggestions": [],
                },
            }

    monkeypatch.setattr(
        "backend.routers.component_recorder.RecorderSegmentValidator",
        _FakeValidator,
    )

    body = await validate_segment(
        RecorderValidateSegmentRequest(
            platform="miaoshou",
            component_type="export",
            account_id="acc-1",
            step_start=1,
            step_end=2,
            steps=[
                {"id": 1, "action": "click", "step_group": "navigation"},
                {"id": 2, "action": "click", "step_group": "navigation"},
            ],
        ),
        db=None,
    )

    assert body["success"] is True
    assert body["data"]["resolved_signal"] == "navigation_ready"
    assert body["data"]["validated_steps"] == 2
