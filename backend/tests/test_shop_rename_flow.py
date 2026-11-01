"""改名联动（一次改名，三处同步，老数据不断）的端到端与契约测试。

改名固定六步：唯一性校验 -> 旧名转曾用名 -> 新名接管主别名
-> 同步 core.dim_shops.shop_name -> 同步 internal_code -> 入刷新队列一次。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.models.database import get_async_db
from modules.core.db import (
    DimPlatform,
    DimShop,
    MainAccount,
    ShopAccount,
    ShopAccountAlias,
    ShopAccountCapability,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTER = REPO_ROOT / "backend" / "domains" / "collection" / "routers" / "shop_accounts.py"
SERVICE = REPO_ROOT / "backend" / "services" / "shop_rename_service.py"


def test_rename_flow_is_wired():
    """改名必须走联动服务，且不得破坏现有的字段赋值与唯一性校验。

    注意：断言必须**跨文件**看「调用了具名服务 + 服务里做了什么」，
    不能在 ``update_shop_account`` 函数体内找字符串 —— 联动逻辑放在独立服务里，
    在函数体内找 ``former_name`` / ``dim_shops`` 永远找不到。
    """
    body = ROUTER.read_text(encoding="utf-8").split("async def update_shop_account", 1)[1].split("\nasync def ", 1)[0]

    # 1) 改名分支必须调用具名的联动服务
    assert "_apply_store_name_rename" in body, "update_shop_account 没有调用改名联动"

    # 2) 现有的通用赋值与 platform_shop_id 唯一性校验必须保留
    #    （前端每次编辑提交整个表单，改名分支若用 if/else 会把其它字段全丢掉）
    assert "setattr(record, field, value)" in body, "改名把原有的字段赋值分支弄丢了"
    assert "_assert_platform_shop_id_unique" in body, "改名把 platform_shop_id 唯一性校验弄丢了"

    # 3) 联动服务里必须有曾用名、主别名接管、dim_shops 同步
    assert SERVICE.exists(), "缺少改名联动服务 backend/services/shop_rename_service.py"
    service = SERVICE.read_text(encoding="utf-8")
    assert "former_name" in service, "改名联动没有写曾用名"
    assert "is_primary" in service, "改名联动没有处理主别名接管"
    assert "dim_shops" in service, "改名联动没有同步 core.dim_shops 展示名"


def test_rename_refresh_targets_cover_identity_recomputation():
    """改名后必须能重算归属。

    两个 monthly 物化视图是唯一会缓存归属结果的对象；它们在
    ``refresh_registry`` 里都依赖 ``semantic.shop_identity_resolution_candidates``，
    刷新计划会把候选视图先重建、再刷新物化视图。
    ``semantic.fact_orders_atomic`` / ``semantic.fact_analytics_atomic`` 是普通 VIEW
    （读时求值），候选视图一重建它们就自动是新归属 —— 不需要单独重建。
    """
    from backend.services.data_pipeline.refresh_registry import (
        PIPELINE_DEPENDENCIES,
        SQL_TARGET_PATHS,
    )

    assert "semantic.shop_identity_resolution_candidates" in SQL_TARGET_PATHS
    for target in (
        "semantic.fact_orders_monthly_atomic_mv",
        "semantic.fact_analytics_monthly_atomic_mv",
    ):
        assert "semantic.shop_identity_resolution_candidates" in (
            PIPELINE_DEPENDENCIES.get(target, [])
        ), f"{target} 不再依赖候选视图 -> 改名后归属不会重算"


# ---------------------------------------------------------------------------
# 端到端：真的走一次改名
# ---------------------------------------------------------------------------


class _FakeBusinessOverviewCache:
    def __init__(self, calls):
        self.calls = calls

    async def invalidate_dashboard_business_overview(self):
        self.calls.append("invalidate_dashboard_business_overview")
        return 0


class _FakeRefreshQueueService:
    calls: list = []

    def __init__(self, db):
        self.db = db

    async def enqueue_refresh(self, **kwargs):
        self.calls.append(kwargs)
        return type("Task", (), {"job_id": "refresh-test"})()


@pytest_asyncio.fixture
async def rename_session_factory():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.exec_driver_sql("ATTACH DATABASE ':memory:' AS core")
        await conn.run_sync(MainAccount.__table__.create)
        await conn.run_sync(ShopAccount.__table__.create)
        await conn.run_sync(ShopAccountAlias.__table__.create)
        await conn.run_sync(ShopAccountCapability.__table__.create)
        await conn.run_sync(DimPlatform.__table__.create)
        await conn.run_sync(DimShop.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _seed_rename_data(session_factory, *, with_dim_shop=True):
    async with session_factory() as session:
        session.add(
            MainAccount(
                platform="tiktok",
                main_account_id="main-tiktok",
                username="demo-user",
                password_encrypted="enc:demo",
                enabled=True,
            )
        )
        session.add(
            ShopAccount(
                platform="tiktok",
                shop_account_id="tiktok_sg_daone_mall_local",
                main_account_id="main-tiktok",
                store_name="DAONE Mall",
                shop_region="SG",
                platform_shop_id="1234567",
            )
        )
        session.add(
            ShopAccount(
                platform="tiktok",
                shop_account_id="tiktok_sg_other_local",
                main_account_id="main-tiktok",
                store_name="Other Shop",
                shop_region="SG",
            )
        )
        if with_dim_shop:
            session.add(
                DimPlatform(platform_code="tiktok", name="TikTok")
            )
            session.add(
                DimShop(
                    platform_code="tiktok",
                    shop_id="tiktok_sg_daone_mall_local",
                    shop_name="DAONE Mall",
                    region="SG",
                )
            )
        await session.commit()


@pytest_asyncio.fixture
async def rename_client(rename_session_factory, monkeypatch):
    from backend.domains.collection.routers import shop_accounts as shop_accounts_router

    refresh_calls: list[dict] = []
    cache_calls: list[str] = []

    class _RecordingRefreshQueueService(_FakeRefreshQueueService):
        calls = refresh_calls

    monkeypatch.setattr(
        "backend.domains.collection.routers.shop_accounts.RefreshQueueService",
        _RecordingRefreshQueueService,
        raising=False,
    )
    monkeypatch.setattr(
        "backend.domains.collection.routers.shop_accounts.get_cache_service",
        lambda: _FakeBusinessOverviewCache(cache_calls),
        raising=False,
    )

    app = FastAPI()
    app.include_router(shop_accounts_router.router, prefix="/api")

    async def override_get_async_db():
        async with rename_session_factory() as session:
            yield session

    async def override_current_user():
        return type(
            "AdminUser",
            (),
            {
                "user_id": 1,
                "id": 1,
                "username": "admin",
                "is_active": True,
                "status": "active",
                "is_superuser": True,
                "roles": [type("Role", (), {"role_code": "admin", "role_name": "admin"})()],
            },
        )()

    app.dependency_overrides[get_async_db] = override_get_async_db
    from backend.dependencies.auth import get_current_user

    app.dependency_overrides[get_current_user] = override_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        client.refresh_calls = refresh_calls
        client.cache_calls = cache_calls
        yield client


@pytest.mark.asyncio
async def test_rename_end_to_end_syncs_three_places_and_keeps_other_fields(
    rename_client, rename_session_factory
):
    """一次改名，三处同步；同一次 payload 的其它字段也必须落库。"""
    await _seed_rename_data(rename_session_factory)

    response = await rename_client.put(
        "/api/shop-accounts/tiktok_sg_daone_mall_local",
        json={
            "store_name": "FIORO",
            "shop_region": "SG",
            "enabled": False,
            "notes": "改名备注",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["store_name"] == "FIORO"
    # 前端整表提交 -> 其它字段不能被改名分支吃掉
    assert payload["enabled"] is False
    assert payload["notes"] == "改名备注"
    assert payload["shop_region"] == "SG"

    async with rename_session_factory() as session:
        aliases = (await session.execute(select(ShopAccountAlias))).scalars().all()
        by_value = {alias.alias_value: alias for alias in aliases}

        # 1) 旧名转曾用名：仍 active（老数据继续命中），但不再是主别名
        former = by_value["DAONE Mall"]
        assert former.is_active is True
        assert former.is_primary is False
        assert former.alias_type == "former_name"

        # 2) 新名接管主别名
        primary = by_value["FIORO"]
        assert primary.is_primary is True
        assert primary.is_active is True

        # 3) 展示名同步到 core.dim_shops
        dim_shop = (
            await session.execute(
                select(DimShop).where(
                    DimShop.platform_code == "tiktok",
                    DimShop.shop_id == "tiktok_sg_daone_mall_local",
                )
            )
        ).scalar_one()
        assert dim_shop.shop_name == "FIORO"

        # 4) 店铺账号自身落库
        shop = (
            await session.execute(
                select(ShopAccount).where(
                    ShopAccount.shop_account_id == "tiktok_sg_daone_mall_local"
                )
            )
        ).scalar_one()
        assert shop.store_name == "FIORO"

    # 5) 刷新队列只入队一次，且带上 store_name（归属重算由这一次入队覆盖）
    assert len(rename_client.refresh_calls) == 1
    changed_fields = rename_client.refresh_calls[0]["context"]["changed_fields"]
    assert "store_name" in changed_fields


@pytest.mark.asyncio
async def test_rename_keeps_old_alias_active_so_old_data_still_matches(
    rename_client, rename_session_factory
):
    """曾用名仍参与匹配 —— 它就是别名表里一条 active 记录。"""
    await _seed_rename_data(rename_session_factory)

    response = await rename_client.put(
        "/api/shop-accounts/tiktok_sg_daone_mall_local",
        json={"store_name": "FIORO"},
    )
    assert response.status_code == 200, response.text

    async with rename_session_factory() as session:
        active_aliases = (
            await session.execute(
                select(ShopAccountAlias).where(ShopAccountAlias.is_active == True)  # noqa: E712
            )
        ).scalars().all()
        active_values = {alias.alias_value for alias in active_aliases}

    assert "DAONE Mall" in active_values, "旧名必须仍是 active 别名，老数据才能继续命中"
    assert "FIORO" in active_values


@pytest.mark.asyncio
async def test_rename_with_same_normalized_value_skips_alias_write(
    rename_client, rename_session_factory
):
    """DAONE Mall -> DAONE MALL：规范化后相同 -> 不写别名（避免撞唯一约束）。"""
    await _seed_rename_data(rename_session_factory)

    response = await rename_client.put(
        "/api/shop-accounts/tiktok_sg_daone_mall_local",
        json={"store_name": "DAONE MALL"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["store_name"] == "DAONE MALL"

    async with rename_session_factory() as session:
        aliases = (await session.execute(select(ShopAccountAlias))).scalars().all()
        assert aliases == [], "规范化后相同的改名不应该产生别名记录"


@pytest.mark.asyncio
async def test_rename_rejects_name_already_used_in_same_main_account(
    rename_client, rename_session_factory
):
    await _seed_rename_data(rename_session_factory)

    response = await rename_client.put(
        "/api/shop-accounts/tiktok_sg_daone_mall_local",
        json={"store_name": "Other Shop"},
    )

    assert response.status_code == 409, response.text
    assert "Other Shop" in response.json()["detail"]


@pytest.mark.asyncio
async def test_rename_rejects_alias_owned_by_another_shop(
    rename_client, rename_session_factory
):
    """新名已被别的店占用（同平台同区域）-> 409，不静默覆盖。"""
    await _seed_rename_data(rename_session_factory)

    async with rename_session_factory() as session:
        other = (
            await session.execute(
                select(ShopAccount).where(
                    ShopAccount.shop_account_id == "tiktok_sg_other_local"
                )
            )
        ).scalar_one()
        session.add(
            ShopAccountAlias(
                shop_account_id=other.id,
                platform="tiktok",
                alias_value="FIORO",
                alias_normalized="fioro",
                alias_type="claimed",
                shop_region="SG",
                is_primary=True,
                is_active=True,
            )
        )
        await session.commit()

    response = await rename_client.put(
        "/api/shop-accounts/tiktok_sg_daone_mall_local",
        json={"store_name": "FIORO"},
    )

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert "FIORO" in detail
    assert "tiktok_sg_other_local" in detail


@pytest.mark.asyncio
async def test_rename_syncs_internal_code_only_when_auto_generated(
    rename_client, rename_session_factory
):
    """自动生成的标准名跟着改名走；人工改过的不动。"""
    await _seed_rename_data(rename_session_factory)

    async with rename_session_factory() as session:
        shop = (
            await session.execute(
                select(ShopAccount).where(
                    ShopAccount.shop_account_id == "tiktok_sg_daone_mall_local"
                )
            )
        ).scalar_one()
        shop.internal_code = "DAONE_MALL_SG"
        await session.commit()

    response = await rename_client.put(
        "/api/shop-accounts/tiktok_sg_daone_mall_local",
        json={"store_name": "FIORO"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["internal_code"] == "FIORO_SG"

    async with rename_session_factory() as session:
        shop = (
            await session.execute(
                select(ShopAccount).where(
                    ShopAccount.shop_account_id == "tiktok_sg_daone_mall_local"
                )
            )
        ).scalar_one()
        shop.internal_code = "CUSTOM_BY_HUMAN"
        await session.commit()

    response = await rename_client.put(
        "/api/shop-accounts/tiktok_sg_daone_mall_local",
        json={"store_name": "FIORO2"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["internal_code"] == "CUSTOM_BY_HUMAN"


@pytest.mark.asyncio
async def test_rename_without_dim_shop_row_does_not_fail(
    rename_client, rename_session_factory
):
    """core.dim_shops 里没有对应行时：不新建、只记日志、改名本身仍要成功。"""
    await _seed_rename_data(rename_session_factory, with_dim_shop=False)

    response = await rename_client.put(
        "/api/shop-accounts/tiktok_sg_daone_mall_local",
        json={"store_name": "FIORO"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["store_name"] == "FIORO"


# ---------------------------------------------------------------------------
# 别名唯一性的应用层友好预检（库层约束已由第一批落地）
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def alias_api_client(rename_session_factory, monkeypatch):
    from backend.domains.collection.routers import (
        shop_account_aliases as alias_router,
    )

    monkeypatch.setattr(
        "backend.domains.collection.routers.shop_account_aliases.RefreshQueueService",
        _FakeRefreshQueueService,
        raising=False,
    )
    monkeypatch.setattr(
        "backend.domains.collection.routers.shop_account_aliases.get_cache_service",
        lambda: _FakeBusinessOverviewCache([]),
        raising=False,
    )

    app = FastAPI()
    app.include_router(alias_router.router, prefix="/api")

    async def override_get_async_db():
        async with rename_session_factory() as session:
            yield session

    async def override_current_user():
        return type(
            "AdminUser",
            (),
            {
                "user_id": 1,
                "id": 1,
                "username": "admin",
                "is_active": True,
                "status": "active",
                "is_superuser": True,
                "roles": [type("Role", (), {"role_code": "admin", "role_name": "admin"})()],
            },
        )()

    app.dependency_overrides[get_async_db] = override_get_async_db
    from backend.dependencies.auth import get_current_user

    app.dependency_overrides[get_current_user] = override_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


async def _seed_two_regions(session_factory):
    """两个店：同平台，区域不同（SG / MY）。"""
    async with session_factory() as session:
        session.add(
            MainAccount(
                platform="tiktok",
                main_account_id="main-tiktok",
                username="demo-user",
                password_encrypted="enc:demo",
                enabled=True,
            )
        )
        session.add(
            ShopAccount(
                platform="tiktok",
                shop_account_id="tiktok_sg_fioro_local",
                main_account_id="main-tiktok",
                store_name="FIORO SG",
                shop_region="SG",
            )
        )
        session.add(
            ShopAccount(
                platform="tiktok",
                shop_account_id="tiktok_my_fioro_local",
                main_account_id="main-tiktok",
                store_name="FIORO MY",
                shop_region="MY",
            )
        )
        await session.commit()


async def _seed_same_region(session_factory):
    """两个店：同平台，区域相同（都是 SG）—— 别名只能属于其中一个。"""
    async with session_factory() as session:
        session.add(
            MainAccount(
                platform="tiktok",
                main_account_id="main-tiktok",
                username="demo-user",
                password_encrypted="enc:demo",
                enabled=True,
            )
        )
        session.add(
            ShopAccount(
                platform="tiktok",
                shop_account_id="tiktok_sg_fioro_local",
                main_account_id="main-tiktok",
                store_name="FIORO SG",
                shop_region="SG",
            )
        )
        session.add(
            ShopAccount(
                platform="tiktok",
                shop_account_id="tiktok_sg_fioro_other_local",
                main_account_id="main-tiktok",
                store_name="FIORO SG Second",
                shop_region="SG",
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_claim_alias_rejects_label_owned_by_another_shop_in_same_region(
    alias_api_client, rename_session_factory
):
    """同一个平台 + 同一个区域，别名只能属于一个店 -> 409 且说清占用方。"""
    await _seed_same_region(rename_session_factory)

    first = await alias_api_client.post(
        "/api/shop-account-aliases/claim",
        json={
            "platform": "tiktok",
            "alias_value": "FIORO",
            "shop_account_id": "tiktok_sg_fioro_local",
        },
    )
    assert first.status_code == 200, first.text

    second = await alias_api_client.post(
        "/api/shop-account-aliases/claim",
        json={
            "platform": "tiktok",
            "alias_value": "FIORO",
            "shop_account_id": "tiktok_sg_fioro_other_local",
        },
    )

    assert second.status_code == 409, second.text
    detail = second.json()["detail"]
    assert "FIORO" in detail
    assert "tiktok_sg_fioro_local" in detail


@pytest.mark.asyncio
async def test_claim_alias_allows_same_label_in_different_region(
    alias_api_client, rename_session_factory
):
    """同名品牌店按区域分流：SG 与 MY 可以各自认领同一个标签。"""
    await _seed_two_regions(rename_session_factory)

    sg_response = await alias_api_client.post(
        "/api/shop-account-aliases/claim",
        json={
            "platform": "tiktok",
            "alias_value": "FIORO",
            "shop_account_id": "tiktok_sg_fioro_local",
        },
    )
    assert sg_response.status_code == 200, sg_response.text

    my_response = await alias_api_client.post(
        "/api/shop-account-aliases/claim",
        json={
            "platform": "tiktok",
            "alias_value": "FIORO",
            "shop_account_id": "tiktok_my_fioro_local",
        },
    )

    assert my_response.status_code == 200, my_response.text
    assert my_response.json()["is_primary"] is True
