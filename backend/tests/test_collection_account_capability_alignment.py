from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_create_task_filters_domains_before_runtime_manifest_resolution(monkeypatch):
    captured = {}
    fake_db = MagicMock()
    fake_db.add = MagicMock()
    fake_db.commit = AsyncMock()

    async def _refresh(obj):
        if getattr(obj, "id", None) is None:
            obj.id = 1
        if getattr(obj, "progress", None) is None:
            obj.progress = 0
        if getattr(obj, "files_collected", None) is None:
            obj.files_collected = 0
        if getattr(obj, "created_at", None) is None:
            obj.created_at = datetime.now(timezone.utc)
        if getattr(obj, "updated_at", None) is None:
            obj.updated_at = datetime.now(timezone.utc)

    fake_db.refresh = AsyncMock(side_effect=_refresh)

    class _FakeLoader:
        async def load_account_async(self, account_id, db):
            return {
                "account_id": account_id,
                "enabled": True,
                "capabilities": {
                    "orders": True,
                    "services": False,
                },
            }

    class _FakeResolver:
        @classmethod
        def from_async_session(cls, db):
            return cls()

        async def resolve_task_manifests(self, **kwargs):
            captured.update(kwargs)
            return {"login": {}, "exports": [], "exports_by_domain": {}}

    def _discard_background_task(coro):
        coro.close()
        return MagicMock()

    monkeypatch.setattr(
        "backend.services.account_loader_service.get_account_loader_service",
        lambda: _FakeLoader(),
    )
    monkeypatch.setattr(
        "backend.services.component_runtime_resolver.ComponentRuntimeResolver",
        _FakeResolver,
    )
    monkeypatch.setattr(
        "backend.routers.collection_tasks.asyncio.create_task",
        _discard_background_task,
    )

    from backend.models.database import get_async_db
    from backend.routers.collection import router as collection_router

    app = FastAPI()
    app.include_router(collection_router, prefix="/collection")

    async def _override_get_async_db():
        yield fake_db

    app.dependency_overrides[get_async_db] = _override_get_async_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        response = await async_client.post(
            "/collection/tasks",
            json={
                "platform": "shopee",
                "account_id": "acc-1",
                "data_domains": ["orders", "services"],
                "granularity": "daily",
                "date_range": {"start_date": "2026-03-01", "end_date": "2026-03-07"},
                "parallel_mode": False,
                "max_parallel": 3,
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["data_domains"] == ["orders"]
    assert captured["data_domains"] == ["orders"]


@pytest.mark.asyncio
async def test_create_task_preserves_config_origin(monkeypatch):
    fake_db = MagicMock()
    added_objects = []
    fake_db.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))
    fake_db.commit = AsyncMock()

    async def _refresh(obj):
        if getattr(obj, "id", None) is None:
            obj.id = 1
        if getattr(obj, "progress", None) is None:
            obj.progress = 0
        if getattr(obj, "files_collected", None) is None:
            obj.files_collected = 0
        if getattr(obj, "created_at", None) is None:
            obj.created_at = datetime.now(timezone.utc)
        if getattr(obj, "updated_at", None) is None:
            obj.updated_at = datetime.now(timezone.utc)

    fake_db.refresh = AsyncMock(side_effect=_refresh)

    class _FakeLoader:
        async def load_account_async(self, account_id, db):
            return {
                "account_id": account_id,
                "enabled": True,
                "capabilities": {
                    "orders": True,
                },
            }

    class _FakeResolver:
        @classmethod
        def from_async_session(cls, db):
            return cls()

        async def resolve_task_manifests(self, **kwargs):
            return {"login": {}, "exports": [], "exports_by_domain": {}}

    def _discard_background_task(coro):
        coro.close()
        return MagicMock()

    monkeypatch.setattr(
        "backend.services.account_loader_service.get_account_loader_service",
        lambda: _FakeLoader(),
    )
    monkeypatch.setattr(
        "backend.services.component_runtime_resolver.ComponentRuntimeResolver",
        _FakeResolver,
    )
    monkeypatch.setattr(
        "backend.routers.collection_tasks.asyncio.create_task",
        _discard_background_task,
    )

    from backend.models.database import get_async_db
    from backend.routers.collection import router as collection_router

    app = FastAPI()
    app.include_router(collection_router, prefix="/collection")

    async def _override_get_async_db():
        yield fake_db

    app.dependency_overrides[get_async_db] = _override_get_async_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        response = await async_client.post(
            "/collection/tasks",
            json={
                "platform": "shopee",
                "account_id": "acc-1",
                "config_id": 11,
                "data_domains": ["orders"],
                "granularity": "daily",
                "date_range": {"start_date": "2026-03-01", "end_date": "2026-03-07"},
                "parallel_mode": False,
                "max_parallel": 3,
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["config_id"] == 11
    assert body["trigger_type"] == "config"

    created_task = next(obj for obj in added_objects if obj.__class__.__name__ == "CollectionTask")
    assert created_task.config_id == 11
    assert created_task.trigger_type == "config"


@pytest.mark.asyncio
async def test_collection_accounts_expose_shop_type_and_capabilities(monkeypatch):
    fake_db = MagicMock()

    class _FakeLoader:
        async def load_all_accounts_async(self, db, platform=None):
            return [
                {
                    "account_id": "acc-1",
                    "store_name": "Test Store",
                    "platform": "shopee",
                    "shop_region": "SG",
                    "enabled": True,
                    "shop_type": "local",
                    "capabilities": {
                        "orders": True,
                        "services": False,
                    },
                }
            ]

    monkeypatch.setattr(
        "backend.services.account_loader_service.get_account_loader_service",
        lambda: _FakeLoader(),
    )

    from backend.models.database import get_async_db
    from backend.routers.collection import router as collection_router

    app = FastAPI()
    app.include_router(collection_router, prefix="/collection")

    async def _override_get_async_db():
        yield fake_db

    app.dependency_overrides[get_async_db] = _override_get_async_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        response = await async_client.get("/collection/accounts")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["shop_type"] == "local"
    assert body[0]["capabilities"] == {"orders": True, "services": False}
