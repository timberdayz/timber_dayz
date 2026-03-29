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

    assert "只有稳定版本可用于正式采集和定时调度" in text


def test_frontend_lint_script_uses_existing_gitignore():
    package_json = json.loads((FRONTEND_ROOT / "package.json").read_text(encoding="utf-8"))

    assert "--ignore-path ../.gitignore" in package_json["scripts"]["lint"]


def test_frontend_eslint_patch_dependency_is_declared():
    package_json = json.loads((FRONTEND_ROOT / "package.json").read_text(encoding="utf-8"))

    assert "@rushstack/eslint-patch" in package_json["devDependencies"]


def test_component_versions_closes_verification_dialog_after_submission():
    text = (PROJECT_ROOT / "frontend/src/views/ComponentVersions.vue").read_text(encoding="utf-8")

    assert "verificationRequired.value = null" in text
    assert "} else {" in text
    assert "verificationRequired.value = null" in text
