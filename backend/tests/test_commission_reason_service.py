"""零提成原因的唯一实现（backend/services/commission_reason_service.py）。

铁律：**有提成就不给「提成为 0」的原因**。
以前调用方漏传「实际算出来的预计提成」，导致有提成的店铺也被标成
「本店本月归属的提成比合计为 0」，页面自相矛盾。
"""

from backend.services.commission_reason_service import commission_zero_reason


def _base(**overrides):
    payload = {
        "is_rate_configured": True,
        "allocatable_rate": 0.25,
        "profit_basis_amount": 1000.0,
        "estimated_total_commission": 100.0,
        "has_assignment": True,
        "cost_status": "ready",
    }
    payload.update(overrides)
    return payload


def test_has_commission_never_reports_zero_reason():
    assert commission_zero_reason(**_base()) is None


def test_unconfigured_rate_is_distinguished_from_zero_rate():
    assert (
        commission_zero_reason(**_base(is_rate_configured=False))
        == "未配置可分配率，该店本月不参与提成分配"
    )
    assert (
        commission_zero_reason(**_base(allocatable_rate=0.0))
        == "可分配率为 0，该店本月不参与提成分配"
    )


def test_loss_shop_is_reported_as_loss():
    assert (
        commission_zero_reason(**_base(profit_basis_amount=-100.0))
        == "本店本月结算利润为负（亏损），按规则不计提成"
    )


def test_missing_assignment_is_reported_before_ratio():
    assert (
        commission_zero_reason(**_base(has_assignment=False))
        == "本店本月没有生效的归属与提成比配置"
    )


def test_person_level_ratio_and_shop_level_ratio_sum():
    assert (
        commission_zero_reason(**_base(commission_ratio=0.0))
        == "本店本月该人员的归属提成比未配置"
    )
    assert (
        commission_zero_reason(**_base(commission_ratio_sum=0.0))
        == "本店本月归属的提成比合计为 0"
    )


def test_zero_profit_is_reported_when_ratio_is_configured():
    assert (
        commission_zero_reason(
            **_base(
                estimated_total_commission=0.0,
                commission_ratio=0.5,
                commission_ratio_sum=0.5,
            )
        )
        == "本店本月结算利润为 0，暂不产生提成"
    )


def test_missing_labor_allocation_is_flagged_as_reference_only():
    assert (
        commission_zero_reason(**_base(cost_status="missing_labor_allocation"))
        == "人力成本分摊未完成，当前为参考值"
    )
