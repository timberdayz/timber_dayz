from modules.core.db import Base


def test_task_center_tables_are_registered():
    assert "task_center_tasks" in Base.metadata.tables
    assert "task_center_logs" in Base.metadata.tables
    assert "task_center_links" in Base.metadata.tables
