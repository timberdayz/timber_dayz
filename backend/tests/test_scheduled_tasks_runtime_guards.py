from unittest.mock import MagicMock, patch

from backend.tasks.scheduled_tasks import (
    backup_database,
    check_overdue_accounts_receivable,
)


def test_backup_database_delegates_to_trigger_system_backup():
    with patch("backend.tasks.scheduled_tasks.trigger_system_backup", return_value={"status": "success"}) as trigger:
        result = backup_database()

    assert result == {"status": "success"}
    trigger.assert_called_once_with()


def test_check_overdue_accounts_receivable_skips_when_runtime_table_missing():
    session = MagicMock()
    session.execute.side_effect = Exception('relation "fact_accounts_receivable" does not exist')

    with patch("backend.tasks.scheduled_tasks.SessionLocal", return_value=session), patch(
        "backend.tasks.scheduled_tasks.logger"
    ) as logger:
        result = check_overdue_accounts_receivable()

    assert result["status"] == "skipped"
    assert result["reason"] == "accounts_receivable_asset_missing"
    session.rollback.assert_called_once_with()
    session.close.assert_called_once_with()
    logger.warning.assert_called()
