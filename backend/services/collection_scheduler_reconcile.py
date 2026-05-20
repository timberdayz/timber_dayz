"""
Scheduler reconcile helpers.

At startup, APScheduler jobstore can contain stale jobs (e.g. configs disabled in DB).
This module provides a narrow reconcile function to align jobstore with DB truth
without touching unrelated jobs (e.g. daily_cleanup).
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Protocol, Set


COLLECTION_CONFIG_JOB_PREFIX = "collection_config_"


class _SchedulerLike(Protocol):
    def get_all_jobs(self) -> list[dict[str, Any]]: ...

    def remove_schedule(self, config_id: int) -> Awaitable[bool]: ...


async def reconcile_collection_schedules(
    scheduler: _SchedulerLike,
    list_enabled_config_crons: Callable[[], Awaitable[Dict[int, str]]],
) -> int:
    """
    Remove stale collection-config schedules from jobstore.

    Rules:
    - Only considers jobs whose job_id starts with "collection_config_".
    - If the extracted config_id is not enabled per DB, remove it via scheduler.remove_schedule(config_id).
    - Never removes unrelated jobs (e.g. "daily_cleanup").
    """
    enabled_config_crons = await list_enabled_config_crons()
    enabled_config_ids: Set[int] = set(enabled_config_crons.keys())

    removed_count = 0
    for job in scheduler.get_all_jobs():
        job_id = str(job.get("job_id") or job.get("id") or "")
        if not job_id.startswith(COLLECTION_CONFIG_JOB_PREFIX):
            continue

        suffix = job_id[len(COLLECTION_CONFIG_JOB_PREFIX) :]
        try:
            config_id = int(suffix)
        except ValueError:
            continue

        if config_id in enabled_config_ids:
            continue

        await scheduler.remove_schedule(config_id)
        removed_count += 1

    return removed_count

