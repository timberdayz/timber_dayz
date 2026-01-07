"""
通用响应Schemas
用于标准化API响应格式
"""

from typing import Any, Dict, List, Optional, Generic, TypeVar
from datetime import datetime
from pydantic import BaseModel, Field

T = TypeVar('T')


class SuccessResponse(BaseModel, Generic[T]):
    """成功响应（通用）"""
    success: bool = Field(default=True, description="请求是否成功")
    data: T = Field(description="响应数据")
    message: Optional[str] = Field(None, description="可选的成功消息")
    timestamp: datetime = Field(default_factory=datetime.now, description="响应时间")


class ErrorDetail(BaseModel):
    """错误详情"""
    code: str = Field(description="错误代码")
    message: str = Field(description="错误消息")
    field: Optional[str] = Field(None, description="错误字段（用于表单验证）")
    recovery_suggestion: Optional[str] = Field(None, description="恢复建议")


class ErrorResponse(BaseModel):
    """错误响应"""
    success: bool = Field(default=False, description="请求是否成功")
    error: ErrorDetail = Field(description="错误详情")
    message: str = Field(description="用户友好的错误信息")
    timestamp: datetime = Field(default_factory=datetime.now, description="响应时间")


class PaginationMeta(BaseModel):
    """分页元数据"""
    page: int = Field(description="当前页码（1-based）")
    page_size: int = Field(description="每页条数")
    total: int = Field(description="总记录数")
    total_pages: int = Field(description="总页数")
    has_previous: bool = Field(description="是否有上一页")
    has_next: bool = Field(description="是否有下一页")


class PaginatedResponse(BaseModel, Generic[T]):
    """分页响应"""
    success: bool = Field(default=True, description="请求是否成功")
    data: List[T] = Field(description="数据列表")
    pagination: PaginationMeta = Field(description="分页信息")
    timestamp: datetime = Field(default_factory=datetime.now, description="响应时间")

