from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _parse_string_array(text: str, prefix: str, label: str) -> list:
    assert prefix in text, f"{label} definition not found"
    remainder = text.split(prefix, 1)[1]
    start = remainder.index("[")
    end = remainder.index("]", start)
    body = remainder[start + 1 : end]
    return [item.strip().strip("'\"") for item in body.split(",") if item.strip()]


def test_collection_tasks_closes_verification_dialog_after_resume_submission_ack():
    text = (
        PROJECT_ROOT
        / "frontend/src/domains/collection/views/collection/CollectionTasks.vue"
    ).read_text(encoding="utf-8")

    assert "const verificationSubmitting = ref(false)" in text
    assert ':submitting="verificationSubmitting"' in text
    assert "verificationSubmitting.value = true" in text
    submit_block = text.split(
        "const submitVerification = async (submitted) =>", 1
    )[1].split("const skipVerification =", 1)[0]
    assert "verificationDialogVisible.value = false" in submit_block
    assert "await loadTasks()" in submit_block


def test_collection_tasks_refreshes_screenshot_url_with_cache_busting_timestamp():
    text = (
        PROJECT_ROOT
        / "frontend/src/domains/collection/views/collection/CollectionTasks.vue"
    ).read_text(encoding="utf-8")

    assert "const getVerificationScreenshotUrl = (taskId) =>" in text
    assert "collectionApi.getTaskScreenshotUrl(taskId, { ts: Date.now() })" in text


def test_collection_tasks_closes_verification_dialog_when_task_reaches_terminal_status():
    text = (
        PROJECT_ROOT
        / "frontend/src/domains/collection/views/collection/CollectionTasks.vue"
    ).read_text(encoding="utf-8")

    terminal_statuses = _parse_string_array(
        text, "const TERMINAL_STATUSES = ", "TERMINAL_STATUSES"
    )
    assert {
        "completed",
        "failed",
        "cancelled",
        "partial_success",
        "interrupted",
    } <= set(terminal_statuses)
    assert "if (TERMINAL_STATUSES.includes(currentTaskFromList.status))" in text
    assert "verificationDialogVisible.value = false" in text
    assert "verificationSubmitting.value = false" in text


def test_collection_tasks_does_not_keep_verification_submitted_as_dialog_state():
    text = (
        PROJECT_ROOT
        / "frontend/src/domains/collection/views/collection/CollectionTasks.vue"
    ).read_text(encoding="utf-8")

    sync_block = text.split("const syncVerificationDialogFromTasks = (taskList) =>", 1)[1].split("const copyTaskId =", 1)[0]
    assert "currentTaskFromList.status === 'verification_submitted'" not in sync_block
