from pathlib import Path
from typing import AsyncGenerator
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from unittest.mock import AsyncMock, MagicMock

from modules.core.db import ComponentVersion


@pytest_asyncio.fixture
async def component_version_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(ComponentVersion.__table__.create)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(ComponentVersion.__table__.drop)

    await engine.dispose()


@pytest.fixture
def collection_app():
    from backend.routers.collection import router as collection_router

    app = FastAPI()
    app.include_router(collection_router, prefix="/collection", tags=["collection"])
    app.state.redis = None
    return app


@pytest.mark.asyncio
async def test_resolve_runtime_component_requires_stable_version(component_version_session, tmp_path: Path, monkeypatch):
    from backend.services.component_runtime_resolver import (
        ComponentRuntimeResolver,
        NoStableComponentVersionError,
    )

    monkeypatch.setattr(
        "backend.services.component_runtime_resolver.is_active_component_name",
        lambda name: True,
    )
    resolver = ComponentRuntimeResolver(component_version_session, project_root=tmp_path)

    with pytest.raises(NoStableComponentVersionError):
        await resolver.resolve_export_component(
            platform="shopee",
            data_domain="orders",
            sub_domain=None,
        )


@pytest.mark.asyncio
async def test_resolve_runtime_component_rejects_multiple_stable_versions(component_version_session, tmp_path: Path, monkeypatch):
    from backend.services.component_runtime_resolver import (
        ComponentRuntimeResolver,
        MultipleStableComponentVersionsError,
    )

    monkeypatch.setattr(
        "backend.services.component_runtime_resolver.is_active_component_name",
        lambda name: True,
    )
    component_version_session.add_all(
        [
            ComponentVersion(
                component_name="shopee/orders_export",
                version="1.0.0",
                file_path="modules/platforms/shopee/components/orders_export_v1_0_0.py",
                is_stable=True,
                is_active=True,
            ),
            ComponentVersion(
                component_name="shopee/orders_export",
                version="1.1.0",
                file_path="modules/platforms/shopee/components/orders_export_v1_1_0.py",
                is_stable=True,
                is_active=True,
            ),
        ]
    )
    await component_version_session.commit()

    resolver = ComponentRuntimeResolver(component_version_session, project_root=tmp_path)

    with pytest.raises(MultipleStableComponentVersionsError):
        await resolver.resolve_export_component(
            platform="shopee",
            data_domain="orders",
            sub_domain=None,
        )


@pytest.mark.asyncio
async def test_resolve_runtime_component_rejects_missing_file_path(component_version_session, tmp_path: Path, monkeypatch):
    from backend.services.component_runtime_resolver import (
        ComponentRuntimeResolver,
        MissingStableComponentFileError,
    )

    monkeypatch.setattr(
        "backend.services.component_runtime_resolver.is_active_component_name",
        lambda name: True,
    )
    component_version_session.add(
        ComponentVersion(
            component_name="shopee/orders_export",
            version="1.2.0",
            file_path="modules/platforms/shopee/components/orders_export_v1_2_0.py",
            is_stable=True,
            is_active=True,
        )
    )
    await component_version_session.commit()

    resolver = ComponentRuntimeResolver(component_version_session, project_root=tmp_path)

    with pytest.raises(MissingStableComponentFileError):
        await resolver.resolve_export_component(
            platform="shopee",
            data_domain="orders",
            sub_domain=None,
        )


@pytest.mark.asyncio
async def test_resolve_runtime_component_returns_manifest_for_single_stable(component_version_session, tmp_path: Path, monkeypatch):
    from backend.services.component_runtime_resolver import ComponentRuntimeResolver

    monkeypatch.setattr(
        "backend.services.component_runtime_resolver.is_active_component_name",
        lambda name: True,
    )
    relative_path = "modules/platforms/shopee/components/orders_export_v1_2_0.py"
    target_file = tmp_path / relative_path
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text("class Dummy:\n    pass\n", encoding="utf-8")

    component_version_session.add(
        ComponentVersion(
            component_name="shopee/orders_export",
            version="1.2.0",
            file_path=relative_path,
            is_stable=True,
            is_active=True,
        )
    )
    await component_version_session.commit()

    resolver = ComponentRuntimeResolver(component_version_session, project_root=tmp_path)
    manifest = await resolver.resolve_export_component(
        platform="shopee",
        data_domain="orders",
        sub_domain=None,
    )

    assert manifest.component_name == "shopee/orders_export"
    assert manifest.version == "1.2.0"
    assert manifest.file_path == relative_path
    assert manifest.platform == "shopee"
    assert manifest.component_type == "export"
    assert manifest.data_domain == "orders"
    assert manifest.sub_domain is None


@pytest.mark.asyncio
async def test_preflight_create_task_rejects_when_export_component_has_no_stable(collection_app, monkeypatch):
    from backend.models.database import get_async_db
    from backend.services.component_runtime_resolver import NoStableComponentVersionError

    class _FakeLoader:
        async def load_account_async(self, account_id, db):
            return {
                "account_id": account_id,
                "capabilities": {"orders": True},
            }

    class _RaisingResolver:
        @classmethod
        def from_async_session(cls, db):
            return cls()

        async def resolve_task_manifests(self, **kwargs):
            raise NoStableComponentVersionError("shopee/orders_export")

    async def _override_get_async_db():
        session = MagicMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        session.add = MagicMock()
        yield session

    monkeypatch.setattr(
        "backend.services.account_loader_service.get_account_loader_service",
        lambda: _FakeLoader(),
    )
    monkeypatch.setattr(
        "backend.services.component_runtime_resolver.ComponentRuntimeResolver",
        _RaisingResolver,
    )

    collection_app.dependency_overrides[get_async_db] = _override_get_async_db
    try:
        transport = ASGITransport(app=collection_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/collection/tasks",
                json={
                    "platform": "shopee",
                    "account_id": "acc-1",
                    "data_domains": ["orders"],
                    "granularity": "daily",
                    "date_range": {"start": "2026-03-01", "end": "2026-03-02"},
                    "parallel_mode": False,
                    "max_parallel": 3,
                },
            )

        assert response.status_code == 400
        assert "stable" in response.json()["detail"].lower()
    finally:
        collection_app.dependency_overrides.pop(get_async_db, None)


@pytest.mark.asyncio
async def test_scheduler_runtime_manifest_helper_uses_stable_resolver(monkeypatch):
    from backend.services.collection_scheduler import resolve_runtime_manifests_for_config

    expected = {
        "login": {"component_name": "shopee/login"},
        "exports_by_domain": {"orders": {"component_name": "shopee/orders_export"}},
    }

    class _FakeResolver:
        async def resolve_task_manifests(self, **kwargs):
            assert kwargs["platform"] == "shopee"
            assert kwargs["data_domains"] == ["orders"]
            assert kwargs["sub_domains"] is None
            return expected

    monkeypatch.setattr(
        "backend.services.collection_scheduler.ComponentRuntimeResolver.from_async_session",
        lambda db: _FakeResolver(),
    )

    config = SimpleNamespace(platform="shopee", data_domains=["orders"], sub_domains=None)
    manifests = await resolve_runtime_manifests_for_config(db=object(), config=config)

    assert manifests == expected


@pytest.mark.asyncio
async def test_resolve_task_manifests_supports_domain_scoped_subtypes(component_version_session, tmp_path: Path, monkeypatch):
    from backend.services.component_runtime_resolver import ComponentRuntimeResolver

    monkeypatch.setattr(
        "backend.services.component_runtime_resolver.is_active_component_name",
        lambda name: True,
    )
    monkeypatch.setattr(
        "backend.services.component_name_utils.DATA_DOMAIN_SUB_TYPES",
        {
            "services": ["agent", "ai_assistant"],
            "products": ["basic"],
        },
    )

    relative_files = {
        "shopee/login": "modules/platforms/shopee/components/login_v1_0_0.py",
        "shopee/orders_export": "modules/platforms/shopee/components/orders_export_v1_0_0.py",
        "shopee/services_agent_export": "modules/platforms/shopee/components/services_agent_export_v1_0_0.py",
        "shopee/products_basic_export": "modules/platforms/shopee/components/products_basic_export_v1_0_0.py",
    }

    for relative_path in relative_files.values():
        target_file = tmp_path / relative_path
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text("class Dummy:\n    pass\n", encoding="utf-8")

    component_version_session.add_all(
        [
            ComponentVersion(
                component_name=component_name,
                version="1.0.0",
                file_path=relative_path,
                is_stable=True,
                is_active=True,
            )
            for component_name, relative_path in relative_files.items()
        ]
    )
    await component_version_session.commit()

    resolver = ComponentRuntimeResolver(component_version_session, project_root=tmp_path)
    manifests = await resolver.resolve_task_manifests(
        platform="shopee",
        data_domains=["orders", "services", "products"],
        domain_subtypes={
            "services": ["agent"],
            "products": ["basic"],
        },
    )

    assert sorted(manifests["exports_by_domain"].keys()) == [
        "orders",
        "products:basic",
        "services:agent",
    ]


@pytest.mark.asyncio
async def test_runtime_resolver_supports_miaoshou_orders_subtypes(component_version_session, tmp_path: Path, monkeypatch):
    from backend.services.component_runtime_resolver import ComponentRuntimeResolver

    monkeypatch.setattr(
        "backend.services.component_runtime_resolver.is_active_component_name",
        lambda name: True,
    )
    monkeypatch.setattr(
        "backend.services.component_name_utils.DATA_DOMAIN_SUB_TYPES",
        {
            "orders": ["shopee", "tiktok"],
        },
    )

    relative_files = {
        "miaoshou/login": "modules/platforms/miaoshou/components/login.py",
        "miaoshou/orders_shopee_export": "modules/platforms/miaoshou/components/orders_shopee_export.py",
        "miaoshou/orders_tiktok_export": "modules/platforms/miaoshou/components/orders_tiktok_export.py",
    }

    for relative_path in relative_files.values():
        target_file = tmp_path / relative_path
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text("class Dummy:\n    pass\n", encoding="utf-8")

    component_version_session.add_all(
        [
            ComponentVersion(
                component_name=component_name,
                version="1.0.0",
                file_path=relative_path,
                is_stable=True,
                is_active=True,
            )
            for component_name, relative_path in relative_files.items()
        ]
    )
    await component_version_session.commit()

    resolver = ComponentRuntimeResolver(component_version_session, project_root=tmp_path)
    manifests = await resolver.resolve_task_manifests(
        platform="miaoshou",
        data_domains=["orders"],
        domain_subtypes={"orders": ["shopee", "tiktok"]},
    )

    assert sorted(manifests["exports_by_domain"].keys()) == [
        "orders:shopee",
        "orders:tiktok",
    ]


@pytest.mark.asyncio
async def test_runtime_resolver_rejects_non_active_component_name(component_version_session, tmp_path: Path):
    from backend.services.component_runtime_resolver import (
        ComponentRuntimeResolver,
        NoStableComponentVersionError,
    )

    relative_path = "modules/platforms/shopee/components/orders_export_v1_0_0.py"
    target_file = tmp_path / relative_path
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text("class Dummy:\n    pass\n", encoding="utf-8")

    component_version_session.add(
        ComponentVersion(
            component_name="shopee/orders_export",
            version="1.0.0",
            file_path=relative_path,
            is_stable=True,
            is_active=True,
        )
    )
    await component_version_session.commit()

    resolver = ComponentRuntimeResolver(component_version_session, project_root=tmp_path)

    with pytest.raises(NoStableComponentVersionError):
        await resolver.resolve_export_component(
            platform="shopee",
            data_domain="orders",
            sub_domain=None,
        )


@pytest.mark.asyncio
async def test_runtime_resolver_rejects_archive_only_stable_file(component_version_session, tmp_path: Path):
    from backend.services.component_runtime_resolver import (
        ComponentRuntimeResolver,
        MissingStableComponentFileError,
    )

    relative_path = "modules/platforms/miaoshou/archive/orders_shopee_export_v1_0_0.py"
    target_file = tmp_path / relative_path
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text("class Dummy:\n    pass\n", encoding="utf-8")

    component_version_session.add(
        ComponentVersion(
            component_name="miaoshou/orders_shopee_export",
            version="1.0.0",
            file_path=relative_path,
            is_stable=True,
            is_active=True,
        )
    )
    await component_version_session.commit()

    resolver = ComponentRuntimeResolver(component_version_session, project_root=tmp_path)

    with pytest.raises(MissingStableComponentFileError):
        await resolver.resolve_export_component(
            platform="miaoshou",
            data_domain="orders",
            sub_domain="shopee",
        )
