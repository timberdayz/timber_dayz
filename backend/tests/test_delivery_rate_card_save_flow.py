"""尾程费率的「卡片保存链路」端到端守护（2026-11-17）。

背景
----
商品中心「定价设置 → 尾程费率」在批次 8 改成**卡片式**（一个「平台 × 仓」一张卡，
卡内列全部重量段）。卡片的核心动作就两个：

1. **改价** ⇒ 版本化只进不退 ⇒ 走 ``POST``（旧行闭区间 + 新行今天起生效）
2. **只改备注** ⇒ 走 ``PATCH``（不新建行）

这两个动作以前只有「源码级」守护（``test_delivery_rate_currency_guard.py``），
**没有跑过真实路由**。2026-11-17 实测发现：卡片改价对**已存在**的档位直接返回
**409 「active delivery rate rule already exists」** ⇒ 功能不可用。

根因
----
改价时前端把**原行的生效日**（如 2026-01-01）一起发出去，而后端据此把旧行
闭区间到 ``生效日 - 1 天`` = 2025-12-31 ⇒

* 旧行的区间**倒挂**（``effective_to < effective_from``）⇒ 撞数据库检查约束
  ``ck_delivery_rate_rules_window`` ⇒ IntegrityError ⇒ 被当成「重复行」报 409；
* 就算没有那个约束，历史也会被**抹掉**（2026-01-01 起就算新价了）⇒
  事后对不上「当时按多少钱算的」。

本文件把这条链路钉住：**改价 ⇒ 新价今天起生效，旧价闭区间到昨天，历史留痕。**

⚠️ 跑的是**隔离库**（``pg_database``：每用例一个独立 database，用完 DROP），
不碰本地开发库、更不碰生产库。
"""

from datetime import date, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from modules.core.db import (
    Base,
    DeliveryRateRule,
    DimPlatform,
    DimWarehouse,
    DimWeightTier,
)

PLATFORM = "shopee"
WAREHOUSE = "SG-01"
TIER = "T01"
OLD_PRICE = 20.93
NEW_PRICE = 25.00
#: 老费率行的生效日（生产里 Shopee SG 五档都是 2026-01-01 起的）
OLD_EFFECTIVE_FROM = date(2026, 1, 1)


# ---------------------------------------------------------------------------
# 夹具：隔离库 + 真实路由（只覆盖鉴权与数据库连接）
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def delivery_client(pg_database):
    """真实 ``/api/delivery-rate-rules`` 路由 + 每用例独立 database。"""
    from backend.dependencies.auth import get_current_user
    from backend.main import app
    from backend.models.database import get_async_db

    async with pg_database() as pg:
        async_url = pg.get_connection_url().replace(
            "postgresql://", "postgresql+asyncpg://"
        )
        engine = create_async_engine(async_url, echo=False)
        async with engine.begin() as conn:
            for schema_name in (
                "core",
                "a_class",
                "b_class",
                "c_class",
                "finance",
                "ops",
                "semantic",
            ):
                await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))
            await conn.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

        async def override_get_async_db():
            async with session_factory() as session:
                yield session

        class _MockUser:
            id = 1
            username = "test_admin"
            is_active = True
            is_superuser = True
            role_id = 1

        async def override_current_user():
            return _MockUser()

        app.dependency_overrides[get_async_db] = override_get_async_db
        app.dependency_overrides[get_current_user] = override_current_user
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://localhost"
        ) as client:
            yield client, session_factory
        app.dependency_overrides.clear()
        await engine.dispose()


async def _seed(
    session_factory, *, tier_code=TIER, unit_price=OLD_PRICE, with_rate=True
):
    """种下「平台 × 仓 × 重量段」与一条当期费率行，返回那条行的 rule_id。

    ``with_rate=False`` ⇒ 只种段定义、不种费率行（模拟「这一段第一次录价」）。
    """
    async with session_factory() as session:
        session.add(
            DimPlatform(
                platform_code=PLATFORM,
                name="Shopee",
                platform_role="sales",
                is_active=True,
            )
        )
        session.add(
            DimWarehouse(
                warehouse_code=WAREHOUSE,
                warehouse_name="新加坡仓",
                country_code="SG",
                country_name="新加坡",
                status="active",
            )
        )
        session.add(
            DimWeightTier(
                tier_code=tier_code,
                label="0-1 kg",
                min_kg=0,
                max_kg=1,
                sort_order=1,
                status="active",
            )
        )
        await session.flush()
        if not with_rate:
            await session.commit()
            return None
        row = DeliveryRateRule(
            platform_code=PLATFORM,
            warehouse_code=WAREHOUSE,
            weight_tier_code=tier_code,
            unit_price=unit_price,
            currency="CNY",
            effective_from=OLD_EFFECTIVE_FROM,
            status="active",
            source="test_seed",
            version="v1",
        )
        session.add(row)
        await session.flush()
        await session.commit()
        return row.rule_id


def _create_payload(**overrides):
    payload = {
        "platform_code": PLATFORM,
        "warehouse_code": WAREHOUSE,
        "weight_tier_code": TIER,
        "unit_price": NEW_PRICE,
        "currency": "CNY",
        "effective_from": OLD_EFFECTIVE_FROM.isoformat(),
        "effective_to": None,
        "status": "active",
        "source": "test_seed",
        "version": "v2",
        "notes": "卡片改价",
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# 1 · 改价：新价今天起生效，旧价闭区间到昨天（历史留痕）
# ---------------------------------------------------------------------------


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_reprice_opens_new_version_from_today(delivery_client):
    """改价 ⇒ 新行今天起生效；旧行闭区间到昨天并退出当期。"""
    client, session_factory = delivery_client
    old_rule_id = await _seed(session_factory)

    response = await client.post("/api/delivery-rate-rules", json=_create_payload())
    assert response.status_code == 201, response.text
    body = response.json()
    today = date.today()

    assert body["unit_price"] == NEW_PRICE
    assert body["effective_from"] == today.isoformat()
    assert body["effective_to"] is None
    assert body["status"] == "active"
    assert body["rule_id"] != old_rule_id

    async with session_factory() as session:
        old = await session.get(DeliveryRateRule, old_rule_id)
        assert old.status == "inactive"
        assert old.effective_to == today - timedelta(days=1)
        # ⚠️ 区间不许倒挂（`ck_delivery_rate_rules_window`）——
        # 倒挂就是「把旧价抹掉」，也就是这次要修的那个 bug。
        assert old.effective_to >= old.effective_from
        # 旧价本身不能被改写
        assert float(old.unit_price) == OLD_PRICE


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_reprice_ignores_backdated_effective_from(delivery_client):
    """改价时**传过去的生效日不许抹掉历史** ⇒ 生效日一律从今天起。"""
    client, session_factory = delivery_client
    old_rule_id = await _seed(session_factory)

    response = await client.post(
        "/api/delivery-rate-rules",
        json=_create_payload(effective_from="2026-01-01"),
    )
    assert response.status_code == 201, response.text
    assert response.json()["effective_from"] == date.today().isoformat()

    async with session_factory() as session:
        old = await session.get(DeliveryRateRule, old_rule_id)
        # 旧价这一段（2026-01-01 ~ 昨天）仍然是历史的一部分
        assert old.effective_from == OLD_EFFECTIVE_FROM
        assert old.effective_to == date.today() - timedelta(days=1)


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_reprice_keeps_exactly_one_current_row(delivery_client):
    """改价后当期行仍然只有一条（``uq_delivery_rate_rules_current``）。"""
    client, session_factory = delivery_client
    await _seed(session_factory)

    response = await client.post("/api/delivery-rate-rules", json=_create_payload())
    assert response.status_code == 201, response.text

    async with session_factory() as session:
        current = (
            (
                await session.execute(
                    select(DeliveryRateRule).where(
                        DeliveryRateRule.platform_code == PLATFORM,
                        DeliveryRateRule.warehouse_code == WAREHOUSE,
                        DeliveryRateRule.weight_tier_code == TIER,
                        DeliveryRateRule.status == "active",
                        DeliveryRateRule.effective_to.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(current) == 1
        assert float(current[0].unit_price) == NEW_PRICE


# ---------------------------------------------------------------------------
# 2 · 只改备注：走 PATCH，不新建行
# ---------------------------------------------------------------------------


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_notes_only_update_does_not_create_new_version(delivery_client):
    """只改备注 ⇒ PATCH ⇒ 行数不变、单价不变（不该开新版本）。"""
    client, session_factory = delivery_client
    rule_id = await _seed(session_factory)

    response = await client.patch(
        f"/api/delivery-rate-rules/{rule_id}",
        json={"notes": "买家承担运费，卖家承担 2.30"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["notes"] == "买家承担运费，卖家承担 2.30"
    assert body["rule_id"] == rule_id
    assert float(body["unit_price"]) == OLD_PRICE

    async with session_factory() as session:
        rows = (await session.execute(select(DeliveryRateRule))).scalars().all()
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# 3 · 币种护栏（写入端只收人民币等值）
# ---------------------------------------------------------------------------


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_create_rejects_foreign_currency(delivery_client):
    """外币价目表不能直接当人民币存 ⇒ 尾程少算 5 倍 ⇒ 成本底线偏低 ⇒ 漏钱。"""
    client, session_factory = delivery_client
    await _seed(session_factory)

    response = await client.post(
        "/api/delivery-rate-rules",
        json=_create_payload(currency="SGD", unit_price=4.29),
    )
    assert response.status_code in (400, 422), response.text


# ---------------------------------------------------------------------------
# 4 · 新增（该段本来没有当期行）：生效日由调用方给，可回填整张价目表
# ---------------------------------------------------------------------------


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_new_tier_keeps_caller_supplied_effective_from(delivery_client):
    """第一次录某一档 ⇒ 生效日照调用方给的来（整张价目表可以从 2026-01-01 起算）。"""
    client, session_factory = delivery_client
    # T02 的段定义有，但**还没有费率行**（第一次录这一档）
    await _seed(session_factory, tier_code="T02", with_rate=False)

    response = await client.post(
        "/api/delivery-rate-rules",
        json=_create_payload(weight_tier_code="T02", effective_from="2026-01-01"),
    )
    assert response.status_code == 201, response.text
    assert response.json()["effective_from"] == "2026-01-01"
