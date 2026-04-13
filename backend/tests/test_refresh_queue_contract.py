from modules.core.db import Base, RefreshQueueTask


def test_refresh_queue_task_model_exists_in_metadata():
    assert "core.refresh_queue_tasks" in Base.metadata.tables


def test_refresh_queue_task_exposes_expected_columns():
    table = Base.metadata.tables["core.refresh_queue_tasks"]

    expected_columns = {
        "id",
        "job_id",
        "trigger_type",
        "pipeline_name",
        "dedupe_key",
        "targets_json",
        "context_json",
        "status",
        "attempt_count",
        "last_error",
        "created_at",
        "started_at",
        "finished_at",
    }

    assert expected_columns.issubset(set(table.c.keys()))


def test_refresh_queue_task_status_default_and_indexes():
    table = Base.metadata.tables["core.refresh_queue_tasks"]

    assert table.c.status.default is not None
    assert table.c.status.default.arg == "pending"

    index_names = {index.name for index in table.indexes}
    assert "ix_refresh_queue_tasks_status" in index_names
    assert "ix_refresh_queue_tasks_dedupe_key" in index_names
    assert "ix_refresh_queue_tasks_created_at" in index_names


def test_refresh_queue_task_uses_core_schema_and_json_columns():
    assert RefreshQueueTask.__table__.schema == "core"
    assert RefreshQueueTask.__table__.c.targets_json is not None
    assert RefreshQueueTask.__table__.c.context_json is not None
