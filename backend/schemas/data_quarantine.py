"""
数据隔离 API 契约 (Contract-First)
"""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel


class QuarantineListRequest(BaseModel):
    """隔离数据列表查询请求"""

    file_id: Optional[int] = None
    platform: Optional[str] = None
    data_domain: Optional[str] = None
    error_type: Optional[str] = None
    page: int = 1
    page_size: int = 20


class QuarantineDetailResponse(BaseModel):
    """隔离数据详情响应"""

    id: int
    file_id: int
    file_name: str
    platform_code: str
    data_domain: str
    row_index: int
    raw_data: dict
    error_type: str
    error_message: str
    validation_errors: Optional[dict]
    created_at: datetime

    class Config:
        from_attributes = True


class ReprocessRequest(BaseModel):
    """重新处理请求"""

    quarantine_ids: List[int]
    corrections: Optional[dict] = None


class ReprocessResponse(BaseModel):
    """重新处理响应"""

    success: bool
    processed: int
    succeeded: int
    failed: int
    errors: List[dict]
