import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.models.database import get_async_db
from backend.routers import main_accounts, shop_account_aliases, shop_accounts
from modules.core.db import MainAccount, ShopAccount, ShopAccountAlias, ShopAccountCapability


class _FakeBusinessOverviewCache:
    def __init__(self, calls):
        self.calls = calls

    async def invalidate_dashboard_business_overview(self):
        self.calls.append("invalidate_dashboard_business_overview")
        return 0


class _FakeRefreshQueueService:
    calls = []

    def __init__(self, db):
        self.db = db

    async def enqueue_refresh(self, **kwargs):
        self.calls.append(kwargs)
        return type("Task", (), {"job_id": "refresh-test"})()


@pytest_asyncio.fixture
async def alias_client(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.exec_driver_sql("ATTACH DATABASE ':memory:' AS core")
        await conn.run_sync(MainAccount.__table__.create)
        await conn.run_sync(ShopAccount.__table__.create)
        await conn.run_sync(ShopAccountAlias.__table__.create)
        await conn.run_sync(ShopAccountCapability.__table__.create)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    app = FastAPI()
    app.include_router(main_accounts.router, prefix="/api")
    app.include_router(shop_accounts.router, prefix="/api")
    app.include_router(shop_account_aliases.router, prefix="/api")

    async def override_get_async_db():
        async with session_factory() as session:
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
    monkeypatch.setattr(
        "backend.routers.main_accounts.get_encryption_service",
        lambda: type("Enc", (), {"encrypt_password": lambda self, value: f"enc:{value}"})(),
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    await engine.dispose()


async def _seed_shop_account(alias_client):
    await alias_client.post(
        "/api/main-accounts",
        json={
            "platform": "shopee",
            "main_account_id": "hongxikeji:main",
            "username": "demo-user",
            "password": "plain-password",
            "enabled": True,
        },
    )
    await alias_client.post(
        "/api/shop-accounts",
        json={
            "platform": "shopee",
            "shop_account_id": "shopee_sg_hongxi_local",
            "main_account_id": "hongxikeji:main",
            "store_name": "HongXi SG",
            "enabled": True,
        },
    )


@pytest.mark.asyncio
async def test_claim_unmatched_alias_binds_to_shop_account(alias_client):
    await _seed_shop_account(alias_client)

    response = await alias_client.post(
        "/api/shop-account-aliases/claim",
        json={
            "platform": "shopee",
            "alias_value": "HongXi SG Raw",
            "shop_account_id": "shopee_sg_hongxi_local",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["platform"] == "shopee"
    assert payload["alias_value"] == "HongXi SG Raw"
    assert payload["is_primary"] is True

    shop_accounts_response = await alias_client.get("/api/shop-accounts")
    assert shop_accounts_response.status_code == 200
    assert shop_accounts_response.json()[0]["account_alias"] == "HongXi SG Raw"


@pytest.mark.asyncio
async def test_claim_alias_rejects_collection_source_shop_account(alias_client):
    await alias_client.post(
        "/api/main-accounts",
        json={
            "platform": "shopee",
            "main_account_id": "hongxikeji:collection-main",
            "username": "demo-user",
            "password": "plain-password",
            "enabled": True,
        },
    )
    create_shop = await alias_client.post(
        "/api/shop-accounts",
        json={
            "platform": "shopee",
            "shop_account_id": "shopee_collection_source",
            "main_account_id": "hongxikeji:collection-main",
            "store_name": "Collection Source",
            "business_role": "collection_source",
            "enabled": True,
        },
    )
    assert create_shop.status_code == 200

    response = await alias_client.post(
        "/api/shop-account-aliases/claim",
        json={
            "platform": "shopee",
            "alias_value": "Collection Source Raw",
            "shop_account_id": "shopee_collection_source",
        },
    )

    assert response.status_code in {400, 422}
    assert "collection_source" in response.json()["detail"]


@pytest.mark.asyncio
async def test_claim_alias_repairs_mojibake_value(alias_client):
    await _seed_shop_account(alias_client)
    expected = "\u0033\u0043\u5e97"
    mojibake = expected.encode("utf-8").decode("latin1")

    response = await alias_client.post(
        "/api/shop-account-aliases/claim",
        json={
            "platform": "shopee",
            "alias_value": mojibake,
            "shop_account_id": "shopee_sg_hongxi_local",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["alias_value"] == expected
    assert payload["is_primary"] is True


@pytest.mark.asyncio
async def test_claim_alias_allows_new_primary_after_clear(alias_client):
    await _seed_shop_account(alias_client)

    first_response = await alias_client.post(
        "/api/shop-account-aliases/claim",
        json={
            "platform": "shopee",
            "alias_value": "HongXi SG Raw",
            "shop_account_id": "shopee_sg_hongxi_local",
        },
    )
    assert first_response.status_code == 200

    clear_response = await alias_client.delete("/api/shop-account-aliases/primary/shopee_sg_hongxi_local")
    assert clear_response.status_code == 200

    second_response = await alias_client.post(
        "/api/shop-account-aliases/claim",
        json={
            "platform": "shopee",
            "alias_value": "HongXi SG New",
            "shop_account_id": "shopee_sg_hongxi_local",
        },
    )

    assert second_response.status_code == 200
    assert second_response.json()["alias_value"] == "HongXi SG New"
    assert second_response.json()["is_primary"] is True

    aliases_response = await alias_client.get("/api/shop-account-aliases")
    assert aliases_response.status_code == 200
    active_primary_aliases = [
        item["alias_value"]
        for item in aliases_response.json()
        if item["is_active"] and item["is_primary"]
    ]
    assert active_primary_aliases == ["HongXi SG New"]

    shop_accounts_response = await alias_client.get("/api/shop-accounts")
    assert shop_accounts_response.status_code == 200
    assert shop_accounts_response.json()[0]["account_alias"] == "HongXi SG New"


@pytest.mark.asyncio
async def test_claim_alias_rejects_shop_account_with_different_active_primary_alias(alias_client):
    await _seed_shop_account(alias_client)

    first_response = await alias_client.post(
        "/api/shop-account-aliases/claim",
        json={
            "platform": "shopee",
            "alias_value": "HongXi SG Raw",
            "shop_account_id": "shopee_sg_hongxi_local",
        },
    )
    assert first_response.status_code == 200

    second_response = await alias_client.post(
        "/api/shop-account-aliases/claim",
        json={
            "platform": "shopee",
            "alias_value": "Another Raw Alias",
            "shop_account_id": "shopee_sg_hongxi_local",
        },
    )

    assert second_response.status_code == 409
    assert "already has an active primary alias" in second_response.json()["detail"]


@pytest.mark.asyncio
async def test_clear_primary_alias_removes_shop_account_alias_display(alias_client):
    await _seed_shop_account(alias_client)
    claim_response = await alias_client.post(
        "/api/shop-account-aliases/claim",
        json={
            "platform": "shopee",
            "alias_value": "HongXi SG Raw",
            "shop_account_id": "shopee_sg_hongxi_local",
        },
    )
    assert claim_response.status_code == 200

    clear_response = await alias_client.delete("/api/shop-account-aliases/primary/shopee_sg_hongxi_local")
    assert clear_response.status_code == 200

    shop_accounts_response = await alias_client.get("/api/shop-accounts")
    assert shop_accounts_response.status_code == 200
    assert shop_accounts_response.json()[0]["account_alias"] is None


@pytest.mark.asyncio
async def test_shop_accounts_list_falls_back_to_active_alias_when_primary_missing(alias_client):
    await _seed_shop_account(alias_client)
    shop_accounts_response = await alias_client.get("/api/shop-accounts")
    assert shop_accounts_response.status_code == 200
    shop_account_db_id = shop_accounts_response.json()[0]["id"]

    create_alias_response = await alias_client.post(
        "/api/shop-account-aliases",
        json={
            "shop_account_id": shop_account_db_id,
            "platform": "shopee",
            "alias_value": "Legacy Alias",
            "alias_type": "legacy",
            "source": "migration",
            "is_primary": False,
            "is_active": True,
        },
    )
    assert create_alias_response.status_code == 200

    refreshed_shop_accounts = await alias_client.get("/api/shop-accounts")
    assert refreshed_shop_accounts.status_code == 200
    assert refreshed_shop_accounts.json()[0]["account_alias"] == "Legacy Alias"


@pytest.mark.asyncio
async def test_create_shop_account_alias_enqueues_identity_refresh_and_invalidates_cache(
    alias_client,
    monkeypatch,
):
    await _seed_shop_account(alias_client)
    refresh_calls = []
    cache_calls = []

    class FakeRefreshQueueService(_FakeRefreshQueueService):
        calls = refresh_calls

    monkeypatch.setattr(
        "backend.domains.collection.routers.shop_account_aliases.RefreshQueueService",
        FakeRefreshQueueService,
        raising=False,
    )
    monkeypatch.setattr(
        "backend.domains.collection.routers.shop_account_aliases.get_cache_service",
        lambda: _FakeBusinessOverviewCache(cache_calls),
        raising=False,
    )

    shop_accounts_response = await alias_client.get("/api/shop-accounts")
    assert shop_accounts_response.status_code == 200
    shop_account_db_id = shop_accounts_response.json()[0]["id"]

    response = await alias_client.post(
        "/api/shop-account-aliases",
        json={
            "shop_account_id": shop_account_db_id,
            "platform": "shopee",
            "alias_value": "HongXi SG Raw",
            "alias_type": "manual",
            "source": "operator",
            "is_primary": False,
            "is_active": True,
        },
    )

    assert response.status_code == 200
    assert len(refresh_calls) == 1
    assert refresh_calls[0]["trigger_type"] == "shop_identity_changed"
    assert refresh_calls[0]["pipeline_name"] == "postgresql_dashboard"
    assert refresh_calls[0]["context"]["changed_fields"] == ["alias"]
    assert refresh_calls[0]["context"]["shop_account_db_id"] == shop_account_db_id
    assert cache_calls == ["invalidate_dashboard_business_overview"]


@pytest.mark.asyncio
async def test_claim_shop_account_alias_enqueues_identity_refresh_and_invalidates_cache(
    alias_client,
    monkeypatch,
):
    await _seed_shop_account(alias_client)
    refresh_calls = []
    cache_calls = []

    class FakeRefreshQueueService(_FakeRefreshQueueService):
        calls = refresh_calls

    monkeypatch.setattr(
        "backend.domains.collection.routers.shop_account_aliases.RefreshQueueService",
        FakeRefreshQueueService,
        raising=False,
    )
    monkeypatch.setattr(
        "backend.domains.collection.routers.shop_account_aliases.get_cache_service",
        lambda: _FakeBusinessOverviewCache(cache_calls),
        raising=False,
    )

    response = await alias_client.post(
        "/api/shop-account-aliases/claim",
        json={
            "platform": "shopee",
            "alias_value": "HongXi SG Raw",
            "shop_account_id": "shopee_sg_hongxi_local",
        },
    )

    assert response.status_code == 200
    assert len(refresh_calls) == 1
    assert refresh_calls[0]["trigger_type"] == "shop_identity_changed"
    assert refresh_calls[0]["pipeline_name"] == "postgresql_dashboard"
    assert refresh_calls[0]["context"]["shop_account_id"] == "shopee_sg_hongxi_local"
    assert refresh_calls[0]["context"]["changed_fields"] == ["alias"]
    assert cache_calls == ["invalidate_dashboard_business_overview"]


@pytest.mark.asyncio
async def test_clear_shop_account_primary_alias_enqueues_identity_refresh_and_invalidates_cache(
    alias_client,
    monkeypatch,
):
    await _seed_shop_account(alias_client)
    claim_response = await alias_client.post(
        "/api/shop-account-aliases/claim",
        json={
            "platform": "shopee",
            "alias_value": "HongXi SG Raw",
            "shop_account_id": "shopee_sg_hongxi_local",
        },
    )
    assert claim_response.status_code == 200

    refresh_calls = []
    cache_calls = []

    class FakeRefreshQueueService(_FakeRefreshQueueService):
        calls = refresh_calls

    monkeypatch.setattr(
        "backend.domains.collection.routers.shop_account_aliases.RefreshQueueService",
        FakeRefreshQueueService,
        raising=False,
    )
    monkeypatch.setattr(
        "backend.domains.collection.routers.shop_account_aliases.get_cache_service",
        lambda: _FakeBusinessOverviewCache(cache_calls),
        raising=False,
    )

    response = await alias_client.delete("/api/shop-account-aliases/primary/shopee_sg_hongxi_local")

    assert response.status_code == 200
    assert len(refresh_calls) == 1
    assert refresh_calls[0]["trigger_type"] == "shop_identity_changed"
    assert refresh_calls[0]["pipeline_name"] == "postgresql_dashboard"
    assert refresh_calls[0]["context"]["shop_account_id"] == "shopee_sg_hongxi_local"
    assert refresh_calls[0]["context"]["changed_fields"] == ["alias"]
    assert cache_calls == ["invalidate_dashboard_business_overview"]


def test_shop_account_aliases_router_exposes_unmatched_route():
    from pathlib import Path

    text = (
        Path(__file__).resolve().parents[2]
        / "backend/domains/collection/routers/shop_account_aliases.py"
    ).read_text(encoding="utf-8")

    assert '@router.get("/unmatched"' in text


def test_shop_account_aliases_unmatched_query_keeps_complete_json_keys():
    from pathlib import Path

    text = (
        Path(__file__).resolve().parents[2]
        / "backend/domains/collection/routers/shop_account_aliases.py"
    ).read_text(encoding="utf-8")

    assert r'_CN_STORE_NAME = _u(r"\u5e97\u94fa\u540d\u79f0")' in text
    assert r'_CN_ORDER_ID = _u(r"\u8ba2\u5355\u53f7")' in text
    assert r'_CN_SHOPEE_PAID = _u(r"\u5b9e\u4ed8\u91d1\u989d")' in text
    assert "raw_data->>:cn_store_name" in text
    assert "raw_data->>:cn_order_id" in text


def test_shop_account_aliases_unmatched_query_reads_semantic_orders_atomic():
    from pathlib import Path

    text = (
        Path(__file__).resolve().parents[2]
        / "backend/domains/collection/routers/shop_account_aliases.py"
    ).read_text(encoding="utf-8")

    assert "FROM semantic.fact_orders_atomic" in text


def test_shop_alias_normalization_strips_platform_prefix():
    from backend.utils.text_normalization import normalize_alias_key

    assert normalize_alias_key("Shopee新加坡1店") == "新加坡1店"
    assert normalize_alias_key("shopee 新加坡1店") == "新加坡1店"
    assert normalize_alias_key("TikTok Shop 菲律宾2店") == "菲律宾2店"
    assert normalize_alias_key("TK新加坡1店") == "新加坡1店"


@pytest_asyncio.fixture
async def alias_session_factory():
    """独立的 SQLite 内存库，用于直接验证店铺别名占用统计。"""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.exec_driver_sql("ATTACH DATABASE ':memory:' AS core")
        await conn.run_sync(MainAccount.__table__.create)
        await conn.run_sync(ShopAccount.__table__.create)
        await conn.run_sync(ShopAccountAlias.__table__.create)
        await conn.run_sync(ShopAccountCapability.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _seed_tiktok_shop_accounts(session_factory):
    """3 个 TikTok 店铺账号，其中 2 个已被其它标签 1:1 占满。"""
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
        session.add_all(
            [
                ShopAccount(
                    platform="tiktok",
                    shop_account_id="tiktok_sg_hx_home_local",
                    main_account_id="main-tiktok",
                    store_name="Singapore(HX Home)",
                ),
                ShopAccount(
                    platform="tiktok",
                    shop_account_id="tiktok_sg_daone_mall_local",
                    main_account_id="main-tiktok",
                    store_name="DAONE Mall",
                ),
                ShopAccount(
                    platform="tiktok",
                    shop_account_id="tiktok_my_flora_mall_local",
                    main_account_id="main-tiktok",
                    store_name="Malaysia(Flora Mall)",
                ),
            ]
        )
        await session.commit()

        accounts = (
            (await session.execute(select(ShopAccount).order_by(ShopAccount.id)))
            .scalars()
            .all()
        )
        session.add_all(
            [
                ShopAccountAlias(
                    shop_account_id=accounts[0].id,
                    platform="tiktok",
                    alias_value="TK新加坡1店",
                    alias_normalized="新加坡1店",
                    alias_type="claimed",
                    is_primary=True,
                    is_active=True,
                ),
                ShopAccountAlias(
                    shop_account_id=accounts[1].id,
                    platform="tiktok",
                    alias_value="TK新加坡2店",
                    alias_normalized="新加坡2店",
                    alias_type="claimed",
                    is_primary=True,
                    is_active=True,
                ),
            ]
        )
        await session.commit()


@pytest.mark.asyncio
async def test_load_platform_alias_occupancy_counts_occupied_and_claimable_shop_accounts(
    alias_session_factory,
):
    """占用统计：被 1:1 占满的店铺账号不能再作为认领目标。"""
    from backend.domains.collection.routers.shop_account_aliases import (
        _load_platform_alias_occupancy,
    )

    await _seed_tiktok_shop_accounts(alias_session_factory)

    async with alias_session_factory() as session:
        occupancy = await _load_platform_alias_occupancy(session)

    tiktok = occupancy["tiktok"]
    assert tiktok.total_shop_accounts == 3
    assert tiktok.occupied_shop_accounts == 2
    assert tiktok.claimable_shop_accounts == 1


def test_claim_hint_requires_new_shop_account_when_platform_fully_occupied():
    """现有店账号被其它标签 1:1 占满时，必须提示需新建店账号才能认领。"""
    from backend.domains.collection.routers.shop_account_aliases import (
        _PlatformAliasOccupancy,
        _build_claim_hint,
    )

    hint = _build_claim_hint(
        _PlatformAliasOccupancy(
            total_shop_accounts=6,
            occupied_shop_accounts=6,
            claimable_shop_accounts=0,
        )
    )

    assert hint is not None
    assert "1:1 占满" in hint
    assert "需新建店账号才能认领" in hint
    assert "6" in hint


def test_claim_hint_lists_claimable_shop_accounts_when_slots_available():
    """还有空位时，提示有多少个店铺账号可以直接认领。"""
    from backend.domains.collection.routers.shop_account_aliases import (
        _PlatformAliasOccupancy,
        _build_claim_hint,
    )

    hint = _build_claim_hint(
        _PlatformAliasOccupancy(
            total_shop_accounts=6,
            occupied_shop_accounts=4,
            claimable_shop_accounts=2,
        )
    )

    assert hint == "该平台下有 2 个店铺账号可直接认领"


def test_claim_hint_requires_new_shop_account_when_platform_has_no_shop_account():
    """平台下还没有任何店铺账号时，同样只能新建。"""
    from backend.domains.collection.routers.shop_account_aliases import (
        _PlatformAliasOccupancy,
        _build_claim_hint,
    )

    hint = _build_claim_hint(_PlatformAliasOccupancy())

    assert hint is not None
    assert "需新建店账号才能认领" in hint


def test_build_unmatched_alias_items_attaches_claim_hint_for_tiktok_3c_store():
    """TK新加坡3C店 暂不认领，但面板必须带上认领提示。"""
    from backend.domains.collection.routers.shop_account_aliases import (
        _PlatformAliasOccupancy,
        _build_unmatched_alias_items,
    )

    rows = [
        {
            "platform": "tiktok",
            "site": "新加坡",
            "store_label_raw": "TK新加坡3C店",
            "row_count": 90,
            "order_count": 62,
            "paid_amount": 8046.67,
        }
    ]
    occupancy = {
        "tiktok": _PlatformAliasOccupancy(
            total_shop_accounts=6,
            occupied_shop_accounts=6,
            claimable_shop_accounts=0,
        )
    }

    items = _build_unmatched_alias_items(rows, occupancy)

    assert len(items) == 1
    item = items[0]
    assert item.platform == "tiktok"
    assert item.store_label_raw == "TK新加坡3C店"
    assert item.row_count == 90
    assert item.order_count == 62
    assert item.claim_hint is not None
    assert "1:1 占满" in item.claim_hint
    assert "需新建店账号才能认领" in item.claim_hint

