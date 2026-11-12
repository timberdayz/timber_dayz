"""阶段 4 · 基准售价工具的回归测试。

这一阶段要钉死五件事：

1. **来源是枚举**（工具 1）：自由文本不再被接受；历史数据被清洗到枚举上；
   枚举 CHECK 约束真的生效。
2. **确认日期自动跟着价格走**（工具 2）：价格变了 ⇒ 日期重写；
   价格没变 ⇒ 日期不动；价格清空 ⇒ 日期清空；运营显式给了 ⇒ 以运营为准。
3. **即时预览 = 保存后的真实结果**（工具 3，最重要）：
   预览说最低售价会变成 63.00，保存后就**必须**是 63.00。
   这条是阶段 4 的核心价值 —— 基准售价填错的真正风险不是亏本，是**货卖不动**
   （纪律线抬高 ⇒ 护栏把品拦死），而这个风险必须在填的瞬间被看见。
4. **人工覆盖锁死时纪律线不生效**（工具 3）：预览必须说清楚「改了也没用」。
5. **偏差校验给不出数就不给结论**（工具 4）：「算不出」不等于「没问题」。

口径纪律（贯穿全部用例）
------------------------
- **缺输入宁可不算，不可乐观**：算不出历史成交价就返回「不可用」，
  绝不用「看起来能用」的数顶替。
- **预览与保存同源**：预览走的是 ``compute_pricing_state``，
  页面显示的底线也是同一个函数算出来的 ⇒ 不存在第二份口径。
"""

from __future__ import annotations

import importlib.util
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from alembic.migration import MigrationContext
from alembic.operations import Operations
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from backend.schemas.product_center import (
    SkuBulkItem,
    SkuCreateRequest,
    SkuSellingPricePreviewRequest,
    SkuUpdateRequest,
)
from backend.services.product_pricing_query_service import (
    compute_pricing_state,
    load_pricing_context,
)
from backend.services.product_selling_price_service import (
    apply_selling_price_confirmation,
    assess_selling_price_deviation,
    build_selling_price_preview,
    compute_selling_price_age,
)
from backend.utils.project_env import isolated_database_url


VERSIONS_DIR = Path("current_migrations/versions")
SOURCE_ENUM_MIGRATION = VERSIONS_DIR / "20261121_selling_price_source_enum.py"

# ---------------------------------------------------------------------------
# 测试用的口径参数（全部是能手算的数）
# ---------------------------------------------------------------------------

#: 平台费率：other 25% + 达人 5% + SPU 退货 2% + SPU 货损 1% + 目标利润率 25%
#: ⇒ 成本线分母 = 1 − 0.25 − 0.05 − 0.02 − 0.01 − 0.25 = 0.42
OTHER_COST_RATE = Decimal("0.25")
CREATOR_RATE = Decimal("0.05")
SPU_RETURN_LOSS_RATE = Decimal("0.02")
SPU_DAMAGE_RATE = Decimal("0.01")
TARGET_MARGIN_RATE = Decimal("0.25")
DISCOUNT_RATE = Decimal("0.10")

#: 采购成本 11.8566 ÷ 0.42 = 28.23 ⇒ 成本线正好 28.23（方案 §6.1 工具 3 的例子）
PURCHASE_COST = Decimal("11.8566")
COST_FLOOR = Decimal("28.23")
#: 纪律线 = 基准售价 × (1 − 让利率 10%) = 70 × 0.9 = 63.00
DISCIPLINE_LINE_AT_70 = Decimal("63.00")


def _load_migration_module():
    spec = importlib.util.spec_from_file_location(
        "selling_price_source_enum_under_test", SOURCE_ENUM_MIGRATION
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pricing_context(*, with_override: Decimal | None = None) -> dict:
    """构造一个不依赖数据库的定价上下文。

    口径全部按上面的常量来，所以期望值能手算：
    成本线 = 11.8566 ÷ 0.42 = 28.23；纪律线 = 基准售价 × 0.9。
    """
    platform = SimpleNamespace(
        platform_code="tiktok",
        other_cost_rate=OTHER_COST_RATE,
        default_creator_commission_rate=CREATOR_RATE,
        platform_role="sales",
    )
    overrides = {}
    if with_override is not None:
        overrides = {
            (1, "tiktok"): SimpleNamespace(min_selling_price_override=with_override)
        }
    return {
        "policies": [
            {
                "min_restock_days": 0,
                "tier_label": "日常",
                "discount_rate": DISCOUNT_RATE,
                "target_margin_rate": TARGET_MARGIN_RATE,
                "platform_basis": "tiktok",
            }
        ],
        "platform": platform,
        "platforms": {"tiktok": platform},
        "priceable_platform_codes": ["tiktok"],
        "overrides": overrides,
        "days_since_restock": {},
        "restock_rows": {},
    }


def _sku_row(*, reference_selling_price=Decimal("20")):
    return SimpleNamespace(
        sku_id=1,
        sku_key="SKU-TEST-1",
        default_purchase_cost=PURCHASE_COST,
        reference_selling_price=reference_selling_price,
        creator_commission_rate=None,
    )


def _linked_spu():
    return SimpleNamespace(
        return_loss_rate=SPU_RETURN_LOSS_RATE,
        logistics_damage_rate=SPU_DAMAGE_RATE,
    )


# ---------------------------------------------------------------------------
# ① 来源枚举（工具 1）
# ---------------------------------------------------------------------------


def test_selling_price_source_accepts_only_enum_values():
    for value in ("platform_listing", "erp", "manual"):
        assert (
            SkuCreateRequest(
                sku_key="X", selling_price_source=value
            ).selling_price_source
            == value
        )
        assert (
            SkuUpdateRequest(selling_price_source=value).selling_price_source == value
        )
        assert (
            SkuBulkItem(sku_key="X", selling_price_source=value).selling_price_source
            == value
        )


@pytest.mark.parametrize("value", ["manual ", "MANUAL", "人工填写", "", "unknown"])
def test_selling_price_source_rejects_free_text(value):
    """自由文本不再被接受 —— 枚举化是这一阶段的目的。"""
    with pytest.raises(ValidationError):
        SkuCreateRequest(sku_key="X", selling_price_source=value)


def test_selling_price_source_may_be_absent():
    """没填来源是允许的（**没填**与**填错**是两回事）。"""
    assert SkuCreateRequest(sku_key="X").selling_price_source is None


# ---------------------------------------------------------------------------
# ② 确认日期自动维护（工具 2）
# ---------------------------------------------------------------------------


def test_confirmation_date_is_written_when_price_changes():
    values = {"reference_selling_price": 70.0}
    now = datetime(2026, 11, 6, 8, 0, tzinfo=timezone.utc)
    apply_selling_price_confirmation(
        values, current_price=20.0, current_confirmed_at=None, now=now
    )
    assert values["selling_price_confirmed_at"] == now


def test_confirmation_date_is_untouched_when_price_is_unchanged():
    """价格没变 ⇒ 这不是一次新的确认，日期保留原值。"""
    old = datetime(2026, 1, 1, tzinfo=timezone.utc)
    values = {"reference_selling_price": 20.0}
    apply_selling_price_confirmation(
        values,
        current_price=20.0,
        current_confirmed_at=old,
        now=datetime.now(timezone.utc),
    )
    assert "selling_price_confirmed_at" not in values


def test_confirmation_date_is_cleared_when_price_is_cleared():
    values = {"reference_selling_price": None}
    apply_selling_price_confirmation(
        values,
        current_price=20.0,
        current_confirmed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert values["selling_price_confirmed_at"] is None


def test_explicit_confirmation_date_wins():
    """运营显式给了**不同的**确认日期 ⇒ 以运营为准（导入历史数据时要能指定）。"""
    explicit = datetime(2026, 3, 3, tzinfo=timezone.utc)
    values = {"reference_selling_price": 70.0, "selling_price_confirmed_at": explicit}
    apply_selling_price_confirmation(
        values,
        current_price=20.0,
        current_confirmed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        now=datetime.now(timezone.utc),
    )
    assert values["selling_price_confirmed_at"] == explicit


def test_echoed_confirmation_date_does_not_block_the_auto_write():
    """⚠️ **回归**：页面整行回传会把旧的确认日期一起带回来。

    如果按「客户端给过日期」判断，「显式优先」就会把自动写入挡掉 ——
    运营改了价格，确认日期却停在旧值，过期巡检从此永远不响。
    """
    stored = datetime(2026, 1, 1, tzinfo=timezone.utc)
    now = datetime(2026, 11, 6, 8, 0, tzinfo=timezone.utc)
    values = {"reference_selling_price": 70.0, "selling_price_confirmed_at": stored}
    apply_selling_price_confirmation(
        values, current_price=20.0, current_confirmed_at=stored, now=now
    )
    assert values["selling_price_confirmed_at"] == now


def test_echoed_confirmation_date_in_another_timezone_is_still_an_echo():
    """同一刻、不同时区表示 ⇒ 还是回传，不是修正。"""
    stored = datetime(2026, 1, 1, tzinfo=timezone.utc)
    echoed = datetime(2026, 1, 1, 8, 0, tzinfo=timezone(timedelta(hours=8)))
    now = datetime(2026, 11, 6, 8, 0, tzinfo=timezone.utc)
    values = {"reference_selling_price": 70.0, "selling_price_confirmed_at": echoed}
    apply_selling_price_confirmation(
        values, current_price=20.0, current_confirmed_at=stored, now=now
    )
    assert values["selling_price_confirmed_at"] == now


def test_confirmation_rule_does_nothing_without_price_change():
    """只改了别的字段 ⇒ 不碰确认日期。"""
    values = {"sku_name": "改名了"}
    apply_selling_price_confirmation(
        values, current_price=20.0, current_confirmed_at=datetime.now(timezone.utc)
    )
    assert "selling_price_confirmed_at" not in values


# ---------------------------------------------------------------------------
# ③ 过期巡检（工具 4）
# ---------------------------------------------------------------------------


def test_never_confirmed_is_not_the_same_as_confirmed_today():
    """「从没确认过」和「今天刚确认」不能混成同一个 0。"""
    age_days, stale = compute_selling_price_age(None)
    assert age_days is None
    assert stale is False


def test_fresh_confirmation_is_not_stale():
    now = datetime(2026, 11, 6, tzinfo=timezone.utc)
    age_days, stale = compute_selling_price_age(now - timedelta(days=10), now=now)
    assert age_days == 10
    assert stale is False


def test_confirmation_older_than_90_days_is_stale():
    now = datetime(2026, 11, 6, tzinfo=timezone.utc)
    age_days, stale = compute_selling_price_age(now - timedelta(days=91), now=now)
    assert age_days == 91
    assert stale is True


def test_confirmation_exactly_at_threshold_is_not_stale():
    """阈值是「超过 90 天」，正好 90 天不算过期。"""
    now = datetime(2026, 11, 6, tzinfo=timezone.utc)
    _age_days, stale = compute_selling_price_age(now - timedelta(days=90), now=now)
    assert stale is False


# ---------------------------------------------------------------------------
# ④ 偏差校验（工具 4）
# ---------------------------------------------------------------------------


def test_deviation_is_unavailable_without_transaction_price():
    """算不出历史成交价 ⇒ **不给结论**（不是「没有偏差」）。"""
    verdict = assess_selling_price_deviation(70.0, None)
    assert verdict["available"] is False
    assert verdict["reason"] == "no_transaction_price"
    assert verdict["deviation_pct"] is None
    assert verdict["exceeds_threshold"] is False


def test_deviation_is_unavailable_without_reference_price():
    verdict = assess_selling_price_deviation(None, 35.0)
    assert verdict["available"] is False
    assert verdict["reason"] == "no_reference_price"


def test_deviation_flags_a_tenfold_typo():
    """基准售价 620、历史成交价 35 ⇒ 偏差 1672%，必须报警。"""
    verdict = assess_selling_price_deviation(620.0, 35.0)
    assert verdict["available"] is True
    assert verdict["exceeds_threshold"] is True
    assert verdict["deviation_pct"] == pytest.approx(1671.4, abs=0.1)


def test_deviation_within_threshold_is_not_flagged():
    verdict = assess_selling_price_deviation(38.0, 35.0)
    assert verdict["available"] is True
    assert verdict["exceeds_threshold"] is False
    assert verdict["deviation_pct"] == pytest.approx(8.6, abs=0.1)


# ---------------------------------------------------------------------------
# ⑤ 即时影响预览（工具 3）
# ---------------------------------------------------------------------------


def test_preview_shows_the_discipline_line_raising_the_floor():
    """方案 §6.1 工具 3 的例子：成本线 28.23 / 基准售价 70 ⇒ 最低售价 63.00（+123%）。"""
    preview = build_selling_price_preview(
        context=_pricing_context(),
        sku_row=_sku_row(reference_selling_price=Decimal("20")),
        linked_spu=_linked_spu(),
        reference_selling_price=70.0,
    )
    assert len(preview["platforms"]) == 1
    item = preview["platforms"][0]
    assert item["platform_code"] == "tiktok"
    assert Decimal(str(item["min_selling_price_current"])) == COST_FLOOR
    assert Decimal(str(item["min_selling_price_preview"])) == DISCIPLINE_LINE_AT_70
    assert Decimal(str(item["change"])) == Decimal("34.77")
    assert item["change_pct"] == pytest.approx(123.2, abs=0.1)
    assert item["source_current"] == "cost_floor"
    assert item["source_preview"] == "discount_guard"
    assert preview["warnings"], "抬高超过 20% 必须给出整体提示"


def test_preview_matches_the_pricing_computed_after_saving():
    """**核心保证**：预览说多少，保存后就是多少。

    做法：先预览，再把同样的基准售价交给 ``compute_pricing_state``（页面显示底线走的
    就是它），两个数必须一致。
    """
    context = _pricing_context()
    sku_row = _sku_row(reference_selling_price=Decimal("20"))
    linked_spu = _linked_spu()

    preview = build_selling_price_preview(
        context=context,
        sku_row=sku_row,
        linked_spu=linked_spu,
        reference_selling_price=70.0,
    )

    # 模拟保存：SKU 上的基准售价换成新值
    sku_row.reference_selling_price = Decimal("70")
    after_save = compute_pricing_state(
        context=context, sku_row=sku_row, linked_spu=linked_spu, platform_code="tiktok"
    )["pricing"]

    assert Decimal(
        str(preview["platforms"][0]["min_selling_price_preview"])
    ) == Decimal(str(after_save["min_selling_price"]))


def test_preview_reports_that_a_manual_override_wins():
    """人工覆盖**直接替换**底线 ⇒ 改了基准售价也不动。预览必须说清楚。"""
    preview = build_selling_price_preview(
        context=_pricing_context(with_override=Decimal("50")),
        sku_row=_sku_row(reference_selling_price=Decimal("20")),
        linked_spu=_linked_spu(),
        reference_selling_price=70.0,
    )
    item = preview["platforms"][0]
    assert item["override_locked"] is True
    assert Decimal(str(item["min_selling_price_current"])) == Decimal("50.00")
    assert Decimal(str(item["min_selling_price_preview"])) == Decimal("50.00")
    assert item["change"] == 0
    assert "人工覆盖" in item["message"]
    assert preview["warnings"] == [], "人工覆盖锁死时不报「纪律线抬高」"


def test_preview_of_clearing_the_price_falls_back_to_the_cost_floor():
    preview = build_selling_price_preview(
        context=_pricing_context(),
        sku_row=_sku_row(reference_selling_price=Decimal("70")),
        linked_spu=_linked_spu(),
        reference_selling_price=None,
    )
    item = preview["platforms"][0]
    assert Decimal(str(item["min_selling_price_current"])) == DISCIPLINE_LINE_AT_70
    assert Decimal(str(item["min_selling_price_preview"])) == COST_FLOOR


def test_preview_request_requires_the_price_field():
    """请求体必须显式带这个字段（没带 ≠ 预览清空）。"""
    with pytest.raises(ValidationError):
        SkuSellingPricePreviewRequest()
    assert (
        SkuSellingPricePreviewRequest(
            reference_selling_price=None
        ).reference_selling_price
        is None
    )


# ---------------------------------------------------------------------------
# ⑥ SQLite 集成：确认日期落库 + 列表里的过期标记
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def selling_price_sqlite_session():
    from modules.core.db import Base

    wanted = (
        "core.dim_platforms",
        "core.dim_spu",
        "core.dim_erp_sku",
        "core.bridge_spu_sku",
        "finance.sku_pricing_policies",
        "finance.sku_platform_pricing",
    )
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.connect() as conn:
        for schema in ("core", "finance", "ops"):
            await conn.exec_driver_sql(f"ATTACH DATABASE ':memory:' AS {schema}")
        for name in wanted:
            await conn.run_sync(Base.metadata.tables[name].create, checkfirst=True)
        async with AsyncSession(conn, expire_on_commit=False) as session:
            yield session
    await engine.dispose()


async def _seed_sku(session) -> int:
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
                default_creator_commission_rate=CREATOR_RATE,
                other_cost_rate=OTHER_COST_RATE,
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
        default_purchase_cost=PURCHASE_COST,
        purchase_cost_currency="CNY",
        purchase_cost_confidence="high",
        reference_selling_price=Decimal("20"),
        # 阶段 4 工具 2：有基准售价就必须有确认日期（DB 约束）
        selling_price_confirmed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        selling_price_currency="CNY",
        selling_price_source="manual",
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
async def test_update_sku_writes_the_confirmation_date(
    selling_price_sqlite_session, monkeypatch
):
    """改基准售价 ⇒ 确认日期自动写成当天（阶段 4 工具 2 的落库路径）。"""
    from backend.domains.business.routers import product_center as pc_router
    from modules.core.db import DimErpSku

    sku_id = await _seed_sku(selling_price_sqlite_session)

    async def _noop_enqueue(db, row):
        return None

    async def _noop_trigger():
        return None

    monkeypatch.setattr(pc_router, "_enqueue_sku_projection", _noop_enqueue)
    monkeypatch.setattr(pc_router, "trigger_pending_projection_delivery", _noop_trigger)

    before = datetime.now(timezone.utc) - timedelta(seconds=5)
    await pc_router.update_sku(
        sku_id,
        pc_router.SkuUpdateRequest(reference_selling_price=70.0),
        selling_price_sqlite_session,
        _user=SimpleNamespace(user_id=None),
    )

    row = await selling_price_sqlite_session.get(DimErpSku, sku_id)
    assert row.reference_selling_price == 70.0
    assert row.selling_price_confirmed_at is not None
    # SQLite 存回来的时间戳是 naive 的，比较前统一成 UTC
    stored = row.selling_price_confirmed_at
    if stored.tzinfo is None:
        stored = stored.replace(tzinfo=timezone.utc)
    assert stored >= before


@pytest.mark.asyncio
async def test_update_sku_clearing_the_price_clears_the_confirmation_date(
    selling_price_sqlite_session, monkeypatch
):
    from backend.domains.business.routers import product_center as pc_router
    from modules.core.db import DimErpSku

    sku_id = await _seed_sku(selling_price_sqlite_session)

    async def _noop_enqueue(db, row):
        return None

    async def _noop_trigger():
        return None

    monkeypatch.setattr(pc_router, "_enqueue_sku_projection", _noop_enqueue)
    monkeypatch.setattr(pc_router, "trigger_pending_projection_delivery", _noop_trigger)

    await pc_router.update_sku(
        sku_id,
        pc_router.SkuUpdateRequest(reference_selling_price=70.0),
        selling_price_sqlite_session,
        _user=SimpleNamespace(user_id=None),
    )
    await pc_router.update_sku(
        sku_id,
        pc_router.SkuUpdateRequest(reference_selling_price=None),
        selling_price_sqlite_session,
        _user=SimpleNamespace(user_id=None),
    )

    row = await selling_price_sqlite_session.get(DimErpSku, sku_id)
    assert row.reference_selling_price is None
    assert row.selling_price_confirmed_at is None


@pytest.mark.asyncio
async def test_preview_endpoint_agrees_with_the_stored_floor(
    selling_price_sqlite_session,
):
    """走**真实路由**的预览，与真实定价算出来的底线一致。"""
    from backend.domains.business.routers import product_center as pc_router
    from modules.core.db import DimErpSku, DimSpu

    sku_id = await _seed_sku(selling_price_sqlite_session)

    response = await pc_router.preview_sku_selling_price(
        sku_id,
        pc_router.SkuSellingPricePreviewRequest(reference_selling_price=70.0),
        selling_price_sqlite_session,
    )
    item = response.platforms[0]
    assert Decimal(str(item.min_selling_price_current)) == COST_FLOOR
    assert Decimal(str(item.min_selling_price_preview)) == DISCIPLINE_LINE_AT_70

    # 保存同样的价，再按页面的算法重算一次 —— 必须一致
    row = await selling_price_sqlite_session.get(DimErpSku, sku_id)
    row.reference_selling_price = 70.0
    await selling_price_sqlite_session.flush()
    context = await load_pricing_context(selling_price_sqlite_session, [sku_id])
    linked_spu = await selling_price_sqlite_session.get(DimSpu, "SPU-1")
    after_save = compute_pricing_state(
        context=context, sku_row=row, linked_spu=linked_spu, platform_code="tiktok"
    )["pricing"]
    assert Decimal(str(item.min_selling_price_preview)) == Decimal(
        str(after_save["min_selling_price"])
    )


@pytest.mark.asyncio
async def test_check_endpoint_separates_exceeded_stale_and_unverified(
    selling_price_sqlite_session,
):
    """巡检接口把三类分开报：**算不出偏差 ≠ 没问题**。

    这一条钉的是**计数口径**：偏差超阈值的、被判定过期的、算不出偏差的，
    三个数各自独立，且「算不出」必须单独归类 ——
    把没检查过的合并进「检查通过」，等于把没数据说成没问题。
    """
    from backend.domains.business.routers import product_center as pc_router
    from modules.core.db import DimErpSku

    sku_id = await _seed_sku(selling_price_sqlite_session)

    # 关掉偏差计算（它要扫订单事实表，SQLite 上没有那张视图）
    response = await pc_router.check_sku_selling_prices(
        sku_id=None,
        include_deviation=False,
        db=selling_price_sqlite_session,
    )

    assert response.deviation_count == 0
    # 种子的确认日期是 2026-01-01 ⇒ 早已超过 90 天阈值 ⇒ 过期计数为 1
    assert response.stale_count == 1
    # 算不出偏差 ⇒ 单独归类，**不是**「偏差正常」
    assert response.unverified_count == 1

    item = next(i for i in response.items if i.sku_id == sku_id)
    assert item.stale is True
    assert item.age_days is not None and item.age_days > 90
    assert item.deviation.available is False
    assert item.deviation.deviation_pct is None
    assert item.deviation.exceeds_threshold is False
    assert item.deviation.reason == "no_transaction_price"


# ---------------------------------------------------------------------------
# ⑦ 迁移：来源清洗 + 确认日期回填 + 约束
# ---------------------------------------------------------------------------


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


def _check_constraint_names(engine) -> list[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid = 'core.dim_erp_sku'::regclass AND contype = 'c'"
            )
        ).all()
    return [row[0] for row in rows]


def test_source_enum_migration_is_chained_on_the_current_head():
    module = _load_migration_module()
    assert module.revision == "current_schema_20261121_selling_price_source_enum"
    assert module.down_revision == "current_schema_20261120_rename_pricing_tier_labels"


def test_source_enum_migration_guards_every_object():
    """幂等范式：每个对象都有存在性守卫，重复执行不报错。"""
    source = SOURCE_ENUM_MIGRATION.read_text(encoding="utf-8")
    assert "def _has_table(" in source
    assert "def _has_column(" in source
    assert "def _has_constraint(" in source
    assert "def upgrade() -> None:" in source
    assert "def downgrade() -> None:" in source
    # 顺序：先清洗来源 → 再回填确认日期 → 最后加约束。顺序反了约束加不上。
    assert source.index("selling_price_source = 'manual'") < source.index(
        "create_check_constraint"
    )
    assert source.index("selling_price_confirmed_at = created_at") < source.index(
        "create_check_constraint"
    )
    # 回填必须用 created_at（记录进入系统的时间）；updated_at 是同步时间，
    # 拿它回填会让所有历史价格看起来「刚确认过」，过期巡检就永远不会报警。
    backfill = source.split("SET selling_price_confirmed_at = created_at")[1].split(
        "WHERE"
    )[0]
    assert "updated_at" not in backfill


def test_source_enum_migration_is_repeatable_and_rolls_back_cleanly(isolated_engine):
    """真实 PostgreSQL 上跑：upgrade ×2 → downgrade → upgrade。"""
    module = _load_migration_module()
    _run_migration(isolated_engine, module, "upgrade")
    _run_migration(isolated_engine, module, "upgrade")

    columns = {
        column["name"]
        for column in inspect(isolated_engine).get_columns("dim_erp_sku", schema="core")
    }
    assert "selling_price_source_cleaned_at" in columns
    assert "ck_dim_erp_sku_selling_price_source" in _check_constraint_names(
        isolated_engine
    )
    assert "ck_dim_erp_sku_selling_price_confirmed" in _check_constraint_names(
        isolated_engine
    )

    _run_migration(isolated_engine, module, "downgrade")
    # ⚠️ 必须重新 inspect：inspector 会缓存列信息，复用旧实例会看到降级前的列
    columns = {
        column["name"]
        for column in inspect(isolated_engine).get_columns("dim_erp_sku", schema="core")
    }
    assert "selling_price_source_cleaned_at" not in columns
    assert "ck_dim_erp_sku_selling_price_source" not in _check_constraint_names(
        isolated_engine
    )
    assert "ck_dim_erp_sku_selling_price_confirmed" not in _check_constraint_names(
        isolated_engine
    )

    _run_migration(isolated_engine, module, "upgrade")


def test_source_enum_migration_cleans_history_and_backfills_confirmation(
    isolated_engine,
):
    """历史自由文本被归一到枚举；有价格没确认日期的补上确认日期。

    ⚠️ 确认日期用 ``created_at`` 回填 —— ``updated_at`` 是同步时间，会让所有历史价格
    看起来「刚确认过」，过期巡检就永远不会报警。
    """
    module = _load_migration_module()
    # ⚠️ 先把约束撤掉，造出「迁移前」的样子 —— 否则带价格、没有确认日期的脏数据
    #    连插都插不进去（这正是约束在起作用），也就测不到「迁移负责清洗存量」。
    with isolated_engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE core.dim_erp_sku "
                "DROP CONSTRAINT IF EXISTS ck_dim_erp_sku_selling_price_confirmed"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE core.dim_erp_sku "
                "DROP CONSTRAINT IF EXISTS ck_dim_erp_sku_selling_price_source"
            )
        )
        conn.execute(
            text(
                "INSERT INTO core.dim_erp_sku (sku_key, sku_name, purchase_cost_currency, "
                "purchase_cost_confidence, selling_price_currency, status, "
                "reference_selling_price, selling_price_source, created_at, updated_at) "
                "VALUES ('SKU-MIG-FREE-TEXT', '自由文本来源', 'CNY', 'high', 'CNY', "
                "'active', 50.00, '手工拍的', NOW() - INTERVAL '200 days', NOW()) "
                "ON CONFLICT (sku_key) DO NOTHING"
            )
        )
        conn.execute(
            text(
                "INSERT INTO core.dim_erp_sku (sku_key, sku_name, purchase_cost_currency, "
                "purchase_cost_confidence, selling_price_currency, status, "
                "reference_selling_price, selling_price_source, created_at, updated_at) "
                "VALUES ('SKU-MIG-EMPTY-SRC', '空来源', 'CNY', 'high', 'CNY', "
                "'active', 60.00, '', NOW() - INTERVAL '200 days', NOW()) "
                "ON CONFLICT (sku_key) DO NOTHING"
            )
        )

    _run_migration(isolated_engine, module, "upgrade")

    with isolated_engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT sku_key, selling_price_source, selling_price_confirmed_at, "
                "selling_price_source_cleaned_at "
                "FROM core.dim_erp_sku WHERE sku_key IN ('SKU-MIG-FREE-TEXT', 'SKU-MIG-EMPTY-SRC')"
            )
        ).all()

    by_key = {row[0]: row for row in rows}
    assert by_key["SKU-MIG-FREE-TEXT"][1] == "manual", "自由文本应归一到 manual"
    assert by_key["SKU-MIG-EMPTY-SRC"][1] == "manual", "空串应归一到 manual"
    for row in rows:
        assert row[2] is not None, "有基准售价就必须有确认日期"
        assert row[3] is not None, "被清洗过的行应记录清洗时间"


# ---------------------------------------------------------------------------
# 成交价带 SQL 必须在真 PostgreSQL 上跑通（这条测试是被两次真炸出来的）
# ---------------------------------------------------------------------------


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_transaction_price_band_sql_runs_on_postgres(pg_session):
    """成交价带的 SQL 必须能在 PostgreSQL 上跑通，并给出正确的中位数。

    ⚠️ 这条测试是被两次真炸出来的：

    ① SQL 写成 ``IN :statuses`` —— PostgreSQL 的语法要求 ``IN`` 后面必须跟
       括号里的表达式列表，``IN $1`` 是**语法错误**（asyncpg 下必炸）。
    ② CTE 命名为 ``window`` —— 那是 PostgreSQL 的保留字（窗口函数帧的关键字），
       拿来当 CTE 名直接语法错误。

    两次都**不是单测能发现的**：单测只测了纯函数
    ``assess_selling_price_deviation``，从没让这条 SQL 落到真库上。
    ⇒ 这里用真实的 PostgreSQL（asyncpg，与生产同驱动）跑一遍，把缺口堵上。
    """
    from modules.core.db.schema_parts.dimensions import BridgeErpSkuKey, DimErpSku
    from backend.services.product_transaction_price_service import (
        load_transaction_price_bands,
    )

    await pg_session.execute(text('CREATE SCHEMA IF NOT EXISTS "semantic"'))
    await pg_session.execute(
        text(
            """
            CREATE TABLE semantic.fact_orders_atomic (
                id integer PRIMARY KEY,
                metric_date date,
                product_sku text,
                product_quantity numeric,
                raw_data jsonb
            )
            """
        )
    )

    sku = DimErpSku(
        sku_id=9001,
        sku_key="PG-BAND-001",
        reference_selling_price=100.0,
        selling_price_source="manual",
        selling_price_confirmed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    pg_session.add(sku)
    await pg_session.flush()
    pg_session.add(
        BridgeErpSkuKey(
            source_system="miaoshou",
            source_platform="miaoshou",
            source_key_type="product_sku",
            source_key="KEY-1",
            sku_id=9001,
            effective_from=date(2025, 1, 1),
            active=True,
        )
    )
    await pg_session.flush()

    # 五笔成交：单价 40 / 60 / 80 / 100 / 100（最后一笔是 2 件 200 元）
    # 外加一笔「已关闭」，它不该被算进来。
    await pg_session.execute(
        text(
            """
            INSERT INTO semantic.fact_orders_atomic
                (id, metric_date, product_sku, product_quantity, raw_data)
            VALUES
                (1, DATE '2026-01-10', 'KEY-1', 1, '{"订单状态": "已完成", "买家支付(RMB)": "40.00"}'::jsonb),
                (2, DATE '2026-01-11', 'KEY-1', 1, '{"订单状态": "已完成", "买家支付(RMB)": "60.00"}'::jsonb),
                (3, DATE '2026-01-12', 'KEY-1', 1, '{"订单状态": "已完成", "买家支付(RMB)": "80.00"}'::jsonb),
                (4, DATE '2026-01-13', 'KEY-1', 1, '{"订单状态": "已发货", "买家支付(RMB)": "100.00"}'::jsonb),
                (5, DATE '2026-01-14', 'KEY-1', 2, '{"订单状态": "已完成", "买家支付(RMB)": "200.00"}'::jsonb),
                (6, DATE '2026-01-15', 'KEY-1', 1, '{"订单状态": "已关闭", "买家支付(RMB)": "999.00"}'::jsonb)
            """
        )
    )

    bands = await load_transaction_price_bands(pg_session, [9001])

    assert 9001 in bands, "成交价带算不出来 —— SQL 在真库上没跑通"
    band = bands[9001]
    assert band["sample_size"] == 5, "已关闭的订单不该被算进来"
    # 单价 40 / 60 / 80 / 100 / 100 ⇒ 中位数 80（落在真实数据点上，不靠插值）
    assert abs(float(band["median_price"]) - 80.0) < 0.01, band["median_price"]
    assert band["window_end"] == date(2026, 1, 14), band["window_end"]


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_transaction_price_band_reports_missing_as_unavailable(pg_session):
    """算不出成交价 ⇒ 结果里**没有这个 SKU**（调用方必须理解成「算不出」）。

    「没出现」不等于「没有偏差」—— 这个区分是偏差校验存在的意义。
    """
    from backend.services.product_transaction_price_service import (
        load_transaction_price_bands,
    )

    await pg_session.execute(text('CREATE SCHEMA IF NOT EXISTS "semantic"'))
    await pg_session.execute(
        text(
            """
            CREATE TABLE semantic.fact_orders_atomic (
                id integer PRIMARY KEY,
                metric_date date,
                product_sku text,
                product_quantity numeric,
                raw_data jsonb
            )
            """
        )
    )

    bands = await load_transaction_price_bands(pg_session, [999999])

    assert 999999 not in bands, "没有成交记录时不应给出成交价带"
