from pathlib import Path

from modules.apps.collection_center.transition_gates import (
    GateStatus,
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
