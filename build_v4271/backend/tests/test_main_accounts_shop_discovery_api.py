import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.models.database import get_async_db
from backend.routers import main_accounts
from modules.core.db import MainAccount


@pytest_asyncio.fixture
async def main_account_discovery_client(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.exec_driver_sql("ATTACH DATABASE ':memory:' AS core")
        await conn.run_sync(MainAccount.__table__.create)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    app = FastAPI()
    app.include_router(main_accounts.router, prefix="/api")

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

    class _FakeDiscoveryService:
        async def run_current_discovery(self, db, *, platform, main_account_id, request):  # noqa: ANN001
            return {
                "success": True,
                "platform": platform,
                "main_account_id": main_account_id,
                "mode": request.mode,
                "discovery": {
                    "detected_store_name": "HongXi SG",
                    "detected_platform_shop_id": "1227491331",
                    "detected_region": request.expected_region,
                    "current_url": "https://seller.example/path?shop_id=1227491331",
                    "source": {
                        "platform_shop_id": "url",
                        "store_name": "dom",
                        "region": "input",
                    },
                    "confidence": 0.95,
                },
                "match": {
                    "status": "no_match",
                    "shop_account_id": None,
                    "candidate_count": 0,
                },
                "evidence": {
                    "screenshot_path": "temp/discovery/test.png",
                },
            }

    monkeypatch.setattr(
        "backend.routers.main_accounts.get_shop_discovery_service",
        lambda: _FakeDiscoveryService(),
        raising=False,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    await engine.dispose()


@pytest.mark.asyncio
async def test_trigger_current_shop_discovery_from_main_account(main_account_discovery_client):
    create_response = await main_account_discovery_client.post(
        "/api/main-accounts",
        json={
            "platform": "shopee",
            "main_account_id": "hongxikeji:main",
            "username": "demo-user",
            "password": "plain-password",
            "login_url": "https://seller.shopee.cn",
            "enabled": True,
        },
    )
    assert create_response.status_code == 200

    response = await main_account_discovery_client.post(
        "/api/main-accounts/hongxikeji:main/shop-discovery/current",
        json={
            "mode": "current_only",
            "reuse_session": True,
            "expected_region": "SG",
            "capture_evidence": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["main_account_id"] == "hongxikeji:main"
    assert payload["platform"] == "shopee"
    assert payload["mode"] == "current_only"
    assert payload["match"]["status"] == "no_match"
