"""
组件版本管理 API 合同 (Contract-First)

从 `backend/routers/component_versions.py` 提取的 Pydantic 模型：
- ComponentVersionResponse / VersionListResponse
- VersionRegisterRequest / ABTestRequest / VersionUpdateRequest
- BatchRegisterRequest / BatchRegisterResult / BatchRegisterResponse
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class ComponentVersionResponse(BaseModel):
    """组件版本响应模型。"""

    id: int
    component_name: str
    version: str
    file_path: str
    is_stable: bool
    is_active: bool
    is_testing: bool
    usage_count: int
    success_count: int
    failure_count: int
    success_rate: float
    test_ratio: float
    test_start_at: Optional[str] = None
    test_end_at: Optional[str] = None
    description: Optional[str] = None
    created_by: Optional[str] = None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class VersionListResponse(BaseModel):
    """版本列表响应。"""

    data: List[ComponentVersionResponse]
    total: int
    page: int
    page_size: int


class VersionRegisterRequest(BaseModel):
    """注册版本请求。"""

    component_name: str = Field(..., description="组件名称(如 shopee/login)")
    version: str = Field(..., description="版本号(如 1.0.0)")
    file_path: str = Field(..., description="文件路径")
    description: Optional[str] = Field(None, description="版本说明")
    is_stable: bool = Field(
        False,
        description="是否标记为稳定版本(正式运行需通过 promote 单独提升,注册时会忽略此值)",
    )
    created_by: Optional[str] = Field(None, description="创建人")


class ABTestRequest(BaseModel):
    """启动 A/B 测试请求。"""

    test_ratio: float = Field(..., ge=0.05, le=0.5, description="测试流量比例(0.05-0.5)")
    duration_days: int = Field(..., ge=1, le=30, description="测试持续天数(1-30)")


class VersionUpdateRequest(BaseModel):
    """更新版本请求。"""

    is_active: Optional[bool] = Field(None, description="是否启用")
    description: Optional[str] = Field(None, description="版本说明")


class BatchRegisterRequest(BaseModel):
    """批量注册请求。"""

    platform: Optional[str] = Field(None, description="指定平台(可选)")


class BatchRegisterResult(BaseModel):
    """批量注册结果。"""

    component_name: str
    file_path: str
    version: str
    status: str  # registered, updated, skipped, error
    error: Optional[str] = None


class BatchRegisterResponse(BaseModel):
    """批量注册响应。"""

    success: bool
    registered_count: int
    skipped_count: int
    error_count: int
    details: List[BatchRegisterResult]


class TimeSelectionPayload(BaseModel):
    """统一时间选择模型"""

    mode: Literal["preset", "custom"] = Field(..., description="时间模式")
    preset: Optional[Literal["today", "yesterday", "last_7_days", "last_30_days"]] = Field(
        None,
        description="快捷时间预设",
    )
    start_date: Optional[str] = Field(None, description="自定义开始日期 YYYY-MM-DD")
    end_date: Optional[str] = Field(None, description="自定义结束日期 YYYY-MM-DD")
    start_time: Optional[str] = Field("00:00:00", description="自定义开始时间 HH:MM:SS")
    end_time: Optional[str] = Field("23:59:59", description="自定义结束时间 HH:MM:SS")


class ComponentTestRequest(BaseModel):
    """测试组件请求"""

    account_id: str = Field(..., description="测试账号ID")
    granularity: Optional[str] = Field(None, description="导出测试粒度(快捷时间将自动推导)")
    time_mode: Optional[Literal["preset", "custom"]] = Field(None, description="时间选择模式")
    date_preset: Optional[Literal["today", "yesterday", "last_7_days", "last_30_days"]] = Field(
        None,
        description="快捷时间预设",
    )
    start_date: Optional[str] = Field(None, description="导出测试开始日期 YYYY-MM-DD")
    end_date: Optional[str] = Field(None, description="导出测试结束日期 YYYY-MM-DD")
    start_time: Optional[str] = Field(None, description="导出测试开始时间 HH:MM:SS")
    end_time: Optional[str] = Field(None, description="导出测试结束时间 HH:MM:SS")
    time_selection: Optional[TimeSelectionPayload] = Field(None, description="统一时间选择模型")
    sub_domain: Optional[str] = Field(None, description="导出测试子数据域")


class TestHistoryResponse(BaseModel):
    """测试历史响应模型"""

    test_id: str
    component_name: str
    component_version: Optional[str] = None
    platform: str
    account_id: str
    status: str
    duration_ms: int
    steps_total: int
    steps_passed: int
    steps_failed: int
    success_rate: float
    tested_at: str
    tested_by: Optional[str] = None

    class Config:
        from_attributes = True


class TestHistoryListResponse(BaseModel):
    """测试历史列表响应"""

    total: int
    items: List[TestHistoryResponse]


class TestResumeRequest(BaseModel):
    """测试验证码回传请求体"""

    captcha_code: Optional[str] = Field(None, description="图形验证码")
    otp: Optional[str] = Field(None, description="短信/OTP 验证码")
    manual_completed: Optional[bool] = Field(None, description="用户已手动完成滑块等验证,请求继续")

    @model_validator(mode="after")
    def validate_exactly_one_value(self):
        captcha = (self.captcha_code or "").strip()
        otp = (self.otp or "").strip()
        manual_completed = bool(self.manual_completed)
        filled_count = sum(1 for value in (captcha, otp) if value) + (1 if manual_completed else 0)
        if filled_count != 1:
            raise ValueError("exactly one of captcha_code, otp, or manual_completed is required")
        self.captcha_code = captcha or None
        self.otp = otp or None
        self.manual_completed = True if manual_completed else None
        return self


__all__ = [
    "ComponentVersionResponse",
    "VersionListResponse",
    "VersionRegisterRequest",
    "ABTestRequest",
    "VersionUpdateRequest",
    "BatchRegisterRequest",
    "BatchRegisterResult",
    "BatchRegisterResponse",
    "TimeSelectionPayload",
    "ComponentTestRequest",
    "TestHistoryResponse",
    "TestHistoryListResponse",
    "TestResumeRequest",
]
