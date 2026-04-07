import pytest

from modules.core.db import CollectionConfig, CollectionTask, CollectionTaskLog


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
