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
