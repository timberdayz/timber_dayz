"""
数据质量 API 契约 (Contract-First)
"""

from typing import Any, Dict, List

from pydantic import BaseModel


class CClassReadinessResponse(BaseModel):
    """C类数据计算就绪状态响应"""

    c_class_ready: bool
    b_class_completeness: Dict[str, float]
    missing_core_fields: List[str]
    data_quality_score: float
    warnings: List[str]
    timestamp: str


class CoreFieldsStatusResponse(BaseModel):
    """核心字段状态响应"""

    total_fields: int
    present_fields: int
    missing_fields: int
    fields_by_domain: Dict[str, Dict[str, Any]]
    timestamp: str
