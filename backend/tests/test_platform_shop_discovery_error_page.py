"""采集侧：打开到平台的**错误页 / 404 页 / 登录页** ⇒ 判「探测失败」，不制造假冲突。

问题
----
2026-11-07 实测事故：采集器打开的第一个页面是

    https://seller.shopee.cn/404?cnsc_shop_id=1391124228

这个 URL **照样带着 ``cnsc_shop_id``** —— 而那个编号是**上一家店**的
（持久 profile 会把上次会话停着的页面恢复出来）。旧代码把它当成一次正常探测 ⇒

* 该编号被另一个账号占着 ⇒ 记成 ``conflict_detected``；
* 业务概览页弹出「店铺身份未对齐 / 采集期探测到 1 次店铺身份异常」。

**页面上压根没有店铺身份信息**，拿 URL 参数做绑定判定 = 制造假冲突。

做法
----
* 采集侧识别错误页（404 / error / 登录页）⇒ 记 ``status='failed'``；
* ``failed`` **不做绑定判定**、**不写候选账号**、**不把编号当成探测值**；
* ``failed`` 不在「需要人看一眼」的状态清单里 ⇒ 不计入身份异常告警
  （2026-04 已有 3 条同口径的历史记录，当时命中的是登录页）。
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from backend.services.platform_shop_discovery_service import (
    PLATFORM_SHOP_DISCOVERY_ISSUE_STATUSES,
    PLATFORM_SHOP_DISCOVERY_STATUS_CONFLICT_DETECTED,
    PLATFORM_SHOP_DISCOVERY_STATUS_FAILED,
    PlatformShopDiscoveryService,
)
from modules.apps.collection_center.executor_v2 import (
    _extract_platform_shop_context,
    _is_platform_error_page,
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
        "shop_account_id": "shopee_sg_strawberries_store_local",
        "main_account_id": "main_1",
        "store_name": "strawberries_store.sg",
        "internal_code": "STRAW_SG",
        "platform_shop_id": "1391124224",
        "shop_region": "SG",
        "enabled": True,
    }
    defaults.update(kwargs)
    return ShopAccount(**defaults)


# ---------------------------------------------------------------------------
# 错误页识别
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        # 2026-11-07 事故现场
        "https://seller.shopee.cn/404?cnsc_shop_id=1391124228",
        "https://seller.shopee.cn/404",
        "https://seller.shopee.cn/404error?cnsc_shop_id=1",
        "https://seller.shopee.cn/error?cnsc_shop_id=1",
        # 2026-04 历史 failed 记录命中的登录页
        "https://seller.shopee.cn/account/signin?next=%2Fportal%2Fhome",
        "https://seller.shopee.cn/login",
    ],
)
def test_error_pages_are_recognized(url):
    assert _is_platform_error_page(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1227491331&shop_region=SG",
        "https://seller.shopee.cn/portal/home?cnsc_shop_id=1227491331",
        "https://seller.tiktokshopglobalselling.com/homepage?shop_region=MY",
    ],
)
def test_normal_pages_are_not_error_pages(url):
    assert _is_platform_error_page(url) is False


def test_error_page_url_keeps_evidence_but_flags_failure():
    """错误页上照样能读到 ``cnsc_shop_id`` —— 但那**不是探测结果**。

    证据必须留在载荷里（URL 是复盘的唯一线索），同时必须被标记成错误页。
    """
    payload = _extract_platform_shop_context(
        "shopee",
        "https://seller.shopee.cn/404?cnsc_shop_id=1391124228",
    )

    assert payload["is_error_page"] is True
    assert payload["detected_platform_shop_id"] == "1391124228"
    assert payload["current_url"] == (
        "https://seller.shopee.cn/404?cnsc_shop_id=1391124228"
    )


def test_normal_page_url_is_not_flagged_as_error_page():
    payload = _extract_platform_shop_context(
        "shopee",
        "https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1227491331",
    )

    assert payload["is_error_page"] is False
    assert payload["detected_platform_shop_id"] == "1227491331"


# ---------------------------------------------------------------------------
# 状态机
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_error_page_probe_is_recorded_as_failed(discovery_session):
    """错误页 ⇒ ``failed``：不做绑定判定、不写候选账号、不把编号当探测值。"""
    discovery_session.add(_account())
    await discovery_session.commit()

    service = PlatformShopDiscoveryService()
    discovery = await service.record_runtime_discovery(
        discovery_session,
        platform="shopee",
        main_account_id="main_1",
        shop_account_id="shopee_sg_strawberries_store_local",
        detected_store_name="strawberries_store.sg",
        detected_platform_shop_id="1391124228",
        detected_region="SG",
        raw_payload={
            "current_url": "https://seller.shopee.cn/404?cnsc_shop_id=1391124228",
            "is_error_page": True,
        },
        probe_failed=True,
    )

    assert discovery is not None
    assert discovery.status == PLATFORM_SHOP_DISCOVERY_STATUS_FAILED
    # 编号是**上一家店**的 ⇒ 不能当成「探测到的编号」写进主字段。
    assert discovery.detected_platform_shop_id is None
    assert discovery.detected_store_name is None
    assert list(discovery.candidate_shop_account_ids or []) == []
    # 证据留着。
    assert discovery.raw_payload["current_url"].endswith(
        "/404?cnsc_shop_id=1391124228"
    )
    assert discovery.raw_payload["probe_failed"] is True


@pytest.mark.asyncio
async def test_failed_status_is_not_an_identity_issue():
    """「没探测到」**不是**「探测到且对不上」⇒ 不进身份异常告警。"""
    assert PLATFORM_SHOP_DISCOVERY_STATUS_FAILED not in PLATFORM_SHOP_DISCOVERY_ISSUE_STATUSES


@pytest.mark.asyncio
async def test_same_number_on_normal_page_is_still_a_conflict(discovery_session):
    """同一个编号、正常页面 ⇒ 仍然判冲突（改动**只**作用于错误页路径）。"""
    discovery_session.add(_account())
    # 另一个账号占着 1391124228
    discovery_session.add(
        _account(
            shop_account_id="shopee_sg_hx_home_local",
            store_name="hx_home",
            internal_code="HXHOME_SG",
            platform_shop_id="1391124228",
        )
    )
    await discovery_session.commit()

    service = PlatformShopDiscoveryService()
    discovery = await service.record_runtime_discovery(
        discovery_session,
        platform="shopee",
        main_account_id="main_1",
        shop_account_id="shopee_sg_strawberries_store_local",
        detected_store_name="strawberries_store.sg",
        detected_platform_shop_id="1391124228",
        detected_region="SG",
        raw_payload={
            "current_url": (
                "https://seller.shopee.cn/datacenter/product/overview"
                "?cnsc_shop_id=1391124228"
            ),
            "is_error_page": False,
        },
        probe_failed=False,
    )

    assert discovery is not None
    assert discovery.status == PLATFORM_SHOP_DISCOVERY_STATUS_CONFLICT_DETECTED
    assert discovery.detected_platform_shop_id == "1391124228"
