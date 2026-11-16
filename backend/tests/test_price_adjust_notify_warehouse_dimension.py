"""批次 5 · 调价通知链下沉到仓维度 + 遗留收口的守护测试。

要钉死五件事：

1. **基线主键含仓**：底线是「SKU × 平台 × 仓」的量（批次 4 起尾程按仓计价），
   基线表的主键必须跟着走，否则 A 仓的底线变化会被记成所有仓的变化。
2. **通知按仓分别比对**：同一个 SKU 在两个仓，基线互相独立 ——
   A 仓变了只通知 A 仓，B 仓没变就不通知。
3. **归因快照带仓与尾程**：下一次变化时能说清"哪个仓、因为尾程变了"。
4. **去重闸不能把第二次变化吞掉**：去重键 + 载荷哈希双因子 ——
   真正的重复是"同一次变化"（载荷逐字相同 ⇒ 哈希相同），
   而不是"同一个键出现过"（底线会反复变）。
5. **利润算术只有一处**：费率口径与金额口径共用 `build_profit_from_components`。
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from backend.services.price_adjust_notify_service import (
    PriceAdjustNotifyService,
    build_context,
)


# ---------------------------------------------------------------------------
# 1 · 基线主键含仓
# ---------------------------------------------------------------------------


def test_baseline_primary_key_includes_warehouse():
    """基线主键必须是 (sku_id, platform_code, warehouse_code)。"""
    from modules.core.db import PriceAdjustBaseline

    pk_columns = [column.name for column in PriceAdjustBaseline.__table__.primary_key]
    assert pk_columns == ["sku_id", "platform_code", "warehouse_code"]


def test_baseline_migration_backfills_legacy_rows_with_empty_warehouse():
    """迁移必须把老行回填成**空串**（与任何真实仓都对不上 ⇒ 老基线自动失效）。

    这是「不会误报一批底线变了」的关键：老口径的底线没有仓维度。
    """
    source = Path(
        "current_migrations/versions/20261235_price_adjust_baseline_warehouse.py"
    ).read_text(encoding="utf-8")

    assert 'COLUMN = "warehouse_code"' in source
    assert "LEGACY_MARKER" in source
    # 回填语句存在
    assert "WHERE {COLUMN} IS NULL" in source or "IS NULL" in source
    # 主键改成三列
    assert '["sku_id", "platform_code", COLUMN]' in source
    # ⚠️ 主键名不能硬编码成建表时的那个名字（20261115 那次重建把它改过了）：
    #    建表时叫 pk_price_adjust_baselines，重建后是 price_adjust_baselines_pkey。
    assert 'PK_NAME = "pk_price_adjust_baselines"' not in source
    assert 'PK_FALLBACK_NAME = "price_adjust_baselines_pkey"' in source
    assert "_primary_key_name()" in source


# ---------------------------------------------------------------------------
# 2 · 通知按仓分别比对
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


def _context(**overrides):
    base = {
        "platform_code": "tiktok",
        "warehouse_code": "",
        "min_selling_price": "100.00",
        "min_selling_price_source": "cost_floor",
        "min_selling_price_is_override": False,
        "pricing_tier_source": "restock_days",
        "pricing_tier_label": "日常",
        "pricing_tier_min_restock_days": 0,
        "target_margin_rate": "0.25",
        "discount_rate": "0.10",
        "age_days": 10,
        "purchase_cost": "20.00",
        "other_cost_rate": "0.2727",
        "creator_commission_rate": "0.0606",
        "spu_return_loss_rate": "0.0467",
        "spu_damage_rate": "0.0158",
        "reference_selling_price": None,
        "delivery_cost": "5.00",
        "delivery_cost_rate": "0.10",
        "missing_reasons": [],
    }
    base.update(overrides)
    return base


def _state(sku_id, price, context, warehouse_code=""):
    return {
        "sku_id": sku_id,
        "platform_code": "tiktok",
        "warehouse_code": warehouse_code,
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


@pytest.mark.asyncio
async def test_two_warehouses_have_independent_baselines():
    """同一个 SKU 在两个仓：基线互相独立，A 仓变了不牵连 B 仓。"""
    prev_my = _context(warehouse_code="MY-01", min_selling_price="100.00")
    prev_sg = _context(warehouse_code="SG-01", min_selling_price="100.00")
    cur_my = _context(warehouse_code="MY-01", min_selling_price="110.00")
    cur_sg = _context(warehouse_code="SG-01", min_selling_price="100.00")

    service = _FakeService(
        {
            (1, "tiktok", "MY-01"): _state(1, 110.00, cur_my, "MY-01"),
            (1, "tiktok", "SG-01"): _state(1, 100.00, cur_sg, "SG-01"),
        },
        {
            (1, "tiktok", "MY-01"): {
                "min_selling_price": Decimal("100.00"),
                "context": prev_my,
            },
            (1, "tiktok", "SG-01"): {
                "min_selling_price": Decimal("100.00"),
                "context": prev_sg,
            },
        },
    )

    notify, silent = await service.detect_changes()

    assert len(notify) == 1, "只有 MY-01 的底线变了 ⇒ 只通知 MY-01"
    assert notify[0]["warehouse_code"] == "MY-01"
    assert notify[0]["direction"] == "上升"
    assert silent == []


@pytest.mark.asyncio
async def test_legacy_baseline_with_empty_warehouse_does_not_match_real_warehouse():
    """老基线（空串仓）不能被当成某个真实仓的基线。

    否则上线后第一轮就会误报一批"底线变了"。
    """
    prev = _context(warehouse_code="", min_selling_price="100.00")
    cur = _context(warehouse_code="MY-01", min_selling_price="110.00")

    service = _FakeService(
        {(1, "tiktok", "MY-01"): _state(1, 110.00, cur, "MY-01")},
        {
            (1, "tiktok", ""): {
                "min_selling_price": Decimal("100.00"),
                "context": prev,
            }
        },
    )

    notify, silent = await service.detect_changes()

    assert notify == [], "老基线与真实仓对不上 ⇒ 不该报变化"
    assert len(silent) == 1, "应该只重建这个仓的基线"
    assert silent[0]["warehouse_code"] == "MY-01"


# ---------------------------------------------------------------------------
# 3 · 归因快照带仓与尾程
# ---------------------------------------------------------------------------


def test_context_snapshot_carries_warehouse_and_delivery_inputs():
    """快照必须记仓 + 单件尾程 + 平台尾程占比，否则下次变化说不清原因。"""
    snapshot = build_context(
        pricing={
            "min_selling_price": 33.03,
            "min_selling_price_source": "cost_floor",
            "min_selling_price_is_override": False,
            "pricing_tier_source": "restock_days",
            "pricing_tier_label": "日常",
            "pricing_tier_min_restock_days": 0,
            "min_selling_price_missing_reasons": [],
        },
        age_days=10,
        target_margin_rate=Decimal("0.25"),
        discount_rate=Decimal("0.10"),
        purchase_cost=Decimal("10"),
        other_cost_rate=Decimal("0.2727"),
        creator_commission_rate=Decimal("0.0606"),
        spu_return_loss_rate=Decimal("0.0467"),
        spu_damage_rate=Decimal("0.0158"),
        reference_selling_price=None,
        platform_code="tiktok",
        warehouse_code="MY-01",
        delivery_cost=Decimal("5"),
        delivery_cost_rate=Decimal("0.10"),
    )

    assert snapshot["warehouse_code"] == "MY-01"
    assert snapshot["delivery_cost"] == "5"
    assert snapshot["delivery_cost_rate"] == "0.10"


def test_delisting_jump_is_not_excluded_when_delivery_cost_changed():
    """尾程变了 ⇒ 这次跳高不只是"下架"造成的 ⇒ 不能被静默排除。

    排除掉就等于把一次真实变化吞掉（基线还会跟上 ⇒ 永远不会再报）。
    """
    from backend.services.price_adjust_notify_service import is_delisting_jump

    prev = _context(
        pricing_tier_source="restock_days",
        pricing_tier_label="滞销60天",
        delivery_cost="5.00",
    )
    cur = _context(
        pricing_tier_source="fallback_no_restock_days",
        pricing_tier_label="日常",
        delivery_cost="8.00",
    )

    assert is_delisting_jump(prev, cur) is False


# ---------------------------------------------------------------------------
# 4 · 去重闸：第二次变化不能被吞掉
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def outbox_session():
    """只建 outbox 任务表的 SQLite 会话。

    SQLite 没有真正的 schema：`ops.xxx` 会被当成「ops 库里的 xxx 表」，
    所以先 `ATTACH ':memory:' AS ops`。
    """
    from modules.core.db import Base

    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.connect() as conn:
        await conn.exec_driver_sql("ATTACH DATABASE ':memory:' AS ops")
        await conn.run_sync(
            Base.metadata.tables["ops.feishu_projection_tasks"].create,
            checkfirst=True,
        )
        async with AsyncSession(conn) as session:
            yield session
    await engine.dispose()


def _change(new_price: str, warehouse_code: str = "") -> dict:
    return {
        "sku_id": 1,
        "platform_code": "tiktok",
        "warehouse_code": warehouse_code,
        "sku_key": "SKU-1",
        "spu": "SPU-1",
        "sku_name": "商品1",
        "specification": "黑色",
        "old_min_selling_price": "100.00",
        "new_min_selling_price": new_price,
        "change_rate": 0.1,
        "direction": "上升",
        "reason": "采购成本变化",
        "pricing_tier_label": "日常",
        "age_days": 10,
        "current_qty": 100,
        "inventory_value": 1000.0,
        "context": {"min_selling_price": new_price},
    }


@pytest.mark.asyncio
async def test_second_change_of_the_same_key_is_not_swallowed(outbox_session):
    """同一 SKU × 平台 × 仓的**第二次**变化必须还能入队。

    以前去重闸只看 business_key（还把 completed 也算成"在途"），
    于是第一次通知之后这个键就永远不会再通知 ⇒ 通知表退化成一次性快照。
    """
    from backend.services.feishu_projection_service import projection_payload_hash
    from backend.tasks.price_adjust_notify_tasks import (
        _business_key,
        _build_payload,
        _existing_price_adjust_tasks,
    )
    from modules.core.db import FeishuProjectionTask

    change = _change("110.00")
    payload = _build_payload(change)
    key = _business_key(change)
    payload_hash = projection_payload_hash(payload)

    # 第一轮：库里没有历史任务 ⇒ 放行
    existing = await _existing_price_adjust_tasks(outbox_session, [(key, payload_hash)])
    assert (key, payload_hash) not in existing

    # 投一条**已完成**的历史任务（同一次变化）
    outbox_session.add(
        FeishuProjectionTask(
            entity_type="price_adjust",
            business_key=key,
            payload_hash=payload_hash,
            payload_json=payload,
            status="completed",
        )
    )
    await outbox_session.flush()

    # 同一次变化：必须被拦住（不能重复建任务、不能产生重复行）
    existing = await _existing_price_adjust_tasks(outbox_session, [(key, payload_hash)])
    assert (key, payload_hash) in existing

    # 第二次变化（底线又变了 ⇒ payload 不同 ⇒ 哈希不同）：必须放行
    second_payload = _build_payload(_change("120.00"))
    second_hash = projection_payload_hash(second_payload)
    assert second_hash != payload_hash, "不同的变化必须有不同的载荷哈希"
    existing = await _existing_price_adjust_tasks(outbox_session, [(key, second_hash)])
    assert (key, second_hash) not in existing


def test_business_key_carries_warehouse():
    """去重键必须带仓：同一 SKU × 平台在不同仓是两次独立的变化。"""
    from backend.tasks.price_adjust_notify_tasks import _business_key

    assert _business_key(_change("110.00", "MY-01")) == "1:tiktok:MY-01"
    assert _business_key(_change("110.00", "SG-01")) == "1:tiktok:SG-01"
    # 没有仓维度时退回老格式（与批次 4 之前的历史键一致）
    assert _business_key(_change("110.00")) == "1:tiktok"


def test_payload_carries_warehouse():
    """payload 必须带仓，投递成功后才能把基线推进到正确的行。"""
    from backend.tasks.price_adjust_notify_tasks import _build_payload

    payload = _build_payload(_change("110.00", "MY-01"))
    assert payload["warehouse_code"] == "MY-01"


def test_feishu_row_writes_warehouse_into_note():
    """飞书行要能看出是哪个仓。

    表里没有"仓库"列（外部 Base 的固定结构，不能擅自加列）⇒ 写进「备注」。
    """
    from backend.services.feishu_projection_service import FeishuProjectionService

    service = FeishuProjectionService(db=None)  # type: ignore[arg-type]

    class _Task:
        payload_json = {
            "sku_key": "SKU-1",
            "spu": "SPU-1",
            "platform_code": "tiktok",
            "warehouse_code": "MY-01",
            "sku_name": "商品1",
            "specification": "黑色",
            "old_min_selling_price": "100.00",
            "new_min_selling_price": "110.00",
            "change_rate": 0.1,
            "direction": "上升",
            "reason": "采购成本变化",
            "pricing_tier_label": "日常",
            "age_days": 10,
            "current_qty": 100,
            "inventory_value": 1000.0,
        }
        created_at = None

    fields = service._price_adjust_payload(_Task())
    assert fields["备注"] == "仓库：MY-01"

    # 没有仓维度时不写（不污染历史行）
    _Task.payload_json = dict(_Task.payload_json, warehouse_code="")
    fields = service._price_adjust_payload(_Task())
    assert "备注" not in fields


# ---------------------------------------------------------------------------
# 5 · 利润算术只有一处
# ---------------------------------------------------------------------------


def test_profit_arithmetic_lives_in_one_place():
    """费率口径与金额口径共用 `build_profit_from_components`。"""
    from backend.services.product_profit_service import (
        build_baseline_profit,
        build_profit_from_components,
    )

    result = build_profit_from_components(
        revenue=Decimal("100"),
        purchase_cost=Decimal("20"),
        logistics_cost=Decimal("15"),
        storage_cost=Decimal("5"),
        platform_fee=Decimal("10"),
        return_loss=Decimal("5"),
        damage_loss=Decimal("2"),
    )
    # 100 − (20 + 15 + 5 + 10 + 5 + 2) = 43
    assert result["estimated_contribution_profit"] == Decimal("43.00")
    assert result["estimated_margin_rate"] == Decimal("0.43000000")

    # 费率口径走同一个算术 ⇒ 同样的数
    baseline = build_baseline_profit(
        selling_price=Decimal("100"),
        default_purchase_cost=Decimal("20"),
        confirmed_logistics_cost=Decimal("15"),
        assumption_logistics_cost=Decimal("30"),
        storage_cost=Decimal("5"),
        platform_fee_rate=Decimal("0.10"),
        return_rate=Decimal("0.05"),
        damage_rate=Decimal("0.02"),
    )
    assert baseline["estimated_contribution_profit"] == Decimal("43.00")
    assert baseline["estimated_margin_rate"] == result["estimated_margin_rate"]


def test_profit_margin_is_none_when_revenue_is_zero():
    """收入为 0 ⇒ 利润率算不出来（None），不是 0。"""
    from backend.services.product_profit_service import build_profit_from_components

    result = build_profit_from_components(
        revenue=Decimal("0"), purchase_cost=Decimal("5")
    )
    assert result["estimated_margin_rate"] is None


def test_router_profit_estimate_uses_the_shared_calculator():
    """落库路由不再自己写一遍"收入减成本"。"""
    source = Path("backend/domains/business/routers/product_center.py").read_text(
        encoding="utf-8"
    )
    assert "build_profit_from_components" in source

    section = source[
        source.index("async def create_profit_estimate(") : source.index(
            '@router.post("/api/product-profit-estimates/preview")'
        )
    ]
    # 路由里不该再有自己写的加减法
    assert "revenue - costs" not in section
    assert "costs = sum(" not in section
