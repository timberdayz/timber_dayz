from modules.core.db import Base


def test_cloud_auto_sync_task_table_is_registered():
    assert "cloud_b_class_sync_tasks" in Base.metadata.tables
