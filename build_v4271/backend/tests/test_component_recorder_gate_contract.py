import pytest
from unittest.mock import AsyncMock, MagicMock
from types import SimpleNamespace
import backend.routers.component_recorder as component_recorder_router

from backend.routers.component_recorder import (
    _build_recorder_status_payload,
    _launch_inspector_recorder_subprocess,
    get_recording_steps,
    get_recorder_segment_artifact,
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


def test_build_recorder_status_payload_exposes_shared_verification_fields():
    payload = _build_recorder_status_payload(
        state="login_verification_pending",
        gate_stage="login_gate",
        ready_to_record=False,
        active=True,
        platform="miaoshou",
        component_type="export",
        steps_count=0,
        started_at=None,
        verification_type="graphical_captcha",
        verification_screenshot="verification_screenshot.png",
        verification_id="verify-1",
        verification_message="login requires verification",
        verification_expires_at="2026-03-26T21:30:00+00:00",
        verification_attempt_count=1,
    )

    assert payload["verification_id"] == "verify-1"
    assert payload["verification_message"] == "login requires verification"
    assert payload["verification_expires_at"] == "2026-03-26T21:30:00+00:00"
    assert payload["verification_attempt_count"] == 1


@pytest.mark.asyncio
async def test_resume_recorder_verification_writes_response_file(tmp_path):
    status_path = tmp_path / "status.json"
    response_path = tmp_path / "verification_response.json"
    status_path.write_text(
        '{"state":"login_verification_pending","gate_stage":"login_gate","ready_to_record":false,"verification_id":"verify-1","verification_type":"graphical_captcha","verification_message":"login requires verification","verification_expires_at":"2026-03-26T21:30:00+00:00","verification_attempt_count":0}',
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
    updated_status = status_path.read_text(encoding="utf-8")
    assert '"state": "verification_submitted"' in updated_status


@pytest.mark.asyncio
async def test_resume_recorder_verification_uses_shared_verification_request(tmp_path, monkeypatch):
    status_path = tmp_path / "status.json"
    response_path = tmp_path / "verification_response.json"
    status_path.write_text(
        '{"state":"login_verification_pending","gate_stage":"login_gate","ready_to_record":false}',
        encoding="utf-8",
    )

    recorder_session.status_file = str(status_path)
    recorder_session.response_file = str(response_path)

    captured = {}

    class _FakeVerificationService:
        def __init__(self, store=None):
            self.store = store

        def mark_submitted(self, *, verification_id: str):
            captured["verification_id"] = verification_id
            return {"state": "verification_submitted"}

    class _FakeVerificationStore:
        def __init__(self, storage_path=None):
            captured["storage_path"] = storage_path

        def save(self, payload):
            captured["saved_payload"] = payload
            return payload

    monkeypatch.setattr(
        component_recorder_router,
        "VerificationService",
        _FakeVerificationService,
        raising=False,
    )
    monkeypatch.setattr(
        component_recorder_router,
        "VerificationStateStore",
        _FakeVerificationStore,
        raising=False,
    )
    monkeypatch.setattr(
        component_recorder_router,
        "_read_recorder_runtime_status",
        lambda path: {
            "state": "login_verification_pending",
            "verification_id": "verify-1",
        },
    )

    body = await resume_recorder_verification(
        RecorderResumeRequest(captcha_code="1234")
    )

    assert body["success"] is True
    assert captured["verification_id"] == "verify-1"
    assert str(captured["storage_path"]).endswith("verification_state.json")


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

    account = SimpleNamespace(
        account_id="acc-1",
        platform="miaoshou",
        store_name="Miaoshou Test Store",
        username="user@example.com",
        password_encrypted="encrypted-password",
        login_url="https://erp.91miaoshou.com/login",
        capabilities={},
        enabled=True,
    )

    db = MagicMock()
    db.execute = AsyncMock()

    class _FakeShopLoader:
        async def load_shop_account_async(self, account_id, db_session):
            assert account_id == "acc-1"
            return {
                "main_account": {
                    "main_account_id": "main-1",
                    "platform": "miaoshou",
                    "username": "user@example.com",
                    "login_url": "https://erp.91miaoshou.com/login",
                },
                "shop_context": {
                    "shop_account_id": "acc-1",
                    "platform": "miaoshou",
                    "store_name": "Miaoshou Test Store",
                    "enabled": True,
                    "shop_region": "",
                    "platform_shop_id": None,
                },
                "capabilities": {},
                "compat_account": {
                    "account_id": "acc-1",
                    "email": "",
                    "phone": "",
                    "region": "CN",
                    "currency": "CNY",
                },
            }

    monkeypatch.setattr(
        "backend.services.shop_account_loader_service.get_shop_account_loader_service",
        lambda: _FakeShopLoader(),
    )

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


@pytest.mark.asyncio
async def test_get_recorder_segment_artifact_serves_validation_screenshot(tmp_path, monkeypatch):
    artifact_dir = tmp_path / "segment_validation"
    artifact_dir.mkdir(parents=True)
    artifact_path = artifact_dir / "failure.png"
    artifact_path.write_bytes(b"fake-png")
    monkeypatch.setattr(
        component_recorder_router,
        "SEGMENT_VALIDATION_ARTIFACT_DIR",
        artifact_dir,
        raising=False,
    )

    response = await get_recorder_segment_artifact(name="failure.png")

    assert str(response.path).endswith("failure.png")


def test_launch_inspector_recorder_subprocess_uses_prepared_account_info(monkeypatch):
    captured = {}

    class _FakeProcess:
        pid = 4321

    def _fake_prepare_account_info(account):
        return {
            "account_id": account.account_id,
            "platform": account.platform,
            "username": account.username,
            "password": "plain-password",
            "login_url": "https://erp.91miaoshou.com",
            "store_name": account.store_name,
        }

    def _fake_json_dump(data, fp, ensure_ascii=False, indent=2):
        captured["config"] = data
        fp.write("{}")

    class _FakeComponentTestService:
        @staticmethod
        def prepare_account_info(account):
            return _fake_prepare_account_info(account)

    monkeypatch.setattr(
        component_recorder_router,
        "ComponentTestService",
        _FakeComponentTestService,
        raising=False,
    )
    monkeypatch.setattr(
        "backend.routers.component_recorder.subprocess.Popen",
        lambda *args, **kwargs: _FakeProcess(),
    )
    monkeypatch.setattr(
        "backend.routers.component_recorder.json.dump",
        _fake_json_dump,
    )

    account = SimpleNamespace(
        account_id="acc-1",
        platform="miaoshou",
        store_name="Miaoshou Test Store",
        username="user@example.com",
        password_encrypted="encrypted-password",
        login_url="https://erp.91miaoshou.com/login",
        capabilities={},
        enabled=True,
    )

    _launch_inspector_recorder_subprocess(account, "miaoshou", "export")

    assert captured["config"]["account_info"]["password"] == "plain-password"
    assert (
        captured["config"]["account_info"]["login_url"]
        == "https://erp.91miaoshou.com"
    )


def test_component_recorder_router_uses_shop_account_loader_without_platform_account_fallback():
    from pathlib import Path

    text = (
        Path(__file__).resolve().parents[2]
        / "backend/routers/component_recorder.py"
    ).read_text(encoding="utf-8")

    assert "get_shop_account_loader_service" in text
    assert "select(PlatformAccount)" not in text
