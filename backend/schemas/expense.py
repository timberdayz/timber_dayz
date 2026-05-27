"""
费用管理 API 契约 (Contract-First)
"""

from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel, Field, field_validator, model_validator


class ExpenseCreateRequest(BaseModel):
    """创建/更新费用请求(Upsert)"""

    platform_code: Optional[str] = Field(None, description="平台编码")
    shop_id: str = Field(..., description="店铺ID")
    year_month: str = Field(
        ..., description="费用月份(YYYY-MM)", pattern=r"^\d{4}-\d{2}$"
    )
    rent: float = Field(0.0, ge=0, description="租金(CNY)")
    marketing_fee: float = Field(0.0, ge=0, description="营销费用(CNY)")
    utilities: float = Field(0.0, ge=0, description="水电费(CNY)")
    ai_token_cost: float = Field(0.0, ge=0, description="AI Token费用(CNY)")
    other_costs: float = Field(0.0, ge=0, description="其他成本(CNY)")
    note: Optional[str] = Field(None, description="备注")
    attachments: Optional[list[Any]] = Field(None, description="附件(JSON数组)")

    @field_validator("shop_id")
    @classmethod
    def validate_required_non_empty_string(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("must not be empty")
        return normalized

    @field_validator("platform_code")
    @classmethod
    def normalize_optional_platform_code(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @field_validator("year_month")
    @classmethod
    def validate_year_month_non_empty(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("must not be empty")
        return normalized

    @model_validator(mode="after")
    def validate_meaningful_payload(self):
        note = str(self.note or "").strip()
        attachments = self.attachments or []
        if (
            self.rent == 0
            and self.marketing_fee == 0
            and self.utilities == 0
            and self.ai_token_cost == 0
            and self.other_costs == 0
            and not note
            and not attachments
        ):
            raise ValueError("empty expense record is not allowed")
        return self


class ExpenseUpdateRequest(BaseModel):
    """更新费用请求"""

    platform_code: Optional[str] = Field(None)
    rent: Optional[float] = Field(None, ge=0)
    marketing_fee: Optional[float] = Field(None, ge=0)
    utilities: Optional[float] = Field(None, ge=0)
    ai_token_cost: Optional[float] = Field(None, ge=0)
    other_costs: Optional[float] = Field(None, ge=0)
    note: Optional[str] = Field(None)
    attachments: Optional[list[Any]] = Field(None)

    @field_validator("platform_code")
    @classmethod
    def validate_optional_platform_code(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        normalized = str(value).strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_not_all_empty(self):
        if not any(
            value is not None
            for value in (
                self.platform_code,
                self.rent,
                self.marketing_fee,
                self.utilities,
                self.ai_token_cost,
                self.other_costs,
                self.note,
                self.attachments,
            )
        ):
            return self

        note = str(self.note or "").strip() if self.note is not None else ""
        attachments = self.attachments if self.attachments is not None else []
        if (
            (self.rent in (None, 0))
            and (self.marketing_fee in (None, 0))
            and (self.utilities in (None, 0))
            and (self.ai_token_cost in (None, 0))
            and (self.other_costs in (None, 0))
            and not note
            and attachments == []
        ):
            raise ValueError("empty expense update is not allowed")
        return self


class ExpenseResponse(BaseModel):
    """费用响应"""

    id: int
    platform_code: Optional[str] = None
    shop_id: str
    year_month: str
    rent: float
    marketing_fee: float
    utilities: float
    ai_token_cost: float
    other_costs: float
    total_cost: float
    total: float
    note: Optional[str] = None
    attachments: list[Any] = Field(default_factory=list)
    locked: bool = False
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ExpenseSummaryResponse(BaseModel):
    """费用汇总响应"""

    year_month: str
    shop_count: int
    total_rent: float
    total_marketing_fee: float
    total_utilities: float
    total_ai_token_cost: float
    total_other_costs: float
    total_amount: float
