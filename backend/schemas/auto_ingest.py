"""
自动入库 API 契约 (Contract-First)
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class BatchAutoIngestRequest(BaseModel):
    """批量自动入库请求"""

    platform: Optional[str] = Field(
        None, description="平台代码;传入'*'或省略表示全部平台"
    )
    domains: Optional[List[str]] = Field(
        None, description="数据域列表(可选,空=全部)"
    )
    granularities: Optional[List[str]] = Field(
        None, description="粒度列表(可选,空=全部)"
    )
    since_hours: Optional[int] = Field(
        None, description="只处理最近N小时的文件"
    )
    limit: int = Field(100, description="最多处理N个文件", ge=1, le=1000)
    only_with_template: bool = Field(True, description="只处理有模板的文件")
    allow_quarantine: bool = Field(True, description="允许隔离错误数据")


class SingleAutoIngestRequest(BaseModel):
    """单文件自动入库请求"""

    file_id: int = Field(..., description="文件ID")
    only_with_template: bool = Field(True, description="只处理有模板的文件")
    allow_quarantine: bool = Field(True, description="允许隔离错误数据")


class ClearDataRequest(BaseModel):
    """数据库清理请求"""

    confirm: bool = Field(True, description="必须显式确认")
