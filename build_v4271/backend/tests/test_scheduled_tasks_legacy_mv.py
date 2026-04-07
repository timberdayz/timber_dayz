from unittest.mock import MagicMock, patch

from backend.tasks.scheduled_tasks import (
    refresh_inventory_finance_views,
    refresh_sales_materialized_views,
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
