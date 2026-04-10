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


def test_inventory_script_classifies_extra_only_runtime_tables_into_follow_up_buckets():
    expected = {}
    actual = {
        "fact_shopee_orders_daily": ["b_class"],
        "business_overview_kpi_module": ["api"],
        "data_freshness_log": ["ops"],
        "alembic_version__archive_retired": ["public"],
    }

    report = analyze_duplicate_groups(expected, actual)
    by_name = {item["table_name"]: item for item in report["extra_only_tables"]}

    assert by_name["fact_shopee_orders_daily"]["risk_class"] == "generated_runtime_fact"
    assert by_name["business_overview_kpi_module"]["risk_class"] == "generated_runtime_api"
    assert by_name["data_freshness_log"]["risk_class"] == "operations_runtime_table"
    assert by_name["alembic_version__archive_retired"]["risk_class"] == "historical_migration_artifact"


def test_inventory_script_emits_follow_up_wave_groups_for_extra_only_tables():
    expected = {}
    actual = {
        "fact_shopee_orders_daily": ["b_class"],
        "business_overview_kpi_module": ["api"],
        "data_freshness_log": ["ops"],
    }

    report = analyze_duplicate_groups(expected, actual)
    follow_up = report["follow_up_waves"]

    assert "wave_2_runtime_generated" in follow_up
    assert "wave_3_ops_and_historical" in follow_up
    assert "fact_shopee_orders_daily" in follow_up["wave_2_runtime_generated"]
    assert "business_overview_kpi_module" in follow_up["wave_2_runtime_generated"]
    assert "data_freshness_log" in follow_up["wave_3_ops_and_historical"]
