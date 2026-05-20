import pytest


class FakeScheduler:
    def __init__(self, job_ids: list[str]):
        self._job_ids = job_ids
        self.remove_calls: list[int] = []

    def get_all_jobs(self):
        return [{"job_id": job_id} for job_id in self._job_ids]

    async def remove_schedule(self, config_id: int):
        self.remove_calls.append(config_id)
        return True


@pytest.mark.asyncio
async def test_reconcile_removes_stale_collection_config_jobs():
    from backend.services.collection_scheduler_reconcile import reconcile_collection_schedules

    scheduler = FakeScheduler(["collection_config_1", "collection_config_999"])

    async def list_enabled_config_crons():
        return {1: "0 6 * * *"}

    removed_count = await reconcile_collection_schedules(scheduler, list_enabled_config_crons)

    assert removed_count == 1
    assert scheduler.remove_calls == [999]


@pytest.mark.asyncio
async def test_reconcile_does_not_remove_non_collection_jobs():
    from backend.services.collection_scheduler_reconcile import reconcile_collection_schedules

    scheduler = FakeScheduler(["daily_cleanup", "something_else", "collection_config_not_an_int"])

    async def list_enabled_config_crons():
        return {}

    removed_count = await reconcile_collection_schedules(scheduler, list_enabled_config_crons)

    assert removed_count == 0
    assert scheduler.remove_calls == []

