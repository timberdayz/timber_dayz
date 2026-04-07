from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from backend.schemas.verification import VerificationResumeRequest
from backend.services.verification_service import VerificationService
from backend.services.verification_state_store import VerificationStateStore


def test_verification_payload_contains_owner_and_expiry():
    store = VerificationStateStore()
    service = VerificationService(store=store)

    payload = service.raise_required(
        owner_type="recorder",
        owner_id="session-1",
        verification_type="graphical_captcha",
        phase="login",
        current_url="https://erp.91miaoshou.com/login",
        screenshot_url="/api/collection/recorder/verification-screenshot",
        message="login requires captcha",
        account_id="miaoshou_real_001",
        store_name="Miaoshou Test Store",
    )

    assert payload["state"] == "verification_required"
    assert payload["owner_type"] == "recorder"
    assert payload["owner_id"] == "session-1"
    assert payload["verification_type"] == "graphical_captcha"
    assert payload["phase"] == "login"
    assert payload["current_url"] == "https://erp.91miaoshou.com/login"
    assert payload["screenshot_url"] == "/api/collection/recorder/verification-screenshot"
    assert payload["account_id"] == "miaoshou_real_001"
    assert payload["store_name"] == "Miaoshou Test Store"
    assert payload["verification_id"]
    assert payload["created_at"]
    assert payload["expires_at"]


def test_verification_state_store_advances_through_resume_flow():
    store = VerificationStateStore()
    service = VerificationService(store=store)

    payload = service.raise_required(
        owner_type="component_test",
        owner_id="test-1",
        verification_type="otp",
        phase="login",
        current_url="https://example.com/login",
        screenshot_url=None,
        message="otp required",
    )

    verification_id = payload["verification_id"]
    submitted = service.mark_submitted(verification_id=verification_id)
    retrying = service.mark_retrying(verification_id=verification_id)
    resolved = service.mark_resolved(verification_id=verification_id)

    assert submitted["state"] == "verification_submitted"
    assert retrying["state"] == "verification_retrying"
    assert resolved["state"] == "verification_resolved"


def test_verification_state_store_persists_payload_across_store_instances(tmp_path):
    storage_path = tmp_path / "verification-store.json"

    first_store = VerificationStateStore(storage_path=storage_path)
    first_service = VerificationService(store=first_store)
    payload = first_service.raise_required(
        owner_type="recorder",
        owner_id="session-1",
        verification_type="graphical_captcha",
        phase="login",
        current_url="https://example.com/login",
        screenshot_url="/api/verification.png",
        message="captcha required",
    )

    second_store = VerificationStateStore(storage_path=storage_path)
    second_service = VerificationService(store=second_store)
    submitted = second_service.mark_submitted(
        verification_id=payload["verification_id"]
    )

    assert submitted["state"] == "verification_submitted"
    assert submitted["owner_id"] == "session-1"
    assert submitted["message"] == "captcha required"
    assert storage_path.exists()


def test_verification_resume_request_requires_exactly_one_value():
    with pytest.raises(ValidationError):
        VerificationResumeRequest(captcha_code="1234", otp="567890")

    with pytest.raises(ValidationError):
        VerificationResumeRequest()

    body = VerificationResumeRequest(captcha_code="1234")

    assert body.captcha_code == "1234"
    assert body.otp is None


def test_verification_resume_request_allows_manual_completed_without_code():
    body = VerificationResumeRequest(manual_completed=True)

    assert body.manual_completed is True
    assert body.captcha_code is None
    assert body.otp is None


def test_verification_resume_request_rejects_manual_completed_when_code_present():
    with pytest.raises(ValidationError):
        VerificationResumeRequest(captcha_code="1234", manual_completed=True)


def test_verification_payload_maps_manual_intervention_to_manual_continue():
    store = VerificationStateStore()
    service = VerificationService(store=store)

    payload = service.raise_required(
        owner_type="component_test",
        owner_id="test-1",
        verification_type="manual_intervention",
        phase="login",
        current_url="https://seller.shopee.cn/portal/merchant/setting",
        screenshot_url="/api/verification.png",
        message="special case requires manual handling",
    )

    assert payload["verification_type"] == "manual_intervention"
    assert payload["verification_input_mode"] == "manual_continue"
