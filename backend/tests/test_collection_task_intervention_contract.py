from types import SimpleNamespace

from backend.routers.collection_tasks import _build_task_verification_item


def test_build_task_verification_item_supports_manual_intervention_required():
    task = SimpleNamespace(
        task_id="task-1",
        account="acc-1",
        platform="miaoshou",
        status="manual_intervention_required",
        verification_type="manual_intervention",
        current_step="需要人工处理页面异常",
        error_message=None,
        verification_screenshot="temp/manual.png",
        created_at=None,
    )

    item = _build_task_verification_item(task)

    assert item is not None
    assert item["task_id"] == "task-1"
    assert item["verification_type"] == "manual_intervention"
    assert item["verification_input_mode"] == "manual_continue"


def test_build_task_verification_item_still_supports_graphical_captcha():
    task = SimpleNamespace(
        task_id="task-2",
        account="acc-2",
        platform="shopee",
        status="verification_required",
        verification_type="graphical_captcha",
        current_step="等待验证码",
        error_message=None,
        verification_screenshot="temp/captcha.png",
        created_at=None,
    )

    item = _build_task_verification_item(task)

    assert item is not None
    assert item["verification_type"] == "graphical_captcha"
    assert item["verification_input_mode"] == "code_entry"
