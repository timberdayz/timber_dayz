"""
数据同步相关的Pydantic Schemas
用于数据同步API的请求和响应模型

v4.18.0: 从backend/routers/data_sync.py迁移到schemas（Contract-First架构）
"""

from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field


class SingleFileSyncRequest(BaseModel):
    """单文件同步请求"""
    file_id: int = Field(..., description="文件ID")
    only_with_template: bool = Field(True, description="只处理有模板的文件")
    allow_quarantine: bool = Field(True, description="允许隔离错误数据")
    use_template_header_row: bool = Field(True, description="使用模板表头行（严格模式，不自动检测）")
    priority: int = Field(5, description="任务优先级（1-10，10最高，默认5）", ge=1, le=10)  # ⭐ Phase 4: 任务优先级


class BatchSyncRequest(BaseModel):
    """批量同步请求（基于筛选条件）"""
    platform: Optional[str] = Field(None, description="平台代码；传入'*'或省略表示全部平台")
    domains: Optional[List[str]] = Field(None, description="数据域列表（可选，空=全部）")
    granularities: Optional[List[str]] = Field(None, description="粒度列表（可选，空=全部）")
    since_hours: Optional[int] = Field(None, description="只处理最近N小时的文件")
    limit: int = Field(100, description="最多处理N个文件", ge=1, le=1000)
    only_with_template: bool = Field(True, description="只处理有模板的文件")
    allow_quarantine: bool = Field(True, description="允许隔离错误数据")
    priority: int = Field(5, description="任务优先级（1-10，10最高，默认5）", ge=1, le=10)  # ⭐ Phase 4: 任务优先级


class BatchSyncByFileIdsRequest(BaseModel):
    """批量同步请求（基于文件ID列表）"""
    file_ids: List[int] = Field(..., description="文件ID列表", min_length=1, max_length=1000)
    only_with_template: bool = Field(True, description="只处理有模板的文件")
    allow_quarantine: bool = Field(True, description="允许隔离错误数据")
    use_template_header_row: bool = Field(True, description="使用模板表头行（严格模式）")
    priority: int = Field(5, description="任务优先级（1-10，10最高，默认5）", ge=1, le=10)  # ⭐ Phase 4: 任务优先级


class DataSyncFilePreviewRequest(BaseModel):
    """数据同步的文件预览请求（使用file_id）"""
    file_id: int = Field(..., description="文件ID")
    header_row: int = Field(0, description="表头行（0-based，0=Excel第1行）", ge=0, le=100)


class FileListRequest(BaseModel):
    """文件列表请求（查询参数）"""
    platform: Optional[str] = Field(None, description="平台代码")


# ⭐ Phase 1.4.3: 任务状态管理 Schemas
class CeleryTaskStatusResponse(BaseModel):
    """Celery 任务状态响应"""
    celery_task_id: str = Field(..., description="Celery 任务ID")
    state: str = Field(..., description="任务状态（PENDING/STARTED/SUCCESS/FAILURE/REVOKED/RETRY）")
    ready: bool = Field(..., description="任务是否已完成（成功或失败）")
    successful: Optional[bool] = Field(None, description="任务是否成功（仅当ready=True时有效）")
    result: Optional[Any] = Field(None, description="任务结果（仅当ready=True且successful=True时有效）")
    traceback: Optional[str] = Field(None, description="错误堆栈（仅当ready=True且successful=False时有效）")
    info: Optional[Dict[str, Any]] = Field(None, description="任务详细信息")
    
    class Config:
        from_attributes = True


class CancelTaskResponse(BaseModel):
    """取消任务响应"""
    celery_task_id: str = Field(..., description="Celery 任务ID")
    message: str = Field(..., description="操作结果消息")
    revoked: bool = Field(..., description="任务是否已成功撤销")
    
    class Config:
        from_attributes = True


class RetryTaskResponse(BaseModel):
    """重试任务响应"""
    original_celery_task_id: str = Field(..., description="原始 Celery 任务ID")
    new_celery_task_id: Optional[str] = Field(None, description="新 Celery 任务ID（如果创建了新任务）")
    new_task_id: Optional[str] = Field(None, description="新任务ID（如果创建了新任务）")
    message: str = Field(..., description="操作结果消息")
    
    class Config:
        from_attributes = True

