from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from backend.routers.component_versions import get_test_status, post_test_resume
from backend.schemas.component_version import TestResumeRequest as ComponentTestResumeRequest
from backend.services.verification_service import VerificationService
from backend.services.verification_state_store import VerificationStateStore


def _make_test_dir(test_id: str) -> Path:
    project_root = Path(__file__).resolve().parents[2]
    test_dir = project_root / "temp" / "component_tests" / test_id
    test_dir.mkdir(parents=True, exist_ok=True)
    return test_dir


@pytest.mark.asyncio
async def test_get_test_status_exposes_shared_verification_fields():
    test_id = f"pytest-{uuid.uuid4().hex[:8]}"
    test_dir = _make_test_dir(test_id)
    progress_path = test_dir / "progress.json"
    progress_path.write_text(
        json.dumps(
            {
                "status": "verification_required",
                "progress": 10,
                "current_step": "Waiting for verification",
                "verification_type": "graphical_captcha",
                "verification_screenshot": "verification_screenshot.png",
                "verification_id": "verify-1",
                "verification_message": "login requires verification",
                "verification_expires_at": "2026-03-27T20:30:00+00:00",
                "verification_attempt_count": 1,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    resp = await get_test_status(version_id=1, test_id=test_id, db=None)

    assert resp["status"] == "verification_required"
    assert resp["verification_id"] == "verify-1"
    assert resp["verification_message"] == "login requires verification"
    assert resp["verification_expires_at"] == "2026-03-27T20:30:00+00:00"
    assert resp["verification_attempt_count"] == 1


@pytest.mark.asyncio
async def test_post_test_resume_marks_progress_as_verification_submitted():
    test_id = f"pytest-{uuid.uuid4().hex[:8]}"
    test_dir = _make_test_dir(test_id)
    progress_path = test_dir / "progress.json"
    store_path = test_dir / "verification_state.json"

    store = VerificationStateStore(storage_path=store_path)
    payload = VerificationService(store=store).raise_required(
        owner_type="component_test",
        owner_id="acc-1",
        verification_type="graphical_captcha",
        phase="login",
        current_url="https://example.com/login",
        screenshot_url="verification_screenshot.png",
        message="login requires verification",
        account_id="acc-1",
        store_name="Test Store",
    )

    progress_path.write_text(
        json.dumps(
            {
                "status": "verification_required",
                "verification_type": "graphical_captcha",
                "verification_screenshot": "verification_screenshot.png",
                "verification_id": payload["verification_id"],
                "verification_message": payload["message"],
                "verification_expires_at": payload["expires_at"],
                "verification_attempt_count": 0,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    body = await post_test_resume(
        version_id=1,
        test_id=test_id,
        body=ComponentTestResumeRequest(captcha_code="1234"),
    )

    assert body["success"] is True
    updated_progress = json.loads(progress_path.read_text(encoding="utf-8"))
    assert updated_progress["status"] == "verification_submitted"
    assert updated_progress["verification_attempt_count"] == 1
