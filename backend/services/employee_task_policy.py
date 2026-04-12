from __future__ import annotations


TASK_TYPE_POLICIES = {
    "monthly_cost_entry": {
        "task_category": "execution",
        "target_route": "/expense-management",
        "required_permission": "expense-management",
        "allowed_roles": {"admin", "manager", "finance"},
        "owner_actions": {"start_task", "submit_result"},
        "collaborator_actions": {"append_comment", "append_evidence", "append_structured_data"},
        "initiator_actions": {"close_unstarted_task", "request_cancel"},
        "admin_actions": {"reassign_task", "takeover_task", "force_close_task"},
    },
    "performance_confirmation": {
        "task_category": "confirmation",
        "target_route": "/hr-performance-display",
        "required_permission": "performance:read",
        "allowed_roles": {"admin", "manager", "operator", "finance"},
        "owner_actions": {"submit_result"},
        "collaborator_actions": {"append_comment", "append_evidence", "append_structured_data"},
        "initiator_actions": {"close_unstarted_task", "request_cancel"},
        "admin_actions": {"reassign_task", "takeover_task", "force_close_task"},
    },
}


def get_task_type_policy(task_type: str) -> dict:
    policy = TASK_TYPE_POLICIES.get(task_type)
    if policy is None:
        raise ValueError(f"Unknown task type: {task_type}")
    return policy


def can_user_perform_task_action(
    task_category: str,
    task_status: str,
    actor_role: str,
    action: str,
) -> bool:
    if actor_role == "collaborator":
        return action in {"append_comment", "append_evidence", "append_structured_data"}
    if actor_role == "initiator":
        if action == "close_unstarted_task":
            return task_status == "pending"
        if action == "request_cancel":
            return task_status in {"in_progress", "pending_confirmation"}
        return False
    if actor_role == "admin":
        return action in {"reassign_task", "takeover_task", "force_close_task"}
    if actor_role == "owner":
        if task_category == "execution":
            return action in {"start_task", "submit_result"}
        if task_category == "confirmation":
            return action in {"submit_result"}
    return False


def validate_task_target_permission(task_type: str, user_permissions: set[str]) -> None:
    policy = get_task_type_policy(task_type)
    required_permission = policy["required_permission"]
    if required_permission not in user_permissions:
        raise ValueError(f"User lacks required permission for task target: {required_permission}")
