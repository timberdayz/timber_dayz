from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.routers.component_versions import (
    batch_register_python_components,
    list_versions,
)
from backend.schemas.component_version import BatchRegisterRequest
from modules.core.db import ComponentVersion


@pytest_asyncio.fixture
async def component_version_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.exec_driver_sql("ATTACH DATABASE ':memory:' AS core")
        await conn.run_sync(ComponentVersion.__table__.create)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(ComponentVersion.__table__.drop)

    await engine.dispose()


def _write_component(path: Path, class_name: str, component_type: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "class %s:" % class_name,
                f"    component_type = {component_type!r}",
                "",
            ]
        ),
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_batch_register_only_registers_canonical_components(
    component_version_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "backend.routers.component_versions.is_active_component_name",
        lambda name: name in {"shopee/login", "shopee/products_export"},
    )
    project_root = tmp_path
    fake_router_file = project_root / "backend" / "routers" / "component_versions.py"
    fake_router_file.parent.mkdir(parents=True, exist_ok=True)
    fake_router_file.write_text("# fake router marker\n", encoding="utf-8")
    monkeypatch.setattr(
        "backend.routers.component_versions.__file__", str(fake_router_file)
    )

    shopee_dir = project_root / "modules" / "platforms" / "shopee" / "components"
    _write_component(shopee_dir / "login.py", "ShopeeLogin", "login")
    _write_component(
        shopee_dir / "products_export.py", "ShopeeProductsExport", "export"
    )
    _write_component(
        shopee_dir / "recorder_test_login.py", "ShopeeRecorderTestLogin", "login"
    )
    _write_component(shopee_dir / "export.py", "ShopeeExporterComponent", "export")
    _write_component(shopee_dir / "analytics_config.py", "AnalyticsSelectors", "other")

    response = await batch_register_python_components(
        request=BatchRegisterRequest(platform="shopee"),
        db=component_version_session,
        http_request=None,
    )

    result = await component_version_session.execute(select(ComponentVersion))
    rows = result.scalars().all()
    names = sorted(v.component_name for v in rows)

    assert response.success is True
    assert names == [
        "shopee/login",
        "shopee/products_export",
    ]


@pytest.mark.asyncio
async def test_batch_register_uses_shop_switch_as_tiktok_canonical_entry(
    component_version_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "backend.routers.component_versions.is_active_component_name",
        lambda name: name in {"tiktok/login", "tiktok/shop_switch"},
    )
    project_root = tmp_path
    fake_router_file = project_root / "backend" / "routers" / "component_versions.py"
    fake_router_file.parent.mkdir(parents=True, exist_ok=True)
    fake_router_file.write_text("# fake router marker\n", encoding="utf-8")
    monkeypatch.setattr("backend.routers.component_versions.__file__", str(fake_router_file))

    tiktok_dir = project_root / "modules" / "platforms" / "tiktok" / "components"
    _write_component(tiktok_dir / "login.py", "TiktokLogin", "login")
    _write_component(tiktok_dir / "shop_switch.py", "TiktokShopSwitch", "shop_switch")
    _write_component(tiktok_dir / "shop_selector.py", "TiktokShopSelector", "shop_selector")

    response = await batch_register_python_components(
        request=BatchRegisterRequest(platform="tiktok"),
        db=component_version_session,
        http_request=None,
    )

    result = await component_version_session.execute(select(ComponentVersion))
    rows = result.scalars().all()
    names = sorted(v.component_name for v in rows)

    assert response.success is True
    assert names == [
        "tiktok/login",
        "tiktok/shop_switch",
    ]


@pytest.mark.asyncio
async def test_batch_register_discovers_tiktok_domain_export_entries(
    component_version_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "backend.routers.component_versions.is_active_component_name",
        lambda name: name
        in {
            "tiktok/analytics_export",
            "tiktok/services_agent_export",
        },
    )
    project_root = tmp_path
    fake_router_file = project_root / "backend" / "routers" / "component_versions.py"
    fake_router_file.parent.mkdir(parents=True, exist_ok=True)
    fake_router_file.write_text("# fake router marker\n", encoding="utf-8")
    monkeypatch.setattr("backend.routers.component_versions.__file__", str(fake_router_file))

    tiktok_dir = project_root / "modules" / "platforms" / "tiktok" / "components"
    _write_component(tiktok_dir / "analytics_export.py", "TiktokAnalyticsExport", "export")
    _write_component(
        tiktok_dir / "services_agent_export.py",
        "TiktokServicesAgentExport",
        "export",
    )

    response = await batch_register_python_components(
        request=BatchRegisterRequest(platform="tiktok"),
        db=component_version_session,
        http_request=None,
    )

    result = await component_version_session.execute(select(ComponentVersion))
    rows = result.scalars().all()
    names = sorted(v.component_name for v in rows)

    assert response.success is True
    assert names == [
        "tiktok/analytics_export",
        "tiktok/services_agent_export",
    ]


@pytest.mark.asyncio
async def test_list_versions_returns_all_platform_components(
    component_version_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "backend.routers.component_versions.list_active_component_names",
        lambda: ["shopee/login", "shopee/products_export"],
    )
    now = datetime.now(timezone.utc)
    component_version_session.add_all(
        [
            ComponentVersion(
                component_name="shopee/login",
                version="1.0.0",
                file_path="modules/platforms/shopee/components/login.py",
                is_stable=False,
                is_active=True,
                created_at=now,
                updated_at=now,
            ),
            ComponentVersion(
                component_name="shopee/products_export",
                version="1.0.0",
                file_path="modules/platforms/shopee/components/products_export.py",
                is_stable=False,
                is_active=True,
                created_at=now,
                updated_at=now,
            ),
            ComponentVersion(
                component_name="shopee/recorder_test_login",
                version="1.0.0",
                file_path="modules/platforms/shopee/components/recorder_test_login.py",
                is_stable=False,
                is_active=True,
                created_at=now,
                updated_at=now,
            ),
            ComponentVersion(
                component_name="shopee/export",
                version="1.0.0",
                file_path="modules/platforms/shopee/components/export.py",
                is_stable=False,
                is_active=True,
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    await component_version_session.commit()

    response = await list_versions(
        platform="shopee",
        component_type=None,
        status=None,
        page=1,
        page_size=20,
        db=component_version_session,
        request=None,
    )

    names = sorted(item.component_name for item in response.data)

    assert names == [
        "shopee/login",
        "shopee/products_export",
    ]


@pytest.mark.asyncio
async def test_list_versions_collapses_multiple_versions_to_single_working_row(
    component_version_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "backend.routers.component_versions.list_active_component_names",
        lambda: ["shopee/login"],
    )
    older = datetime(2026, 3, 20, tzinfo=timezone.utc)
    newer = datetime(2026, 3, 21, tzinfo=timezone.utc)
    component_version_session.add_all(
        [
            ComponentVersion(
                component_name="shopee/login",
                version="1.0.0",
                file_path="modules/platforms/shopee/components/login_v1_0_0.py",
                is_stable=False,
                is_active=True,
                created_at=older,
                updated_at=older,
            ),
            ComponentVersion(
                component_name="shopee/login",
                version="1.0.1",
                file_path="modules/platforms/shopee/components/login_v1_0_1.py",
                is_stable=False,
                is_active=True,
                created_at=newer,
                updated_at=newer,
            ),
        ]
    )
    await component_version_session.commit()

    response = await list_versions(
        platform="shopee",
        component_type=None,
        status=None,
        page=1,
        page_size=20,
        db=component_version_session,
        request=None,
    )

    assert len(response.data) == 1
    assert response.total == 1
    assert response.data[0].component_name == "shopee/login"
    assert response.data[0].version == "1.0.1"


@pytest.mark.asyncio
async def test_list_versions_component_type_export_matches_domain_exports(
    component_version_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "backend.routers.component_versions.list_active_component_names",
        lambda: ["shopee/products_export", "shopee/login"],
    )
    now = datetime.now(timezone.utc)
    component_version_session.add_all(
        [
            ComponentVersion(
                component_name="shopee/products_export",
                version="1.0.0",
                file_path="modules/platforms/shopee/components/products_export.py",
                is_stable=False,
                is_active=True,
                created_at=now,
                updated_at=now,
            ),
            ComponentVersion(
                component_name="shopee/login",
                version="1.0.0",
                file_path="modules/platforms/shopee/components/login.py",
                is_stable=False,
                is_active=True,
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    await component_version_session.commit()

    response = await list_versions(
        platform="shopee",
        component_type="export",
        status=None,
        page=1,
        page_size=20,
        db=component_version_session,
        request=None,
    )

    names = [item.component_name for item in response.data]

    assert names == ["shopee/products_export"]


@pytest.mark.asyncio
async def test_list_versions_platform_only_does_not_apply_canonical_whitelist(
    component_version_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "backend.routers.component_versions.list_active_component_names",
        lambda: ["miaoshou/login"],
    )
    now = datetime.now(timezone.utc)
    component_version_session.add_all(
        [
            ComponentVersion(
                component_name="miaoshou/login",
                version="1.0.0",
                file_path="modules/platforms/miaoshou/components/login.py",
                is_stable=False,
                is_active=True,
                created_at=now,
                updated_at=now,
            ),
            ComponentVersion(
                component_name="miaoshou/miaoshou_login",
                version="1.0.0",
                file_path="modules/platforms/miaoshou/components/miaoshou_login.py",
                is_stable=False,
                is_active=True,
                created_at=now,
                updated_at=now,
            ),
            ComponentVersion(
                component_name="miaoshou/login_v1_0_1",
                version="1.0.1",
                file_path="modules/platforms/miaoshou/components/login_v1_0_1.py",
                is_stable=False,
                is_active=True,
                created_at=now,
                updated_at=now,
            ),
            ComponentVersion(
                component_name="miaoshou/orders_config",
                version="1.0.0",
                file_path="modules/platforms/miaoshou/components/orders_config.py",
                is_stable=False,
                is_active=True,
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    await component_version_session.commit()

    response = await list_versions(
        platform="miaoshou",
        component_type=None,
        status=None,
        page=1,
        page_size=20,
        db=component_version_session,
        request=None,
    )

    names = sorted(item.component_name for item in response.data)

    assert names == [
        "miaoshou/login",
    ]


@pytest.mark.asyncio
async def test_list_versions_defaults_to_active_manifest_components_only(
    component_version_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    now = datetime.now(timezone.utc)
    component_version_session.add_all(
        [
            ComponentVersion(
                component_name="miaoshou/login",
                version="1.0.3",
                file_path="modules/platforms/miaoshou/components/login_v1_0_3.py",
                is_stable=True,
                is_active=True,
                created_at=now,
                updated_at=now,
            ),
            ComponentVersion(
                component_name="shopee/orders_export",
                version="1.0.0",
                file_path="modules/platforms/shopee/components/orders_export.py",
                is_stable=False,
                is_active=True,
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    await component_version_session.commit()

    monkeypatch.setattr(
        "backend.routers.component_versions.list_active_component_names",
        lambda: ["miaoshou/login"],
    )

    response = await list_versions(
        platform=None,
        component_type=None,
        status=None,
        page=1,
        page_size=20,
        db=component_version_session,
        request=None,
    )

    assert [item.component_name for item in response.data] == ["miaoshou/login"]


@pytest.mark.asyncio
async def test_batch_register_includes_split_miaoshou_order_exports_when_present(
    component_version_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "backend.routers.component_versions.is_active_component_name",
        lambda name: name in {"miaoshou/login", "miaoshou/orders_shopee_export", "miaoshou/orders_tiktok_export"},
    )
    project_root = tmp_path
    fake_router_file = project_root / "backend" / "routers" / "component_versions.py"
    fake_router_file.parent.mkdir(parents=True, exist_ok=True)
    fake_router_file.write_text("# fake router marker\n", encoding="utf-8")
    monkeypatch.setattr("backend.routers.component_versions.__file__", str(fake_router_file))

    miaoshou_dir = project_root / "modules" / "platforms" / "miaoshou" / "components"
    _write_component(miaoshou_dir / "login.py", "MiaoshouLogin", "login")
    _write_component(miaoshou_dir / "orders_shopee_export.py", "MiaoshouOrdersShopeeExport", "export")
    _write_component(miaoshou_dir / "orders_tiktok_export.py", "MiaoshouOrdersTiktokExport", "export")
    _write_component(miaoshou_dir / "orders_config.py", "OrdersSelectors", "other")

    response = await batch_register_python_components(
        request=BatchRegisterRequest(platform="miaoshou"),
        db=component_version_session,
        http_request=None,
    )

    result = await component_version_session.execute(select(ComponentVersion))
    rows = result.scalars().all()
    names = sorted(v.component_name for v in rows)

    assert response.success is True
    assert names == [
        "miaoshou/login",
        "miaoshou/orders_shopee_export",
        "miaoshou/orders_tiktok_export",
    ]


@pytest.mark.asyncio
async def test_batch_register_accepts_any_domain_export_filename_by_rule(
    component_version_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "backend.routers.component_versions.is_active_component_name",
        lambda name: name == "shopee/services_agent_export",
    )
    project_root = tmp_path
    fake_router_file = project_root / "backend" / "routers" / "component_versions.py"
    fake_router_file.parent.mkdir(parents=True, exist_ok=True)
    fake_router_file.write_text("# fake router marker\n", encoding="utf-8")
    monkeypatch.setattr("backend.routers.component_versions.__file__", str(fake_router_file))

    shopee_dir = project_root / "modules" / "platforms" / "shopee" / "components"
    _write_component(shopee_dir / "services_agent_export.py", "ShopeeServicesAgentExport", "export")
    _write_component(shopee_dir / "services_config.py", "ServicesSelectors", "other")

    response = await batch_register_python_components(
        request=BatchRegisterRequest(platform="shopee"),
        db=component_version_session,
        http_request=None,
    )

    result = await component_version_session.execute(select(ComponentVersion))
    rows = result.scalars().all()
    names = sorted(v.component_name for v in rows)

    assert response.success is True
    assert names == ["shopee/services_agent_export"]


@pytest.mark.asyncio
async def test_batch_register_skips_legacy_generic_export_file(
    component_version_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "backend.routers.component_versions.is_active_component_name",
        lambda name: name == "tiktok/orders_export",
    )
    project_root = tmp_path
    fake_router_file = project_root / "backend" / "routers" / "component_versions.py"
    fake_router_file.parent.mkdir(parents=True, exist_ok=True)
    fake_router_file.write_text("# fake router marker\n", encoding="utf-8")
    monkeypatch.setattr("backend.routers.component_versions.__file__", str(fake_router_file))

    tiktok_dir = project_root / "modules" / "platforms" / "tiktok" / "components"
    _write_component(tiktok_dir / "export.py", "TiktokExport", "export")
    _write_component(tiktok_dir / "orders_export.py", "TiktokOrdersExport", "export")

    response = await batch_register_python_components(
        request=BatchRegisterRequest(platform="tiktok"),
        db=component_version_session,
        http_request=None,
    )

    result = await component_version_session.execute(select(ComponentVersion))
    rows = result.scalars().all()
    names = sorted(v.component_name for v in rows)

    assert response.success is True
    assert names == ["tiktok/orders_export"]


@pytest.mark.asyncio
async def test_batch_register_skips_non_active_canonical_files_by_default(
    component_version_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    project_root = tmp_path
    fake_router_file = project_root / "backend" / "routers" / "component_versions.py"
    fake_router_file.parent.mkdir(parents=True, exist_ok=True)
    fake_router_file.write_text("# fake router marker\n", encoding="utf-8")
    monkeypatch.setattr("backend.routers.component_versions.__file__", str(fake_router_file))
    monkeypatch.setattr(
        "backend.routers.component_versions.is_active_component_name",
        lambda name: name == "miaoshou/login",
    )

    miaoshou_dir = project_root / "modules" / "platforms" / "miaoshou" / "components"
    _write_component(miaoshou_dir / "login.py", "MiaoshouLogin", "login")
    _write_component(miaoshou_dir / "orders_export.py", "MiaoshouOrdersExport", "export")

    response = await batch_register_python_components(
        request=BatchRegisterRequest(platform="miaoshou"),
        db=component_version_session,
        http_request=None,
    )

    result = await component_version_session.execute(select(ComponentVersion))
    rows = result.scalars().all()
    names = sorted(v.component_name for v in rows)

    assert response.success is True
    assert names == ["miaoshou/login"]
