from modules.core.db import Base


def test_cloud_sync_state_tables_are_registered():
    assert "cloud_b_class_sync_checkpoints" in Base.metadata.tables
    assert "cloud_b_class_sync_runs" in Base.metadata.tables
