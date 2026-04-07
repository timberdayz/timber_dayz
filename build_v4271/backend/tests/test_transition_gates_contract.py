from modules.apps.collection_center.transition_gates import (
    GateStatus,
    evaluate_date_picker_ready,
    evaluate_filters_ready,
    evaluate_navigation_ready,
)
from modules.apps.collection_center.executor_v2 import CollectionExecutorV2


def test_navigation_ready_requires_url_and_marker_signal():
    gate = evaluate_navigation_ready(
        current_url="https://example.com/orders",
        expected_url="orders",
        target_marker_visible=True,
    )

    assert gate.status is GateStatus.READY
    assert gate.stage == "navigation"
    assert gate.matched_signal == "url_and_marker"


def test_navigation_ready_fails_without_marker_even_if_url_matches():
    gate = evaluate_navigation_ready(
        current_url="https://example.com/orders",
        expected_url="orders",
        target_marker_visible=False,
    )

    assert gate.status is GateStatus.FAILED
    assert gate.reason == "target marker not visible"


def test_date_picker_ready_accepts_value_change_signal():
    gate = evaluate_date_picker_ready(value_applied=True, panel_closed=False)

    assert gate.status is GateStatus.READY
    assert gate.stage == "date_picker"
    assert gate.matched_signal == "value_applied"


def test_filters_ready_accepts_results_refresh_signal():
    gate = evaluate_filters_ready(results_refreshed=True, filter_value_applied=False)

    assert gate.status is GateStatus.READY
    assert gate.stage == "filters"
    assert gate.matched_signal == "results_refreshed"


def test_filters_ready_fails_when_no_observable_signal_present():
    gate = evaluate_filters_ready(results_refreshed=False, filter_value_applied=False)

    assert gate.status is GateStatus.FAILED
    assert gate.reason == "filter state not confirmed"


def test_executor_default_order_is_login_then_export_only():
    executor = CollectionExecutorV2()

    assert executor._get_default_execution_order() == [
        {"component": "login", "required": True, "index": 0},
        {"component": "export", "required": True, "index": 1},
    ]
