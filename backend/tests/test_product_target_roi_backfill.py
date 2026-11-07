"""阶段 3 · 广告分成率降级 + 目标 ROI 反解的回归测试。

要钉死四件事：

1. **广告费用优先按「目标 ROI」算**（平台口径），没有目标 ROI 才回落到老口径
   「广告分成率」。
2. **两个口径等价**：同一组成本下，用「广告分成率」和用它反解出来的
   「目标 ROI」算出来的广告费与利润**一个数都不变** ——
   这是存量反解可以放心做的全部前提。
3. **广告费不能是负数**：广告前利润 ≤ 0 时广告预算为 0，利润如实显示亏损。
   老写法会算出负广告费 ⇒ 亏损被缩小 ⇒ 乐观。
4. **反解有守卫**：保本 ROI 算不出来就跳过（缺输入宁可算）；
   写库前逐行自证等价；只动 ``target_roi IS NULL`` 的行（幂等）。
"""

from __future__ import annotations

from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from backend.services.product_profit_service import build_platform_profit_preview
from backend.services.product_target_roi_backfill_service import (
    MIGRATED_SOURCE,
    backfill_target_roi_from_legacy_ad_rate,
)


# ---------------------------------------------------------------------------
# 1 · 广告费用的口径（纯函数，无 DB）
# ---------------------------------------------------------------------------


def _inputs(**overrides):
    base = dict(
        expected_selling_price=Decimal("100"),
        competitor_price=None,
        seller_coupon_amount=Decimal("0"),
        purchase_cost=Decimal("30"),
        expected_logistics_cost=Decimal("20"),
        expected_storage_cost=Decimal("10"),
        expected_label_fee=None,
        actual_logistics_cost=None,
        actual_storage_cost=None,
        platform_fee_rate=Decimal("0.10"),
        expected_ad_rate=Decimal("0"),
        return_rate=Decimal("0.02"),
        damage_rate=Decimal("0.01"),
        creator_commission_rate=Decimal("0.05"),
        roi_safety_margin=Decimal("0.20"),
        target_roi_ceiling=Decimal("50"),
    )
    base.update(overrides)
    return base


def test_ad_cost_uses_target_roi_when_given():
    """给了目标 ROI 就按平台口径算广告费：商家实收 ÷ 目标 ROI。"""
    preview = build_platform_profit_preview(**_inputs(target_roi=Decimal("2.5")))
    expected = preview["expected"]
    # 商家实收 100 ÷ 2.5 = 40
    assert expected["ad_cost"] == Decimal("40.00")
    assert expected["ad_cost_source"] == "target_roi"
    # 广告前利润 = 100 − 30 − 20 − 10 − 10(平台佣金) − 5(达人) − 2(退货) − 1(货损) = 22
    assert expected["profit"] == Decimal("22.00") - Decimal("40.00")
    # 保本 ROI = 100 ÷ 22 = 4.5454…
    assert expected["break_even_roi"] == Decimal("100") / Decimal("22")


def test_ad_cost_falls_back_to_legacy_ad_rate_without_target_roi():
    preview = build_platform_profit_preview(**_inputs(expected_ad_rate=Decimal("0.15")))
    expected = preview["expected"]
    # 老口径：广告费 = 广告前利润 × 分成率 = 22 × 0.15 = 3.30
    assert expected["ad_cost"] == Decimal("3.30")
    assert expected["ad_cost_source"] == "legacy_ad_rate"
    assert expected["profit"] == Decimal("18.70")


def test_equivalent_target_roi_equals_the_entered_target_roi():
    """目标 ROI 口径下，「等效目标 ROI」必须**恰好等于**运营填的那个数。"""
    preview = build_platform_profit_preview(**_inputs(target_roi=Decimal("3.7")))
    expected = preview["expected"]
    equivalent = Decimal(str(expected["equivalent_target_roi"]))
    assert abs(equivalent - Decimal("3.7")) <= Decimal("0.0001")


def test_two_calibers_produce_the_same_ad_cost_and_profit():
    """**等价性**：广告分成率 0.15 ⇔ 目标 ROI = 保本ROI ÷ 0.15。

    这是存量反解可以放心做的全部前提 —— 换口径不改利润。
    """
    legacy = build_platform_profit_preview(**_inputs(expected_ad_rate=Decimal("0.15")))
    break_even_roi = legacy["expected"]["break_even_roi"]
    derived_target_roi = break_even_roi / Decimal("0.15")

    switched = build_platform_profit_preview(
        **_inputs(target_roi=derived_target_roi, expected_ad_rate=Decimal("0.15"))
    )
    assert switched["expected"]["ad_cost"] == legacy["expected"]["ad_cost"]
    assert switched["expected"]["profit"] == legacy["expected"]["profit"]
    assert (
        switched["expected"]["break_even_roi"] == legacy["expected"]["break_even_roi"]
    )


def test_ad_cost_is_never_negative_for_a_loss_making_product():
    """广告前利润 ≤ 0 ⇒ 广告预算 0，利润如实显示亏损（老写法会算出负广告费）。

    老写法 ad_cost = pre_ad_profit × s，在 pre_ad_profit < 0 时算出负广告费，
    于是 profit = pre_ad_profit − 负数 ⇒ 亏损被缩小 ⇒ 乐观。
    """
    preview = build_platform_profit_preview(
        **_inputs(
            expected_selling_price=Decimal("30"), expected_ad_rate=Decimal("0.15")
        )
    )
    expected = preview["expected"]
    # 收入 30，成本合计 78 ⇒ 广告前利润为负
    assert expected["pre_ad_profit"] < 0
    assert expected["ad_cost"] == Decimal("0.00")
    assert expected["profit"] == expected["pre_ad_profit"]
    # 成本不全 ⇒ 保本 ROI 不可信 ⇒ 不给乐观值
    assert expected["break_even_roi"] is None
    assert "non_positive_cost_denominator" in expected["roi_missing_reasons"]


# ---------------------------------------------------------------------------
# 2 · 反解服务（守卫 / 等价性自检 / 幂等）
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def backfill_sqlite_session():
    from modules.core.db import Base

    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.connect() as conn:
        for schema in ("core", "finance", "ops"):
            await conn.exec_driver_sql(f"ATTACH DATABASE ':memory:' AS {schema}")
        await conn.run_sync(
            Base.metadata.tables["finance.sku_operating_profiles"].create,
            checkfirst=True,
        )
        async with AsyncSession(conn, expire_on_commit=False) as session:
            yield session
    await engine.dispose()


def _profile(session, **overrides):
    from modules.core.db import SkuOperatingProfile

    row = SkuOperatingProfile(
        sku_id=overrides.get("sku_id", 751),
        platform_code=overrides.get("platform_code", "tiktok"),
        warehouse_code=overrides.get("warehouse_code", "WH01"),
        status="active",
        expected_ad_rate=overrides.get("expected_ad_rate", Decimal("0.15")),
        target_roi=overrides.get("target_roi"),
        target_roi_source=overrides.get("target_roi_source"),
    )
    session.add(row)
    return row


def _preview(*, break_even_roi=None, ad_cost=None, profit=None):
    return {
        "expected": {
            "break_even_roi": break_even_roi,
            "ad_cost": ad_cost,
            "profit": profit,
            "roi_missing_reasons": (
                [] if break_even_roi is not None else ["non_positive_cost_denominator"]
            ),
        }
    }


@pytest.mark.asyncio
async def test_backfill_writes_target_roi_with_migrated_source(
    monkeypatch, backfill_sqlite_session
):
    async def _preview_stub(_self, data):
        if data.get("target_roi") is not None:
            return _preview(
                break_even_roi=Decimal("2.5"),
                ad_cost=Decimal("40.00"),
                profit=Decimal("-18.00"),
            )
        return _preview(
            break_even_roi=Decimal("2.5"),
            ad_cost=Decimal("40.00"),
            profit=Decimal("-18.00"),
        )

    monkeypatch.setattr(
        "backend.services.product_target_roi_backfill_service.ProductFinanceService."
        "preview_platform_sku_profit",
        _preview_stub,
    )
    profile = _profile(backfill_sqlite_session)
    await backfill_sqlite_session.flush()

    report = await backfill_target_roi_from_legacy_ad_rate(
        backfill_sqlite_session, dry_run=False
    )
    assert report["updated"] == 1
    assert report["skipped"] == []
    # 保本 ROI 2.5 ÷ 广告分成率 0.15 = 16.6667
    assert profile.target_roi == Decimal("16.6667")
    assert profile.target_roi_source == MIGRATED_SOURCE


@pytest.mark.asyncio
async def test_backfill_is_idempotent(monkeypatch, backfill_sqlite_session):
    async def _preview_stub(_self, _data):
        return _preview(
            break_even_roi=Decimal("2.5"),
            ad_cost=Decimal("40.00"),
            profit=Decimal("-18.00"),
        )

    monkeypatch.setattr(
        "backend.services.product_target_roi_backfill_service.ProductFinanceService."
        "preview_platform_sku_profit",
        _preview_stub,
    )
    profile = _profile(backfill_sqlite_session)
    await backfill_sqlite_session.flush()

    await backfill_target_roi_from_legacy_ad_rate(
        backfill_sqlite_session, dry_run=False
    )
    first_value = profile.target_roi
    second = await backfill_target_roi_from_legacy_ad_rate(
        backfill_sqlite_session, dry_run=False
    )
    # 已经有 target_roi 的行不再被扫到 ⇒ 第二次没有任何改动
    assert second["scanned"] == 0
    assert second["updated"] == 0
    assert profile.target_roi == first_value


@pytest.mark.asyncio
async def test_backfill_skips_rows_without_computable_break_even(
    monkeypatch, backfill_sqlite_session
):
    """成本不全 ⇒ 保本 ROI 不可信 ⇒ 跳过（缺输入宁可不算，不可乐观）。"""

    async def _preview_stub(_self, _data):
        return _preview(break_even_roi=None)

    monkeypatch.setattr(
        "backend.services.product_target_roi_backfill_service.ProductFinanceService."
        "preview_platform_sku_profit",
        _preview_stub,
    )
    profile = _profile(backfill_sqlite_session)
    await backfill_sqlite_session.flush()

    report = await backfill_target_roi_from_legacy_ad_rate(
        backfill_sqlite_session, dry_run=False
    )
    assert report["updated"] == 0
    assert report["skipped"][0]["reason"] == "break_even_roi_not_computable"
    assert profile.target_roi is None
    assert profile.target_roi_source is None


@pytest.mark.asyncio
async def test_backfill_skips_rows_whose_calibers_do_not_match(
    monkeypatch, backfill_sqlite_session
):
    """自证等价没过 ⇒ 跳过（宁可不反解，也不能悄悄改掉利润）。"""

    async def _preview_stub(_self, data):
        if data.get("target_roi") is not None:
            # 目标 ROI 口径算出来的广告费与老口径差 5 元 ⇒ 不等价
            return _preview(
                break_even_roi=Decimal("2.5"),
                ad_cost=Decimal("45.00"),
                profit=Decimal("-23.00"),
            )
        return _preview(
            break_even_roi=Decimal("2.5"),
            ad_cost=Decimal("40.00"),
            profit=Decimal("-18.00"),
        )

    monkeypatch.setattr(
        "backend.services.product_target_roi_backfill_service.ProductFinanceService."
        "preview_platform_sku_profit",
        _preview_stub,
    )
    profile = _profile(backfill_sqlite_session)
    await backfill_sqlite_session.flush()

    report = await backfill_target_roi_from_legacy_ad_rate(
        backfill_sqlite_session, dry_run=False
    )
    assert report["updated"] == 0
    assert report["skipped"][0]["reason"] == "caliber_not_equivalent"
    assert profile.target_roi is None


@pytest.mark.asyncio
async def test_backfill_dry_run_does_not_write(monkeypatch, backfill_sqlite_session):
    async def _preview_stub(_self, _data):
        return _preview(
            break_even_roi=Decimal("2.5"),
            ad_cost=Decimal("40.00"),
            profit=Decimal("-18.00"),
        )

    monkeypatch.setattr(
        "backend.services.product_target_roi_backfill_service.ProductFinanceService."
        "preview_platform_sku_profit",
        _preview_stub,
    )
    profile = _profile(backfill_sqlite_session)
    await backfill_sqlite_session.flush()

    report = await backfill_target_roi_from_legacy_ad_rate(
        backfill_sqlite_session, dry_run=True
    )
    assert report["dry_run"] is True
    assert report["updated"] == 1
    # 干跑只报告，不写库
    assert profile.target_roi is None


# ---------------------------------------------------------------------------
# 3 · 档位改名：通知归因要比「身份」而不是「显示名」
# ---------------------------------------------------------------------------


def test_renaming_a_tier_label_is_not_reported_as_a_tier_change():
    """**显示名改了 ≠ 库龄跨档。**

    阶段 3 把档位名从「滞销30天」改成「库龄≥60天」。如果通知归因拿显示名当
    档位身份，改一次名字就让**全库 SKU** 看起来都"跨了档"
    ⇒ 最低售价变更通知会误报成「库龄档位变化」⇒ 通知风暴。

    所以归因要比**档位的身份**（库龄起点 min_restock_days）。
    """
    from backend.services.price_adjust_notify_service import (
        REASON_POLICY,
        REASON_TIER_CHANGE,
        classify_change_reason,
    )

    base = {
        "missing_reasons": [],
        "min_selling_price_is_override": False,
        "purchase_cost": "10",
        "other_cost_rate": "0.2727",
        "creator_commission_rate": "0.0606",
        "discount_rate": "0.15",
        "reference_selling_price": None,
    }
    prev = {
        **base,
        "pricing_tier_label": "滞销30天",
        "pricing_tier_min_restock_days": 60,
    }
    cur = {
        **base,
        "pricing_tier_label": "库龄≥60天",
        "pricing_tier_min_restock_days": 60,
    }
    # 显示名变了但身份没变 ⇒ 不该报「库龄档位变化」
    assert classify_change_reason(prev, cur) != REASON_TIER_CHANGE
    assert classify_change_reason(prev, cur) == REASON_POLICY

    # 身份真的变了（60 → 90）⇒ 照报不误
    crossed = {**cur, "pricing_tier_min_restock_days": 90}
    assert classify_change_reason(prev, crossed) == REASON_TIER_CHANGE


def test_old_snapshots_without_identity_fall_back_to_the_label():
    """老快照没有身份字段 ⇒ 退回比显示名（只影响该行第一次通知的归因）。"""
    from backend.services.price_adjust_notify_service import (
        REASON_TIER_CHANGE,
        classify_change_reason,
    )

    base = {
        "missing_reasons": [],
        "min_selling_price_is_override": False,
        "purchase_cost": "10",
        "other_cost_rate": "0.2727",
        "creator_commission_rate": "0.0606",
        "discount_rate": "0.15",
        "reference_selling_price": None,
    }
    prev = {**base, "pricing_tier_label": "日常"}
    cur = {**base, "pricing_tier_label": "库龄≥60天"}
    assert classify_change_reason(prev, cur) == REASON_TIER_CHANGE
