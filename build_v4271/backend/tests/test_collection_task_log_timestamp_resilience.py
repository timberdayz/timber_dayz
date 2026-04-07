from modules.core.db import CollectionTaskLog


def test_collection_task_log_timestamp_has_application_side_default():
    column = CollectionTaskLog.__table__.c.timestamp

    assert column.default is not None
