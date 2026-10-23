"""最低售价变更检测与通知的单元测试。

分两类：

1. **纯函数测试**（无 DB）——覆盖全部业务判断：方向、幅度、归因、排除规则。
   这些是这块代码里最容易出错、后果最直接的部分（错判方向 = 运营做错动作；
   误排除 = 该通知的没通知；归因错 = 运营看不懂为什么变）。
2. **口径一致性测试**——同一批原料下，
   商品中心路由算出的最低售价与检测服务算出的必须**完全相等**。
   两边喂给 `compute_sku_pricing` 的原料一旦分叉，就会出现
   「页面显示按日常档、通知却按滞销档发」的自相矛盾。
3. **投递行为测试**（SQLite）——批量投递的分块成败、回写基线的时机。
"""

from __future__ import annotations

import json
import os
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select

from backend.services.price_adjust_notify_service import (
    DIRECTION_DOWN,
    DIRECTION_PROTECTION_LOST,
    DIRECTION_UP,
    REASON_DATA_MISSING,
    REASON_MANUAL_OVERRIDE,
    REASON_PLATFORM_RATE,
    REASON_POLICY,
    REASON_PURCHASE_COST,
    REASON_REFERENCE_PRICE,
    REASON_TIER_CHANGE,
    PriceAdjustNotifyService,
    build_context,
    classify_change_reason,
    classify_direction,
    compute_change_rate,
    is_delisting_jump,
)


def _context(**overrides) -> dict:
    """一份"日常档、有库龄"的默认归因上下文。"""
    base = {
        "min_selling_price": "128.56",
        "min_selling_price_source": "cost_floor",
        "min_selling_price_is_override": False,
        "pricing_tier_source": "age_data",
        "pricing_tier_label": "日常",
        "target_margin_rate": "0.25",
        "discount_rate": "0.10",
        "age_days": 10,
        "purchase_cost": "45.20",
        "other_cost_rate": "0.2727",
        "creator_commission_rate": "0.0606",
        "spu_return_loss_rate": "0.0467",
        "spu_damage_rate": "0.0158",
        "reference_selling_price": None,
        "missing_reasons": [],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# 方向
# ---------------------------------------------------------------------------


def test_classify_direction_down_when_floor_drops():
    assert classify_direction("128.56", "90.82") == DIRECTION_DOWN


def test_classify_direction_up_when_floor_rises():
    assert classify_direction("90.82", "128.56") == DIRECTION_UP


def test_classify_direction_protection_lost_when_floor_becomes_uncomputable():
    assert classify_direction("90.82", None) == DIRECTION_PROTECTION_LOST


def test_classify_direction_up_when_floor_appears_from_nothing():
    """从"算不出底线"变成"算得出"：底线从无到有 = 变严格了。"""
    assert classify_direction(None, "128.56") == DIRECTION_UP


def test_classify_direction_none_when_price_unchanged():
    assert classify_direction("128.56", "128.56") is None
    assert classify_direction("128.56", Decimal("128.56")) is None


def test_classify_direction_none_when_both_missing():
    assert classify_direction(None, None) is None


# ---------------------------------------------------------------------------
# 幅度
# ---------------------------------------------------------------------------


def test_compute_change_rate_is_negative_for_floor_drop():
    # 90.82 / 128.56 - 1 = -0.2936...
    rate = compute_change_rate("128.56", "90.82")
    assert rate is not None
    assert rate < 0
    assert round(rate, 4) == -0.2936


def test_compute_change_rate_is_positive_for_floor_rise():
    rate = compute_change_rate("90.82", "128.56")
    assert rate is not None and rate > 0


def test_compute_change_rate_none_when_old_price_missing_or_zero():
    assert compute_change_rate(None, "128.56") is None
    assert compute_change_rate("0", "128.56") is None
    assert compute_change_rate("128.56", None) is None


# ---------------------------------------------------------------------------
# 归因
# ---------------------------------------------------------------------------


def test_reason_tier_change_when_tier_label_moved():
    prev = _context(pricing_tier_label="日常", target_margin_rate="0.25", discount_rate="0.10")
    cur = _context(pricing_tier_label="滞销60天", target_margin_rate="0.18", discount_rate="0.20")
    assert classify_change_reason(prev, cur) == REASON_TIER_CHANGE


def test_reason_purchase_cost_change():
    prev = _context(purchase_cost="45.20")
    cur = _context(purchase_cost="51.00")
    assert classify_change_reason(prev, cur) == REASON_PURCHASE_COST


def test_reason_platform_rate_change():
    prev = _context(other_cost_rate="0.2727")
    cur = _context(other_cost_rate="0.3000")
    assert classify_change_reason(prev, cur) == REASON_PLATFORM_RATE


def test_reason_platform_rate_change_on_creator_commission():
    prev = _context(creator_commission_rate="0.0606")
    cur = _context(creator_commission_rate="0.0800")
    assert classify_change_reason(prev, cur) == REASON_PLATFORM_RATE


def test_reason_policy_change_when_discount_rate_moved_but_tier_stayed():
    """同一档改了折扣率 = 规则调整（全局规则表改动），不是库龄跨档。"""
    prev = _context(pricing_tier_label="日常", discount_rate="0.10")
    cur = _context(pricing_tier_label="日常", discount_rate="0.15")
    assert classify_change_reason(prev, cur) == REASON_POLICY


def test_reason_reference_price_change():
    prev = _context(reference_selling_price=None)
    cur = _context(reference_selling_price="128.56")
    assert classify_change_reason(prev, cur) == REASON_REFERENCE_PRICE


def test_reason_data_missing_when_degradation_chain_changed():
    prev = _context(missing_reasons=[])
    cur = _context(missing_reasons=["missing_purchase_cost"])
    assert classify_change_reason(prev, cur) == REASON_DATA_MISSING


def test_reason_manual_override_when_override_flag_flipped():
    prev = _context(min_selling_price_is_override=False)
    cur = _context(min_selling_price_is_override=True)
    assert classify_change_reason(prev, cur) == REASON_MANUAL_OVERRIDE


def test_reason_data_missing_outranks_everything():
    """缺料是"算不出底线"，比任何单价变化都更该先说。"""
    prev = _context(purchase_cost="45.20", missing_reasons=[])
    cur = _context(purchase_cost="51.00", missing_reasons=["missing_purchase_cost"])
    assert classify_change_reason(prev, cur) == REASON_DATA_MISSING


# ---------------------------------------------------------------------------
# 排除规则：下架造成的跳高
# ---------------------------------------------------------------------------


def test_delisting_jump_is_excluded():
    """库存清零 -> 库龄记录消失 -> 回落日常档 -> 底线跳回最高。

    这个品已经不卖了，底线高低没有业务含义，不该通知。
    """
    prev = _context(
        pricing_tier_source="age_data",
        pricing_tier_label="滞销60天",
        target_margin_rate="0.18",
        discount_rate="0.20",
        age_days=95,
    )
    cur = _context(
        pricing_tier_source="fallback_no_age_data",
        pricing_tier_label="日常",
        target_margin_rate="0.25",
        discount_rate="0.10",
        age_days=None,
    )
    assert is_delisting_jump(prev, cur) is True


def test_delisting_jump_not_excluded_when_other_input_also_changed():
    """同时成本也变了 -> 这次变化不只是"下架"造成的 -> 仍然要通知。"""
    prev = _context(pricing_tier_source="age_data", purchase_cost="45.20")
    cur = _context(
        pricing_tier_source="fallback_no_age_data",
        purchase_cost="51.00",
    )
    assert is_delisting_jump(prev, cur) is False


def test_delisting_jump_not_excluded_when_age_record_still_present():
    """库龄记录还在（只是天数归零 = 补货）-> 滞销品复活，要通知。"""
    prev = _context(pricing_tier_source="age_data", pricing_tier_label="滞销60天")
    cur = _context(pricing_tier_source="age_data", pricing_tier_label="日常")
    assert is_delisting_jump(prev, cur) is False


def test_delisting_jump_not_excluded_when_previous_had_no_age_either():
    prev = _context(pricing_tier_source="fallback_no_age_data")
    cur = _context(pricing_tier_source="fallback_no_age_data")
    assert is_delisting_jump(prev, cur) is False


# ---------------------------------------------------------------------------
# 上下文快照
# ---------------------------------------------------------------------------


def test_build_context_serializes_decimal_as_string():
    """JSON 存不下 Decimal；转字符串避免二进制浮点误差。"""
    context = build_context(
        pricing={
            "min_selling_price": 128.56,
            "min_selling_price_source": "cost_floor",
            "min_selling_price_is_override": False,
            "pricing_tier_source": "age_data",
            "pricing_tier_label": "日常",
            "min_selling_price_missing_reasons": [],
        },
        age_days=10,
        target_margin_rate=Decimal("0.25"),
        discount_rate=Decimal("0.10"),
        purchase_cost=Decimal("45.20"),
        other_cost_rate=Decimal("0.2727"),
        creator_commission_rate=Decimal("0.0606"),
        spu_return_loss_rate=Decimal("0.0467"),
        spu_damage_rate=Decimal("0.0158"),
        reference_selling_price=None,
    )
    assert context["target_margin_rate"] == "0.25"
    assert context["discount_rate"] == "0.10"
    assert context["purchase_cost"] == "45.20"
    assert context["reference_selling_price"] is None
    assert context["missing_reasons"] == []


def test_build_context_has_no_timestamp():
    """上下文里不能有时间戳——它是 outbox payload 哈希的输入，带时间戳会让去重失效。"""
    context = build_context(
        pricing={
            "min_selling_price": 1.0,
            "min_selling_price_source": "cost_floor",
            "min_selling_price_is_override": False,
            "pricing_tier_source": "age_data",
            "pricing_tier_label": "日常",
            "min_selling_price_missing_reasons": [],
        },
        age_days=1,
        target_margin_rate=Decimal("0.25"),
        discount_rate=Decimal("0.10"),
        purchase_cost=Decimal("1"),
        other_cost_rate=Decimal("0.27"),
        creator_commission_rate=Decimal("0.06"),
        spu_return_loss_rate=Decimal("0.04"),
        spu_damage_rate=Decimal("0.01"),
        reference_selling_price=None,
    )
    assert not any("time" in key or "date" in key for key in context)


# ---------------------------------------------------------------------------
# detect_changes（用假 service 覆盖取数，不碰 DB）
# ---------------------------------------------------------------------------


class _FakeService(PriceAdjustNotifyService):
    def __init__(self, states, baselines):
        super().__init__(db=None)  # type: ignore[arg-type]
        self._states = states
        self._baselines = baselines

    async def collect_pricing_states(self):
        return self._states

    async def load_baselines(self):
        return self._baselines


def _state(sku_id, price, context, **extra):
    payload = {
        "sku_id": sku_id,
        "sku_key": f"SKU-{sku_id}",
        "spu": "SPU-1",
        "sku_name": f"商品{sku_id}",
        "specification": "黑色",
        "min_selling_price": price,
        "context": context,
        "age_days": context.get("age_days"),
        "current_qty": 100,
        "inventory_value": 1000.0,
    }
    payload.update(extra)
    return payload


@pytest.mark.asyncio
async def test_first_run_only_builds_baseline_without_notifying():
    """首次运行：没有基线 -> 只建基线，不通知。

    否则第一天就会把全量 SKU 当成"变了"推一遍。
    """
    service = _FakeService({1: _state(1, 128.56, _context())}, {})
    notify, silent = await service.detect_changes()

    assert notify == []
    assert len(silent) == 1
    assert silent[0]["sku_id"] == 1
    assert silent[0]["min_selling_price"] == 128.56


@pytest.mark.asyncio
async def test_unchanged_floor_produces_no_change():
    service = _FakeService(
        {1: _state(1, 128.56, _context())},
        {1: {"min_selling_price": Decimal("128.56"), "context": _context()}},
    )
    notify, silent = await service.detect_changes()

    assert notify == []
    assert silent == []


@pytest.mark.asyncio
async def test_dropped_floor_produces_a_downward_notification():
    prev = _context(
        pricing_tier_label="滞销60天", target_margin_rate="0.18", discount_rate="0.20", age_days=95
    )
    cur = _context(
        pricing_tier_label="滞销60天以上",
        target_margin_rate="0.10",
        discount_rate="0.30",
        age_days=125,
    )
    service = _FakeService(
        {1: _state(1, 90.82, cur)},
        {1: {"min_selling_price": Decimal("128.56"), "context": prev}},
    )
    notify, silent = await service.detect_changes()

    assert silent == []
    assert len(notify) == 1
    change = notify[0]
    assert change["direction"] == DIRECTION_DOWN
    assert change["reason"] == REASON_TIER_CHANGE
    assert change["old_min_selling_price"] == "128.56"
    assert change["new_min_selling_price"] == "90.82"
    assert change["change_rate"] < 0


@pytest.mark.asyncio
async def test_delisting_jump_is_excluded_but_baseline_still_advances():
    """下架造成的跳高：不通知，但基线必须跟上。

    基线不跟上 -> 明天还会重复判定为同一次跳高 -> 永远排除、永远不通知，
    后续真实变化也会被这坨噪音挡住。
    """
    prev = _context(
        pricing_tier_source="age_data",
        pricing_tier_label="滞销60天",
        target_margin_rate="0.18",
        discount_rate="0.20",
        age_days=95,
    )
    cur = _context(
        pricing_tier_source="fallback_no_age_data",
        pricing_tier_label="日常",
        target_margin_rate="0.25",
        discount_rate="0.10",
        age_days=None,
    )
    service = _FakeService(
        {1: _state(1, 128.56, cur)},
        {1: {"min_selling_price": Decimal("90.82"), "context": prev}},
    )
    notify, silent = await service.detect_changes()

    assert notify == []
    assert len(silent) == 1
    assert silent[0]["min_selling_price"] == 128.56
    assert silent[0]["context"]["pricing_tier_source"] == "fallback_no_age_data"


@pytest.mark.asyncio
async def test_protection_loss_produces_a_notification():
    prev = _context()
    cur = _context(
        min_selling_price=None,
        min_selling_price_source="unavailable",
        missing_reasons=["missing_purchase_cost"],
    )
    service = _FakeService(
        {1: _state(1, None, cur)},
        {1: {"min_selling_price": Decimal("128.56"), "context": prev}},
    )
    notify, silent = await service.detect_changes()

    assert silent == []
    assert len(notify) == 1
    assert notify[0]["direction"] == DIRECTION_PROTECTION_LOST
    assert notify[0]["reason"] == REASON_DATA_MISSING
    assert notify[0]["change_rate"] is None


@pytest.mark.asyncio
async def test_protection_recovery_produces_a_notification():
    """底线从「算不出」变成「算得出」= 保护恢复了，必须通知。

    ⚠️ 这条曾经**永远发不出去**：算不出时基线价格是 NULL，
    而基线判据若用 `last_notified_min_price IS NOT NULL`，这个 SKU 就一直被当成
    "从未处理过" → 每次都静默重建基线 → 等它算出来了也仍然不通知。
    （2026-10-23 用真实库跑出来才发现：1122 个 SKU 里有 39 个一直在重复建基线。）
    """
    prev = _context(
        min_selling_price=None,
        min_selling_price_source="unavailable",
        missing_reasons=["missing_purchase_cost"],
    )
    cur = _context(min_selling_price="128.56", missing_reasons=[])
    service = _FakeService(
        {1: _state(1, 128.56, cur)},
        {1: {"min_selling_price": None, "context": prev}},
    )
    notify, silent = await service.detect_changes()

    assert silent == []
    assert len(notify) == 1
    assert notify[0]["direction"] == DIRECTION_UP
    assert notify[0]["reason"] == REASON_DATA_MISSING
    assert notify[0]["old_min_selling_price"] is None
    assert notify[0]["new_min_selling_price"] == "128.56"


# ---------------------------------------------------------------------------
# 口径一致性（SQLite，不依赖 PostgreSQL 容器）
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def core_sqlite_session():
    """只建 core 库里这几张表的 SQLite 会话。

    SQLite 没有真正的 schema：`core.xxx` 会被当成「core 库里的 xxx 表」，
    所以先 `ATTACH ':memory:' AS core`。

    只建本用例需要的 5 张表——**不**走全量 `Base.metadata.create_all`：
    那 191 张表里有 postgres 专有的类型与表达式，在 SQLite 上建表会挂，
    与本用例要验证的事情无关。
    """
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from modules.core.db import Base

    wanted = (
        "core.dim_platforms",
        "finance.sku_pricing_policies",
        "core.dim_spu",
        "core.dim_erp_sku",
        "core.bridge_spu_sku",
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


async def _seed_pricing_fixture(session) -> int:
    """种一条最小可算价的数据：平台 + 两档规则 + SPU + SKU + 绑定。

    库龄表（mart 层）在 SQLite 里不存在 → 库龄回落「无库龄」，
    这正是要覆盖的场景：两边都必须在**没有库龄**时给出同一个答案。
    """
    from datetime import date

    from modules.core.db import BridgeSpuSku, DimErpSku, DimPlatform, DimSpu, SkuPricingPolicy

    session.add(
        DimPlatform(
            platform_code="tiktok",
            name="TikTok",
            default_creator_commission_rate=Decimal("0.0606"),
            other_cost_rate=Decimal("0.2727"),
            platform_role="sales",
            is_active=True,
        )
    )
    session.add_all(
        [
            SkuPricingPolicy(
                min_age_days=0,
                tier_label="日常",
                discount_rate=Decimal("0.10"),
                target_margin_rate=Decimal("0.25"),
                platform_basis="tiktok",
                effective_from=date(2026, 1, 1),
                effective_to=None,
                status="active",
                source="test",
            ),
            SkuPricingPolicy(
                min_age_days=60,
                tier_label="滞销30天",
                discount_rate=Decimal("0.15"),
                target_margin_rate=Decimal("0.22"),
                platform_basis="tiktok",
                effective_from=date(2026, 1, 1),
                effective_to=None,
                status="active",
                source="test",
            ),
        ]
    )
    session.add(
        DimSpu(
            spu="SPU-1",
            spu_name="测试 SPU",
            logistics_damage_rate=0.0158,
            return_loss_rate=0.0467,
            biz_status="active",
            active=True,
        )
    )
    sku = DimErpSku(
        sku_key="SKU-TEST-1",
        sku_name="测试 SKU",
        specification="1 件",
        default_purchase_cost=45.20,
        purchase_cost_currency="CNY",
        purchase_cost_confidence="high",
        reference_selling_price=30.00,
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


@pytest.mark.asyncio
async def test_router_and_detection_share_one_pricing_implementation(core_sqlite_session):
    """商品中心页面算出的最低售价 == 通知里说的最低售价（无需 PostgreSQL）。

    这是「口径一致」的**结构性保证**：两边调用的是同一个函数
    （`backend/services/product_pricing_query_service.py`），
    所以不存在"页面按日常档、通知按滞销档"的可能。

    这条用例跑在 SQLite 上，因此**不依赖** pg 容器，
    在任何环境（包括 Windows 事件循环有问题的 CI）都能验证。
    """
    from backend.domains.business.routers.product_center import (
        _compute_pricing_for_sku,
        _pricing_context,
    )
    from backend.services.product_pricing_query_service import (
        compute_pricing_for_sku,
        load_pricing_context,
    )
    from modules.core.db import DimErpSku, DimSpu

    session = core_sqlite_session
    sku_id = await _seed_pricing_fixture(session)

    # 路由侧（商品中心页面）
    router_context = await _pricing_context(session, [sku_id])
    router_payload = _compute_pricing_for_sku(
        context=router_context,
        sku_row=await session.get(DimErpSku, sku_id),
        linked_spu=await session.get(DimSpu, "SPU-1"),
    )

    # 共享实现（唯一计算入口）
    shared_context = await load_pricing_context(session, [sku_id])
    shared_payload = compute_pricing_for_sku(
        context=shared_context,
        sku_row=await session.get(DimErpSku, sku_id),
        linked_spu=await session.get(DimSpu, "SPU-1"),
    )

    # 通知侧
    service = PriceAdjustNotifyService(session)
    states = await service.collect_pricing_states()
    detected = states[sku_id]["min_selling_price"]

    assert router_payload["min_selling_price"] is not None
    assert router_payload["min_selling_price"] == shared_payload["min_selling_price"]
    assert router_payload["min_selling_price"] == detected
    # 没有库龄 → 回落第 1 档，两边都得是同一个档
    assert router_payload["pricing_tier_label"] == "日常"
    assert router_payload["pricing_tier_source"] == "fallback_no_age_data"

    # 首次跑：只建基线，不通知
    notify, silent = await service.detect_changes()
    assert notify == []
    assert len(silent) == 1
    assert silent[0]["sku_id"] == sku_id
    assert silent[0]["min_selling_price"] == detected


@pytest.mark.asyncio
async def test_baseline_with_null_price_is_still_treated_as_processed(core_sqlite_session):
    """算不出最低售价的 SKU（基线价格是 NULL）**也算处理过**，不能每次重建基线。

    判据必须是「有没有基线行」而不是「价格列非 NULL」。
    否则这些 SKU 会永远被当成"首次建基线"，
    「底线从算不出变成算得出」这个变化就永远发不出去。
    """
    from backend.services.price_adjust_notify_service import PriceAdjustNotifyService
    from modules.core.db import PriceAdjustBaseline

    session = core_sqlite_session
    sku_id = await _seed_pricing_fixture(session)

    session.add(
        PriceAdjustBaseline(
            sku_id=sku_id,
            last_notified_min_price=None,
            last_notified_context={
                "min_selling_price": None,
                "missing_reasons": ["missing_purchase_cost"],
            },
        )
    )
    await session.flush()

    service = PriceAdjustNotifyService(session)
    baselines = await service.load_baselines()
    assert sku_id in baselines, "价格列为 NULL 但基线行存在的 SKU 必须被当成已处理"
    assert baselines[sku_id]["min_selling_price"] is None
    assert baselines[sku_id]["context"]["missing_reasons"] == ["missing_purchase_cost"]


@pytest.mark.asyncio
async def test_baseline_lives_outside_the_synced_sku_table(core_sqlite_session):
    """基线必须住在**不参与商品中心同步**的表里。

    商品中心同步对 ``core.dim_erp_sku`` 做 TRUNCATE + 全量重灌——
    基线若挂在那张表上，每次同步都会被抹掉，同步窗口内的真实变化会被静默吞掉。
    """
    from modules.core.db import DimErpSku, PriceAdjustBaseline

    sku_columns = {c.name for c in DimErpSku.__table__.columns}
    assert "last_notified_min_price" not in sku_columns, (
        "基线不能挂在会被 TRUNCATE 的 SKU 表上"
    )
    assert "last_notified_context" not in sku_columns

    assert PriceAdjustBaseline.__tablename__ == "price_adjust_baselines"
    assert PriceAdjustBaseline.__table__.schema == "ops"
    baseline_columns = {c.name for c in PriceAdjustBaseline.__table__.columns}
    assert {"sku_id", "last_notified_min_price", "last_notified_context"} <= baseline_columns


# ---------------------------------------------------------------------------
# 批量投递：分块成败 + 回写基线的时机
# ---------------------------------------------------------------------------


class _ChunkedFailingClient:
    """第 N 次调用失败的假客户端（用来模拟某一块写飞书失败）。"""

    def __init__(self, fail_at_call: int):
        self.fail_at_call = fail_at_call
        self.calls: list[int] = []
        self.base_tokens: list[str | None] = []
        self.base_token = "bascn_default"

    async def batch_create_records(
        self,
        table_id: str,
        records: list[dict],
        base_token: str | None = None,
    ) -> int:
        self.calls.append(len(records))
        self.base_tokens.append(base_token)
        if len(self.calls) == self.fail_at_call:
            raise RuntimeError("Feishu batch create failed: write conflict")
        return len(records)


@pytest.mark.asyncio
async def test_client_uses_base_v3_endpoint_and_create_records_key():
    """写入端点必须是 **base/v3**，body key 必须是 **create_records**。

    ⚠️ 这是 2026-10-23 对真实表实测出来的：旧版
    `/open-apis/bitable/v1/apps/{token}/tables/{id}/records/batch_create`
    会被飞书直接拒掉（`99992402 field validation failed`），
    连只带主字段的最小请求都过不去 → ERP 侧 100% 写不进表。
    """
    import httpx

    from backend.services import feishu_projection_client as mod

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content.decode("utf-8"))
        captured["has_auth"] = "authorization" in request.headers
        if "/auth/v3/tenant_access_token" in request.url.path:
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "t-fake"})
        return httpx.Response(
            200,
            json={"code": 0, "data": {"records": captured["body"]["create_records"]}},
        )

    original = mod.httpx.AsyncClient
    mod.httpx.AsyncClient = lambda *a, **k: original(
        *a, **{**k, "transport": httpx.MockTransport(handler)}
    )
    os.environ["FEISHU_PRODUCT_APP_ID"] = "cli_test"
    os.environ["FEISHU_PRODUCT_APP_SECRET"] = "secret"
    os.environ["FEISHU_PRODUCT_BASE_TOKEN"] = "bascn_default"
    try:
        client = mod.FeishuProjectionClient()
        await client.batch_create_records("tblABC", [{"ERP SKU": "X"}], "bascn_override")
    finally:
        mod.httpx.AsyncClient = original

    assert captured["method"] == "POST"
    assert captured["url"].endswith(
        "/open-apis/base/v3/bases/bascn_override/tables/tblABC/records/batch_create"
    ), captured["url"]
    assert list(captured["body"].keys()) == ["create_records"], captured["body"].keys()
    assert captured["has_auth"], "缺少 Authorization 头"


@pytest.mark.asyncio
async def test_price_adjust_uses_its_own_base_token_when_configured(outbox_sqlite_session):
    """调价记录表可以配在**另一个**多维表格里（base token 独立配置）。"""
    from backend.services.feishu_projection_service import FeishuProjectionService
    from modules.core.db import FeishuProjectionConfig

    session = outbox_sqlite_session
    await _seed_outbox(session, 1)

    config = FeishuProjectionConfig(
        provider_code="feishu",
        spu_table_id="tbl-spu",
        sku_table_id="tbl-sku",
        platform_sku_profit_table_id="tbl-profit",
        price_adjust_table_id="tbl-price",
        price_adjust_base_token="bascn_price_adjust",
        status="ready",
    )
    session.add(config)
    await session.flush()

    service = FeishuProjectionService(session)
    client = _ChunkedFailingClient(fail_at_call=99)
    completed = await service._process_price_adjust_tasks(config, client)

    assert completed == 1
    assert client.base_tokens == ["bascn_price_adjust"]


@pytest_asyncio.fixture
async def outbox_sqlite_session():
    """建 outbox 需要的 4 张表的 SQLite 会话。"""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from modules.core.db import Base

    wanted = (
        "ops.feishu_projection_configs",
        "ops.feishu_projection_tasks",
        "ops.feishu_projection_logs",
        "ops.price_adjust_baselines",
        "core.dim_erp_sku",
    )
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.connect() as conn:
        for schema in ("core", "ops"):
            await conn.exec_driver_sql(f"ATTACH DATABASE ':memory:' AS {schema}")
        for name in wanted:
            await conn.run_sync(Base.metadata.tables[name].create, checkfirst=True)
        async with AsyncSession(conn) as session:
            yield session
    await engine.dispose()


async def _seed_outbox(session, count: int) -> None:
    """种 count 条待投递的价格调整任务。"""
    from modules.core.db import FeishuProjectionTask

    for index in range(count):
        session.add(
            FeishuProjectionTask(
                entity_type="price_adjust",
                business_key=str(index + 1),
                payload_hash=f"hash-{index}",
                payload_json={
                    "sku_id": index + 1,
                    "sku_key": f"SKU-{index}",
                    "spu": "SPU-1",
                    "sku_name": f"商品 {index}",
                    "specification": "1 件",
                    "old_min_selling_price": "100.00",
                    "new_min_selling_price": "110.00",
                    "change_rate": 0.1,
                    "direction": DIRECTION_UP,
                    "reason": REASON_PURCHASE_COST,
                    "pricing_tier_label": "日常",
                    "age_days": 3,
                    "current_qty": 10,
                    "inventory_value": 450.0,
                    "context": {"min_selling_price": "110.00"},
                },
            )
        )
    await session.flush()


@pytest.mark.asyncio
async def test_failed_chunk_does_not_rollback_already_created_chunks(outbox_sqlite_session):
    """某一块写失败时，**已经写成功的那几块不能被一起标成失败**。

    调价记录表是只增不改的：如果第 2 块失败时把第 1 块也标成 failed，
    重试会把第 1 块的 500 行再写一遍 → 飞书表里出现重复行，
    而且重复行不会被覆盖，只会一直堆着。
    """
    from backend.services.feishu_projection_client import FEISHU_BATCH_CREATE_LIMIT
    from backend.services.feishu_projection_service import FeishuProjectionService
    from modules.core.db import FeishuProjectionConfig, FeishuProjectionTask

    session = outbox_sqlite_session
    await _seed_outbox(session, FEISHU_BATCH_CREATE_LIMIT + 10)

    config = FeishuProjectionConfig(
        provider_code="feishu",
        spu_table_id="tbl-spu",
        sku_table_id="tbl-sku",
        platform_sku_profit_table_id="tbl-profit",
        price_adjust_table_id="tbl-price",
        status="ready",
    )
    session.add(config)
    await session.flush()

    service = FeishuProjectionService(session)
    client = _ChunkedFailingClient(fail_at_call=2)
    completed = await service._process_price_adjust_tasks(config, client)

    assert len(client.calls) == 2, "应当按飞书单次上限分块"
    assert client.calls[0] == FEISHU_BATCH_CREATE_LIMIT
    assert client.calls[1] == 10
    assert completed == FEISHU_BATCH_CREATE_LIMIT

    rows = (
        await session.execute(
            select(FeishuProjectionTask.status, FeishuProjectionTask.business_key)
        )
    ).all()
    by_status: dict[str, list[str]] = {}
    for status, business_key in rows:
        by_status.setdefault(status, []).append(business_key)

    # 第一块：成功；第二块：失败待重试
    assert len(by_status.get("completed", [])) == FEISHU_BATCH_CREATE_LIMIT
    assert len(by_status.get("failed", [])) == 10
    # 失败的那 10 条要排上重试时间，等下一轮再投
    failed_rows = (
        await session.execute(
            select(FeishuProjectionTask).where(
                FeishuProjectionTask.status == "failed"
            )
        )
    ).scalars().all()
    assert all(row.next_retry_at is not None for row in failed_rows)


@pytest.mark.asyncio
async def test_baseline_is_advanced_only_after_successful_delivery(outbox_sqlite_session):
    """基线必须在**投递成功之后**才回写。

    先推基线再投递，一旦飞书写失败，那次变化就永远不会再被检出——
    最该通知的变化被静默吞掉。
    """
    from backend.services.feishu_projection_service import FeishuProjectionService
    from modules.core.db import (
        DimErpSku,
        FeishuProjectionConfig,
        FeishuProjectionTask,
        PriceAdjustBaseline,
    )

    session = outbox_sqlite_session
    sku = DimErpSku(
        sku_key="SKU-1",
        purchase_cost_currency="CNY",
        selling_price_currency="CNY",
        status="active",
    )
    session.add(sku)
    await session.flush()
    await _seed_outbox(session, 1)
    # 把任务指向刚建的 SKU
    task = (
        await session.execute(select(FeishuProjectionTask))
    ).scalars().first()
    task.payload_json = {**task.payload_json, "sku_id": sku.sku_id}
    await session.flush()

    config = FeishuProjectionConfig(
        provider_code="feishu",
        spu_table_id="tbl-spu",
        sku_table_id="tbl-sku",
        platform_sku_profit_table_id="tbl-profit",
        price_adjust_table_id="tbl-price",
        status="ready",
    )
    session.add(config)
    await session.flush()

    service = FeishuProjectionService(session)
    client = _ChunkedFailingClient(fail_at_call=1)
    completed = await service._process_price_adjust_tasks(config, client)

    assert completed == 0
    # 投递失败 → 基线**不能**推进（新基线表里连行都不该有）
    baseline = (
        await session.execute(
            select(PriceAdjustBaseline).where(
                PriceAdjustBaseline.sku_id == sku.sku_id
            )
        )
    ).scalar_one_or_none()
    assert baseline is None

    # 投递成功 → 基线推进
    client = _ChunkedFailingClient(fail_at_call=99)
    task.status = "pending"
    task.next_retry_at = None
    await session.flush()
    completed = await service._process_price_adjust_tasks(config, client)

    assert completed == 1
    baseline = (
        await session.execute(
            select(PriceAdjustBaseline).where(
                PriceAdjustBaseline.sku_id == sku.sku_id
            )
        )
    ).scalar_one()
    assert float(baseline.last_notified_min_price) == pytest.approx(110.0)


# ---------------------------------------------------------------------------
# 口径一致性（需要 PostgreSQL）
# ---------------------------------------------------------------------------


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_detection_and_product_center_agree_on_min_selling_price(
    pg_session, pricing_seed
):
    """商品中心页面显示的最低售价 == 通知里说的最低售价。

    两边喂给 `compute_sku_pricing` 的原料必须完全相同：
    采购成本 / 参考售价 / 人工覆盖价 / SKU 达人佣金率 / 平台其他成本率 /
    SPU 绑定与两个 SPU 率 / 命中的档位 / 最深档位 / 库龄。
    只要有一项分叉，就会出现"页面按日常档、通知按滞销档"的自相矛盾。

    实现上两边已经共用 `product_pricing_query_service` 的同一个函数，
    这里再做一次端到端核对，防止有人后来在某一侧又写了一份。
    """
    from backend.domains.business.routers.product_center import (
        _compute_pricing_for_sku,
        _pricing_context,
    )
    from backend.services.price_adjust_notify_service import PriceAdjustNotifyService
    from backend.services.product_pricing_query_service import (
        compute_pricing_for_sku,
        load_pricing_context,
    )

    await pricing_seed()

    service = PriceAdjustNotifyService(pg_session)
    states = await service.collect_pricing_states()
    assert states, "seed 之后应当能算出至少一个 SKU 的定价状态"
    sku_id = next(iter(states))
    detected = states[sku_id]["min_selling_price"]

    from modules.core.db import BridgeSpuSku, DimErpSku, DimSpu
    from sqlalchemy import select

    sku_row = await pg_session.get(DimErpSku, sku_id)
    binding = (
        await pg_session.execute(
            select(BridgeSpuSku).where(
                BridgeSpuSku.sku_id == sku_id,
                BridgeSpuSku.binding_status == "active",
                BridgeSpuSku.effective_to.is_(None),
            )
        )
    ).scalars().first()
    linked_spu = await pg_session.get(DimSpu, binding.spu) if binding else None

    context = await load_pricing_context(pg_session, [sku_id])
    shared_payload = compute_pricing_for_sku(
        context=context, sku_row=sku_row, linked_spu=linked_spu
    )
    router_context = await _pricing_context(pg_session, [sku_id])
    router_payload = _compute_pricing_for_sku(
        context=router_context, sku_row=sku_row, linked_spu=linked_spu
    )

    assert shared_payload["min_selling_price"] == detected
    # 路由侧不得再自己长出一份计算（它应当只是共享实现的转发）
    assert router_payload["min_selling_price"] == detected

