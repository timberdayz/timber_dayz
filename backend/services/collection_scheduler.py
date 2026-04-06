"""
Collection scheduler service.

This module keeps APScheduler usage behind a narrow API surface so config CRUD,
startup recovery, and explicit schedule endpoints all share one implementation.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from modules.core.db import CollectionConfig, CollectionTask
from modules.core.logger import get_logger
from backend.services.component_runtime_resolver import (
    ComponentRuntimeResolver,
    ComponentRuntimeResolverError,
)
from backend.services.collection_contracts import (
    build_date_range_from_time_selection,
    count_collection_targets,
    derive_granularity_from_time_selection,
    normalize_domain_subtypes,
    normalize_time_selection,
)
from backend.services.task_service import TaskService

logger = get_logger(__name__)

CRON_PRESETS: Dict[str, str] = {
    "daily_midnight": "0 0 * * *",
    "daily_6am": "0 6 * * *",
    "daily_four_times": "0 6,12,18,22 * * *",
    "weekly_monday_midnight": "0 0 * * 1",
    "monthly_first_midnight": "0 0 1 * *",
}

try:
    from apscheduler.executors.asyncio import AsyncIOExecutor
    from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger

    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False
    AsyncIOExecutor = None
    SQLAlchemyJobStore = None
    AsyncIOScheduler = None
    CronTrigger = None
    logger.warning("APScheduler not installed, scheduled tasks disabled")


class SchedulerError(Exception):
    """Scheduler-specific error."""


def build_scheduled_task_scope(
    *,
    config: CollectionConfig,
    account_info: Dict[str, Any],
) -> tuple[List[str], Dict[str, List[str]], int]:
    task_service = TaskService(db=None)
    filtered_domains, _ = task_service.filter_domains_by_account_capability(
        account_info,
        list(config.data_domains or []),
    )
    normalized_sub_domains = normalize_domain_subtypes(
        data_domains=filtered_domains,
        sub_domains=config.sub_domains,
    )
    total_targets = count_collection_targets(filtered_domains, normalized_sub_domains)
    return filtered_domains, normalized_sub_domains, total_targets


def resolve_config_debug_mode(config: CollectionConfig | Any) -> bool:
    return str(getattr(config, "execution_mode", "headless") or "headless").strip().lower() == "headed"


async def execute_scheduled_collection_config(config_id: int) -> None:
    from backend.models.database import AsyncSessionLocal
    from backend.services.collection_config_execution import create_tasks_for_config

    logger.info("Executing scheduled task for config %s", config_id)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(CollectionConfig).where(
                CollectionConfig.id == config_id,
                CollectionConfig.is_active == True,
            )
        )
        config = result.scalar_one_or_none()
        if config is None:
            logger.warning("Scheduled config %s not found or inactive", config_id)
            return
        if not config.schedule_enabled or not config.schedule_cron:
            logger.warning("Scheduled config %s is disabled or missing cron", config_id)
            return

        tasks = await create_tasks_for_config(
            db,
            config_id=config_id,
            trigger_type="scheduled",
            start_background=True,
            resolve_runtime=True,
        )
        logger.info("Created %s scheduled tasks for config %s", len(tasks), config_id)


class CollectionScheduler:
    """APScheduler wrapper for collection configs."""

    _instance: Optional["CollectionScheduler"] = None

    def __init__(
        self,
        db_session_factory: Callable[[], Session],
        task_executor: Optional[Callable[[int], Awaitable[None]]] = None,
    ):
        if not APSCHEDULER_AVAILABLE:
            raise SchedulerError("APScheduler is not installed")

        self.db_session_factory = db_session_factory
        self.task_executor = task_executor
        self._initialized = False
        self._scheduler: Optional[AsyncIOScheduler] = None

    @classmethod
    def get_instance(
        cls,
        db_session_factory: Optional[Callable[[], Session]] = None,
        task_executor: Optional[Callable[[int], Awaitable[None]]] = None,
    ) -> "CollectionScheduler":
        if cls._instance is None:
            if db_session_factory is None:
                raise SchedulerError("db_session_factory is required for first initialization")
            cls._instance = cls(db_session_factory=db_session_factory, task_executor=task_executor)
        return cls._instance

    async def initialize(self) -> None:
        if self._initialized:
            return
        if not APSCHEDULER_AVAILABLE:
            raise SchedulerError("APScheduler is not installed")

        database_url = os.getenv("DATABASE_URL", "sqlite:///scheduler_jobs.db")
        self._scheduler = AsyncIOScheduler(
            jobstores={
                "default": SQLAlchemyJobStore(url=database_url, tablename="apscheduler_jobs"),
            },
            executors={"default": AsyncIOExecutor()},
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
                "misfire_grace_time": 300,
            },
            timezone="Asia/Shanghai",
        )
        self._initialized = True
        logger.info("Collection scheduler initialized")

    async def start(self) -> None:
        if not self._initialized:
            await self.initialize()
        if self._scheduler and not self._scheduler.running:
            self._scheduler.start()
            logger.info("Collection scheduler started")

    async def shutdown(self, wait: bool = True) -> None:
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=wait)
            logger.info("Collection scheduler stopped")

    async def load_all_schedules(self) -> int:
        if not self._scheduler:
            return 0

        from backend.models.database import AsyncSessionLocal

        loaded_count = 0
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(CollectionConfig).where(
                    CollectionConfig.schedule_enabled == True,
                    CollectionConfig.schedule_cron.is_not(None),
                    CollectionConfig.is_active == True,
                )
            )
            for config in result.scalars().all():
                await self.add_schedule(config.id, str(config.schedule_cron))
                loaded_count += 1
        return loaded_count

    async def add_schedule(self, config_id: int, cron_expression: str) -> str:
        if not self._scheduler:
            raise SchedulerError("Scheduler not initialized")
        if not self.validate_cron_expression(cron_expression):
            raise SchedulerError(f"invalid cron expression: {cron_expression}")

        job_id = f"collection_config_{config_id}"
        trigger = CronTrigger.from_crontab(cron_expression)

        if self._scheduler.get_job(job_id):
            self._scheduler.reschedule_job(job_id, trigger=trigger)
            logger.info("Rescheduled config %s with cron %s", config_id, cron_expression)
        else:
            self._scheduler.add_job(
                execute_scheduled_collection_config,
                trigger=trigger,
                id=job_id,
                args=[config_id],
                name=f"Collection Config {config_id}",
                replace_existing=True,
            )
            logger.info("Registered config %s with cron %s", config_id, cron_expression)
        return job_id

    async def remove_schedule(self, config_id: int) -> bool:
        if not self._scheduler:
            return False
        job_id = f"collection_config_{config_id}"
        job = self._scheduler.get_job(job_id)
        if job is None:
            return True
        self._scheduler.remove_job(job_id)
        logger.info("Removed schedule for config %s", config_id)
        return True

    async def pause_schedule(self, config_id: int) -> bool:
        if not self._scheduler:
            return False
        job = self._scheduler.get_job(f"collection_config_{config_id}")
        if job is None:
            return False
        self._scheduler.pause_job(job.id)
        return True

    async def resume_schedule(self, config_id: int) -> bool:
        if not self._scheduler:
            return False
        job = self._scheduler.get_job(f"collection_config_{config_id}")
        if job is None:
            return False
        self._scheduler.resume_job(job.id)
        return True

    def get_job_info(self, config_id: int) -> Optional[Dict[str, Any]]:
        if not self._scheduler:
            return None
        job_id = f"collection_config_{config_id}"
        job = self._scheduler.get_job(job_id)
        if job is None:
            return None
        return {
            "id": job.id,
            "job_id": job.id,
            "name": job.name,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            "pending": job.pending,
            "trigger": str(job.trigger),
        }

    def get_all_jobs(self) -> List[Dict[str, Any]]:
        if not self._scheduler:
            return []
        return [
            {
                "id": job.id,
                "job_id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                "pending": job.pending,
                "trigger": str(job.trigger),
            }
            for job in self._scheduler.get_jobs()
        ]

    @staticmethod
    def validate_cron_expression(cron_expression: str) -> bool:
        if not APSCHEDULER_AVAILABLE:
            return False
        try:
            CronTrigger.from_crontab(cron_expression)
            return True
        except Exception:
            return False

    @staticmethod
    def get_cron_description(cron_expression: str) -> str:
        return cron_expression


async def sync_config_schedule_state(config: CollectionConfig) -> Dict[str, Any]:
    """Make runtime scheduler state match database truth for one config."""
    if not APSCHEDULER_AVAILABLE:
        raise SchedulerError("APScheduler is not installed")

    scheduler = CollectionScheduler.get_instance()
    should_register = bool(
        getattr(config, "is_active", False)
        and getattr(config, "schedule_enabled", False)
        and getattr(config, "schedule_cron", None)
    )

    if should_register:
        cron_expression = str(config.schedule_cron or "").strip()
        if not CollectionScheduler.validate_cron_expression(cron_expression):
            raise SchedulerError(f"invalid cron expression: {cron_expression}")
        await scheduler.add_schedule(config.id, cron_expression)
    else:
        await scheduler.remove_schedule(config.id)

    job_info = scheduler.get_job_info(config.id)
    return {
        "job_registered": job_info is not None,
        "job_id": job_info.get("job_id") if job_info else None,
        "next_run_time": job_info.get("next_run_time") if job_info else None,
    }
