"""月度利润看板（只读）的 Pydantic 契约。

⚠️ 预算制（目标比例 / 目标额 / 差异）与审批制已随看板制下线 ⇒ 这里没有
``*_target_*`` / ``difference_*`` / ``follow_*`` 字段。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

#: 人工调整项的取值域（与 ``backend/services/monthly_profit_settlement_service.py``
#: 的 ``ADJUSTMENT_TYPES`` 保持一致）
AdjustmentType = Literal[
    "manual_adjustment",
    "cross_period_expense",
    "one_off_gain_loss",
    "correction",
]


class MonthlyProfitShopBreakdownItemResponse(BaseModel):
    """单个门店的员工侧分配额（只含 shop scope）。

    ⚠️ ``profit_basis_amount`` 为该店利润基数；亏损店（≤ 0）时
    ``allocation_ratio`` 取 0，但 ``over_allocation_flag`` 仍按金额比判定。
    """

    platform_code: Optional[str] = None
    shop_id: Optional[str] = None
    profit_basis_amount: float
    performance_amount: float
    commission_amount: float
    allocation_amount: float
    allocation_ratio: float
    over_allocation_flag: bool


class MonthlyProfitDashboardAdjustmentResponse(BaseModel):
    """一条人工调整项。"""

    id: Optional[int] = None
    adjustment_type: str
    amount: float
    reason: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None


class MonthlyProfitDashboardResponse(BaseModel):
    """月度利润看板 payload（扁平结构）。"""

    period_month: str
    as_of: str
    net_profit_amount: float
    performance_salary_amount: float
    commission_amount: float
    employee_allocation_amount: float
    manual_adjustment_amount: float
    manual_adjustment_count: int
    company_retained_amount: float
    allocation_ratio: float
    over_allocation_flag: bool
    shop_breakdown: list[MonthlyProfitShopBreakdownItemResponse]
    adjustments: list[MonthlyProfitDashboardAdjustmentResponse]
    #: 数据状态：``ready`` = 该月有现行口径结算数据；
    #: ``no_profit_basis`` = 该月没有（历史月份口径归一后清空）⇒ 看板空白属预期。
    data_status: str = "ready"
    #: 给运营看的一句话说明（前端直接渲染，不要自己判断口径）。
    data_status_note: str = ""
    #: 本月使用的利润基数口径（唯一口径）。
    basis_version: str = "SETTLEMENT_BASIS_V1"


class MonthlyProfitDashboardEnvelopeResponse(BaseModel):
    success: bool
    data: MonthlyProfitDashboardResponse
    timestamp: str


class MonthlyProfitAdjustmentCreateRequest(BaseModel):
    period_month: str = Field(..., pattern=r"^\d{4}-\d{2}$")
    adjustment_type: AdjustmentType
    amount: float
    #: 必须写明原因，不允许用默认串兜底
    reason: str = Field(..., min_length=1)


class MonthlyProfitAdjustmentResponse(BaseModel):
    id: Optional[int] = None
    period_month: Optional[str] = None
    settlement_id: Optional[int] = None
    adjustment_type: str
    amount: float
    reason: Optional[str] = None
    created_by: Optional[str] = None


class MonthlyProfitAdjustmentEnvelopeResponse(BaseModel):
    success: bool
    data: MonthlyProfitAdjustmentResponse
    timestamp: str


class MonthlyProfitAdjustmentDeleteResponse(BaseModel):
    id: int
    deleted: bool
    settlement_id: Optional[int] = None


class MonthlyProfitAdjustmentDeleteEnvelopeResponse(BaseModel):
    success: bool
    data: MonthlyProfitAdjustmentDeleteResponse
    timestamp: str
