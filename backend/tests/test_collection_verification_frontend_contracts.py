from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


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

    assert "const TERMINAL_STATUSES = ['completed', 'failed', 'cancelled', 'partial_success']" in text
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
