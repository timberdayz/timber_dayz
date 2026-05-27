from __future__ import annotations

import asyncio

from backend.celery_app import celery_app
from backend.models.database import reset_async_engine_pool_for_new_loop
from modules.core.logger import get_logger

logger = get_logger(__name__)


@celery_app.task(
    name="collection.execute_task",
    bind=True,
    queue="collection",
    priority=5,
    time_limit=1800,
    soft_time_limit=1500,
)
def execute_collection_task(self, **submission_kwargs):
    async def _async_entry() -> None:
        from backend.routers.collection_tasks import (
            _execute_collection_task_background_v2,
        )

        await _execute_collection_task_background_v2(
            app=None,
            **submission_kwargs,
        )

    try:
        reset_async_engine_pool_for_new_loop()
        return asyncio.run(_async_entry())
    except Exception as exc:
        logger.error(
            "[CollectionCelery] task_id=%s failed: %s",
            submission_kwargs.get("task_id"),
            exc,
            exc_info=True,
        )
        raise
