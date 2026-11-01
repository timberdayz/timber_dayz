"""内部标准名（internal_code）的建议值生成、回填与编辑入口契约。

内部标准名 = 人读的唯一标识（FIORO_SG / FIORO_MY / FIORO_PH），
**不参与数据匹配**，所以改名不会把历史数据搅乱。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.models.database import get_async_db
from backend.services.shop_internal_code_service import (
    backfill_internal_codes,
    suggest_internal_code,
)
from modules.core.db import MainAccount, ShopAccount, ShopAccountAlias, ShopAccountCapability


REPO_ROOT = Path(__file__).resolve().parents[2]
STORE_FILE = REPO_ROOT / "frontend" / "src" / "stores" / "accounts.js"
VIEW_FILE = (
    REPO_ROOT / "frontend" / "src" / "domains" / "platform" / "views" / "AccountManagement.vue"
)


# ---------------------------------------------------------------------------
# 建议值生成（纯函数）
# ---------------------------------------------------------------------------


def test_suggest_strips_known_region_suffix():
    assert suggest_internal_code("xhkj1.my", "MY") == "XHKJ1_MY"
    assert suggest_internal_code("xhkj11.sg", "SG") == "XHKJ11_SG"


def test_suggest_handles_parentheses_and_spaces():
    assert suggest_internal_code("Malaysia(Flora Mall)", "MY") == "MALAYSIA_FLORA_MALL_MY"
    assert suggest_internal_code("DAWIE Mall", "MY") == "DAWIE_MALL_MY"


def test_suggest_handles_chinese():
    assert suggest_internal_code("西虹照明", "SG") == "西虹照明_SG"


def test_suggest_is_deterministic():
    a = suggest_internal_code("DAWIE Mall", "MY")
    b = suggest_internal_code("DAWIE Mall", "MY")
    assert a == b


def test_suggest_without_region_has_no_region_suffix():
    assert suggest_internal_code("xihong", "") == "XIHONG"
    assert suggest_internal_code("xihong", None) == "XIHONG"


def test_suggest_falls_back_to_shop_when_name_has_no_alnum():
    assert suggest_internal_code("---", "MY") == "SHOP_MY"


def test_suggest_appends_main_account_short_id_on_conflict():
    """同平台同区域重名 -> 追加主账号短标识（FIORO_MY_T1）。"""
    assert (
        suggest_internal_code("FIORO", "MY", main_account_id="Tiktok 1店", taken={"FIORO_MY"})
        == "FIORO_MY_T1"
    )


def test_suggest_keeps_plain_candidate_when_no_conflict():
    assert (
        suggest_internal_code("FIORO", "MY", main_account_id="Tiktok 1店", taken=set())
        == "FIORO_MY"
    )


def test_suggest_does_not_mutate_region_of_unknown_suffix():
    """未知后缀不剥（例如 .com），只在已知地区后缀上剥离。"""
    assert suggest_internal_code("shop.example.com", "SG") == "SHOP_EXAMPLE_COM_SG"


# ---------------------------------------------------------------------------
# 存量回填
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def internal_code_session_factory():
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


async def _seed_shop_accounts(session_factory, rows):
    async with session_factory() as session:
        for platform in {row["platform"] for row in rows}:
            main_ids = sorted(
                {row["main_account_id"] for row in rows if row["platform"] == platform}
            )
            for main_account_id in main_ids:
                session.add(
                    MainAccount(
                        platform=platform,
                        main_account_id=main_account_id,
                        username="demo-user",
                        password_encrypted="enc:demo",
                        enabled=True,
                    )
                )
        for row in rows:
            session.add(
                ShopAccount(
                    platform=row["platform"],
                    shop_account_id=row["shop_account_id"],
                    main_account_id=row["main_account_id"],
                    store_name=row["store_name"],
                    shop_region=row.get("shop_region"),
                    internal_code=row.get("internal_code"),
                )
            )
        await session.commit()


@pytest.mark.asyncio
async def test_backfill_is_dry_run_by_default(internal_code_session_factory):
    await _seed_shop_accounts(
        internal_code_session_factory,
        [
            {
                "platform": "tiktok",
                "shop_account_id": "tiktok_my_dawie_mall_local",
                "main_account_id": "Tiktok 1店",
                "store_name": "DAWIE Mall",
                "shop_region": "MY",
            }
        ],
    )

    async with internal_code_session_factory() as session:
        result = await backfill_internal_codes(session)

    assert result["dry_run"] is True
    assert result["planned"] == 1
    assert result["applied"] == 0
    assert result["assignments"][0]["internal_code"] == "DAWIE_MALL_MY"

    async with internal_code_session_factory() as session:
        rows = (await session.execute(select(ShopAccount))).scalars().all()
        assert [row.internal_code for row in rows] == [None]


@pytest.mark.asyncio
async def test_backfill_applies_codes_unique_within_platform(internal_code_session_factory):
    await _seed_shop_accounts(
        internal_code_session_factory,
        [
            {
                "platform": "tiktok",
                "shop_account_id": "tiktok_my_fioro_a_local",
                "main_account_id": "main-tiktok-a",
                "store_name": "FIORO",
                "shop_region": "MY",
            },
            {
                "platform": "tiktok",
                "shop_account_id": "tiktok_my_fioro_b_local",
                "main_account_id": "main-tiktok-b",
                "store_name": "FIORO",
                "shop_region": "MY",
            },
            {
                "platform": "shopee",
                "shop_account_id": "shopee_my_fioro_local",
                "main_account_id": "main-shopee-a",
                "store_name": "FIORO",
                "shop_region": "MY",
            },
        ],
    )

    async with internal_code_session_factory() as session:
        result = await backfill_internal_codes(session, dry_run=False)
        assert result["applied"] == 3

        rows = (await session.execute(select(ShopAccount))).scalars().all()
        by_platform: dict[str, list[str]] = {}
        for row in rows:
            by_platform.setdefault(row.platform, []).append(row.internal_code)

    assert all(codes for codes in by_platform.values())
    for codes in by_platform.values():
        assert len(codes) == len(set(codes)), f"同平台内部标准名必须唯一: {codes}"
    # 同平台重名 -> 追加主账号短标识
    tiktok_codes = sorted(by_platform["tiktok"])
    assert tiktok_codes[0] == "FIORO_MY"
    assert tiktok_codes[1].startswith("FIORO_MY_")
    # 不同平台互不影响
    assert by_platform["shopee"] == ["FIORO_MY"]


@pytest.mark.asyncio
async def test_backfill_keeps_manually_filled_codes(internal_code_session_factory):
    await _seed_shop_accounts(
        internal_code_session_factory,
        [
            {
                "platform": "tiktok",
                "shop_account_id": "tiktok_sg_manual_local",
                "main_account_id": "main-a",
                "store_name": "DAONE Mall",
                "shop_region": "SG",
                "internal_code": "CUSTOM_MANUAL_CODE",
            },
            {
                "platform": "tiktok",
                "shop_account_id": "tiktok_sg_auto_local",
                "main_account_id": "main-a",
                "store_name": "DAONE Mall",
                "shop_region": "SG",
            },
        ],
    )

    async with internal_code_session_factory() as session:
        result = await backfill_internal_codes(session, dry_run=False)
        assert result["planned"] == 1
        assert result["already_filled"] == 1

        rows = (
            await session.execute(select(ShopAccount).order_by(ShopAccount.shop_account_id))
        ).scalars().all()

    codes = {row.shop_account_id: row.internal_code for row in rows}
    assert codes["tiktok_sg_manual_local"] == "CUSTOM_MANUAL_CODE"
    # 自动补的名字不能撞上人工填的
    assert codes["tiktok_sg_auto_local"] != "CUSTOM_MANUAL_CODE"


# ---------------------------------------------------------------------------
# API：编辑入口 + 同平台唯一性
# ---------------------------------------------------------------------------


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
async def shop_account_client(internal_code_session_factory, monkeypatch):
    from backend.domains.collection.routers import shop_accounts as shop_accounts_router

    monkeypatch.setattr(
        "backend.domains.collection.routers.shop_accounts.RefreshQueueService",
        _FakeRefreshQueueService,
        raising=False,
    )
    monkeypatch.setattr(
        "backend.domains.collection.routers.shop_accounts.get_cache_service",
        lambda: _FakeBusinessOverviewCache([]),
        raising=False,
    )

    app = FastAPI()
    app.include_router(shop_accounts_router.router, prefix="/api")

    async def override_get_async_db():
        async with internal_code_session_factory() as session:
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


@pytest.mark.asyncio
async def test_update_shop_account_accepts_internal_code(
    shop_account_client, internal_code_session_factory
):
    await _seed_shop_accounts(
        internal_code_session_factory,
        [
            {
                "platform": "tiktok",
                "shop_account_id": "tiktok_sg_daone_mall_local",
                "main_account_id": "main-a",
                "store_name": "DAONE Mall",
                "shop_region": "SG",
            }
        ],
    )

    response = await shop_account_client.put(
        "/api/shop-accounts/tiktok_sg_daone_mall_local",
        json={"internal_code": "FIORO_SG"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["internal_code"] == "FIORO_SG"
    # 没填标准名时给建议值（不落库）
    assert payload["suggested_internal_code"] == "DAONE_MALL_SG"

    async with internal_code_session_factory() as session:
        rows = (await session.execute(select(ShopAccount))).scalars().all()
        assert rows[0].internal_code == "FIORO_SG"


@pytest.mark.asyncio
async def test_update_shop_account_rejects_duplicate_internal_code_in_same_platform(
    shop_account_client, internal_code_session_factory
):
    await _seed_shop_accounts(
        internal_code_session_factory,
        [
            {
                "platform": "tiktok",
                "shop_account_id": "tiktok_sg_daone_mall_local",
                "main_account_id": "main-a",
                "store_name": "DAONE Mall",
                "shop_region": "SG",
                "internal_code": "FIORO_SG",
            },
            {
                "platform": "tiktok",
                "shop_account_id": "tiktok_my_dawie_mall_local",
                "main_account_id": "main-a",
                "store_name": "DAWIE Mall",
                "shop_region": "MY",
            },
        ],
    )

    response = await shop_account_client.put(
        "/api/shop-accounts/tiktok_my_dawie_mall_local",
        json={"internal_code": "FIORO_SG"},
    )

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert "FIORO_SG" in detail
    # 冲突详情要告诉运营是谁占用了
    assert "tiktok_sg_daone_mall_local" in detail


@pytest.mark.asyncio
async def test_update_shop_account_allows_keeping_its_own_internal_code(
    shop_account_client, internal_code_session_factory
):
    """自己已经是这个标准名 -> 允许（不该跟自己冲突）。"""
    await _seed_shop_accounts(
        internal_code_session_factory,
        [
            {
                "platform": "tiktok",
                "shop_account_id": "tiktok_sg_daone_mall_local",
                "main_account_id": "main-a",
                "store_name": "DAONE Mall",
                "shop_region": "SG",
                "internal_code": "FIORO_SG",
            }
        ],
    )

    response = await shop_account_client.put(
        "/api/shop-accounts/tiktok_sg_daone_mall_local",
        json={"internal_code": "FIORO_SG", "notes": "人工确认"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["internal_code"] == "FIORO_SG"


@pytest.mark.asyncio
async def test_update_shop_account_can_clear_internal_code(
    shop_account_client, internal_code_session_factory
):
    await _seed_shop_accounts(
        internal_code_session_factory,
        [
            {
                "platform": "tiktok",
                "shop_account_id": "tiktok_sg_daone_mall_local",
                "main_account_id": "main-a",
                "store_name": "DAONE Mall",
                "shop_region": "SG",
                "internal_code": "FIORO_SG",
            }
        ],
    )

    response = await shop_account_client.put(
        "/api/shop-accounts/tiktok_sg_daone_mall_local",
        json={"internal_code": ""},
    )

    assert response.status_code == 200, response.text
    assert response.json()["internal_code"] is None

    async with internal_code_session_factory() as session:
        rows = (await session.execute(select(ShopAccount))).scalars().all()
        assert rows[0].internal_code is None


# ---------------------------------------------------------------------------
# 前端契约：字段白名单 + 页面入口
# ---------------------------------------------------------------------------


def _extract_update_payload_whitelist() -> list[str]:
    """从 store 源码里解析出 buildShopAccountUpdatePayload 的字段白名单。"""
    source = STORE_FILE.read_text(encoding="utf-8")
    match = re.search(
        r"function buildShopAccountUpdatePayload\(data\)\s*\{.*?const fields\s*=\s*\[(.*?)\]",
        source,
        re.DOTALL,
    )
    assert match, "frontend/src/stores/accounts.js 里找不到 buildShopAccountUpdatePayload 的白名单"
    return re.findall(r"'([^']+)'", match.group(1))


def test_store_update_payload_whitelist_includes_internal_code():
    """白名单漏了 internal_code -> 前端填了内部标准名会被静默丢弃。"""
    whitelist = _extract_update_payload_whitelist()
    assert "internal_code" in whitelist, (
        f"buildShopAccountUpdatePayload 白名单缺 internal_code: {whitelist}"
    )


def test_store_update_payload_whitelist_keeps_existing_fields():
    whitelist = _extract_update_payload_whitelist()
    for field in (
        "store_name",
        "shop_region",
        "shop_type",
        "business_role",
        "capabilities",
        "enabled",
        "notes",
    ):
        assert field in whitelist, f"白名单丢了既有字段 {field}: {whitelist}"


def test_account_management_view_exposes_internal_code():
    text = VIEW_FILE.read_text(encoding="utf-8")
    # 表格列 / 表单输入 / 表单初始值 三处都要有
    assert "内部标准名" in text, "账号管理页缺少「内部标准名」列"
    assert "accountForm.internal_code" in text, "账号管理页表单没有绑定 internal_code"
    assert "suggested_internal_code" in text, "账号管理页没有展示后端给的建议值"
