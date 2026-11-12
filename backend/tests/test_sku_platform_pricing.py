"""阶段 2.1 · 底线下沉到「SKU × 平台」的回归测试。

对应实施方案 §4.1.5 的六条：

1. 同一 SKU 两个平台 ⇒ **两条底线**，按各自费率算
2. ``load_pricing_context`` 返回**两个平台**的费率
3. 人工覆盖：新表读写 + 回落 SKU 级旧列
4. 通知基线：``(sku_id, platform_code)`` 粒度；一个平台变价**不**触发另一个平台的变更通知
5. 迁移幂等：跑两次不报错；``downgrade`` 能回退
6. 护栏：Shopee 底线 > TikTok 底线（回归 §11.2② 的实测偏差）

为什么值得单独钉死这六条
------------------------
生产库实测（2026-11-07 只读核查）：同一个 SKU ``166851422928`` 在 Shopee 与 TikTok 上
底线**完全一样**（59.29），而按 Shopee 真实费率应该是 103.36 —— **偏低 74.3%**。
根因是底线公式里的平台成本率取自规则表指定的**单一 basis 平台**（TikTok），
于是所有平台都拿 TikTok 的成本结构算底线。

方向是**偏松** ⇒ 护栏「预计售价低于最低售价」在 Shopee 上**放行本该拦住的品** ⇒ 真亏本。

所以第 1、2、6 条是**业务红线**：一旦退化回去（两个平台底线又相等），这几条就会红。
第 3、4 条守的是**粒度**：底线按平台分了，基线不按平台分，
就会出现「Shopee 涨了、TikTok 跟着报」这种噪音通知。
第 5 条守的是**部署安全**：迁移必须能重复跑、能干净回退。
"""

from __future__ import annotations

import importlib.util
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from backend.services.price_adjust_notify_service import PriceAdjustNotifyService
from backend.services.product_pricing_query_service import (
    compute_pricing_state,
    load_pricing_context,
    resolve_pricing_platform,
    resolve_pricing_platform_code,
)
from backend.utils.project_env import isolated_database_url


VERSIONS_DIR = Path("current_migrations/versions")
PLATFORM_PRICING_MIGRATION = VERSIONS_DIR / "20261115_add_sku_platform_pricing.py"


# ---------------------------------------------------------------------------
# 固定输入（生产库实测的费率 + 手算的底线）
#
# 底线公式：cost_floor = 采购成本 ÷ (1 − 平台其他成本率 − 达人佣金率
#                                  − SPU退货损失率 − SPU货损率 − 目标利润率)
# 纪律线：discount_guard = 参考售价 × (1 − 当前档折扣率)
# 底线 = max(cost_floor, discount_guard, 人工覆盖)
#
# 这些期望值是**手算**出来的，不依赖被测代码的输出 ——
# 否则测试只是在"验证代码等于它自己"。
# ---------------------------------------------------------------------------

TIKTOK_OTHER_COST_RATE = Decimal("0.2727")
TIKTOK_CREATOR_RATE = Decimal("0.0606")
SHOPEE_OTHER_COST_RATE = Decimal("0.4165")
SHOPEE_CREATOR_RATE = Decimal("0.0111")

PURCHASE_COST = Decimal("45.20")
SPU_RETURN_LOSS_RATE = Decimal("0.0467")
SPU_DAMAGE_RATE = Decimal("0.0158")
TARGET_MARGIN_RATE = Decimal("0.25")
DISCOUNT_RATE = Decimal("0.10")
REFERENCE_SELLING_PRICE = Decimal("30.00")

# 45.20 ÷ (1 − 0.2727 − 0.0606 − 0.0467 − 0.0158 − 0.25) = 127.6115… → 127.61
TIKTOK_FLOOR = Decimal("127.61")
# 45.20 ÷ (1 − 0.4165 − 0.0111 − 0.0467 − 0.0158 − 0.25) = 173.9130… → 173.91
SHOPEE_FLOOR = Decimal("173.91")
# 纪律线：30.00 × (1 − 0.10) = 27.00 —— 比两条成本线都低，所以不参与取最大
DISCOUNT_GUARD = Decimal("27.00")


def _floor(payload: dict) -> Decimal:
    """把计算结果还原成 Decimal（纯函数返回的是 float）。"""
    value = payload["min_selling_price"]
    assert value is not None, payload
    return Decimal(str(value))


# ---------------------------------------------------------------------------
# SQLite 夹具（不依赖 PostgreSQL 容器，任何环境都能跑）
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def pricing_sqlite_session():
    """只建本用例需要的表的 SQLite 会话。

    SQLite 没有真正的 schema：``core.xxx`` 会被当成「core 库里的 xxx 表」，
    所以先 ``ATTACH ':memory:' AS core``。

    只建需要的几张表——**不**走全量 ``Base.metadata.create_all``：
    那 191 张表里有 postgres 专有的类型与表达式，在 SQLite 上建表会挂。
    """
    from modules.core.db import Base

    wanted = (
        "core.dim_platforms",
        "core.dim_warehouses",
        "core.dim_spu",
        "core.dim_erp_sku",
        "core.bridge_spu_sku",
        "finance.sku_pricing_policies",
        "finance.sku_platform_pricing",
        "ops.price_adjust_baselines",
    )
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.connect() as conn:
        for schema in ("core", "finance", "ops"):
            await conn.exec_driver_sql(f"ATTACH DATABASE ':memory:' AS {schema}")
        for name in wanted:
            await conn.run_sync(Base.metadata.tables[name].create, checkfirst=True)
        async with AsyncSession(conn) as session:
            yield session
    await engine.dispose()


async def _seed_two_platforms(session) -> int:
    """种一个 SKU + 两个销售平台 + 一档规则。

    费率取生产库实测值（2026-11-07）：TikTok other 27.27% / 达人 6.06%，
    Shopee other 41.65% / 达人 1.11%。
    """
    from modules.core.db import (
        BridgeSpuSku,
        DimErpSku,
        DimPlatform,
        DimSpu,
        SkuPricingPolicy,
    )

    session.add_all(
        [
            DimPlatform(
                platform_code="tiktok",
                name="TikTok",
                default_creator_commission_rate=TIKTOK_CREATOR_RATE,
                other_cost_rate=TIKTOK_OTHER_COST_RATE,
                platform_role="sales",
                is_active=True,
            ),
            DimPlatform(
                platform_code="shopee",
                name="Shopee",
                default_creator_commission_rate=SHOPEE_CREATOR_RATE,
                other_cost_rate=SHOPEE_OTHER_COST_RATE,
                platform_role="sales",
                is_active=True,
            ),
            SkuPricingPolicy(
                min_restock_days=0,
                tier_label="日常",
                discount_rate=DISCOUNT_RATE,
                target_margin_rate=TARGET_MARGIN_RATE,
                platform_basis="tiktok",
                effective_from=date(2026, 1, 1),
                effective_to=None,
                status="active",
                source="test",
            ),
            DimSpu(
                spu="SPU-1",
                spu_name="测试 SPU",
                logistics_damage_rate=SPU_DAMAGE_RATE,
                return_loss_rate=SPU_RETURN_LOSS_RATE,
                biz_status="candidate",
                active=True,
            ),
        ]
    )
    sku = DimErpSku(
        sku_key="SKU-TEST-1",
        sku_name="测试 SKU",
        specification="1 件",
        default_purchase_cost=PURCHASE_COST,
        purchase_cost_currency="CNY",
        purchase_cost_confidence="high",
        reference_selling_price=REFERENCE_SELLING_PRICE,
        # 阶段 4 工具 2：有基准售价就必须有确认日期
        selling_price_confirmed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        selling_price_currency="CNY",
        status="active",
    )
    session.add(sku)
    await session.flush()
    session.add(
        BridgeSpuSku(
            spu="SPU-1",
            sku_id=sku.sku_id,
            effective_from=date(2026, 1, 1),
            effective_to=None,
            binding_status="active",
        )
    )
    await session.flush()
    return sku.sku_id


async def _floors_by_platform(session, sku_id: int) -> dict[str, Decimal]:
    """同一批原料下，两个平台各自的底线。"""
    from modules.core.db import DimErpSku, DimSpu

    context = await load_pricing_context(session, [sku_id], ["tiktok", "shopee"])
    sku_row = await session.get(DimErpSku, sku_id)
    linked_spu = await session.get(DimSpu, "SPU-1")
    floors = {}
    for platform_code in ("tiktok", "shopee"):
        state = compute_pricing_state(
            context=context,
            sku_row=sku_row,
            linked_spu=linked_spu,
            platform_code=platform_code,
        )
        floors[platform_code] = _floor(state["pricing"])
    return floors


# ---------------------------------------------------------------------------
# ① 同一 SKU 两个平台 ⇒ 两条底线，按各自费率算
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_same_sku_has_one_floor_per_platform(pricing_sqlite_session):
    """同一件商品在 TikTok 与 Shopee 上必须**各有一条底线**。

    修复前两个平台的底线**完全相同**（都拿 TikTok 的费率算），
    Shopee 的底线被低估三到七成 ⇒ 护栏放行本该拦住的品。
    """
    session = pricing_sqlite_session
    sku_id = await _seed_two_platforms(session)

    floors = await _floors_by_platform(session, sku_id)

    assert floors["tiktok"] == TIKTOK_FLOOR
    assert floors["shopee"] == SHOPEE_FLOOR
    # 核心断言：两个平台**不再**共用一条底线
    assert floors["shopee"] > floors["tiktok"]
    # 偏差量级对得上生产库实测（Shopee 费率更高 ⇒ 底线更高）
    assert (floors["shopee"] / floors["tiktok"]) > Decimal("1.3")


@pytest.mark.asyncio
async def test_each_platform_uses_its_own_rate(pricing_sqlite_session):
    """两条底线的差**只能**来自平台费率 —— 换成各自的费率单独验算一遍。

    逐条验算（而不是只比大小）才能保证：不是"碰巧不一样"，
    而是"确实按各自费率算的"。
    """
    session = pricing_sqlite_session
    sku_id = await _seed_two_platforms(session)

    from modules.core.db import DimErpSku, DimSpu

    context = await load_pricing_context(session, [sku_id], ["tiktok", "shopee"])
    sku_row = await session.get(DimErpSku, sku_id)
    linked_spu = await session.get(DimSpu, "SPU-1")

    for platform_code, other_rate, creator_rate, expected in (
        ("tiktok", TIKTOK_OTHER_COST_RATE, TIKTOK_CREATOR_RATE, TIKTOK_FLOOR),
        ("shopee", SHOPEE_OTHER_COST_RATE, SHOPEE_CREATOR_RATE, SHOPEE_FLOOR),
    ):
        denominator = (
            Decimal("1")
            - other_rate
            - creator_rate
            - SPU_RETURN_LOSS_RATE
            - SPU_DAMAGE_RATE
            - TARGET_MARGIN_RATE
        )
        state = compute_pricing_state(
            context=context,
            sku_row=sku_row,
            linked_spu=linked_spu,
            platform_code=platform_code,
        )
        pricing = state["pricing"]
        assert _floor(pricing) == expected, platform_code
        # 成本线是这两条底线里更高的一条（纪律线只有 27.00）
        assert pricing["min_selling_price_source"] == "cost_floor"
        assert denominator > 0


# ---------------------------------------------------------------------------
# ② load_pricing_context 返回两个平台的费率
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pricing_context_exposes_both_platforms_rates(pricing_sqlite_session):
    """取数层要一次把**所有销售平台**的费率读出来，计算层按平台取。

    以前只返回一个 ``platform``（规则表指定的 basis 平台），
    于是所有平台的底线都拿那一份费率算。
    """
    session = pricing_sqlite_session
    sku_id = await _seed_two_platforms(session)

    context = await load_pricing_context(session, [sku_id], ["tiktok", "shopee"])

    platforms = context["platforms"]
    assert set(platforms) >= {"tiktok", "shopee"}
    assert Decimal(str(platforms["tiktok"].other_cost_rate)) == TIKTOK_OTHER_COST_RATE
    assert Decimal(str(platforms["shopee"].other_cost_rate)) == SHOPEE_OTHER_COST_RATE
    assert (
        Decimal(str(platforms["tiktok"].default_creator_commission_rate))
        == TIKTOK_CREATOR_RATE
    )
    assert (
        Decimal(str(platforms["shopee"].default_creator_commission_rate))
        == SHOPEE_CREATOR_RATE
    )

    # 可定价平台 = 有平台其他成本率的销售平台
    assert context["priceable_platform_codes"] == ["shopee", "tiktok"]

    # 取平台费率的那一步必须按 platform_code 命中，不能总拿第一份
    assert resolve_pricing_platform(context, "shopee") is platforms["shopee"]
    assert resolve_pricing_platform(context, "tiktok") is platforms["tiktok"]
    assert resolve_pricing_platform_code(context, "shopee") == "shopee"


@pytest.mark.asyncio
async def test_floor_no_longer_follows_the_policy_basis_platform(
    pricing_sqlite_session,
):
    """规则表里的 ``platform_basis`` **不再**决定用哪个平台的费率算底线。

    这是本阶段最容易被"改回去"的一处：只要还有任何地方按 basis 平台取费率，
    底线就会重新变成 SKU 级。钉死它。
    """
    from modules.core.db import SkuPricingPolicy

    session = pricing_sqlite_session
    sku_id = await _seed_two_platforms(session)

    before = await _floors_by_platform(session, sku_id)

    # 把规则表的 basis 平台从 tiktok 改成 shopee
    policy = (await session.execute(select(SkuPricingPolicy))).scalars().first()
    policy.platform_basis = "shopee"
    await session.flush()

    after = await _floors_by_platform(session, sku_id)

    # 两个平台的底线**一条都没变** —— basis 平台已经不参与费率选择了
    assert after["tiktok"] == before["tiktok"] == TIKTOK_FLOOR
    assert after["shopee"] == before["shopee"] == SHOPEE_FLOOR


# ---------------------------------------------------------------------------
# ③ 人工覆盖：新表读写 + 回落 SKU 级旧列
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_new_table_override_is_scoped_to_its_platform(pricing_sqlite_session):
    """新表 ``finance.sku_platform_pricing`` 的人工覆盖**只影响它自己那个平台**。"""
    from modules.core.db import SkuPlatformPricing

    session = pricing_sqlite_session
    sku_id = await _seed_two_platforms(session)

    session.add(
        SkuPlatformPricing(
            sku_id=sku_id,
            platform_code="shopee",
            min_selling_price_override=Decimal("200.00"),
            min_selling_price_source="manual_override",
        )
    )
    await session.flush()

    floors = await _floors_by_platform(session, sku_id)
    assert floors["shopee"] == Decimal("200.00")
    # TikTok 没有覆盖行 ⇒ 仍然走系统算的底线
    assert floors["tiktok"] == TIKTOK_FLOOR


@pytest.mark.asyncio
async def test_new_table_override_wins_over_the_legacy_sku_column(
    pricing_sqlite_session,
):
    """新表的覆盖值**取代**底线。

    ⚠️ 阶段 2.1b 起**没有**「回落 SKU 级旧列」这条分支了 ——
    旧列 ``core.dim_erp_sku.min_selling_price_override`` 已删：
    它是公司级的（一个数套所有平台），而且那张表会被「采集机 → 云端」
    同步 TRUNCATE ⇒ 覆盖值每次同步都蒸发。
    平台级覆盖的读写与平台隔离另见
    ``backend/tests/test_sku_platform_pricing_override.py``。
    """
    from modules.core.db import SkuPlatformPricing

    session = pricing_sqlite_session
    sku_id = await _seed_two_platforms(session)

    session.add(
        SkuPlatformPricing(
            sku_id=sku_id,
            platform_code="shopee",
            min_selling_price_override=Decimal("200.00"),
        )
    )
    await session.flush()

    floors = await _floors_by_platform(session, sku_id)
    # Shopee 有平台级覆盖 ⇒ 底线被取代
    assert floors["shopee"] == Decimal("200.00")
    # TikTok 没有覆盖 ⇒ 走系统算的底线（**不再**回落到任何 SKU 级旧列）
    assert floors["tiktok"] == TIKTOK_FLOOR


@pytest.mark.asyncio
async def test_legacy_sku_level_override_column_is_gone(pricing_sqlite_session):
    """SKU 级旧列已从 ORM 里删掉 —— 覆盖值只能是平台级的。

    这条是「口径不再错位 + 不会被同步抹掉」的结构性保证。
    """
    from modules.core.db import DimErpSku

    columns = {c.name for c in DimErpSku.__table__.columns}
    assert "min_selling_price_override" not in columns


@pytest.mark.asyncio
async def test_override_is_flagged_as_manual_override(pricing_sqlite_session):
    """人工覆盖生效时，来源标记必须是 ``manual_override``（通知归因靠它）。"""
    from modules.core.db import DimErpSku, DimSpu, SkuPlatformPricing

    session = pricing_sqlite_session
    sku_id = await _seed_two_platforms(session)

    session.add(
        SkuPlatformPricing(
            sku_id=sku_id,
            platform_code="shopee",
            min_selling_price_override=Decimal("200.00"),
        )
    )
    await session.flush()

    context = await load_pricing_context(session, [sku_id], ["shopee"])
    state = compute_pricing_state(
        context=context,
        sku_row=await session.get(DimErpSku, sku_id),
        linked_spu=await session.get(DimSpu, "SPU-1"),
        platform_code="shopee",
    )
    pricing = state["pricing"]
    assert pricing["min_selling_price_source"] == "manual_override"
    assert pricing["min_selling_price_is_override"] is True


# ---------------------------------------------------------------------------
# ④ 通知基线：(sku_id, platform_code) 粒度
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_baselines_are_keyed_by_sku_and_platform(pricing_sqlite_session):
    """状态与基线都按 ``(sku_id, platform_code)`` 归位。"""
    from modules.core.db import PriceAdjustBaseline

    session = pricing_sqlite_session
    sku_id = await _seed_two_platforms(session)

    service = PriceAdjustNotifyService(session)
    states = await service.collect_pricing_states()
    assert set(states) == {(sku_id, "tiktok"), (sku_id, "shopee")}

    notify, silent = await service.detect_changes()
    assert notify == []
    assert len(silent) == 2

    await service.advance_baselines(silent)

    baselines = await service.load_baselines()
    assert set(baselines) == {(sku_id, "tiktok"), (sku_id, "shopee")}
    assert baselines[(sku_id, "tiktok")]["min_selling_price"] == TIKTOK_FLOOR
    assert baselines[(sku_id, "shopee")]["min_selling_price"] == SHOPEE_FLOOR

    # 库里也必须是两行（复合主键），不是一行
    rows = (await session.execute(select(PriceAdjustBaseline))).scalars().all()
    assert len(rows) == 2
    assert {(row.sku_id, row.platform_code) for row in rows} == {
        (sku_id, "tiktok"),
        (sku_id, "shopee"),
    }


@pytest.mark.asyncio
async def test_price_change_on_one_platform_does_not_notify_the_other(
    pricing_sqlite_session,
):
    """Shopee 的费率变了 ⇒ 只报 Shopee；TikTok 的底线没动 ⇒ 一声不吭。

    修复前基线只有 ``sku_id`` 一个维度，于是 Shopee 的底线一动
    就会被记成"TikTok 的底线也动了" —— 运营收到一堆假警报。
    """
    from modules.core.db import DimPlatform

    session = pricing_sqlite_session
    sku_id = await _seed_two_platforms(session)

    service = PriceAdjustNotifyService(session)
    notify, silent = await service.detect_changes()
    assert notify == []
    await service.advance_baselines(silent)

    # Shopee 的平台其他成本率 41.65% → 45%
    shopee = await session.get(DimPlatform, "shopee")
    shopee.other_cost_rate = Decimal("0.45")
    await session.flush()

    notify, silent = await service.detect_changes()

    assert len(notify) == 1
    change = notify[0]
    assert change["platform_code"] == "shopee"
    assert change["sku_id"] == sku_id
    assert change["direction"] == "上升"
    assert change["old_min_selling_price"] == str(SHOPEE_FLOOR)
    # 45.20 ÷ (1 − 0.45 − 0.0111 − 0.0467 − 0.0158 − 0.25) = 199.646… → 199.65
    assert change["new_min_selling_price"] == "199.65"
    assert silent == []


@pytest.mark.asyncio
async def test_platform_is_recorded_in_the_attribution_context(pricing_sqlite_session):
    """归因上下文里要带上平台 —— 不然运营看不懂"这是哪个平台的底线变了"。"""
    session = pricing_sqlite_session
    sku_id = await _seed_two_platforms(session)

    service = PriceAdjustNotifyService(session)
    states = await service.collect_pricing_states()

    assert states[(sku_id, "tiktok")]["context"]["platform_code"] == "tiktok"
    assert states[(sku_id, "shopee")]["context"]["platform_code"] == "shopee"


# ---------------------------------------------------------------------------
# ⑤ 迁移幂等 + downgrade 回退
# ---------------------------------------------------------------------------


def _read_migration() -> str:
    return PLATFORM_PRICING_MIGRATION.read_text(encoding="utf-8")


def _load_migration_module():
    spec = importlib.util.spec_from_file_location(
        "_contract_sku_platform_pricing", PLATFORM_PRICING_MIGRATION
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_is_chained_on_the_current_head():
    source = _read_migration()
    assert 'revision = "current_schema_20261115_add_sku_platform_pricing"' in source
    assert 'down_revision = "current_schema_20261114_add_sku_roi_columns"' in source


def test_migration_guards_every_object():
    """幂等范式：每个对象都有存在性守卫，重复执行不报错。"""
    source = _read_migration()
    assert "def _has_table(" in source
    assert "def _has_column(" in source
    assert "def _has_index(" in source
    assert "def _has_unique_constraint(" in source
    assert "def _primary_key_columns(" in source
    assert "def upgrade() -> None:" in source
    assert "def downgrade() -> None:" in source
    # 复合主键：upgrade 换主键、downgrade 换回去
    assert "op.create_primary_key(" in source
    assert '["sku_id", "platform_code"]' in source
    assert '["sku_id"],' in source


@pytest.fixture(scope="module")
def isolated_engine():
    url = isolated_database_url()
    if not url:
        pytest.skip("隔离测试库地址未就绪")
    engine = create_engine(url)
    yield engine
    engine.dispose()


def _run_migration(engine, module, func_name: str) -> None:
    def _do(connection):
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            getattr(module, func_name)()

    with engine.begin() as connection:
        _do(connection)


def test_migration_is_repeatable_and_rolls_back_cleanly(isolated_engine):
    """在真实 PostgreSQL 上跑：upgrade ×2 → downgrade → upgrade。

    重复执行必须无害（部署脚本会重跑）；downgrade 必须能把新表与复合主键都撤掉。
    """
    module = _load_migration_module()

    # 1) 幂等：跑两次不报错
    _run_migration(isolated_engine, module, "upgrade")
    _run_migration(isolated_engine, module, "upgrade")

    inspector = inspect(isolated_engine)
    assert inspector.has_table("sku_platform_pricing", schema="finance")
    pricing_columns = {
        column["name"]
        for column in inspector.get_columns("sku_platform_pricing", schema="finance")
    }
    assert {
        "sku_id",
        "platform_code",
        "min_selling_price_override",
        "min_selling_price_source",
        "pricing_tier_label",
        "pricing_days_since_restock",
        "pricing_tier_source",
    } <= pricing_columns
    baseline_pk = list(
        inspector.get_pk_constraint("price_adjust_baselines", schema="ops")[
            "constrained_columns"
        ]
    )
    assert baseline_pk == ["sku_id", "platform_code"]

    # 2) downgrade 能干净撤掉
    _run_migration(isolated_engine, module, "downgrade")

    inspector = inspect(isolated_engine)
    assert not inspector.has_table("sku_platform_pricing", schema="finance")
    baseline_columns = {
        column["name"]
        for column in inspector.get_columns("price_adjust_baselines", schema="ops")
    }
    assert "platform_code" not in baseline_columns
    baseline_pk = list(
        inspector.get_pk_constraint("price_adjust_baselines", schema="ops")[
            "constrained_columns"
        ]
    )
    assert baseline_pk == ["sku_id"]

    # 3) 再 upgrade 回来
    _run_migration(isolated_engine, module, "upgrade")

    inspector = inspect(isolated_engine)
    assert inspector.has_table("sku_platform_pricing", schema="finance")
    baseline_pk = list(
        inspector.get_pk_constraint("price_adjust_baselines", schema="ops")[
            "constrained_columns"
        ]
    )
    assert baseline_pk == ["sku_id", "platform_code"]


def test_migration_backfills_the_baseline_platform(isolated_engine):
    """老基线行按该 SKU 的经营档案回填平台；没有档案的落规则表 basis 平台。"""
    from modules.core.db import PriceAdjustBaseline

    module = _load_migration_module()

    # 先回到"老结构"：单列主键 + 没有 platform_code
    _run_migration(isolated_engine, module, "downgrade")

    with isolated_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO ops.price_adjust_baselines (sku_id, last_notified_min_price) "
                "VALUES (987654, 88.88)"
            )
        )

    _run_migration(isolated_engine, module, "upgrade")

    with isolated_engine.connect() as connection:
        platform_code = connection.execute(
            text(
                "SELECT platform_code FROM ops.price_adjust_baselines "
                "WHERE sku_id = 987654"
            )
        ).scalar()
    assert platform_code == "tiktok"  # 规则表 basis 平台兜底

    with isolated_engine.begin() as connection:
        connection.execute(
            text("DELETE FROM ops.price_adjust_baselines WHERE sku_id = 987654")
        )


# ---------------------------------------------------------------------------
# ⑥ 护栏：Shopee 底线 > TikTok 底线（端到端，真实 PostgreSQL）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_guardrail_uses_the_floor_of_the_requested_platform(
    pg_async_client, pricing_auth_headers, pg_session, pricing_seed
):
    """**同一个价格**，TikTok 放行、Shopee 拦下。

    这就是生产库实测到的那个病：以前两个平台共用一条底线（都拿 TikTok 费率算），
    于是 Shopee 上本该拦住的品被放行 ⇒ 真亏本。
    """
    await pricing_seed()

    from modules.core.db import DimPlatform

    # 加一个 Shopee 平台（费率取生产库实测值）
    pg_session.add(
        DimPlatform(
            platform_code="shopee",
            name="Shopee",
            platform_role="sales",
            is_active=True,
            default_fee_rate=0.1487,
            default_creator_commission_rate=0.0111,
            other_cost_rate=0.4165,
        )
    )
    await pg_session.flush()

    payload = {
        "sku_id": 9001,
        "warehouse_code": "MY-01",
        "transport_type": "sea",
        "expected_selling_price": 35,
    }

    # TikTok：seed 的成本线 10 ÷ 0.3542 = 28.23，35 高于它 ⇒ 放行
    tiktok = await pg_async_client.post(
        "/api/platform-sku-profit/estimates",
        headers=pricing_auth_headers,
        json={**payload, "platform_code": "tiktok"},
    )
    assert tiktok.status_code == 201, tiktok.text

    # Shopee：成本线 10 ÷ 0.2599 = 38.48，35 低于它 ⇒ 必须拦下
    shopee = await pg_async_client.post(
        "/api/platform-sku-profit/estimates",
        headers=pricing_auth_headers,
        json={**payload, "platform_code": "shopee"},
    )
    assert shopee.status_code == 422, shopee.text
    body = shopee.json()
    assert body["success"] is False
    assert body["error"]["detail"]["code"] == "below_min_selling_price"
    assert body["error"]["detail"]["min_selling_price"] == pytest.approx(
        38.48, abs=0.01
    )


@pytest.mark.asyncio
async def test_candidate_list_reports_the_floor_of_the_selected_platform(
    pg_async_client, pricing_auth_headers, pg_session, pricing_seed
):
    """候选列表按**所选平台**给底线，并把平台带出来（前端要显示，别让人误读）。"""
    await pricing_seed()

    from modules.core.db import DimPlatform

    pg_session.add(
        DimPlatform(
            platform_code="shopee",
            name="Shopee",
            platform_role="sales",
            is_active=True,
            default_fee_rate=0.1487,
            default_creator_commission_rate=0.0111,
            other_cost_rate=0.4165,
        )
    )
    await pg_session.flush()

    floors = {}
    for platform_code in ("tiktok", "shopee"):
        response = await pg_async_client.get(
            "/api/platform-sku-profit/candidates",
            headers=pricing_auth_headers,
            params={
                "platform_code": platform_code,
                "warehouse_code": "MY-01",
                "transport_type": "sea",
            },
        )
        assert response.status_code == 200, response.text
        rows = response.json()["data"]
        assert rows, f"{platform_code} 应有候选行"
        row = rows[0]
        assert row["min_selling_price_platform"] == platform_code
        floors[platform_code] = row["min_selling_price"]

    # 10 ÷ 0.3542 = 28.23（TikTok） vs 10 ÷ 0.2599 = 38.48（Shopee）
    assert floors["tiktok"] == pytest.approx(28.23, abs=0.01)
    assert floors["shopee"] == pytest.approx(38.48, abs=0.01)
    assert floors["shopee"] > floors["tiktok"]
