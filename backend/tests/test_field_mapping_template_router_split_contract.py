from pathlib import Path


def test_template_router_is_split_out_of_dictionary_router():
    # 两个 legacy 兼容壳（backend/routers/field_mapping_*.py）现在只是 re-export，
    # 真身在 backend/domains/data_platform/routers/ 下，断言必须打在真身上。
    dictionary_router = Path(
        "backend/domains/data_platform/routers/field_mapping_dictionary.py"
    ).read_text(encoding="utf-8")
    template_router = Path(
        "backend/domains/data_platform/routers/field_mapping_templates.py"
    ).read_text(encoding="utf-8")

    assert '@router.post("/templates/save"' not in dictionary_router
    assert '@router.get("/templates/default-deduplication-fields"' not in dictionary_router
    assert '@router.get("/templates/{template_id}/update-context"' not in dictionary_router
    assert '@router.post("/templates/detect-header-changes"' not in dictionary_router

    assert '@router.post("/templates/save"' in template_router
    assert '"/templates/default-deduplication-fields"' in template_router
    assert '"/templates/{template_id}/update-context"' in template_router
    assert '"/templates/detect-header-changes"' in template_router


def test_main_registers_template_router_separately():
    main_source = Path("backend/main.py").read_text(encoding="utf-8")

    assert "field_mapping_templates" in main_source
    assert 'field_mapping_templates.router, prefix="/api/field-mapping"' in main_source
