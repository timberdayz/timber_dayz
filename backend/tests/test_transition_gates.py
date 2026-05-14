from pathlib import Path

from modules.apps.collection_center.transition_gates import (
    GateStatus,
    LoginGateEvidence,
    evaluate_login_gate_evidence,
    evaluate_export_complete,
    evaluate_login_ready,
)


def test_login_ready_requires_logged_in_status_and_threshold():
    result = evaluate_login_ready(
        status="logged_in",
        confidence=0.69,
        current_url="https://erp.91miaoshou.com/welcome",
        matched_signal="url+element",
    )

    assert result.stage == "login_gate"
    assert result.status is GateStatus.FAILED


def test_login_ready_accepts_logged_in_status_at_threshold():
    result = evaluate_login_ready(
        status="logged_in",
        confidence=0.70,
        current_url="https://erp.91miaoshou.com/welcome",
        matched_signal="url+element",
    )

    assert result.status is GateStatus.READY


def test_login_gate_evidence_fails_when_login_form_visible_even_with_cookie_signal():
    result = evaluate_login_gate_evidence(
        platform="miaoshou",
        evidence=LoginGateEvidence(
            detector_status="logged_in",
            detector_confidence=0.8,
            auth_cookies_present=True,
            login_form_visible=True,
            logged_in_markers_present=False,
            current_url="https://erp.91miaoshou.com/login",
            matched_signal="password-input",
            detected_by="element",
        ),
    )

    assert result.status is GateStatus.FAILED
    assert result.reason == "login form visible"


def test_login_gate_evidence_accepts_logged_in_markers_without_threshold_score():
    result = evaluate_login_gate_evidence(
        platform="tiktok",
        evidence=LoginGateEvidence(
            detector_status="logged_in",
            detector_confidence=0.55,
            auth_cookies_present=False,
            login_form_visible=False,
            logged_in_markers_present=True,
            current_url="https://seller.tiktok.com/homepage",
            matched_signal="user-avatar",
            detected_by="element",
        ),
    )

    assert result.status is GateStatus.READY
    assert result.reason == "logged-in markers confirmed"


def test_login_gate_evidence_accepts_cookie_backed_shell_without_login_form():
    result = evaluate_login_gate_evidence(
        platform="miaoshou",
        evidence=LoginGateEvidence(
            detector_status="logged_in",
            detector_confidence=0.65,
            auth_cookies_present=True,
            login_form_visible=False,
            logged_in_markers_present=False,
            current_url="https://erp.91miaoshou.com/",
            matched_signal="JSESSIONID",
            detected_by="cookie",
        ),
    )

    assert result.status is GateStatus.READY
    assert result.reason == "cookie-backed session confirmed"


def test_tiktok_login_gate_rejects_cookie_only_root_entry():
    result = evaluate_login_gate_evidence(
        platform="tiktok",
        evidence=LoginGateEvidence(
            detector_status="logged_in",
            detector_confidence=0.85,
            auth_cookies_present=True,
            login_form_visible=False,
            logged_in_markers_present=False,
            current_url="https://seller.tiktokshopglobalselling.com/",
            matched_signal="sessionid",
            detected_by="cookie",
        ),
    )

    assert result.status is GateStatus.FAILED
    assert result.reason == "tiktok page readiness not confirmed"


def test_tiktok_login_gate_rejects_url_only_homepage_without_markers():
    result = evaluate_login_gate_evidence(
        platform="tiktok",
        evidence=LoginGateEvidence(
            detector_status="logged_in",
            detector_confidence=0.90,
            auth_cookies_present=False,
            login_form_visible=False,
            logged_in_markers_present=False,
            current_url="https://seller.tiktokshopglobalselling.com/homepage?shop_region=SG",
            matched_signal="/homepage",
            detected_by="url",
        ),
    )

    assert result.status is GateStatus.FAILED
    assert result.reason == "tiktok page readiness not confirmed"


def test_export_complete_requires_existing_non_empty_file(tmp_path: Path):
    target = tmp_path / "out.xlsx"
    target.write_bytes(b"ok")

    result = evaluate_export_complete(file_path=str(target))

    assert result.stage == "export"
    assert result.status is GateStatus.READY
    assert result.matched_signal == "file_exists"


def test_export_complete_fails_for_missing_file(tmp_path: Path):
    target = tmp_path / "missing.xlsx"

    result = evaluate_export_complete(file_path=str(target))

    assert result.status is GateStatus.FAILED


def test_export_complete_fails_for_empty_file(tmp_path: Path):
    target = tmp_path / "empty.xlsx"
    target.write_bytes(b"")

    result = evaluate_export_complete(file_path=str(target))

    assert result.status is GateStatus.FAILED


def test_export_complete_allows_known_no_data_success_without_file():
    result = evaluate_export_complete(
        file_path=None,
        component_name="tiktok/services_agent_export",
        success_message="no exportable agent service data for selected range",
    )

    assert result.stage == "export"
    assert result.status is GateStatus.READY
    assert result.matched_signal == "no_file_success"
