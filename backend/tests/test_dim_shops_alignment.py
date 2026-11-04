"""P2「数据地基」的契约测试。

三件事
------
1. **``core.dim_shops`` 与 ``core.shop_accounts`` 对齐** —— 生产此前是 0 行，
   看板显示名的 JOIN 永远落空；维度表是店铺账号的**派生物**。
2. **改名新名的跨主账号占用预检** —— 店名是身份解析的第 4 路匹配键，语义层
   按 ``(platform, 规范化店名)`` 找候选、**不区分主账号** ⇒ 跨主账号重名会让
   这家店的钱落进 ``unknown`` 桶。
3. **``platform_shop_id_status`` 由服务端派生** —— 它回答「平台店铺ID是什
   么来路」，必须与数据一致，客户端说了不算。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.domains.collection.routers.shop_accounts import (
    _derive_platform_shop_id_status,
)
from backend.models.database import get_async_db
from backend.routers import main_accounts, shop_accounts
from backend.services.shop_sync_service import resolve_dim_shop_id
from modules.core.db import (
    DimPlatform,
    DimShop,
    MainAccount,
    ShopAccount,
    ShopAccountAlias,
    ShopAccountCapability,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
ALIGN_MIGRATION = (
    "current_migrations/versions/20261107_align_dim_shops_with_shop_accounts.py"
)


# ---------------------------------------------------------------------------
# 1. 迁移契约
# ---------------------------------------------------------------------------


def test_alignment_migration_exists_and_is_chained_after_atomic_views():
    text = (REPO_ROOT / ALIGN_MIGRATION).read_text(encoding="utf-8")
    assert (
        'down_revision = "current_schema_20261106_create_atomic_materialized_views"'
        in text
    )


def test_alignment_migration_uses_the_semantic_layer_key_derivation():
    """键派生必须与语义层逐字一致，否则看板 JOIN 永远落空。"""
    text = (REPO_ROOT / ALIGN_MIGRATION).read_text(encoding="utf-8")
    assert "NULLIF(TRIM(COALESCE(sa.platform_shop_id, '')), '')" in text
    assert "NULLIF(TRIM(COALESCE(sa.shop_account_id, '')), '')" in text
    assert "sa.id::text" in text


def test_alignment_migration_is_idempotent_and_re_runnable():
    """重跑要能「全量对齐」：upsert + 清掉源里已不存在的行。"""
    text = (REPO_ROOT / ALIGN_MIGRATION).read_text(encoding="utf-8")
    assert "ON CONFLICT (platform_code, shop_id) DO UPDATE" in text
    assert "DELETE FROM core.dim_shops" in text


def test_resolve_dim_shop_id_matches_semantic_layer_priority():
    """platform_shop_id > shop_account_id > id（与语义层一致）。"""

    class _Account:
        def __init__(self, platform_shop_id=None, shop_account_id=None, id=7):
            self.platform_shop_id = platform_shop_id
            self.shop_account_id = shop_account_id
            self.id = id

    assert resolve_dim_shop_id(_Account("1308200825", "sa_1")) == "1308200825"
    assert resolve_dim_shop_id(_Account(None, "sa_1")) == "sa_1"
    assert resolve_dim_shop_id(_Account("  ", "  ")) == "7"


# ---------------------------------------------------------------------------
# 2. 平台店铺ID状态：服务端派生
# ---------------------------------------------------------------------------


def test_platform_shop_id_status_is_missing_without_platform_shop_id():
    assert _derive_platform_shop_id_status(None) == "missing"
    assert _derive_platform_shop_id_status("   ") == "missing"


def test_platform_shop_id_status_is_manual_when_the_id_changes():
    assert (
        _derive_platform_shop_id_status(
            "1308200825", previous_status="missing", platform_shop_id_changed=True
        )
        == "manual_confirmed"
    )


def test_platform_shop_id_status_keeps_auto_bound_when_the_id_is_untouched():
    """平台店铺ID没变 ⇒ 保留「自动绑定」成果，不被一次无关编辑改掉。"""
    assert (
        _derive_platform_shop_id_status(
            "1308200825", previous_status="auto_bound", platform_shop_id_changed=False
        )
        == "auto_bound"
    )


# ---------------------------------------------------------------------------
# 3+4. 端点行为：跨主账号占用预检 + 维度表同步
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def shop_account_client(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.exec_driver_sql("ATTACH DATABASE ':memory:' AS core")
        await conn.run_sync(MainAccount.__table__.create)
        await conn.run_sync(ShopAccount.__table__.create)
        await conn.run_sync(ShopAccountAlias.__table__.create)
        await conn.run_sync(ShopAccountCapability.__table__.create)
        await conn.run_sync(DimPlatform.__table__.create)
        await conn.run_sync(DimShop.__table__.create)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    app = FastAPI()
    app.include_router(main_accounts.router, prefix="/api")
    app.include_router(shop_accounts.router, prefix="/api")
    # 把会话工厂挂到 app.state —— 测试要直接查 ``core.dim_shops``
    app.state.session_factory = session_factory

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
                "roles": [
                    type("Role", (), {"role_code": "admin", "role_name": "admin"})()
                ],
            },
        )()

    app.dependency_overrides[get_async_db] = override_get_async_db
    from backend.dependencies.auth import get_current_user

    app.dependency_overrides[get_current_user] = override_current_user
    monkeypatch.setattr(
        "backend.routers.main_accounts.get_encryption_service",
        lambda: type(
            "Enc", (), {"encrypt_password": lambda self, value: f"enc:{value}"}
        )(),
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    await engine.dispose()


async def _bootstrap(
    client,
    *,
    store_name="HongXi SG",
    main_account="hongxikeji:main",
    shop_account_id="shopee_sg_hongxi_local",
    region=None,
    platform_shop_id=None,
):
    await client.post(
        "/api/main-accounts",
        json={
            "platform": "shopee",
            "main_account_id": main_account,
            "username": "demo-user",
            "password": "plain-password",
            "login_url": "https://seller.shopee.cn",
            "enabled": True,
        },
    )
    payload = {
        "platform": "shopee",
        "shop_account_id": shop_account_id,
        "main_account_id": main_account,
        "store_name": store_name,
        "enabled": True,
    }
    if region is not None:
        payload["shop_region"] = region
    if platform_shop_id is not None:
        payload["platform_shop_id"] = platform_shop_id
    return await client.post("/api/shop-accounts", json=payload)


@pytest.mark.asyncio
async def test_creating_shop_account_writes_the_display_dimension_row(
    shop_account_client,
):
    """新账号立刻进 ``core.dim_shops``（展示维度表是店铺账号的派生物）。"""
    from sqlalchemy import select

    response = await _bootstrap(shop_account_client, platform_shop_id="1308200825")
    assert response.status_code == 200, response.text

    session_factory = (
        shop_account_client._transport.app.state.session_factory
    )  # noqa: SLF001
    async with session_factory() as session:
        rows = (
            (await session.execute(select(DimShop).order_by(DimShop.shop_id)))
            .scalars()
            .all()
        )

    assert len(rows) == 1
    row = rows[0]
    # 键派生与语义层一致：platform_shop_id 优先
    assert row.platform_code == "shopee"
    assert row.shop_id == "1308200825"
    assert row.shop_name == "HongXi SG"
    assert row.is_active is True


@pytest.mark.asyncio
async def test_rename_to_a_name_used_by_another_main_account_is_rejected(
    shop_account_client,
):
    """跨主账号重名 ⇒ 409（否则金额会落进 unknown 桶）。"""
    first = await _bootstrap(
        shop_account_client,
        store_name="HongXi SG",
        main_account="hongxikeji:main",
        shop_account_id="shopee_sg_hongxi_local",
        region="SG",
    )
    assert first.status_code == 200, first.text

    second = await _bootstrap(
        shop_account_client,
        store_name="Other Shop",
        main_account="other:main",
        shop_account_id="shopee_sg_other_local",
        region="SG",
    )
    assert second.status_code == 200, second.text

    rename = await shop_account_client.put(
        "/api/shop-accounts/shopee_sg_other_local",
        json={"store_name": "HongXi SG"},
    )
    assert rename.status_code == 409
    assert "占用" in rename.text


@pytest.mark.asyncio
async def test_rename_to_a_name_used_in_another_region_is_allowed(
    shop_account_client,
):
    """区域消歧就是为了让同平台同名在不同区域并存 ⇒ 不该拦。"""
    first = await _bootstrap(
        shop_account_client,
        store_name="HongXi SG",
        main_account="hongxikeji:main",
        shop_account_id="shopee_sg_hongxi_local",
        region="SG",
    )
    assert first.status_code == 200, first.text

    second = await _bootstrap(
        shop_account_client,
        store_name="Other Shop",
        main_account="other:main",
        shop_account_id="shopee_my_other_local",
        region="MY",
    )
    assert second.status_code == 200, second.text

    rename = await shop_account_client.put(
        "/api/shop-accounts/shopee_my_other_local",
        json={"store_name": "HongXi SG"},
    )
    assert rename.status_code == 200, rename.text


@pytest.mark.asyncio
async def test_rename_detects_names_that_normalize_to_the_same_key(
    shop_account_client,
):
    """规范化后同名也算占用（「看着不一样、匹配时一样」）。"""
    first = await _bootstrap(
        shop_account_client,
        store_name="HongXi SG",
        main_account="hongxikeji:main",
        shop_account_id="shopee_sg_hongxi_local",
        region="SG",
    )
    assert first.status_code == 200, first.text

    second = await _bootstrap(
        shop_account_client,
        store_name="Other Shop",
        main_account="other:main",
        shop_account_id="shopee_sg_other_local",
        region="SG",
    )
    assert second.status_code == 200, second.text

    rename = await shop_account_client.put(
        "/api/shop-accounts/shopee_sg_other_local",
        json={"store_name": "hongxi-sg"},
    )
    assert rename.status_code == 409
