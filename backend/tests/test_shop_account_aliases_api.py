import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.models.database import get_async_db
from backend.routers import main_accounts, shop_account_aliases, shop_accounts
from modules.core.db import MainAccount, ShopAccount, ShopAccountAlias, ShopAccountCapability


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
async def test_claim_alias_replaces_existing_primary_alias(alias_client):
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


def test_shop_account_aliases_router_exposes_unmatched_route():
    from pathlib import Path

    text = (
        Path(__file__).resolve().parents[2]
        / "backend/routers/shop_account_aliases.py"
    ).read_text(encoding="utf-8")

    assert '@router.get("/unmatched"' in text


def test_shop_account_aliases_unmatched_query_keeps_complete_json_keys():
    from pathlib import Path

    text = (
        Path(__file__).resolve().parents[2]
        / "backend/routers/shop_account_aliases.py"
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
        / "backend/routers/shop_account_aliases.py"
    ).read_text(encoding="utf-8")

    assert "FROM semantic.fact_orders_atomic" in text
