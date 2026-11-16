"""ROI 与广告费护栏（批次 2，2026-11-16）守护测试。

这一批修的是「运营填的东西会不会被系统悄悄改掉」：

- **P1** 超平台可填上限无校验 —— TikTok 目标 ROI 上限 20，填 50 系统照收，
  于是广告费 ≈ 0、利润虚高（护栏形同虚设）。
- **P2** 清空目标 ROI 静默换口径 —— 运营把目标 ROI 清空，系统却悄悄回落到
  档案里遗留的「广告分成率」口径 ⇒ 用的不是运营刚做的那次决策。
- **P3** 无经营档案时广告费恒为 0 —— 没有档案的行广告费按 0 算，
  利润看着很美，其实只是「没填广告费」。
- **P5** 达人佣金缺失未进缺失清单 —— 佣金按 0 计（利润被高估）却没有任何提示。
- **P6** 三色判定无归因警示 —— 「达标」很可能是平台把自然流量和达人 GMV 也算进去的虚高。

**定稿口径**：``广告费 = 商家实收 ÷ 目标ROI``；**目标 ROI 未填 ⇒ 广告费不可算，不是 0**。
"""

from decimal import Decimal
from pathlib import Path

import pytest

from backend.domains.business.routers import product_center as pc_router
from backend.services.product_profit_service import build_platform_profit_preview

ROUTER_SOURCE = Path("backend/domains/business/routers/product_center.py").read_text(
    encoding="utf-8"
)
FRONTEND_SOURCE = Path(
    "frontend/src/domains/business/views/ProductCenter.vue"
).read_text(encoding="utf-8")


def _inputs(**overrides):
    base = dict(
        expected_selling_price=Decimal("100"),
        competitor_price=None,
        purchase_cost=Decimal("30"),
        expected_logistics_cost=Decimal("20"),
        expected_storage_cost=Decimal("10"),
        expected_label_fee=None,
        actual_logistics_cost=None,
        actual_storage_cost=None,
        platform_fee_rate=Decimal("0.10"),
        expected_ad_rate=None,
        target_roi=None,
        return_rate=Decimal("0.02"),
        damage_rate=Decimal("0.01"),
        creator_commission_rate=Decimal("0.05"),
        roi_safety_margin=Decimal("0.20"),
        target_roi_ceiling=Decimal("50"),
        # 尾程配送费（批次 4）：本文件只守护 ROI/广告费口径，尾程按 0 传入
        # （显式给 0 = 尾程免费，避免它把利润链算成不可算、遮住被测口径）。
        delivery_cost=Decimal("0"),
    )
    base.update(overrides)
    return base


def _values(**overrides):
    values = {
        "sku_id": 751,
        "platform_code": "tiktok",
        "warehouse_code": "WH01",
        "target_roi": None,
        "actual_roi": None,
    }
    values.update(overrides)
    return values


def _guard_preview(*, ceiling=50, **overrides):
    expected = {
        "break_even_roi": None,
        "break_even_roi_lower_bound": None,
        "suggested_roi": None,
        "suggestion_note": None,
    }
    expected.update(overrides)
    return {"expected": expected, "target_roi_ceiling": ceiling}


# ---------------------------------------------------------------------------
# P1 · 超平台可填上限 ⇒ 拦
# ---------------------------------------------------------------------------


def test_target_roi_above_platform_ceiling_is_blocked():
    """TikTok 上限 20，填 50 ⇒ 平台根本不让填 ⇒ 系统也不该收。"""
    result = pc_router._evaluate_roi_guard(
        _values(target_roi=50.0),
        _guard_preview(ceiling=20, break_even_roi=Decimal("2.5")),
        [],
    )
    assert result["error"] is not None
    assert result["error"]["code"] == "target_roi_above_platform_ceiling"
    assert result["error"]["target_roi_ceiling"] == 20


def test_target_roi_at_platform_ceiling_is_allowed():
    result = pc_router._evaluate_roi_guard(
        _values(target_roi=20.0),
        _guard_preview(ceiling=20, break_even_roi=Decimal("2.5")),
        [],
    )
    assert result["error"] is None


def test_ceiling_check_is_skipped_when_platform_has_no_ceiling_configured():
    """平台没配上限 ⇒ 不拦（不能凭空造一个上限来卡人）。"""
    result = pc_router._evaluate_roi_guard(
        _values(target_roi=50.0),
        _guard_preview(ceiling=None, break_even_roi=Decimal("2.5")),
        [],
    )
    assert result["error"] is None


def test_ceiling_check_runs_before_the_break_even_check():
    """超上限是**硬约束**：平台不让填 ⇒ 先报这个，别让运营以为只是亏一点。"""
    result = pc_router._evaluate_roi_guard(
        _values(target_roi=50.0),
        _guard_preview(ceiling=20, break_even_roi=Decimal("60")),
        [],
    )
    assert result["error"]["code"] == "target_roi_above_platform_ceiling"


# ---------------------------------------------------------------------------
# P2 · 清空目标 ROI 不许静默换口径
# ---------------------------------------------------------------------------


def test_missing_target_roi_makes_ad_cost_not_computable():
    """两个口径都没有 ⇒ 广告费不可算（None），**不是 0**。"""
    preview = build_platform_profit_preview(**_inputs())
    expected = preview["expected"]
    assert expected["ad_cost"] is None
    assert expected["profit"] is None
    assert expected["ad_cost_missing_reasons"] == ["missing_target_roi"]
    # 完整度必须跟着说「算不出来」，不能装作 complete
    assert expected["completeness"] == "incomplete"


def test_legacy_ad_rate_caliber_is_still_available_when_explicitly_given():
    """老口径不是被删掉，是**必须显式使用**（运营主动开逃生口）。"""
    preview = build_platform_profit_preview(**_inputs(expected_ad_rate=Decimal("0.15")))
    expected = preview["expected"]
    assert expected["ad_cost"] is not None
    assert expected["ad_cost_source"] == "legacy_ad_rate"
    assert expected["ad_cost_missing_reasons"] == []


def test_target_roi_caliber_wins_over_legacy_ad_rate():
    preview = build_platform_profit_preview(
        **_inputs(target_roi=Decimal("4"), expected_ad_rate=Decimal("0.15"))
    )
    expected = preview["expected"]
    assert expected["ad_cost_source"] == "target_roi"
    # 100 ÷ 4 = 25
    assert expected["ad_cost"] == Decimal("25.00")


def test_frontend_only_sends_ad_rate_when_the_escape_hatch_is_used():
    """前端：主口径下**不把广告分成率发上去**（发 0 就等于悄悄用了老口径）。"""
    assert (
        "expected_ad_rate: row.adRateEscapeUsed ? fromPercent(row.expected_ad_rate_pct, 0) : null"
        in FRONTEND_SOURCE
    )


def test_request_model_defaults_ad_rate_to_none_not_zero():
    """请求模型的默认值必须是 None —— 0 会被当成「这个品不投广告」。"""
    from backend.schemas.product_center import PlatformSkuProfitPreviewRequest

    request = PlatformSkuProfitPreviewRequest(
        sku_id=1,
        platform_code="tiktok",
        warehouse_code="MY-01",
        transport_type="sea",
    )
    assert request.expected_ad_rate is None


# ---------------------------------------------------------------------------
# P3 · 没有经营档案 ⇒ 广告费不可算（不是 0）
# ---------------------------------------------------------------------------


def test_candidate_without_profile_does_not_default_ad_rate_to_zero():
    """没有经营档案的行：广告费率传 None ⇒ 广告费不可算 ⇒ 利润空白。"""
    assert (
        "expected_ad_rate = profile.expected_ad_rate if profile else None"
        in ROUTER_SOURCE
    )


def test_candidate_reports_missing_input_reasons():
    """候选行必须回带「缺哪些输入」—— 利润空白时要能说清为什么空白。"""
    assert "missing_input_reasons" in ROUTER_SOURCE
    assert "missing_operating_profile" in ROUTER_SOURCE
    assert "missing_target_roi" in ROUTER_SOURCE


# ---------------------------------------------------------------------------
# P5 · 达人佣金缺失要进缺失清单
# ---------------------------------------------------------------------------


def test_candidate_reports_missing_creator_commission_rate():
    assert "missing_creator_commission_rate" in ROUTER_SOURCE


def test_creator_commission_source_is_exposed():
    """佣金按 0 计的时候必须说清是「按 0 计」，不是「确实没有这笔佣金」。"""
    assert "creator_commission_source" in ROUTER_SOURCE
    assert "assumed_zero" in ROUTER_SOURCE


# ---------------------------------------------------------------------------
# P6 · 三色判定必须带归因警示
# ---------------------------------------------------------------------------


def test_green_verdict_shows_attribution_warning_in_the_table():
    """「达标」旁边必须**看得见**归因警示，不能只藏在 tooltip 里。"""
    assert "attributionWarning" in FRONTEND_SOURCE
    assert "归因" in FRONTEND_SOURCE


def test_verdict_tooltip_still_explains_attribution():
    assert "roiVerdictTooltip" in FRONTEND_SOURCE


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__])
