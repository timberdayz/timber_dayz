import pytest

from modules.core.db import (
    CollectionConfig,
    CollectionTask,
    CollectionTaskLog,
)


@pytest.mark.parametrize(
    ("model", "table_name"),
    [
        (CollectionConfig, "collection_configs"),
        (CollectionTask, "collection_tasks"),
        (CollectionTaskLog, "collection_task_logs"),
    ],
)
def test_collection_tables_bind_explicitly_to_core_schema(model, table_name):
    table = model.__table__

    assert table.name == table_name
    assert table.schema == "core"
    assert table.fullname == f"core.{table_name}"


def test_collection_config_run_table_binds_explicitly_to_core_schema():
    from modules.core.db import CollectionConfigRun

    table = CollectionConfigRun.__table__

    assert table.name == "collection_config_runs"
    assert table.schema == "core"
    assert table.fullname == "core.collection_config_runs"


def test_collection_task_exposes_config_run_linkage():
    assert hasattr(CollectionTask, "config_run_id")


def test_collection_config_bulk_run_response_resolves_nested_run_schema():
    from backend.schemas.collection import CollectionConfigBulkRunResponse

    schema = CollectionConfigBulkRunResponse.model_json_schema()

    assert "CollectionConfigRunResponse" in schema.get("$defs", {})
