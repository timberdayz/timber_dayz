"""提成为什么是 0 —— 统一口径。

以前页面上只能显示一个「0」，运营看不懂到底卡在哪一步：
是没配可分配率？是亏了？还是这个人的提成比没填？

现在后端在给出 0 的同时给出**业务原因**，前端直接展示，
把「0」变成一句可以行动的话。

这个模块是**唯一**的实现：统计接口、结算预览、店铺维度列表都调它，
避免同一个 0 在不同页面有三种说法。

**一条铁律：有提成就不给「提成为 0」的原因。**
所以调用方必须把「这个维度上实际算出来的预计提成」传进
``estimated_total_commission``；漏传会让有提成的店铺也被标成「提成为 0」。
"""

from __future__ import annotations

from typing import Optional


def commission_zero_reason(
    *,
    is_rate_configured: bool,
    allocatable_rate: float,
    profit_basis_amount: float = 0.0,
    estimated_total_commission: float = 0.0,
    has_assignment: bool = True,
    cost_status: str = "",
    commission_ratio: Optional[float] = None,
    commission_ratio_sum: Optional[float] = None,
) -> Optional[str]:
    """预计提成为 0 时给出业务原因；不是 0 就返回 ``None``。

    顺序按「最先要解决的那个原因」排列：
    配置缺失 → 政策为 0 → 亏损 → 没人负责 → 提成比没配 → 成本口径未就绪。

    参数
    ----
    is_rate_configured:
        该店当月有没有配置可分配率。**没配置 ≠ 配成 0**，
        页面要能区分「忘了配」和「决定本月不分」。
    estimated_total_commission:
        **这个维度上实际算出来的预计提成**（要带上结算系数）。
        大于 0 时一定返回 ``None``，不报「提成为 0」。
    commission_ratio:
        个人维度的归属提成比；传了就按「这个人的提成比没配」来提示。
    commission_ratio_sum:
        店铺维度的归属提成比合计；传了就按「合计为 0」来提示。
    """
    if not is_rate_configured:
        return "未配置可分配率，该店本月不参与提成分配"
    if float(allocatable_rate or 0.0) <= 0:
        return "可分配率为 0，该店本月不参与提成分配"
    if float(profit_basis_amount or 0.0) < 0:
        return "本店本月结算利润为负（亏损），按规则不计提成"
    if not has_assignment:
        return "本店本月没有生效的归属与提成比配置"
    if commission_ratio is not None and float(commission_ratio or 0.0) <= 0:
        return "本店本月该人员的归属提成比未配置"
    if commission_ratio_sum is not None and float(commission_ratio_sum or 0.0) <= 0:
        return "本店本月归属的提成比合计为 0"
    if float(estimated_total_commission or 0.0) <= 0:
        return "本店本月结算利润为 0，暂不产生提成"
    if str(cost_status or "") == "missing_labor_allocation":
        return "人力成本分摊未完成，当前为参考值"
    return None
