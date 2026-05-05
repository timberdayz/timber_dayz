from __future__ import annotations


def test_schema_module_imports() -> None:
    import modules.core.db.schema as schema  # noqa: F401


def test_schema_metadata_contains_representative_tables() -> None:
    from modules.core.db.schema import Base

    assert Base.metadata.tables, "Schema import should register tables into Base.metadata"

    required_table_names = [
        "core.dim_platforms",
        "core.dim_shops",
        "core.accounts",
        "catalog_files",
        "core.data_quarantine",
        "fact_order_amounts",
        "core.collection_tasks",
        "task_center_tasks",
        "core.employee_tasks",
        "approval_instances",
    ]

    missing = [name for name in required_table_names if name not in Base.metadata.tables]
    assert not missing, f"Missing tables: {missing}"


def test_schema_metadata_table_keys_are_unique() -> None:
    from modules.core.db.schema import Base

    table_keys = list(Base.metadata.tables.keys())
    assert len(table_keys) == len(set(table_keys))
