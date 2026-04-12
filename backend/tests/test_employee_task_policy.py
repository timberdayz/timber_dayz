import pytest


def test_execution_task_policy_allows_expected_actions():
    from backend.services.employee_task_policy import get_task_type_policy

    policy = get_task_type_policy("monthly_cost_entry")

    assert policy["target_route"] == "/expense-management"
    assert policy["required_permission"] == "expense-management"
    assert "submit_result" in policy["owner_actions"]
    assert "append_comment" in policy["collaborator_actions"]
    assert "submit_result" not in policy["collaborator_actions"]


def test_confirmation_task_policy_maps_public_page_permission():
    from backend.services.employee_task_policy import get_task_type_policy

    policy = get_task_type_policy("performance_confirmation")

    assert policy["target_route"] == "/hr-performance-display"
    assert policy["required_permission"] == "performance:read"


def test_unknown_task_type_policy_raises():
    from backend.services.employee_task_policy import get_task_type_policy

    with pytest.raises(ValueError, match="Unknown task type"):
        get_task_type_policy("unknown_task_type")


def test_initiator_close_only_allowed_for_pending_tasks():
    from backend.services.employee_task_policy import can_user_perform_task_action

    assert can_user_perform_task_action("execution", "pending", "initiator", "close_unstarted_task") is True
    assert can_user_perform_task_action("execution", "in_progress", "initiator", "close_unstarted_task") is False


def test_admin_has_override_actions():
    from backend.services.employee_task_policy import can_user_perform_task_action

    assert can_user_perform_task_action("execution", "pending", "admin", "reassign_task") is True
    assert can_user_perform_task_action("execution", "in_progress", "admin", "takeover_task") is True
    assert can_user_perform_task_action("execution", "pending_confirmation", "admin", "force_close_task") is True


def test_validate_task_target_permission_for_monthly_cost_entry():
    from backend.services.employee_task_policy import validate_task_target_permission

    validate_task_target_permission("monthly_cost_entry", {"expense-management", "my-tasks"})

    with pytest.raises(ValueError, match="permission"):
        validate_task_target_permission("monthly_cost_entry", {"my-tasks"})


def test_validate_task_target_permission_for_performance_confirmation():
    from backend.services.employee_task_policy import validate_task_target_permission

    validate_task_target_permission("performance_confirmation", {"performance:read", "my-tasks"})

    with pytest.raises(ValueError, match="permission"):
        validate_task_target_permission("performance_confirmation", {"expense-management"})
