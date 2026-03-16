"""
HR 人力/员工与收入相关 API 契约 (Contract-First)
add-performance-and-personal-income: 我的收入响应等
"""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class MyIncomeResponse(BaseModel):
    """我的收入响应；未关联员工时 linked=false，仅返回 linked 字段。"""
    linked: bool = Field(True, description="是否已关联员工档案")
    period: Optional[str] = Field(None, description="月份 YYYY-MM")
    base_salary: Optional[float] = Field(None, description="基本工资")
    commission_amount: Optional[float] = Field(None, description="提成金额")
    commission_rate: Optional[float] = Field(None, description="提成比例")
    performance_score: Optional[float] = Field(None, description="绩效得分")
    achievement_rate: Optional[float] = Field(None, description="达成率")
    total_income: Optional[float] = Field(None, description="总收入")
    breakdown: Optional[Dict[str, Any]] = Field(None, description="明细 breakdown")


class IncomeCalculationResponse(BaseModel):
    """员工 C 类收入数据重算结果。"""
    year_month: str = Field(..., description="计算月份 YYYY-MM")
    employee_count: int = Field(..., description="参与计算的员工数")
    commission_upserts: int = Field(..., description="employee_commissions 写入/更新条数")
    performance_upserts: int = Field(..., description="employee_performance 写入/更新条数")
    source: str = Field(..., description="数据来源说明")
