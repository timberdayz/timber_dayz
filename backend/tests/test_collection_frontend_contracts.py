import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ROOT = PROJECT_ROOT / "frontend"


def test_collection_config_run_uses_sub_domains_payload():
    text = (PROJECT_ROOT / "frontend/src/views/collection/CollectionConfig.vue").read_text(encoding="utf-8")

    assert "sub_domain: row.sub_domain" not in text
    assert "sub_domains: row.sub_domains" in text


def test_collection_tasks_supports_domain_scoped_subtypes():
    text = (PROJECT_ROOT / "frontend/src/views/collection/CollectionTasks.vue").read_text(encoding="utf-8")

    assert "quickForm.sub_domains = {}" in text or "sub_domains: {}" in text


def test_component_recorder_does_not_hardcode_services_only_subtype_logic():
    text = (PROJECT_ROOT / "frontend/src/views/ComponentRecorder.vue").read_text(encoding="utf-8")

    assert 'dataDomain === "services"' not in text


def test_component_versions_page_states_stable_only_for_formal_collection():
    text = (PROJECT_ROOT / "frontend/src/views/ComponentVersions.vue").read_text(encoding="utf-8")

    assert "V2:" in text
    assert "stable" in text


def test_frontend_lint_script_uses_existing_gitignore():
    package_json = json.loads((FRONTEND_ROOT / "package.json").read_text(encoding="utf-8"))

    assert "--ignore-path ../.gitignore" in package_json["scripts"]["lint"]


def test_frontend_eslint_patch_dependency_is_declared():
    package_json = json.loads((FRONTEND_ROOT / "package.json").read_text(encoding="utf-8"))

    assert "@rushstack/eslint-patch" in package_json["devDependencies"]


def test_component_versions_closes_verification_dialog_after_submission():
    text = (PROJECT_ROOT / "frontend/src/views/ComponentVersions.vue").read_text(encoding="utf-8")

    assert "verificationRequired.value = null" in text


def test_account_management_uses_main_and_shop_account_terms():
    text = (PROJECT_ROOT / "frontend/src/views/AccountManagement.vue").read_text(encoding="utf-8")

    assert 'prop="parent_account" label="主账号ID"' in text
    assert 'prop="account_id" label="店铺账号ID"' in text
    assert 'prop="shop_id" label="平台店铺ID"' in text
    assert "parent_account: [{ required: true" in text


def test_component_versions_uses_test_shop_term():
    text = (PROJECT_ROOT / "frontend/src/views/ComponentVersions.vue").read_text(encoding="utf-8")

    assert "测试店铺" in text
    assert "测试账号" not in text


def test_collection_tasks_uses_submitted_verification_payload():
    text = (PROJECT_ROOT / "frontend/src/views/collection/CollectionTasks.vue").read_text(encoding="utf-8")

    assert "const submitVerification = async (submitted) =>" in text
    assert "const code = String(submitted?.value || '').trim()" in text


def test_collection_tasks_cancel_button_targets_verification_required_tasks():
    text = (PROJECT_ROOT / "frontend/src/views/collection/CollectionTasks.vue").read_text(encoding="utf-8")

    assert 'cancel-text="取消任务"' in text
    assert "await collectionApi.cancelTask(currentTask.value.task_id)" in text


def test_component_versions_loads_shop_accounts_directly():
    text = (PROJECT_ROOT / "frontend/src/views/ComponentVersions.vue").read_text(encoding="utf-8")

    assert "listShopAccounts" in text
    assert "listAccounts({" not in text


def test_component_recorder_loads_shop_accounts_directly():
    text = (PROJECT_ROOT / "frontend/src/views/ComponentRecorder.vue").read_text(encoding="utf-8")

    assert "listShopAccounts" in text
    assert "listAccounts(params)" not in text


def test_accounts_api_uses_new_unmatched_alias_route():
    text = (PROJECT_ROOT / "frontend/src/api/accounts.js").read_text(encoding="utf-8")

    assert "/shop-account-aliases/unmatched" in text
    assert "/accounts/unmatched-shop-aliases" not in text
