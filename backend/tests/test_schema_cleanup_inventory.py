from scripts.analyze_schema_cleanup_candidates import analyze_duplicate_groups


def test_inventory_script_emits_duplicate_groups():
    expected = {
        "performance_config": "a_class",
        "catalog_files": "public",
        "task_center_tasks": "public",
    }
    actual = {
        "performance_config": ["a_class", "public"],
        "catalog_files": ["public"],
        "task_center_tasks": ["public"],
        "entity_aliases": ["b_class", "public"],
    }

    report = analyze_duplicate_groups(expected, actual)

    assert "duplicate_groups" in report
    group = next(item for item in report["duplicate_groups"] if item["table_name"] == "performance_config")
    assert group["canonical_schema"] == "a_class"
    assert group["actual_schemas"] == ["a_class", "public"]
    assert group["risk_class"] == "likely_cleanup_candidate"
    assert group["recommended_action"]


def test_inventory_script_marks_wave_one_runtime_tables_with_priority():
    expected = {
        "catalog_files": "public",
        "collection_tasks": "core",
        "collection_task_logs": "core",
        "task_center_tasks": "public",
    }
    actual = {
        "catalog_files": ["public"],
        "collection_tasks": ["core"],
        "collection_task_logs": ["core"],
        "task_center_tasks": ["public"],
    }

    report = analyze_duplicate_groups(expected, actual)

    wave_one = report["wave_one_priority_tables"]
    by_name = {item["table_name"]: item for item in wave_one}

    assert by_name["catalog_files"]["priority"] == "P0"
    assert by_name["catalog_files"]["wave"] == "wave_1"
    assert by_name["catalog_files"]["runtime_schema"] == "public"
    assert by_name["collection_task_logs"]["runtime_time_column"] == "timestamp"


def test_inventory_script_emits_migration_evidence_placeholders_for_wave_one_tables():
    expected = {"catalog_files": "public"}
    actual = {"catalog_files": ["public"]}

    report = analyze_duplicate_groups(expected, actual)

    catalog = report["wave_one_priority_tables"][0]
    assert "migration_evidence" in catalog
    assert "orm_schema" in catalog
    assert "runtime_schema" in catalog
