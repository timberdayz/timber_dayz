from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import ProgrammingError

from backend.services.task_center_sync_service import TaskCenterSyncService


def test_task_center_sync_service_propagates_non_missing_table_errors():
    session = MagicMock()
    session.execute.side_effect = ProgrammingError("SELECT 1", {}, Exception("bad sql"))

    service = TaskCenterSyncService(session)

    with pytest.raises(ProgrammingError):
        service.get_task("task-1")
