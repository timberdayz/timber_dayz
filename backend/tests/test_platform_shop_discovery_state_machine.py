"""探测状态机: 「采集时读到的编号对不上谁」必须被如实记下来。

问题
----
``core.platform_shop_discoveries.status`` 是这套系统里**唯一**记录
「采集时看到的店铺编号到底指向谁」的地方。状态写错, 运营就会以为一切正常。

H4 实测: 26 条探测记录里有 6 条的 ``detected_platform_shop_id``
**对不上任何账号**, 但状态全是 ``detected_single_bound`` —— 看起来像成功。
根因是判定只分了两支:

* 编号被**别人**占着 ⇒ ``conflict_detected``
* 编号和本账号**不一样** ⇒ ``stale_url``
* 其余 ⇒ ``detected_single_bound``

「本账号压根还没有平台编号」这一支掉进了「其余」⇒
探测值谁都对不上, 却被记成了绑定成功。

做法
----
* 补一个 ``unmatched_platform_shop_id`` 状态, 专门表示「什么都没对上」;
* 把状态判定与「问题态」清单收拢成**具名常量**, 看板与列表都引用同一份;
* 列表支持按状态过滤, 并提供问题态汇总 —— 让异常能被主动看见, 而不是
  等下次有人从看板倒查。
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from backend.models.database import get_async_db
from backend.services.platform_shop_discovery_service import (
    PLATFORM_SHOP_DISCOVERY_ISSUE_STATUSES,
    PLATFORM_SHOP_DISCOVERY_STATUS_CONFLICT_DETECTED,
    PLATFORM_SHOP_DISCOVERY_STATUS_DETECTED_SINGLE_BOUND,
    PLATFORM_SHOP_DISCOVERY_STATUS_STALE_URL,
    PLATFORM_SHOP_DISCOVERY_STATUS_UNMATCHED,
    PlatformShopDiscoveryService,
)
from modules.core.db import PlatformShopDiscovery, ShopAccount


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


@pytest_asyncio.fixture
async def discovery_session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        for schema_name in ("core", "a_class", "b_class", "c_class", "finance"):
            await conn.execute(text(f"ATTACH DATABASE ':memory:' AS {schema_name}"))
        await conn.run_sync(ShopAccount.__table__.create)
        await conn.run_sync(PlatformShopDiscovery.__table__.create)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


def _account(**kwargs) -> ShopAccount:
    defaults = {
        "platform": "shopee",
        "shop_account_id": "shopee_my_xhkj1_local",
        "main_account_id": "main_1",
        "store_name": "xhkj1.my",
        "internal_code": "XHKJ1_MY",
        "platform_shop_id": "1308200832",
        "shop_region": "MY",
        "enabled": True,
    }
    defaults.update(kwargs)
    return ShopAccount(**defaults)


# ---------------------------------------------------------------------------
# 状态判定
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_runtime_discovery_marks_unmatched_when_nothing_lines_up(discovery_session):
    """账号自己还没有平台编号, 探测值又谁都不属于 ⇒ **什么都没对上**。

    这条以前会落成 ``detected_single_bound`` —— 看着像绑定成功,
    实际采集到的编号跟哪个账号都对不上。
    """
    account = _account(platform_shop_id=None)
    discovery_session.add(account)
    await discovery_session.commit()
    await discovery_session.refresh(account)

    service = PlatformShopDiscoveryService()
    discovery = await service.record_runtime_discovery(
        discovery_session,
        platform="shopee",
        main_account_id="main_1",
        shop_account_id="shopee_my_xhkj1_local",
        detected_store_name="xhkj1.my",
        detected_platform_shop_id="9999999999",
        detected_region="MY",
    )

    assert discovery is not None
    assert discovery.status == PLATFORM_SHOP_DISCOVERY_STATUS_UNMATCHED
    assert discovery.status != PLATFORM_SHOP_DISCOVERY_STATUS_DETECTED_SINGLE_BOUND


@pytest.mark.asyncio
async def test_unmatched_status_still_leaves_master_data_untouched(discovery_session):
    """补状态不是为了改主数据 —— 运行时探测依然只记录证据。"""
    account = _account(platform_shop_id=None)
    discovery_session.add(account)
    await discovery_session.commit()
    await discovery_session.refresh(account)

    service = PlatformShopDiscoveryService()
    await service.record_runtime_discovery(
        discovery_session,
        platform="shopee",
        main_account_id="main_1",
        shop_account_id="shopee_my_xhkj1_local",
        detected_store_name="xhkj1.my",
        detected_platform_shop_id="9999999999",
        detected_region="MY",
    )

    await discovery_session.refresh(account)
    assert account.platform_shop_id is None


@pytest.mark.asyncio
async def test_issue_statuses_cover_every_problem_state(discovery_session):
    """问题态清单必须覆盖三种「对不上」, 且**不含**成功态。

    清单漏一个状态 ⇒ 那种异常在看板/列表里就静默了。
    """
    assert PLATFORM_SHOP_DISCOVERY_ISSUE_STATUSES == {
        PLATFORM_SHOP_DISCOVERY_STATUS_STALE_URL,
        PLATFORM_SHOP_DISCOVERY_STATUS_CONFLICT_DETECTED,
        PLATFORM_SHOP_DISCOVERY_STATUS_UNMATCHED,
    }
    assert (
        PLATFORM_SHOP_DISCOVERY_STATUS_DETECTED_SINGLE_BOUND
        not in PLATFORM_SHOP_DISCOVERY_ISSUE_STATUSES
    )


# ---------------------------------------------------------------------------
# 可见性
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_can_filter_by_status(discovery_session):
    """列表要能按状态过滤 —— 否则问题记录淹没在正常记录里。"""
    service = PlatformShopDiscoveryService()
    for status in (
        PLATFORM_SHOP_DISCOVERY_STATUS_STALE_URL,
        PLATFORM_SHOP_DISCOVERY_STATUS_CONFLICT_DETECTED,
        PLATFORM_SHOP_DISCOVERY_STATUS_DETECTED_SINGLE_BOUND,
    ):
        discovery_session.add(
            PlatformShopDiscovery(
                platform="shopee",
                main_account_id="main_1",
                detected_store_name="xhkj1.my",
                detected_platform_shop_id="1308200832",
                candidate_shop_account_ids=[],
                status=status,
            )
        )
    await discovery_session.commit()

    only_stale = await service.list_platform_shop_discoveries(
        discovery_session, statuses=[PLATFORM_SHOP_DISCOVERY_STATUS_STALE_URL]
    )
    assert [row.status for row in only_stale] == [
        PLATFORM_SHOP_DISCOVERY_STATUS_STALE_URL
    ]


@pytest.mark.asyncio
async def test_list_can_return_only_issue_records(discovery_session):
    """``only_issues`` 只给问题态 —— 运营要的就是「有没有异常」。"""
    service = PlatformShopDiscoveryService()
    for status in (
        PLATFORM_SHOP_DISCOVERY_STATUS_STALE_URL,
        PLATFORM_SHOP_DISCOVERY_STATUS_DETECTED_SINGLE_BOUND,
    ):
        discovery_session.add(
            PlatformShopDiscovery(
                platform="shopee",
                main_account_id="main_1",
                detected_store_name="xhkj1.my",
                detected_platform_shop_id="1308200832",
                candidate_shop_account_ids=[],
                status=status,
            )
        )
    await discovery_session.commit()

    issues = await service.list_platform_shop_discoveries(
        discovery_session, only_issues=True
    )
    assert [row.status for row in issues] == [PLATFORM_SHOP_DISCOVERY_STATUS_STALE_URL]


@pytest.mark.asyncio
async def test_summary_counts_issue_records_by_status(discovery_session):
    """汇总要给出**问题态总数**与按状态的分项计数。"""
    service = PlatformShopDiscoveryService()
    for status in (
        PLATFORM_SHOP_DISCOVERY_STATUS_STALE_URL,
        PLATFORM_SHOP_DISCOVERY_STATUS_STALE_URL,
        PLATFORM_SHOP_DISCOVERY_STATUS_CONFLICT_DETECTED,
        PLATFORM_SHOP_DISCOVERY_STATUS_DETECTED_SINGLE_BOUND,
    ):
        discovery_session.add(
            PlatformShopDiscovery(
                platform="shopee",
                main_account_id="main_1",
                detected_store_name="xhkj1.my",
                detected_platform_shop_id="1308200832",
                candidate_shop_account_ids=[],
                status=status,
            )
        )
    await discovery_session.commit()

    summary = await service.summarize_platform_shop_discovery_issues(discovery_session)
    assert summary["total"] == 4
    assert summary["issue_count"] == 3
    assert summary["by_status"][PLATFORM_SHOP_DISCOVERY_STATUS_STALE_URL] == 2
    assert summary["by_status"][PLATFORM_SHOP_DISCOVERY_STATUS_CONFLICT_DETECTED] == 1
    assert len(summary["issues"]) == 3


# ---------------------------------------------------------------------------
# API 层
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def discovery_client(discovery_session):
    app = FastAPI()
    from backend.domains.collection.routers import platform_shop_discoveries

    app.include_router(platform_shop_discoveries.router, prefix="/api")

    async def override_get_async_db():
        yield discovery_session

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
async def test_api_list_filters_by_status(discovery_client, discovery_session):
    """``?status=`` 过滤要真的生效。"""
    discovery_session.add(
        PlatformShopDiscovery(
            platform="shopee",
            main_account_id="main_1",
            detected_store_name="xhkj1.my",
            detected_platform_shop_id="1308200832",
            candidate_shop_account_ids=[],
            status=PLATFORM_SHOP_DISCOVERY_STATUS_CONFLICT_DETECTED,
        )
    )
    discovery_session.add(
        PlatformShopDiscovery(
            platform="shopee",
            main_account_id="main_1",
            detected_store_name="xhkj1.my",
            detected_platform_shop_id="1308200832",
            candidate_shop_account_ids=[],
            status=PLATFORM_SHOP_DISCOVERY_STATUS_DETECTED_SINGLE_BOUND,
        )
    )
    await discovery_session.commit()

    response = await discovery_client.get(
        "/api/platform-shop-discoveries",
        params={"status": PLATFORM_SHOP_DISCOVERY_STATUS_CONFLICT_DETECTED},
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["status"] == PLATFORM_SHOP_DISCOVERY_STATUS_CONFLICT_DETECTED


@pytest.mark.asyncio
async def test_api_list_accepts_multiple_statuses(discovery_client, discovery_session):
    """``?status=a,b`` 要能一次筛出多种状态。"""
    for status in (
        PLATFORM_SHOP_DISCOVERY_STATUS_CONFLICT_DETECTED,
        PLATFORM_SHOP_DISCOVERY_STATUS_STALE_URL,
        PLATFORM_SHOP_DISCOVERY_STATUS_DETECTED_SINGLE_BOUND,
    ):
        discovery_session.add(
            PlatformShopDiscovery(
                platform="shopee",
                main_account_id="main_1",
                detected_store_name="xhkj1.my",
                detected_platform_shop_id="1308200832",
                candidate_shop_account_ids=[],
                status=status,
            )
        )
    await discovery_session.commit()

    response = await discovery_client.get(
        "/api/platform-shop-discoveries",
        params={
            "status": ",".join(
                [
                    PLATFORM_SHOP_DISCOVERY_STATUS_CONFLICT_DETECTED,
                    PLATFORM_SHOP_DISCOVERY_STATUS_STALE_URL,
                ]
            )
        },
    )
    assert response.status_code == 200
    assert len(response.json()) == 2


@pytest.mark.asyncio
async def test_api_only_issues_filter(discovery_client, discovery_session):
    """``?only_issues=true`` 只返回问题态。"""
    discovery_session.add(
        PlatformShopDiscovery(
            platform="shopee",
            main_account_id="main_1",
            detected_store_name="xhkj1.my",
            detected_platform_shop_id="1308200832",
            candidate_shop_account_ids=[],
            status=PLATFORM_SHOP_DISCOVERY_STATUS_UNMATCHED,
        )
    )
    discovery_session.add(
        PlatformShopDiscovery(
            platform="shopee",
            main_account_id="main_1",
            detected_store_name="xhkj1.my",
            detected_platform_shop_id="1308200832",
            candidate_shop_account_ids=[],
            status=PLATFORM_SHOP_DISCOVERY_STATUS_DETECTED_SINGLE_BOUND,
        )
    )
    await discovery_session.commit()

    response = await discovery_client.get(
        "/api/platform-shop-discoveries", params={"only_issues": "true"}
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["status"] == PLATFORM_SHOP_DISCOVERY_STATUS_UNMATCHED


@pytest.mark.asyncio
async def test_api_issues_summary_endpoint(discovery_client, discovery_session):
    """问题态汇总端点: 让异常能被**主动**查出来, 而不是等人翻列表。"""
    discovery_session.add(
        PlatformShopDiscovery(
            platform="shopee",
            main_account_id="main_1",
            detected_store_name="xhkj1.my",
            detected_platform_shop_id="1308200832",
            candidate_shop_account_ids=["shopee_sg_xhkj33_local"],
            status=PLATFORM_SHOP_DISCOVERY_STATUS_CONFLICT_DETECTED,
        )
    )
    await discovery_session.commit()

    response = await discovery_client.get("/api/platform-shop-discoveries/issues/summary")
    assert response.status_code == 200
    payload = response.json()
    assert payload["issue_count"] == 1
    assert payload["by_status"][PLATFORM_SHOP_DISCOVERY_STATUS_CONFLICT_DETECTED] == 1
    assert payload["issues"][0]["candidate_shop_account_ids"] == [
        "shopee_sg_xhkj33_local"
    ]


@pytest.mark.asyncio
async def test_api_statuses_endpoint_lists_issue_states(discovery_client):
    """状态字典端点: 让前端/排查脚本知道哪些状态算问题态。"""
    response = await discovery_client.get("/api/platform-shop-discoveries/statuses")
    assert response.status_code == 200
    assert set(response.json()["issue_statuses"]) == set(
        PLATFORM_SHOP_DISCOVERY_ISSUE_STATUSES
    )
