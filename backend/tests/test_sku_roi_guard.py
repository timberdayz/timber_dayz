"""阶段 2.2 · ROI 投放输入与护栏判定的回归测试。

这一阶段要钉死五件事：

1. **目标 ROI 低于保本线 ⇒ 拦**（``below_break_even_roi``）。
2. **护栏顺序**：ROI 护栏排在「资料完整性」校验**之前**。
   缺物流规则时，运营更需要先知道"你填的目标 ROI 连最乐观的保本线都够不着"，
   而不是"去补物流规则"——补完他可能**还是**亏。
3. **成本不全时不能乐观放行**：证不出"必亏"就报 ``roi_cost_incomplete``，
   不给"算不出保本线所以先让你过"的后门。
4. **草稿不拦截**：草稿是"还在填"的中间态，拦了就填不下去。
5. **来源留痕**：``target_roi`` 落经营档案、``actual_roi`` 落利润版本，
   各带 ``*_roi_source`` —— 两个数在利润表里长得一样，但可信度完全不同。

口径纪律（贯穿全部用例）
------------------------
- **缺输入宁可不算，不可乐观**：保本 ROI 算不出来就返回 ``None``，
  绝不用"看起来能用"的数顶替。
- **下界只用于"证死"**：成本不全时算出的保本 ROI **下界**只可能偏松
  （未知成本当 0），所以只能证明"低于它一定亏"，不能证明"高于它就安全"。
"""

from __future__ import annotations

from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from backend.domains.business.routers import product_center as pc_router
from backend.services.product_profit_service import build_platform_profit_preview
from backend.services.product_roi_service import compute_break_even_roi_lower_bound
from backend.schemas.product_center import (
    PlatformSkuProfitDraftRequest,
    PlatformSkuProfitEstimateRequest,
)
from backend.utils.exceptions import BusinessValidationError, error_response_v2


# ---------------------------------------------------------------------------
# 通用夹具
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def roi_sqlite_session():
    """只建本用例需要的表的 SQLite 会话（与阶段 2.1 / 2.1b 的夹具同款）。"""
    from modules.core.db import Base

    wanted = (
        "core.dim_platforms",
        "core.dim_erp_sku",
        "finance.sku_operating_profiles",
        "finance.sku_profit_estimates",
    )
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.connect() as conn:
        for schema in ("core", "finance", "ops"):
            await conn.exec_driver_sql(f"ATTACH DATABASE ':memory:' AS {schema}")
        for name in wanted:
            await conn.run_sync(Base.metadata.tables[name].create, checkfirst=True)
        # ⚠️ 必须跟生产一致用 ``expire_on_commit=False``（见
        # ``backend/models/database.py:423``）—— 否则 commit 之后读对象属性会触发
        # 懒加载刷新，异步会话里直接抛 MissingGreenlet。
        async with AsyncSession(conn, expire_on_commit=False) as session:
            yield session
    await engine.dispose()


class _FakeUser:
    user_id = 4242


# ---------------------------------------------------------------------------
# 1 · 保本 ROI 下界（纯函数）
# ---------------------------------------------------------------------------


def test_break_even_roi_lower_bound_is_the_revenue_over_upper_bound():
    """下界 = 商家实收 ÷ 广告前利润上界。"""
    result = compute_break_even_roi_lower_bound(
        net_revenue=Decimal("100"),
        pre_ad_profit_upper_bound=Decimal("40"),
    )
    assert result["break_even_roi_lower_bound"] == Decimal("100") / Decimal("40")
    assert result["missing_reasons"] == []


def test_break_even_roi_lower_bound_rejects_non_positive_revenue():
    result = compute_break_even_roi_lower_bound(
        net_revenue=Decimal("0"),
        pre_ad_profit_upper_bound=Decimal("40"),
    )
    assert result["break_even_roi_lower_bound"] is None
    assert "non_positive_revenue" in result["missing_reasons"]


def test_break_even_roi_lower_bound_rejects_non_positive_upper_bound():
    """未知成本全当 0 都不赚钱 ⇒ 没有下界（这不是 ROI 问题，是成本问题）。"""
    result = compute_break_even_roi_lower_bound(
        net_revenue=Decimal("100"),
        pre_ad_profit_upper_bound=Decimal("-1"),
    )
    assert result["break_even_roi_lower_bound"] is None
    assert "non_positive_cost_upper_bound" in result["missing_reasons"]


def test_lower_bound_never_exceeds_the_true_break_even():
    """**性质**：下界 ≤ 真实保本线（未知成本当 0 ⇒ 利润只会更大 ⇒ ROI 只会更小）。

    这条是"下界可以用来证死"的全部依据。真实成本里的物流/仓储只会**更大**，
    所以真实保本 ROI 只会**更高**。
    """
    revenue = Decimal("100")
    known_costs = Decimal("30")
    true_logistics = Decimal("20")
    true_storage = Decimal("10")
    upper_bound_profit = revenue - known_costs
    true_profit = revenue - known_costs - true_logistics - true_storage
    lower = compute_break_even_roi_lower_bound(
        net_revenue=revenue, pre_ad_profit_upper_bound=upper_bound_profit
    )["break_even_roi_lower_bound"]
    true_break_even = revenue / true_profit
    assert lower <= true_break_even
    assert lower < true_break_even


# ---------------------------------------------------------------------------
# 2 · 利润预览：成本不全时也要给出下界
# ---------------------------------------------------------------------------


def _preview_inputs(**overrides):
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


def test_preview_exposes_break_even_roi_lower_bound_when_cost_is_missing():
    """缺物流规则 ⇒ break_even_roi 是 None，但**下界仍然算得出来**。"""
    preview = build_platform_profit_preview(
        **_preview_inputs(expected_logistics_cost=None)
    )
    expected = preview["expected"]
    assert expected["break_even_roi"] is None
    assert expected["break_even_roi_lower_bound"] is not None
    # 未知成本当 0 ⇒ 上界 = 100 − 30 − 10(仓储) − 10(平台佣金) − 5(达人) − 2(退货) − 1(货损)
    assert expected["break_even_roi_lower_bound"] == Decimal("100") / Decimal("42")


def test_preview_break_even_roi_lower_bound_matches_exact_value_when_cost_complete():
    preview = build_platform_profit_preview(**_preview_inputs())
    expected = preview["expected"]
    assert expected["break_even_roi"] is not None
    assert expected["break_even_roi_lower_bound"] == expected["break_even_roi"]


# ---------------------------------------------------------------------------
# 3 · 护栏判定表（`_evaluate_roi_guard`）
# ---------------------------------------------------------------------------


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


def _guard_preview(**overrides):
    expected = {
        "break_even_roi": None,
        "break_even_roi_lower_bound": None,
        "suggested_roi": None,
        "suggestion_note": None,
    }
    expected.update(overrides)
    return {"expected": expected, "target_roi_ceiling": 50}


def test_guard_is_silent_when_target_roi_is_not_filled():
    result = pc_router._evaluate_roi_guard(_values(), _guard_preview(), [])
    assert result["error"] is None
    assert result["warnings"] == []


def test_guard_blocks_target_roi_below_break_even():
    result = pc_router._evaluate_roi_guard(
        _values(target_roi=1.2),
        _guard_preview(break_even_roi=Decimal("2.5")),
        [],
    )
    assert result["error"]["code"] == "below_break_even_roi"
    assert result["error"]["basis"] == "exact"
    assert result["error"]["break_even_roi"] == pytest.approx(2.5)


def test_guard_allows_target_roi_above_break_even():
    result = pc_router._evaluate_roi_guard(
        _values(target_roi=3.0),
        _guard_preview(break_even_roi=Decimal("2.5")),
        [],
    )
    assert result["error"] is None


def test_guard_warns_but_does_not_block_on_out_of_platform_range():
    """广告空间不足是客观限制，不是操作错误 ⇒ 只提示，不拦。"""
    result = pc_router._evaluate_roi_guard(
        _values(target_roi=45.0),
        _guard_preview(
            break_even_roi=Decimal("44"),
            suggested_roi=Decimal("54"),
            suggestion_note="above_platform_ceiling",
        ),
        [],
    )
    assert result["error"] is None
    assert [w["code"] for w in result["warnings"]] == ["roi_out_of_platform_range"]


def test_guard_blocks_when_lower_bound_proves_the_target_is_loss_making():
    """成本不全，但下界已经能证明"必亏" ⇒ 仍然拦（护栏不许被"算不出"绕过）。"""
    result = pc_router._evaluate_roi_guard(
        _values(target_roi=1.0),
        _guard_preview(break_even_roi_lower_bound=Decimal("2.0")),
        ["海运参考物流规则"],
    )
    assert result["error"]["code"] == "below_break_even_roi"
    assert result["error"]["basis"] == "lower_bound"


def test_guard_reports_incomplete_cost_when_lower_bound_cannot_prove_it():
    """证不出来 ⇒ 报成本不全（不可乐观放行），而不是放行。"""
    result = pc_router._evaluate_roi_guard(
        _values(target_roi=30.0),
        _guard_preview(break_even_roi_lower_bound=Decimal("2.0")),
        ["海运参考物流规则"],
    )
    assert result["error"]["code"] == "roi_cost_incomplete"
    assert result["error"]["missing_fields"] == ["海运参考物流规则"]


def test_actual_roi_below_break_even_never_blocks():
    """平台报告 ROI 是**事实记录**：低于保本线也照样存。

    拦了就等于不许记录亏损投放 —— 而真实亏过的投放恰恰要留痕。
    """
    result = pc_router._evaluate_roi_guard(
        _values(actual_roi=0.5),
        _guard_preview(break_even_roi=Decimal("2.5")),
        [],
    )
    assert result["error"] is None


# ---------------------------------------------------------------------------
# 4 · 路由层：护栏顺序 / 草稿不拦截 / 来源留痕
# ---------------------------------------------------------------------------


def _install_router_stubs(monkeypatch, *, preview, missing_fields):
    """把路由里那些要碰真实数据的服务替掉，只留要测的判定逻辑。"""

    async def _noop(*_args, **_kwargs):
        return None

    async def _no_floor(*_args, **_kwargs):
        return None

    async def _preview_stub(_self, _data):
        return preview

    async def _missing_stub(*_args, **_kwargs):
        return list(missing_fields)

    async def _label_fee_stub(_self, _warehouse_code):
        return None

    monkeypatch.setattr(pc_router, "_validate_operating_dimensions", _noop)
    monkeypatch.setattr(pc_router, "_write_product_center_audit", _noop)
    monkeypatch.setattr(pc_router, "_enqueue_platform_sku_profit_projection", _noop)
    monkeypatch.setattr(pc_router, "_compute_sku_min_selling_price", _no_floor)
    monkeypatch.setattr(
        pc_router.ProductFinanceService, "preview_platform_sku_profit", _preview_stub
    )
    monkeypatch.setattr(pc_router, "_platform_profit_missing_fields", _missing_stub)
    monkeypatch.setattr(
        pc_router.ProductFinanceService, "find_reference_label_fee", _label_fee_stub
    )


def _router_preview(*, break_even_roi=None, lower_bound=None):
    """一份够路由跑完的 preview（只填路由真正读到的键）。"""
    section = {
        "net_revenue": Decimal("100"),
        "purchase_cost": Decimal("30"),
        "logistics_cost": Decimal("20"),
        "storage_cost": Decimal("10"),
        "label_fee": Decimal("0"),
        "platform_fee": Decimal("10"),
        "creator_commission": Decimal("5"),
        "ad_cost": Decimal("0"),
        "return_loss": Decimal("2"),
        "damage_loss": Decimal("1"),
        "profit": Decimal("22"),
        "margin_rate": Decimal("0.22"),
        "pre_ad_profit": Decimal("22"),
        "break_even_roi": break_even_roi,
        "break_even_roi_lower_bound": lower_bound,
        "suggested_roi": None,
        "suggested_roi_clamped": None,
        "suggestion_note": None,
        "equivalent_target_roi": None,
        "completeness": "complete",
    }
    actual_section = dict(section)
    # actual_recost 段的完整度取值域与 expected 段**不同**（incomplete/estimated/mixed/actual）
    actual_section["completeness"] = "estimated"
    return {
        "expected": dict(section),
        "actual_recost": actual_section,
        "variance": {"logistics": None, "storage": None, "total": None},
        "expected_selling_price_source": "user_input",
        "reference_storage_days": 30,
        "reference_storage_rule_id": 1,
        "reference_storage_rule_version": 1,
        "actual_logistics_cost": None,
        "actual_storage_cost": None,
        "target_roi_ceiling": Decimal("50"),
    }


@pytest.mark.asyncio
async def test_roi_guard_fires_before_missing_cost_check(
    monkeypatch, roi_sqlite_session
):
    """护栏顺序：目标 ROI 低于保本线 **且** 缺物流规则 ⇒ 报 ROI 错误，不是报缺资料。"""
    preview = _router_preview(break_even_roi=Decimal("2.5"))
    _install_router_stubs(
        monkeypatch, preview=preview, missing_fields=["海运参考物流规则"]
    )
    body = PlatformSkuProfitEstimateRequest(
        sku_id=751,
        platform_code="tiktok",
        warehouse_code="WH01",
        transport_type="sea",
        expected_selling_price=100,
        target_roi=1.2,
    )
    with pytest.raises(BusinessValidationError) as excinfo:
        await pc_router.save_platform_sku_profit_estimates(
            body, roi_sqlite_session, _FakeUser()
        )
    assert excinfo.value.detail["code"] == "below_break_even_roi"


@pytest.mark.asyncio
async def test_roi_guard_fires_before_missing_cost_check_even_when_cost_incomplete(
    monkeypatch, roi_sqlite_session
):
    """成本不全时，下界能证明"必亏" ⇒ 仍然先报 ROI 错误。"""
    preview = _router_preview(break_even_roi=None, lower_bound=Decimal("2.0"))
    _install_router_stubs(
        monkeypatch, preview=preview, missing_fields=["海运参考物流规则"]
    )
    body = PlatformSkuProfitEstimateRequest(
        sku_id=751,
        platform_code="tiktok",
        warehouse_code="WH01",
        transport_type="sea",
        expected_selling_price=100,
        target_roi=1.0,
    )
    with pytest.raises(BusinessValidationError) as excinfo:
        await pc_router.save_platform_sku_profit_estimates(
            body, roi_sqlite_session, _FakeUser()
        )
    assert excinfo.value.detail["code"] == "below_break_even_roi"
    assert excinfo.value.detail["basis"] == "lower_bound"


@pytest.mark.asyncio
async def test_cost_incomplete_is_reported_when_guard_cannot_prove_it(
    monkeypatch, roi_sqlite_session
):
    """证不出"必亏" ⇒ 报成本不全（不可乐观放行）。"""
    preview = _router_preview(break_even_roi=None, lower_bound=Decimal("2.0"))
    _install_router_stubs(
        monkeypatch, preview=preview, missing_fields=["海运参考物流规则"]
    )
    body = PlatformSkuProfitEstimateRequest(
        sku_id=751,
        platform_code="tiktok",
        warehouse_code="WH01",
        transport_type="sea",
        expected_selling_price=100,
        target_roi=30.0,
    )
    with pytest.raises(BusinessValidationError) as excinfo:
        await pc_router.save_platform_sku_profit_estimates(
            body, roi_sqlite_session, _FakeUser()
        )
    assert excinfo.value.detail["code"] == "roi_cost_incomplete"


@pytest.mark.asyncio
async def test_draft_is_not_blocked_by_roi_guard(monkeypatch, roi_sqlite_session):
    """草稿不拦截：草稿是"还在填"的中间态，拦了就填不下去。"""
    preview = _router_preview(break_even_roi=Decimal("2.5"))
    _install_router_stubs(
        monkeypatch, preview=preview, missing_fields=["海运参考物流规则"]
    )
    body = PlatformSkuProfitDraftRequest(
        sku_id=751,
        platform_code="tiktok",
        warehouse_code="WH01",
        transport_type="sea",
        expected_selling_price=100,
        target_roi=1.2,
    )
    result = await pc_router.save_platform_sku_profit_draft(
        body, roi_sqlite_session, _FakeUser()
    )
    assert result["status"] == "draft_saved"

    from modules.core.db import SkuOperatingProfile
    from sqlalchemy import select

    rows = (
        (await roi_sqlite_session.execute(select(SkuOperatingProfile))).scalars().all()
    )
    assert len(rows) == 1
    assert Decimal(str(rows[0].target_roi)) == Decimal("1.2")
    assert rows[0].target_roi_source == "user_input"


@pytest.mark.asyncio
async def test_estimate_persists_target_roi_and_actual_roi_with_sources(
    monkeypatch, roi_sqlite_session
):
    """来源留痕：目标 ROI 落经营档案、平台报告 ROI 落利润版本，各带来源标记。"""
    from sqlalchemy import select

    from modules.core.db import SkuOperatingProfile, SkuProfitEstimate

    preview = _router_preview(break_even_roi=Decimal("2.5"))
    _install_router_stubs(monkeypatch, preview=preview, missing_fields=[])
    body = PlatformSkuProfitEstimateRequest(
        sku_id=751,
        platform_code="tiktok",
        warehouse_code="WH01",
        transport_type="sea",
        expected_selling_price=100,
        target_roi=3.0,
        actual_roi=1.1,
    )
    result = await pc_router.save_platform_sku_profit_estimates(
        body, roi_sqlite_session, _FakeUser()
    )
    assert result["estimate_ids"]

    profiles = (
        (await roi_sqlite_session.execute(select(SkuOperatingProfile))).scalars().all()
    )
    assert Decimal(str(profiles[0].target_roi)) == Decimal("3.0")
    assert profiles[0].target_roi_source == "user_input"

    estimates = (
        (await roi_sqlite_session.execute(select(SkuProfitEstimate))).scalars().all()
    )
    assert len(estimates) == 1
    assert Decimal(str(estimates[0].actual_roi)) == Decimal("1.1")
    assert estimates[0].actual_roi_source == "user_input"


@pytest.mark.asyncio
async def test_actual_roi_below_break_even_is_still_saved(
    monkeypatch, roi_sqlite_session
):
    """亏损投放照样能记录（只是标红，不拦）。"""
    from sqlalchemy import select

    from modules.core.db import SkuProfitEstimate

    preview = _router_preview(break_even_roi=Decimal("2.5"))
    _install_router_stubs(monkeypatch, preview=preview, missing_fields=[])
    body = PlatformSkuProfitEstimateRequest(
        sku_id=751,
        platform_code="tiktok",
        warehouse_code="WH01",
        transport_type="sea",
        expected_selling_price=100,
        actual_roi=0.8,
    )
    await pc_router.save_platform_sku_profit_estimates(
        body, roi_sqlite_session, _FakeUser()
    )
    estimates = (
        (await roi_sqlite_session.execute(select(SkuProfitEstimate))).scalars().all()
    )
    assert Decimal(str(estimates[0].actual_roi)) == Decimal("0.8")


# ---------------------------------------------------------------------------
# 5 · 错误信封
# ---------------------------------------------------------------------------


def test_error_envelope_shape_for_roi_guard():
    """错误信封：``{"success": false, "error": {"code": 3001, "detail": {...}}}``。

    顶层**不能**有 ``detail`` 键 —— 全局异常处理器会把 ``detail`` 拍平成字符串，
    前端就读不到 ``code`` 了。
    """
    import json

    error = BusinessValidationError(
        message="目标 ROI 1.2 低于保本线 2.5",
        detail={"code": "below_break_even_roi", "break_even_roi": 2.5},
    )
    response = error_response_v2(error)
    payload = json.loads(response.body)
    assert payload["success"] is False
    assert "detail" not in payload
    assert payload["error"]["code"] == 3001
    assert payload["error"]["detail"]["code"] == "below_break_even_roi"
