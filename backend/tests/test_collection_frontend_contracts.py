from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


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
