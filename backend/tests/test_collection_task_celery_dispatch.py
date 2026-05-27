from dataclasses import dataclass
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import sys

import pytest


class _ResolverStub:
    async def resolve_task_manifests(self, **kwargs):
        return {
            "login": _ManifestStub(
                component_name="shopee/login",
                version="1.0.0",
                file_path="modules/platforms/shopee/components/login.py",
                platform="shopee",
                component_type="login",
            ),
            "exports": [
                _ManifestStub(
                    component_name="shopee/orders_export",
                    version="1.0.0",
                    file_path="modules/platforms/shopee/components/orders_export.py",
                    platform="shopee",
                    component_type="export",
                    data_domain="orders",
                )
            ],
            "exports_by_domain": {
                "orders": _ManifestStub(
                    component_name="shopee/orders_export",
                    version="1.0.0",
                    file_path="modules/platforms/shopee/components/orders_export.py",
                    platform="shopee",
                    component_type="export",
                    data_domain="orders",
                )
            },
        }


@dataclass(frozen=True)
class _ManifestStub:
    component_name: str
    version: str
    file_path: str
    platform: str
    component_type: str
    data_domain: str | None = None
    sub_domain: str | None = None


def _install_fake_collection_task_module(monkeypatch, task_result_id: str, captured: dict):
    task_callable = SimpleNamespace()

    def _fake_apply_async(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return SimpleNamespace(id=task_result_id)

    task_callable.apply_async = _fake_apply_async

    module = ModuleType("backend.tasks.collection_tasks")
    module.execute_collection_task = task_callable
    monkeypatch.setitem(sys.modules, "backend.tasks.collection_tasks", module)


@pytest.mark.asyncio
async def test_create_task_prefers_celery_dispatch_when_enabled(monkeypatch):
    from backend.routers import collection_tasks
    from backend.routers.collection_tasks import create_task
    from backend.schemas.collection import TaskCreateRequest
    from backend.services import component_runtime_resolver

    monkeypatch.setenv("COLLECTION_EXECUTION_BACKEND", "celery")
    monkeypatch.setattr(
        component_runtime_resolver.ComponentRuntimeResolver,
        "from_async_session",
        classmethod(lambda cls, db: _ResolverStub()),
    )
    monkeypatch.setattr(
        collection_tasks.asyncio,
        "create_task",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("should not use asyncio.create_task when celery dispatch is enabled")
        ),
    )
    monkeypatch.setattr(
        collection_tasks,
        "_mirror_collection_task",
        AsyncMock(),
    )
    monkeypatch.setattr(
        collection_tasks,
        "_mirror_collection_task_log",
        AsyncMock(),
    )

    captured = {}
    _install_fake_collection_task_module(monkeypatch, "celery-collection-1", captured)

    db = MagicMock()
    db.execute = AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: None))
    db.commit = AsyncMock()

    async def _fake_refresh(task):
        task.id = 1

    db.refresh = AsyncMock(side_effect=_fake_refresh)
    db.add = MagicMock()

    account_loader = SimpleNamespace(
        load_account_async=AsyncMock(
            return_value={"account_id": "acc-1", "capabilities": {"orders": True}}
        )
    )
    monkeypatch.setattr(
        "backend.services.account_loader_service.get_account_loader_service",
        lambda: account_loader,
    )
    monkeypatch.setattr(
        "backend.services.task_service.TaskService.filter_domains_by_account_capability",
        lambda self, account_info, data_domains: (data_domains, []),
    )

    response = await create_task(
        request=TaskCreateRequest(
            platform="shopee",
            account_id="acc-1",
            data_domains=["orders"],
            time_selection={"mode": "preset", "preset": "yesterday"},
        ),
        fastapi_request=SimpleNamespace(app=None),
        db=db,
    )

    assert response["task_id"]
    assert captured["kwargs"]["queue"] == "collection"
    assert captured["kwargs"]["kwargs"]["task_id"] == response["task_id"]
    assert isinstance(captured["kwargs"]["kwargs"]["runtime_manifests"]["login"], dict)


@pytest.mark.asyncio
async def test_retry_task_prefers_celery_dispatch_when_enabled(monkeypatch):
    from backend.routers.collection_tasks import retry_task
    from backend.services import component_runtime_resolver

    monkeypatch.setenv("COLLECTION_EXECUTION_BACKEND", "celery")
    monkeypatch.setattr(
        component_runtime_resolver.ComponentRuntimeResolver,
        "from_async_session",
        classmethod(lambda cls, db: _ResolverStub()),
    )

    captured = {}
    _install_fake_collection_task_module(monkeypatch, "celery-collection-retry-1", captured)

    db = MagicMock()
    original_task = SimpleNamespace(
        id=1,
        task_id="collection-task-retry-1",
        platform="shopee",
        account="acc-1",
        status="failed",
        trigger_type="manual",
        data_domains=["orders"],
        sub_domains=None,
        granularity="daily",
        date_range={"start": "2026-03-01", "end": "2026-03-01"},
        retry_count=0,
        debug_mode=False,
    )
    db.execute = AsyncMock(
        return_value=SimpleNamespace(scalar_one_or_none=lambda: original_task)
    )
    db.commit = AsyncMock()

    async def _fake_refresh(task):
        task.id = 2

    db.refresh = AsyncMock(side_effect=_fake_refresh)
    db.add = MagicMock()

    monkeypatch.setattr(
        "backend.routers.collection_tasks._mirror_collection_task",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "backend.routers.collection_tasks._mirror_collection_task_log",
        AsyncMock(),
    )

    response = await retry_task(
        task_id=original_task.task_id,
        request=None,
        db=db,
    )

    assert response["task_id"]
    assert captured["kwargs"]["queue"] == "collection"
    assert captured["kwargs"]["kwargs"]["task_id"] == response["task_id"]
    assert isinstance(captured["kwargs"]["kwargs"]["runtime_manifests"]["login"], dict)
