from modules.core.db import CollectionTask


def test_collection_task_status_column_supports_verification_required_state():
    status_column = CollectionTask.__table__.c.status

    assert getattr(status_column.type, "length", 0) >= len("verification_required")
