"""
组件版本管理 API 契约 (Contract-First)

从 `backend/routers/component_versions.py` 提取的 Pydantic 模型：
- ComponentVersionResponse / VersionListResponse
- VersionRegisterRequest / ABTestRequest / VersionUpdateRequest
- BatchRegisterRequest / BatchRegisterResult / BatchRegisterResponse
"""

from typing import List, Optional

from pydantic import BaseModel, Field


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
    is_stable: bool = Field(False, description="是否标记为稳定版本")
    created_by: Optional[str] = Field(None, description="创建人")


class ABTestRequest(BaseModel):
    """启动 A/B 测试请求。"""

    test_ratio: float = Field(
        ..., ge=0.05, le=0.5, description="测试流量比例(0.05-0.5)"
    )
    duration_days: int = Field(
        ..., ge=1, le=30, description="测试持续天数(1-30)"
    )


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


class ComponentTestRequest(BaseModel):
    """测试组件请求"""

    account_id: str = Field(..., description="测试账号ID")


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


__all__ = [
    "ComponentVersionResponse",
    "VersionListResponse",
    "VersionRegisterRequest",
    "ABTestRequest",
    "VersionUpdateRequest",
    "BatchRegisterRequest",
    "BatchRegisterResult",
    "BatchRegisterResponse",
    "ComponentTestRequest",
    "TestHistoryResponse",
    "TestHistoryListResponse",
    "TestResumeRequest",
]

