import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ROOT = PROJECT_ROOT / "frontend"
COLLECTION_CONFIG_VIEW = PROJECT_ROOT / "frontend/src/domains/collection/views/collection/CollectionConfig.vue"
COLLECTION_TASKS_VIEW = PROJECT_ROOT / "frontend/src/domains/collection/views/collection/CollectionTasks.vue"
COLLECTION_HISTORY_VIEW = PROJECT_ROOT / "frontend/src/domains/collection/views/collection/CollectionHistory.vue"
COMPONENT_RECORDER_VIEW = PROJECT_ROOT / "frontend/src/domains/collection/views/ComponentRecorder.vue"
COMPONENT_VERSIONS_VIEW = PROJECT_ROOT / "frontend/src/domains/collection/views/ComponentVersions.vue"
ACCOUNT_MANAGEMENT_VIEW = PROJECT_ROOT / "frontend/src/domains/platform/views/AccountManagement.vue"
VSCODE_SETTINGS = PROJECT_ROOT / ".vscode/settings.json"
EDITOR_CONFIG = PROJECT_ROOT / ".editorconfig"


def test_collection_config_run_uses_sub_domains_payload():
    text = COLLECTION_CONFIG_VIEW.read_text(encoding="utf-8")

    assert "sub_domain: row.sub_domain" not in text
    assert "sub_domains" in text


def test_collection_config_uses_generic_domain_subtype_controls():
    text = COLLECTION_CONFIG_VIEW.read_text(encoding="utf-8")

    assert "sub-domain-section" in text
    assert "sub-domain-label" in text
    assert "shop-scope-meta" in text
    assert "getScopeSubtypeDomains(row.scope).length" in text
    assert "Maximum recursive updates exceeded" not in text
    assert "getSelectedSubtypeDomains" in text
    assert "getScopeSubtypeDomains(row.scope)" in text
    assert "function getDomainLabel(domain)" in text
    assert "getSubtypeOptions(domain)" in text
    assert "row.scope.sub_domains.services" not in text
    assert "getSubtypeOptions('services')" not in text
    assert ".map((scope) => {\n      ensureScopeSubtypeMap(scope)" not in text


def test_collection_tasks_supports_domain_scoped_subtypes():
    text = COLLECTION_TASKS_VIEW.read_text(encoding="utf-8")

    assert "quickForm.sub_domains = {}" in text or "sub_domains: {}" in text


def test_component_recorder_does_not_hardcode_services_only_subtype_logic():
    text = COMPONENT_RECORDER_VIEW.read_text(encoding="utf-8")

    assert 'dataDomain === "services"' not in text


def test_component_versions_page_states_stable_only_for_formal_collection():
    text = COMPONENT_VERSIONS_VIEW.read_text(encoding="utf-8")

    assert "V2:" in text
    assert "stable" in text


def test_frontend_lint_script_uses_existing_gitignore():
    package_json = json.loads((FRONTEND_ROOT / "package.json").read_text(encoding="utf-8"))

    assert "--ignore-path ../.gitignore" in package_json["scripts"]["lint"]


def test_frontend_eslint_patch_dependency_is_declared():
    package_json = json.loads((FRONTEND_ROOT / "package.json").read_text(encoding="utf-8"))

    assert "@rushstack/eslint-patch" in package_json["devDependencies"]


def test_component_versions_closes_verification_dialog_after_submission():
    text = COMPONENT_VERSIONS_VIEW.read_text(encoding="utf-8")

    assert "verificationRequired.value = null" in text


def test_account_management_uses_main_and_shop_account_terms():
    text = ACCOUNT_MANAGEMENT_VIEW.read_text(encoding="utf-8")

    assert 'prop="parent_account" label="主账号ID"' in text
    assert 'prop="account_id" label="店铺账号ID"' in text
    assert 'prop="shop_id" label="平台店铺ID"' in text
    assert "parent_account: [{ required: true" in text


def test_component_versions_uses_test_shop_term():
    text = COMPONENT_VERSIONS_VIEW.read_text(encoding="utf-8")

    assert "测试店铺" in text
    assert "测试账号" not in text


def test_collection_tasks_uses_submitted_verification_payload():
    text = COLLECTION_TASKS_VIEW.read_text(encoding="utf-8")

    assert "const submitVerification = async (submitted) =>" in text
    assert "const code = String(submitted?.value || '').trim()" in text


def test_collection_tasks_cancel_button_targets_verification_required_tasks():
    text = COLLECTION_TASKS_VIEW.read_text(encoding="utf-8")

    assert 'cancel-text="取消任务"' in text
    assert "await collectionApi.cancelTask(currentTask.value.task_id)" in text


def test_component_versions_loads_shop_accounts_directly():
    text = COMPONENT_VERSIONS_VIEW.read_text(encoding="utf-8")

    assert "listShopAccounts" in text
    assert "listAccounts({" not in text


def test_component_recorder_loads_shop_accounts_directly():
    text = COMPONENT_RECORDER_VIEW.read_text(encoding="utf-8")

    assert "listShopAccounts" in text
    assert "listAccounts(params)" not in text


def test_accounts_api_uses_new_unmatched_alias_route():
    text = (PROJECT_ROOT / "frontend/src/api/accounts.js").read_text(encoding="utf-8")

    assert "/shop-account-aliases/unmatched" in text
    assert "/accounts/unmatched-shop-aliases" not in text


def test_collection_config_run_uses_backend_config_run_endpoint():
    text = COLLECTION_CONFIG_VIEW.read_text(encoding="utf-8")

    assert "collectionApi.runConfig(row.id, {" in text
    assert "expected_granularity: activeGranularity.value" in text
    assert "for (const accountId of accountIds)" not in text


def test_collection_config_loads_config_run_queue_panel():
    text = COLLECTION_CONFIG_VIEW.read_text(encoding="utf-8")

    assert "collectionApi.getConfigRuns(" in text
    assert "activeConfigRuns" in text
    assert "queuedConfigRuns" in text
    assert "max-height: 260px" in text
    assert "overflow-y: auto" in text
    assert "queue-status-bar" in text
    assert "cancelConfigRun(run)" in text


def test_collection_config_run_uses_queue_run_feedback_not_task_id_redirect():
    text = COLLECTION_CONFIG_VIEW.read_text(encoding="utf-8")

    assert "runResult.run_id" in text
    assert "task_ids" not in text or "taskIds" not in text


def test_collection_config_exposes_cancel_action_for_active_runs():
    text = COLLECTION_CONFIG_VIEW.read_text(encoding="utf-8")
    api_text = (PROJECT_ROOT / "frontend/src/api/collection.js").read_text(encoding="utf-8")

    assert "collectionApi.cancelConfigRun(run.run_id)" in text
    assert "run.can_cancel" in text
    assert "cancelConfigRun" in api_text


def test_collection_config_consumes_unified_runtime_health_states():
    text = COLLECTION_CONFIG_VIEW.read_text(encoding="utf-8")

    assert "runtime_mode" in text
    assert "deployment_role" in text
    assert "leader_lock" in text
    assert "queue_runner" in text
    assert "scheduler" in text
    assert "can_consume_queue" in text
    assert "scheduler === 'ok'" not in text
    assert "queue_runner !== 'running'" not in text


def test_collection_config_source_has_no_known_mojibake_tokens():
    text = COLLECTION_CONFIG_VIEW.read_text(encoding="utf-8")

    forbidden_tokens = [
        "鎵",
        "鍙",
        "閲",
        "歿{",
        "?/div>",
        "?/span>",
        "?/el-",
        "?/p>",
    ]
    for token in forbidden_tokens:
        assert token not in text


def test_utf8_editor_guardrails_are_declared():
    """UTF-8 护栏必须在**受版本管理**的文件里声明。

    [*] 2026-11-09: 这个断言原先要求 ``.vscode/settings.json`` 存在, 但那个文件
    被 ``.gitignore`` 排除(``.gitignore:109``), **从未进过版本库**
    (基线 commit ``419b4436`` 里也没有) —— 于是任何干净 checkout 跑这个测试
    都必然红, CI 也不例外。断言一个「本地才有的文件」等于断言「我本机装过
    什么」, 不是仓库契约。

    现在的口径:
    * ``.editorconfig``(受版本管理) —— **必须**声明 charset / end_of_line /
      insert_final_newline, 这是真正的仓库级护栏;
    * ``.vscode/settings.json``(本地可选) —— **存在时**才校验它的
      files.encoding / files.autoGuessEncoding, 缺失不算失败。
    """
    editor_text = EDITOR_CONFIG.read_text(encoding="utf-8")

    # 仓库级护栏: .editorconfig 受版本管理, 必须齐备
    assert "charset = utf-8" in editor_text
    assert "end_of_line = lf" in editor_text
    assert "insert_final_newline = true" in editor_text

    # 本地可选护栏: 存在才校验, 缺失(干净 checkout / CI)不算失败
    if VSCODE_SETTINGS.exists():
        vscode_settings = json.loads(VSCODE_SETTINGS.read_text(encoding="utf-8"))
        assert vscode_settings["files.encoding"] == "utf8"
        assert vscode_settings["files.autoGuessEncoding"] is False


def test_collection_config_exposes_main_account_scoping_hooks():
    text = COLLECTION_CONFIG_VIEW.read_text(encoding="utf-8")

    assert "selectedMainAccountKey" in text
    assert 'data-testid="collection-config-main-account-field"' in text
    assert "main_account_id: form.main_account_id" in text


def test_collection_config_uses_granularity_filtered_current_config_and_local_edit_state():
    text = COLLECTION_CONFIG_VIEW.read_text(encoding="utf-8")

    assert "normalizeConfigGranularity({" in text
    assert "item.template_id || selectedTemplate.value.id" in text
    assert "editableShopScopes" in text
    assert "editableCurrentConfigId" in text
    assert "syncEditableCurrentConfig" in text


def test_collection_tasks_uses_task_ids_hint_for_config_navigation():
    text = COLLECTION_TASKS_VIEW.read_text(encoding="utf-8")

    assert "route.query.task_ids" in text
    assert "matchedTask" in text


def test_collection_history_exposes_origin_fields():
    text = COLLECTION_HISTORY_VIEW.read_text(encoding="utf-8")

    assert "config_id" in text
    assert "trigger_type" in text


def test_collection_tasks_mentions_main_account_coordination_steps():
    text = COLLECTION_TASKS_VIEW.read_text(encoding="utf-8")

    assert "waiting_for_main_account_session" in text
    assert "preparing_main_account_session" in text
    assert "switching_target_shop" in text
    assert "target_shop_ready" in text


def test_collection_tasks_detail_drawer_shows_runtime_metadata():
    text = COLLECTION_TASKS_VIEW.read_text(encoding="utf-8")

    assert "actual_execution_mode" in text
    assert "runtime_session_mode" in text
    assert "login_gate_reason" in text
    assert "runtime_strategy_reason" in text
    assert "session_source" in text
    assert "getRuntimeSessionModeLabel" in text
    assert "getSessionSourceLabel" in text
    assert "getRuntimeStrategyReasonLabel" in text
    assert "profile_is_single_source_of_truth" in text
    assert "persistent_profile_available" in text


def test_collection_tasks_detail_drawer_uses_profile_session_diagnostics():
    text = COLLECTION_TASKS_VIEW.read_text(encoding="utf-8")

    assert "session_profile_path" in text
    assert "session_reused" in text
    assert "session_proxy" in text

    for removed in (
        "session_quality_score",
        "session_quality_gate_passed",
        "session_quality_source",
        "session_manual_seeded",
        "session_protected",
        "getSessionQualitySourceLabel",
        "persistent_profile_path",
        "profile_contains_state",
        "storage_state_available",
        "storage_state_missing",
        "manual_storage_state_available",
        "storage_state 会话快照",
    ):
        assert removed not in text, f"旧会话诊断字段/文案应已移除: {removed}"


def test_account_management_does_not_offer_free_form_login_url_editing():
    text = ACCOUNT_MANAGEMENT_VIEW.read_text(encoding="utf-8")

    assert '<el-form-item label="登录URL">' not in text
    assert 'v-model="accountForm.login_url"' not in text or 'disabled' in text
