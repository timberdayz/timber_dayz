from unittest.mock import MagicMock, patch

from backend.tasks.scheduled_tasks import (
    backup_database,
    check_overdue_accounts_receivable,
    refresh_inventory_finance_views,
    refresh_sales_materialized_views,
    trigger_system_backup,
)


def test_refresh_sales_materialized_views_is_legacy_noop():
    with patch("backend.tasks.scheduled_tasks.SessionLocal") as session_local, patch(
        "backend.tasks.scheduled_tasks.logger"
    ) as logger:
        result = refresh_sales_materialized_views()

    assert result["status"] == "skipped"
    assert result["reason"] == "legacy_materialized_view_task"
    session_local.assert_not_called()
    logger.warning.assert_called()


def test_refresh_inventory_finance_views_is_legacy_noop():
    with patch("backend.tasks.scheduled_tasks.SessionLocal") as session_local, patch(
        "backend.tasks.scheduled_tasks.logger"
    ) as logger:
        result = refresh_inventory_finance_views()

    assert result["status"] == "skipped"
    assert result["reason"] == "legacy_materialized_view_task"
    session_local.assert_not_called()
    logger.warning.assert_called()


def test_backup_database_alias_delegates_to_trigger_system_backup():
    with patch("backend.tasks.scheduled_tasks.trigger_system_backup", return_value={"status": "success"}) as backup_task:
        result = backup_database()

    assert result == {"status": "success"}
    backup_task.assert_called_once_with()


def test_check_overdue_accounts_receivable_skips_when_runtime_table_is_missing():
    db = MagicMock()
    db.execute.side_effect = Exception('relation "fact_accounts_receivable" does not exist')

    with patch("backend.tasks.scheduled_tasks.SessionLocal", return_value=db), patch(
        "backend.tasks.scheduled_tasks.logger"
    ) as logger:
        result = check_overdue_accounts_receivable()

    assert result["status"] == "skipped"
    assert result["reason"] == "accounts_receivable_asset_missing"
    db.rollback.assert_called()
    logger.warning.assert_called()
