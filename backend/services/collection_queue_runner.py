from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.services.collection_config_run_service import CollectionConfigRunService
from modules.core.db import CollectionConfig
from modules.core.logger import get_logger


logger = get_logger(__name__)


class CollectionQueueRunner:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        poll_interval_seconds: float = 2.0,
        run_processor: Optional[Callable[[object], Awaitable[None]]] = None,
        app: object | None = None,
    ):
        self.session_factory = session_factory
        self.poll_interval_seconds = poll_interval_seconds
        self._task: asyncio.Task | None = None
        self._shutdown = asyncio.Event()
        self._run_processor = run_processor
        self.app = app

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._shutdown.clear()
        self._task = asyncio.create_task(self._run_loop())

    async def shutdown(self) -> None:
        self._shutdown.set()
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def process_once(self) -> bool:
        return await self._process_once_impl()

    async def _run_loop(self) -> None:
        while not self._shutdown.is_set():
            try:
                processed = await self.process_once()
                if not processed:
                    await asyncio.sleep(self.poll_interval_seconds)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("CollectionQueueRunner loop iteration failed: %s", exc)
                await asyncio.sleep(self.poll_interval_seconds)

    async def _process_once_impl(self) -> bool:
        async with self.session_factory() as session:
            service = CollectionConfigRunService(session)
            run = await service.claim_next_queued_run()
            if run is None:
                return False
            try:
                await self._process_run(run)
            except Exception as exc:
                await service.mark_run_failed(run.id, error_message=str(exc))
                logger.warning(
                    "CollectionQueueRunner failed while processing run %s: %s",
                    getattr(run, "run_id", run.id),
                    exc,
                )
            return True

    async def _process_run(self, run: object) -> None:
        if self._run_processor is not None:
            await self._run_processor(run)
            return

        tasks = await self._expand_run_tasks(run)
        for task_info in tasks:
            runtime_manifests = None
            task = task_info
            if isinstance(task_info, tuple) and len(task_info) == 2:
                task, runtime_manifests = task_info
            else:
                runtime_manifests = getattr(task_info, "runtime_manifests", None)
            await self._execute_task(task, runtime_manifests=runtime_manifests)
        await self._finalize_run(run)

    async def _expand_run_tasks(self, run: object):
        from backend.services.collection_config_execution import create_tasks_for_config

        async with self.session_factory() as session:
            config = (
                await session.execute(
                    select(CollectionConfig).where(CollectionConfig.id == run.config_id)
                )
            ).scalar_one()
            return await create_tasks_for_config(
                session,
                config_id=config.id,
                config_run_id=run.id,
                trigger_type=run.trigger_type,
                start_background=False,
                resolve_runtime=True,
            )

    async def _execute_task(
        self,
        task: object,
        *,
        runtime_manifests: object | None = None,
    ) -> None:
        from backend.domains.collection.routers.collection_tasks import (
            _execute_collection_task_background,
        )

        await _execute_collection_task_background(
            task_id=task.task_id,
            platform=task.platform,
            account_id=task.account,
            data_domains=task.data_domains or [],
            sub_domains=task.sub_domains,
            date_range=task.date_range or {},
            granularity=task.granularity or "daily",
            debug_mode=bool(getattr(task, "debug_mode", False)),
            execution_mode="headed" if getattr(task, "debug_mode", False) else "headless",
            parallel_mode=False,
            max_parallel=1,
            runtime_manifests=runtime_manifests,
            app=self.app,
        )

    async def _finalize_run(self, run: object) -> None:
        async with self.session_factory() as session:
            service = CollectionConfigRunService(session)
            await service.finalize_run_from_tasks(run.id)
