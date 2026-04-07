from types import SimpleNamespace

from backend.services.collection_scheduler import (
    build_scheduled_task_scope,
    execute_scheduled_collection_config,
    resolve_config_debug_mode,
)


def test_build_scheduled_task_scope_filters_domains_and_domain_subtypes():
    config = SimpleNamespace(
        data_domains=["orders", "services"],
        sub_domains={"services": ["agent", "ai_assistant"]},
    )
    account_info = {
        "account_id": "acc-1",
        "capabilities": {
            "orders": True,
            "services": False,
        },
    }

    filtered_domains, domain_subtypes, total_targets = build_scheduled_task_scope(
        config=config,
        account_info=account_info,
    )

    assert filtered_domains == ["orders"]
    assert domain_subtypes == {}
    assert total_targets == 1


def test_resolve_config_debug_mode_defaults_to_headless():
    config = SimpleNamespace(execution_mode="headless")

    assert resolve_config_debug_mode(config) is False


def test_resolve_config_debug_mode_treats_headed_as_debug_mode():
    config = SimpleNamespace(execution_mode="headed")

    assert resolve_config_debug_mode(config) is True


def test_add_schedule_registers_module_level_callable(monkeypatch):
    from backend.services import collection_scheduler as scheduler_module

    class FakeInnerScheduler:
        def __init__(self):
            self.job = None

        def get_job(self, _job_id):
            return None

        def add_job(self, func, **kwargs):
            self.job = (func, kwargs)

    monkeypatch.setattr(scheduler_module, "APSCHEDULER_AVAILABLE", True)

    scheduler = scheduler_module.CollectionScheduler(db_session_factory=lambda: None)
    scheduler._scheduler = FakeInnerScheduler()
    monkeypatch.setattr(
        scheduler_module.CollectionScheduler,
        "validate_cron_expression",
        staticmethod(lambda _expr: True),
    )
    monkeypatch.setattr(
        scheduler_module,
        "CronTrigger",
        SimpleNamespace(from_crontab=lambda expr: f"trigger:{expr}"),
    )

    import asyncio

    asyncio.run(scheduler.add_schedule(12, "0 6 * * *"))

    func, kwargs = scheduler._scheduler.job
    assert func is execute_scheduled_collection_config
    assert kwargs["args"] == [12]
