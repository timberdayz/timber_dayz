"""商品中心 ROI 计算的**纯函数**模块（阶段 1 · ROI 只读层）。

设计约束
--------
- **纯函数**：无 ORM、无 DB、无 I/O（与 `product_pricing_service.py` 同风格）。
  这样 ROI 的每个边界都能写成无 DB 单测（设计稿 §5.1「实现时只写一处」）。
- **金额才量化，费率不量化**（设计稿 §2.4②）：ROI 是比率不是金额，
  保留全精度；只有"单均广告费/单均净利"这种金额过 `_money`（`MONEY_QUANTUM=0.01`）。
- **缺输入宁可不算，不可乐观**：分母 ≤ 0 一律返回 None + `missing_reasons`，
  绝不返回一个"看起来能用"的数 —— 成本不全时保本ROI 会偏松，运营照着投广告就是亏。

口径依据
--------
上游设计稿 §2.5⑦⑨⑩⑪：
`docs/superpowers/specs/2026-11-06-product-center-caliber-naming-and-roi-design.md`

关键口径
--------
- **保本ROI 的分母是「商家实收」**（= 测算售价 − 卖家优惠券），不是商品金额，也不是买家实付。
  理由见设计稿 §2.5⑦：TikTok GMV = 买家实付 + 平台补贴 = 售价 − 卖家券 = 商家实收，
  所以这个口径**与平台后台同一把标尺**，可以直接对照。
- **只封顶不封底**（§2.5⑨）：保本ROI < 1 意味着毛利率 > 100%，是"成本算错了"的**异常信号**，
  该报错而不是被 clamp 藏起来。
- **安全边际 20%**（§2.5⑨）：业界实测 buffer 是相对百分比 12%–25%，取下沿，保守。
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

MONEY_QUANTUM = Decimal("0.01")

#: ROI 展示与填写的精度：**两位小数**。
#: 平台后台（TikTok GMV MAX / Shopee Ads）只接受两位小数，运营也只会照抄两位。
ROI_QUANTUM = Decimal("0.01")

#: 安全边际默认值（设计稿 §2.5⑨：业界 12%–25%，取下沿 20%）
DEFAULT_SAFETY_MARGIN = Decimal("0.20")

#: 全局可填上限默认值（设计稿 §2.5⑨：各平台可填上限取 max = Shopee 50）
DEFAULT_TARGET_ROI_CEILING = Decimal("50")

#: 平台可填下限（**当前不参与 clamp**，只记录平台允许填的最小值）
DEFAULT_TARGET_ROI_FLOOR = Decimal("1")


def _decimal(value) -> Optional[Decimal]:
    """费率/比率的入口转换：**保留全精度**，不做量化。"""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _money(value) -> Decimal:
    """金额量化到分。费率与 ROI **不要**用这个函数。"""
    return Decimal(value).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _roi(value) -> Decimal:
    """ROI 量化到两位小数（**运营实际填进平台后台的精度**）。"""
    return Decimal(value).quantize(ROI_QUANTUM, rounding=ROUND_HALF_UP)


def compute_break_even_roi_lower_bound(
    *,
    net_revenue,
    pre_ad_profit_upper_bound,
) -> dict:
    """保本 ROI 的**下界** —— 成本不全时仍能给出的**保守**判定依据（阶段 2.2）。

    为什么需要它
    ------------
    ``break_even_roi = net_revenue ÷ pre_ad_profit``，而 ``pre_ad_profit`` 需要
    采购/物流/仓储/平台佣金/达人佣金/货损/退货**全部**齐了才算得出来。
    缺一项（比如缺物流规则）⇒ ``break_even_roi`` 就是 ``None`` ⇒
    护栏无从判断"运营填的目标 ROI 是不是在亏本线以下"。

    但**完全跳过护栏**有个危险：运营填一个极低的 ROI（明显低于任何合理保本线），
    系统会因为"算不出保本线"而放行 —— 等于给"必亏的投放"开了后门。

    这里的办法（**证明，不是估算**）
    ------------------------------
    把**所有未知成本一律当 0**，算出"最乐观情况下"的广告前利润
    ``pre_ad_profit_upper_bound``。因为未知成本的真值 ≥ 0：

    .. code-block:: text

        真实 pre_ad_profit ≤ pre_ad_profit_upper_bound
        ⇒ 真实 break_even_roi = net_revenue ÷ 真实 pre_ad_profit
          ≥ net_revenue ÷ pre_ad_profit_upper_bound
          = 保本 ROI 的下界

    于是只要 ``target_roi < 下界 ≤ 真实保本线``，就**可以确定**这单投了就是亏 ⇒ 拦得住。

    ⚠️ 口径纪律（重要）
    ------------------
    这里**不是**"乐观地估算一个保本线"，而是拿一个**只可能偏松**的下界去
    **证明**"低于它就一定亏"。**证明成立才拦，证不出来就不拦** ——
    证不出来时交给 ``roi_cost_incomplete``（成本不全 ⇒ 保本ROI 不可信，不可乐观）。

    ``pre_ad_profit_upper_bound ≤ 0`` 时**没有下界**
    （未知成本全部当 0 都不赚钱 ⇒ 不投广告也亏 ⇒ 这不是 ROI 问题，是成本问题），
    返回 ``None`` + ``missing_reasons``。

    参数
    ----
    net_revenue:
        商家实收（= 测算售价 − 卖家优惠券）。
    pre_ad_profit_upper_bound:
        广告前利润的**上界**（未知成本当 0 算出来的那个数）。
    """
    missing_reasons: list[str] = []
    revenue = _decimal(net_revenue)
    upper_bound = _decimal(pre_ad_profit_upper_bound)

    if revenue is None or revenue <= 0:
        missing_reasons.append("non_positive_revenue")
        return {"break_even_roi_lower_bound": None, "missing_reasons": missing_reasons}
    if upper_bound is None or upper_bound <= 0:
        # 未知成本全当 0 都不赚钱 ⇒ 没有任何 ROI 能救 ⇒ 谈不上"低于保本线"
        missing_reasons.append("non_positive_cost_upper_bound")
        return {"break_even_roi_lower_bound": None, "missing_reasons": missing_reasons}

    return {
        "break_even_roi_lower_bound": revenue / upper_bound,
        "missing_reasons": missing_reasons,
    }


def compute_roi_metrics(
    *,
    net_revenue,
    pre_ad_profit,
    safety_margin=DEFAULT_SAFETY_MARGIN,
    target_roi_ceiling=DEFAULT_TARGET_ROI_CEILING,
    expected_ad_rate=None,
) -> dict:
    """算出广告投放边界（保本 ROI / 建议 ROI）与给运营看的等价翻译。

    参数
    ----
    net_revenue:
        **商家实收** = 测算售价 − 卖家优惠券（= 平台 GMV 口径）。不是商品金额。
    pre_ad_profit:
        广告前利润（扣掉采购、物流、仓储、贴单、平台佣金、达人佣金、货损、退货之后，
        **扣广告费之前**）。
    safety_margin:
        安全边际，默认 0.20。
    target_roi_ceiling:
        平台可填上限（硬约束）。默认 50。
    expected_ad_rate:
        老口径的"广告分成率" s（广告费 ÷ 广告前利润）。给了才能算
        `equivalent_target_roi`（= 保本ROI ÷ s），阶段 3 迁移存量时要用。

    返回
    ----
    dict，键如下（值全是 ``Decimal | None``，``None`` 表示算不出来）：

    - ``advertising_contribution_margin_rate`` 广告前贡献毛利率 p
    - ``break_even_roi`` 保本 ROI = net_revenue ÷ pre_ad_profit（**全精度**）
    - ``suggested_roi`` 建议 ROI = 保本ROI × (1 + 安全边际)（**未封顶原值，全精度**）
    - ``suggested_roi_clamped`` **可执行**建议 ROI：两位小数 + 平台上限封顶。
      这是运营真正填进平台后台的数，等效金额也由它推出。
    - ``suggestion_note`` ``"above_platform_ceiling"`` 或 None
    - ``equivalent_target_roi`` 等效目标 ROI = 保本ROI ÷ 广告分成率
    - ``equivalent_ad_cost_per_order`` 等效单均广告费 = net_revenue ÷ 可执行建议ROI
    - ``equivalent_net_profit_per_order`` 等效单均净利
    - ``equivalent_net_margin_rate`` 等效净利率
    - ``missing_reasons`` 算不出来的原因（列表，可能为空）
    - ``anomalies`` 异常信号（列表，可能为空；如保本ROI < 1）
    """
    missing_reasons: list[str] = []
    anomalies: list[str] = []

    revenue = _decimal(net_revenue)
    profit = _decimal(pre_ad_profit)
    margin = _decimal(safety_margin)
    ceiling = _decimal(target_roi_ceiling)
    ad_rate = _decimal(expected_ad_rate)

    if margin is None:
        margin = DEFAULT_SAFETY_MARGIN
    if ceiling is None:
        ceiling = DEFAULT_TARGET_ROI_CEILING

    empty = {
        "advertising_contribution_margin_rate": None,
        "break_even_roi": None,
        "suggested_roi": None,
        "suggested_roi_clamped": None,
        "suggestion_note": None,
        "equivalent_target_roi": None,
        "equivalent_ad_cost_per_order": None,
        "equivalent_net_profit_per_order": None,
        "equivalent_net_margin_rate": None,
        "missing_reasons": missing_reasons,
        "anomalies": anomalies,
    }

    if revenue is None or revenue <= 0:
        missing_reasons.append("non_positive_revenue")
        return empty
    if profit is None or profit <= 0:
        # 成本不全 / 亏本 → 保本ROI 无意义。返回 None 而不是乐观值。
        missing_reasons.append("non_positive_cost_denominator")
        return empty

    contribution_margin_rate = profit / revenue
    break_even_roi = revenue / profit

    # 只封顶不封底：保本ROI < 1 ⇒ 毛利率 > 100%，这是异常信号，**不 clamp**。
    if break_even_roi < 1:
        anomalies.append("break_even_roi_below_one")

    # 未封顶原值：保留全精度，供「真实差距」对比（设计稿 §2.5⑨ 要求仍显示原值）
    suggested_roi = break_even_roi * (Decimal("1") + margin)
    suggestion_note = "above_platform_ceiling" if suggested_roi > ceiling else None

    # 可执行建议 ROI：保本 ROI 先取整到两位，再上安全边际，最后取整，再按平台上限封顶。
    # ⚠️ 为什么不在最后一步才取整：表上保本 ROI 显示 1.97，运营自己算
    #    1.97 × 1.2 = 2.36 —— 表上写的必须是 2.36 才对得上账。
    #    等效单均广告费/净利也由这个数推出，数字之间必须能互相验算。
    executable = _roi(_roi(break_even_roi) * (Decimal("1") + margin))
    clamped = min(executable, ceiling)

    # 等效单均：用**封顶后的可执行 ROI** —— 那是平台实际允许执行的数。
    # 超上限时它会算出负净利，正好传达「按平台上限投也是亏的」。
    equivalent_ad_cost = None
    equivalent_net_profit = None
    equivalent_net_margin_rate = None
    if clamped > 0:
        equivalent_ad_cost = revenue / clamped
        equivalent_net_profit = profit - equivalent_ad_cost
        equivalent_net_margin_rate = equivalent_net_profit / revenue
    else:
        # 保本 ROI 小到取整后归零（极端值），等效金额除法无意义
        missing_reasons.append("non_positive_target_roi")

    # 等效目标 ROI（老口径广告分成率 → 平台语言）。阶段 3 迁移存量时用。
    equivalent_target_roi = None
    if ad_rate is not None and ad_rate > 0:
        equivalent_target_roi = break_even_roi / ad_rate

    return {
        "advertising_contribution_margin_rate": contribution_margin_rate,
        "break_even_roi": break_even_roi,
        "suggested_roi": suggested_roi,
        "suggested_roi_clamped": clamped,
        "suggestion_note": suggestion_note,
        "equivalent_target_roi": equivalent_target_roi,
        "equivalent_ad_cost_per_order": (
            _money(equivalent_ad_cost) if equivalent_ad_cost is not None else None
        ),
        "equivalent_net_profit_per_order": (
            _money(equivalent_net_profit) if equivalent_net_profit is not None else None
        ),
        "equivalent_net_margin_rate": equivalent_net_margin_rate,
        "missing_reasons": missing_reasons,
        "anomalies": anomalies,
    }
