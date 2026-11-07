"""换绑平台店铺ID 时，旧值必须留成别名 —— 否则这家店的历史数据会失联。

问题
----
历史行（订单 / 商品 / 服务 / 库存）的店铺键是**采集时的平台店铺ID**。
换绑后账号上的 ``platform_shop_id`` 变成新值 ⇒ 旧值不再命中任何候选
⇒ 这家店的历史数据全部落进 ``unknown`` ⇒ **看板上这家店的历史直接消失**。

改名（store_name）早就做了这件事（旧名转 ``former_name`` 别名），
换绑平台店铺ID 却漏了 —— 同一类问题的两个入口，只堵了一个。

做法
----
把旧值写成一条 alias（alias_type='former_platform_shop_id'，is_active=true，
is_primary=false）。候选集里别名行与平台店铺ID行走同一套匹配
⇒ 旧值命中别名行 ⇒ 仍然解析回同一个账号 ⇒ 历史数据不搬家、不改写。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from backend.services.platform_shop_discovery_service import (
    PlatformShopDiscoveryService,
)
from backend.services.shop_rename_service import (
    FORMER_PLATFORM_SHOP_ID_ALIAS_TYPE,
    PLATFORM_SHOP_ID_ALIAS_SOURCE,
    retain_previous_platform_shop_id_as_alias,
)
from modules.core.db import PlatformShopDiscovery, ShopAccount, ShopAccountAlias


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTER = (
    REPO_ROOT / "backend" / "domains" / "collection" / "routers" / "shop_accounts.py"
)
DISCOVERY_SERVICE = (
    REPO_ROOT / "backend" / "services" / "platform_shop_discovery_service.py"
)


@pytest_asyncio.fixture
async def alias_session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        for schema_name in ("core", "a_class", "b_class", "c_class", "finance"):
            await conn.execute(text(f"ATTACH DATABASE ':memory:' AS {schema_name}"))
        await conn.run_sync(ShopAccount.__table__.create)
        await conn.run_sync(ShopAccountAlias.__table__.create)
        await conn.run_sync(PlatformShopDiscovery.__table__.create)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


from sqlalchemy import text  # noqa: E402  （需要在 fixture 里用）


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


def test_update_endpoint_calls_the_rebind_alias_service():
    """换绑分支必须调用具名的联动服务。

    断言必须**跨文件**看「调用了具名服务」，不能在函数体内找字符串 ——
    联动逻辑放在独立服务里。
    """
    body = (
        ROUTER.read_text(encoding="utf-8")
        .split("async def update_shop_account", 1)[1]
        .split("\nasync def ", 1)[0]
    )
    assert (
        "_retain_previous_platform_shop_id_as_alias" in body
    ), "update_shop_account 没有在换绑平台店铺ID 时保留旧值别名"
    # 现有的通用赋值与唯一性校验必须保留
    assert "setattr(record, field, value)" in body
    assert "_assert_platform_shop_id_unique" in body


@pytest.mark.asyncio
async def test_rebind_keeps_previous_platform_shop_id_as_alias(alias_session):
    """换绑后旧值成为别名（活跃、非主名）⇒ 历史数据仍能解析回这个账号。"""
    account = _account()
    alias_session.add(account)
    await alias_session.commit()
    await alias_session.refresh(account)

    # 换绑：账号上的 platform_shop_id 变成新值
    account.platform_shop_id = "1407964586"
    await alias_session.commit()

    await retain_previous_platform_shop_id_as_alias(
        alias_session, account, "1308200832"
    )
    await alias_session.commit()

    rows = (
        (
            await alias_session.execute(
                select(ShopAccountAlias).where(
                    ShopAccountAlias.shop_account_id == account.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    alias = rows[0]
    assert alias.alias_value == "1308200832"
    assert alias.alias_normalized == "1308200832"
    assert alias.alias_type == FORMER_PLATFORM_SHOP_ID_ALIAS_TYPE
    assert alias.source == PLATFORM_SHOP_ID_ALIAS_SOURCE
    assert alias.is_active is True
    assert alias.is_primary is False


@pytest.mark.asyncio
async def test_rebind_is_idempotent(alias_session):
    """重复换绑同一对值不产生第二条别名。"""
    account = _account()
    alias_session.add(account)
    await alias_session.commit()
    await alias_session.refresh(account)
    account.platform_shop_id = "1407964586"
    await alias_session.commit()

    for _ in range(3):
        await retain_previous_platform_shop_id_as_alias(
            alias_session, account, "1308200832"
        )
        await alias_session.commit()

    rows = (
        (
            await alias_session.execute(
                select(ShopAccountAlias).where(
                    ShopAccountAlias.shop_account_id == account.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_no_alias_when_platform_shop_id_unchanged(alias_session):
    """没换绑就不该凭空多一条别名。"""
    account = _account()
    alias_session.add(account)
    await alias_session.commit()
    await alias_session.refresh(account)

    await retain_previous_platform_shop_id_as_alias(
        alias_session, account, "1308200832"
    )
    await alias_session.commit()

    rows = (
        (
            await alias_session.execute(
                select(ShopAccountAlias).where(
                    ShopAccountAlias.shop_account_id == account.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert rows == []


@pytest.mark.asyncio
async def test_no_alias_when_previous_value_is_empty(alias_session):
    """原来就没有平台店铺ID（missing 状态）⇒ 没有旧值可留。"""
    account = _account(platform_shop_id=None)
    alias_session.add(account)
    await alias_session.commit()
    await alias_session.refresh(account)
    account.platform_shop_id = "1407964586"
    await alias_session.commit()

    result = await retain_previous_platform_shop_id_as_alias(
        alias_session, account, None
    )
    await alias_session.commit()

    assert result is None


# ---------------------------------------------------------------------------
# 自动绑定路径：同一个问题的第三个入口
# ---------------------------------------------------------------------------


def test_all_discovery_binding_paths_keep_the_previous_id_as_alias():
    """三个会改平台店铺ID 的入口，一个都不能漏。

    运营在后台改（``update_shop_account``）已经堵住了，但自动绑定
    （``record_runtime_discovery`` / ``record_manual_discovery``）和人工确认
    （``confirm_discovery``）同样会覆盖 ``platform_shop_id`` ——
    漏掉任何一个，这家店的历史数据照样会失联。

    断言写成「计数」而不是「找某个字符串」：少堵一个入口时计数会变，
    而找字符串在代码挪位置后仍会误判为通过。
    """
    source = DISCOVERY_SERVICE.read_text(encoding="utf-8")

    assert (
        source.count("previous_platform_shop_id = shop_account.platform_shop_id") == 2
    ), "有入口覆盖了平台店铺ID 却没有先捕获旧值"
    assert (
        source.count("await retain_previous_platform_shop_id_as_alias(") == 2
    ), "有入口覆盖了平台店铺ID 却没有把旧值留成别名"


def test_every_master_data_writing_path_calls_the_shared_ownership_guard():
    """所有改主数据的入口都必须走**同一个**具名归属守卫。

    守卫没被调用 = 某个入口可以覆盖别人的平台店铺ID。
    断言写成计数：漏一个入口时计数会变。
    """
    source = DISCOVERY_SERVICE.read_text(encoding="utf-8")

    assert (
        source.count("await self._guard_platform_shop_id_binding(") == 4
    ), "有改主数据的入口没有走具名归属守卫"
    assert "_owner_of_platform_shop_id" in source


@pytest.mark.asyncio
async def test_runtime_discovery_never_writes_master_data(alias_session):
    """运行时探测**不得**改账号主数据。

    运行时探测发生在「登录刚结束、切店组件还没跑」的位置，
    URL 上的编号是**上一家店**的 ⇒ 写进主数据会让账号整体错位一位。
    """
    account = _account()
    alias_session.add(account)
    await alias_session.commit()
    await alias_session.refresh(account)

    service = PlatformShopDiscoveryService()
    discovery = await service.record_runtime_discovery(
        alias_session,
        platform="shopee",
        main_account_id="main_1",
        shop_account_id="shopee_my_xhkj1_local",
        detected_store_name="xhkj1.my",
        detected_platform_shop_id="1407964586",
        detected_region="MY",
    )

    await alias_session.refresh(account)
    assert account.platform_shop_id == "1308200832", "运行时探测改了账号主数据"
    assert account.platform_shop_id_status != "auto_bound"
    # 证据仍然要留下来
    assert discovery is not None
    assert discovery.detected_platform_shop_id == "1407964586"
    assert discovery.status == "stale_url"


@pytest.mark.asyncio
async def test_runtime_discovery_marks_stale_url_when_id_differs(alias_session):
    """探测值与账号当前编号不一致 ⇒ ``stale_url``（URL 还停在别的店）。"""
    account = _account()
    alias_session.add(account)
    await alias_session.commit()
    await alias_session.refresh(account)

    service = PlatformShopDiscoveryService()
    discovery = await service.record_runtime_discovery(
        alias_session,
        platform="shopee",
        main_account_id="main_1",
        shop_account_id="shopee_my_xhkj1_local",
        detected_store_name="xhkj1.my",
        detected_platform_shop_id="9999999999",
        detected_region="MY",
    )

    await alias_session.refresh(account)
    assert account.platform_shop_id == "1308200832"
    assert discovery.status == "stale_url"


@pytest.mark.asyncio
async def test_runtime_discovery_marks_conflict_when_id_owned_by_another(alias_session):
    """探测值被**另一个**账号占着 ⇒ ``conflict_detected``，且不改主数据。"""
    account = _account()
    other = _account(
        shop_account_id="shopee_sg_xhkj33_local",
        store_name="xhkj33.sg",
        internal_code="XHKJ33_SG",
        platform_shop_id="1308200825",
    )
    alias_session.add_all([account, other])
    await alias_session.commit()
    await alias_session.refresh(account)

    service = PlatformShopDiscoveryService()
    discovery = await service.record_runtime_discovery(
        alias_session,
        platform="shopee",
        main_account_id="main_1",
        shop_account_id="shopee_my_xhkj1_local",
        detected_store_name="xhkj1.my",
        detected_platform_shop_id="1308200825",
        detected_region="MY",
    )

    await alias_session.refresh(account)
    assert account.platform_shop_id == "1308200832"
    assert discovery.status == "conflict_detected"
    assert discovery.candidate_shop_account_ids == ["shopee_sg_xhkj33_local"]


@pytest.mark.asyncio
async def test_runtime_discovery_is_idempotent_when_detected_matches_current(
    alias_session,
):
    """探测值与账号当前编号一致 ⇒ 确认通过，且不产生别名。"""
    account = _account()
    alias_session.add(account)
    await alias_session.commit()
    await alias_session.refresh(account)

    service = PlatformShopDiscoveryService()
    discovery = await service.record_runtime_discovery(
        alias_session,
        platform="shopee",
        main_account_id="main_1",
        shop_account_id="shopee_my_xhkj1_local",
        detected_store_name="xhkj1.my",
        detected_platform_shop_id="1308200832",
        detected_region="MY",
    )

    await alias_session.refresh(account)
    assert account.platform_shop_id == "1308200832"
    assert discovery.status == "detected_single_bound"

    aliases = (
        (
            await alias_session.execute(
                select(ShopAccountAlias).where(
                    ShopAccountAlias.shop_account_id == account.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert aliases == []


@pytest.mark.asyncio
async def test_confirm_discovery_refuses_to_take_over_another_accounts_id(
    alias_session,
):
    """人工确认也不能把**别人**的编号抢到自己名下。"""
    account = _account()
    other = _account(
        shop_account_id="shopee_sg_xhkj33_local",
        store_name="xhkj33.sg",
        internal_code="XHKJ33_SG",
        platform_shop_id="1308200825",
    )
    alias_session.add_all([account, other])
    await alias_session.commit()
    await alias_session.refresh(account)

    service = PlatformShopDiscoveryService()
    discovery = await service.record_runtime_discovery(
        alias_session,
        platform="shopee",
        main_account_id="main_1",
        shop_account_id="shopee_my_xhkj1_local",
        detected_store_name="xhkj1.my",
        detected_platform_shop_id="1308200825",
        detected_region="MY",
    )

    with pytest.raises(ValueError):
        await service.confirm_discovery(
            alias_session, discovery.id, "shopee_my_xhkj1_local"
        )

    await alias_session.refresh(account)
    assert account.platform_shop_id == "1308200832", "人工确认抢走了别人的编号"


@pytest.mark.asyncio
async def test_manual_auto_bound_refuses_to_take_over_another_accounts_id(
    alias_session,
):
    """人工探测的自动绑定同样要过归属校验。"""
    account = _account(platform_shop_id=None, store_name="xhkj1.my")
    other = _account(
        shop_account_id="shopee_sg_xhkj33_local",
        store_name="xhkj33.sg",
        internal_code="XHKJ33_SG",
        platform_shop_id="1308200825",
    )
    alias_session.add_all([account, other])
    await alias_session.commit()
    await alias_session.refresh(account)

    service = PlatformShopDiscoveryService()
    result = await service.record_manual_discovery(
        alias_session,
        platform="shopee",
        main_account_id="main_1",
        detected_store_name="xhkj1.my",
        detected_platform_shop_id="1308200825",
        detected_region="MY",
        raw_payload={"current_url": "https://seller.example/path"},
        confidence=0.9,
        source={"platform_shop_id": "url"},
        screenshot_path=None,
    )

    await alias_session.refresh(account)
    assert account.platform_shop_id is None, "自动绑定抢走了别人的编号"
    assert result.match.status == "pending_confirm"


@pytest.mark.asyncio
async def test_manual_rebind_keeps_previous_platform_shop_id_as_alias(alias_session):
    """人工换绑后旧值成为别名（活跃、非主名）⇒ 历史数据仍能解析回这个账号。"""
    account = _account()
    alias_session.add(account)
    await alias_session.commit()
    await alias_session.refresh(account)

    service = PlatformShopDiscoveryService()
    discovery = await service.record_runtime_discovery(
        alias_session,
        platform="shopee",
        main_account_id="main_1",
        shop_account_id="shopee_my_xhkj1_local",
        detected_store_name="xhkj1.my",
        detected_platform_shop_id="1407964586",
        detected_region="MY",
    )

    await service.confirm_discovery(
        alias_session, discovery.id, "shopee_my_xhkj1_local"
    )
    await alias_session.refresh(account)
    assert account.platform_shop_id == "1407964586"

    rows = (
        (
            await alias_session.execute(
                select(ShopAccountAlias).where(
                    ShopAccountAlias.shop_account_id == account.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].alias_value == "1308200832"
    assert rows[0].alias_normalized == "1308200832"
    assert rows[0].alias_type == FORMER_PLATFORM_SHOP_ID_ALIAS_TYPE
    assert rows[0].source == PLATFORM_SHOP_ID_ALIAS_SOURCE
    assert rows[0].is_active is True
    assert rows[0].is_primary is False


# ---------------------------------------------------------------------------
# 别名要真正生效，候选集的**快照**必须被刷新
# ---------------------------------------------------------------------------


def test_identity_refresh_targets_refresh_the_candidate_snapshot():
    """改名/换绑后的刷新目标必须包含候选集的**物化副本**。

    原子层（orders / analytics / products / services / inventory）读的是
    ``semantic.shop_identity_resolution_candidates_v2_mv`` 的**快照**，
    不是实时算的候选集 ⇒ 不刷副本，新别名在那些链路上永远不生效，
    这家店的历史仍然落进 unknown。

    只刷候选集**正本**（普通视图）没用：正本重建不改变副本的内容。
    """
    from backend.domains.collection.routers import shop_account_aliases, shop_accounts

    for module in (shop_accounts, shop_account_aliases):
        targets = list(module._SHOP_IDENTITY_REFRESH_TARGETS)
        assert (
            "semantic.shop_identity_resolution_candidates_v2_mv" in targets
        ), f"{module.__name__} 的刷新目标没有候选集物化副本 ⇒ 别名写了也不生效"
        # 月度物化视图读的是**正本**（实时算），刷它不等于刷副本。
        assert "semantic.fact_orders_monthly_atomic_mv" in targets
        assert "semantic.fact_analytics_monthly_atomic_mv" in targets


def test_candidate_snapshot_refresh_is_registered_and_ordered():
    """副本必须既能刷新、又排在消费者之前。"""
    from backend.services.data_pipeline.refresh_registry import (
        PIPELINE_DEPENDENCIES,
        SQL_TARGET_PATHS,
    )

    snapshot = "semantic.shop_identity_resolution_candidates_v2_mv"
    assert snapshot in SQL_TARGET_PATHS
    # 副本依赖正本（建 MV 时正本必须先在）
    assert PIPELINE_DEPENDENCIES[snapshot] == [
        "semantic.shop_identity_resolution_candidates"
    ]
    # 原子层读的就是这份副本
    for consumer in (
        "semantic.fact_orders_atomic",
        "semantic.fact_analytics_atomic",
        "semantic.shop_identity_resolver",
    ):
        assert snapshot in PIPELINE_DEPENDENCIES.get(
            consumer, []
        ), f"{consumer} 不再依赖候选集副本 ⇒ 别名变更不会传导到它"
