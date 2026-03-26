from backend.schemas.component_recorder import (
    RecorderValidateSegmentRequest,
)
from backend.services.recorder_segment_validator import (
    RecorderSegmentValidator,
)


def test_validate_segment_request_requires_contiguous_range_bounds():
    request = RecorderValidateSegmentRequest(
        platform="miaoshou",
        component_type="export",
        account_id="acc-1",
        expected_signal="auto",
        step_start=3,
        step_end=4,
        steps=[
            {"id": 3, "action": "click", "step_group": "navigation"},
            {"id": 4, "action": "click", "step_group": "navigation"},
        ],
    )

    assert request.step_start == 3
    assert request.step_end == 4
    assert len(request.steps) == 2


def test_resolve_expected_signal_prefers_step_group_before_component_type():
    validator = RecorderSegmentValidator()

    resolved = validator.resolve_expected_signal(
        component_type="export",
        expected_signal="auto",
        steps=[
            {"id": 3, "action": "click", "step_group": "navigation"},
            {"id": 4, "action": "click", "step_group": "navigation"},
        ],
    )

    assert resolved == "navigation_ready"


def test_validate_selected_range_rejects_non_contiguous_selection():
    validator = RecorderSegmentValidator()

    result = validator.validate_selected_range(
        step_start=3,
        step_end=5,
        steps=[
            {"id": 3, "action": "click"},
            {"id": 5, "action": "click"},
        ],
    )

    assert result["success"] is False
    assert result["error_message"] == "selected steps must be contiguous"


def test_resolve_step_selector_prefers_explicit_selector_then_css_candidate():
    validator = RecorderSegmentValidator()

    explicit = validator.resolve_step_selector(
        {
            "selector": "text=导出",
            "selectors": [{"type": "css", "value": ".ignored"}],
        }
    )
    derived = validator.resolve_step_selector(
        {
            "selectors": [
                {"type": "role", "value": "role=button[name='导出']"},
                {"type": "css", "value": "button.export"},
            ]
        }
    )

    assert explicit == "text=导出"
    assert derived == "button.export"


def test_build_gate_failure_result_uses_export_gate_reason():
    validator = RecorderSegmentValidator()

    result = validator.build_gate_failure_result(
        resolved_signal="export_complete",
        step_start=5,
        step_end=7,
        validated_steps=3,
        current_url="https://example.com/export",
        failure_step_id=7,
        failure_phase="export",
        error_message="download file missing",
    )

    assert result["success"] is True
    assert result["data"]["passed"] is False
    assert result["data"]["resolved_signal"] == "export_complete"
    assert result["data"]["error_message"] == "download file missing"


def test_build_artifact_url_exposes_recorder_segment_artifact_route():
    validator = RecorderSegmentValidator()

    url = validator.build_artifact_url("failure.png")

    assert url == "/api/collection/recorder/segment-artifact?name=failure.png"
