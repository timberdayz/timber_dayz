"""逐店提成明细必须能自己加出总额（尾差吸收）。

背景：提成**总额**的口径是「各店未舍入金额累加后统一舍入一次」，
而逐店明细各自舍入后再相加可能差 1 分
（2026-10 实测：黄嘉矩 9.22 + 144.67 = 153.89，实发总额 153.88）。
尾差必须有归属，否则运营在页面上按店加永远对不上工资单。
"""

from backend.services.hr_income_calculation_service import (
    _absorb_commission_rounding_residue,
)


def test_residue_is_absorbed_into_largest_shop():
    shops = [
        {"commission_amount": 9.22},
        {"commission_amount": 144.67},
    ]
    # 未舍入累加 = 153.884667… → 总额 153.88
    _absorb_commission_rounding_residue(shops, 153.88466711538462)
    assert sum(item["commission_amount"] for item in shops) == 153.88
    # 尾差落在金额最大的那家
    assert shops[0]["commission_amount"] == 9.22
    assert shops[1]["commission_amount"] == 144.66


def test_no_residue_leaves_values_untouched():
    shops = [{"commission_amount": 10.0}, {"commission_amount": 20.0}]
    _absorb_commission_rounding_residue(shops, 30.0)
    assert [item["commission_amount"] for item in shops] == [10.0, 20.0]


def test_negative_residue_is_also_absorbed():
    shops = [
        {"commission_amount": 10.01},
        {"commission_amount": 20.01},
    ]
    _absorb_commission_rounding_residue(shops, 30.0)
    assert sum(item["commission_amount"] for item in shops) == 30.0
    assert shops[1]["commission_amount"] == 19.99


def test_empty_list_is_safe():
    _absorb_commission_rounding_residue([], 100.0)
