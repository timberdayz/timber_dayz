"""
数据备份与恢复相关的Pydantic Schemas

v4.20.0: 系统管理模块API实现
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator


# ==================== 备份相关 ====================

class BackupCreateRequest(BaseModel):
    """创建备份请求"""
    backup_type: str = Field("full", description="备份类型（full 或 incremental）")
    description: Optional[str] = Field(None, max_length=500, description="备份描述（最多500字符）")
    
    @field_validator('backup_type')
    @classmethod
    def validate_backup_type(cls, v):
        if v not in ['full', 'incremental']:
            raise ValueError('备份类型必须是 full 或 incremental')
        return v


class BackupResponse(BaseModel):
    """备份响应模型"""
    id: int
    backup_type: str
    backup_path: str
    backup_size: int
    checksum: Optional[str] = None
    status: str
    description: Optional[str] = None
    created_by: Optional[int] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


class BackupListResponse(BaseModel):
    """备份列表响应（分页）"""
    data: List[BackupResponse]
    page: int
    page_size: int
    total: int
    total_pages: int


class BackupFilterRequest(BaseModel):
    """备份筛选请求"""
    backup_type: Optional[str] = Field(None, description="备份类型（full 或 incremental）")
    status: Optional[str] = Field(None, description="备份状态（pending/completed/failed）")
    start_time: Optional[datetime] = Field(None, description="开始时间")
    end_time: Optional[datetime] = Field(None, description="结束时间")
    page: int = Field(1, ge=1, description="页码（1-based）")
    page_size: int = Field(20, ge=1, le=100, description="每页条数（最大100）")


# ==================== 恢复相关 ====================

class RestoreRequest(BaseModel):
    """恢复请求"""
    confirmed: bool = Field(True, description="二次确认标志（必须为 True）")
    confirmed_by: List[int] = Field(..., min_length=2, description="确认的管理员 ID 列表（至少 2 个不同的管理员 ID）")
    force_outside_window: bool = Field(False, description="是否在维护窗口外强制执行（默认 False）")
    reason: Optional[str] = Field(None, max_length=500, description="恢复原因说明（可选，最多 500 字符）")
    
    @field_validator('confirmed')
    @classmethod
    def validate_confirmed(cls, v):
        if not v:
            raise ValueError('恢复操作必须明确确认（confirmed 必须为 True）')
        return v
    
    @field_validator('confirmed_by')
    @classmethod
    def validate_confirmed_by(cls, v):
        if len(v) < 2:
            raise ValueError('恢复操作需要至少 2 名管理员确认')
        if len(set(v)) != len(v):
            raise ValueError('确认的管理员 ID 必须不同')
        return v


class RestoreResponse(BaseModel):
    """恢复响应模型"""
    backup_id: int
    status: str  # pending/completed/failed
    emergency_backup_id: Optional[int] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    message: str


# ==================== 自动备份配置 ====================

class AutoBackupConfigResponse(BaseModel):
    """自动备份配置响应模型"""
    enabled: bool = Field(description="是否启用自动备份")
    schedule: str = Field(description="备份计划（cron 表达式）")
    backup_type: str = Field(description="备份类型（full 或 incremental）")
    retention_days: int = Field(description="保留天数")
    updated_at: Optional[datetime] = Field(None, description="更新时间")
    updated_by: Optional[int] = Field(None, description="更新人ID")


class AutoBackupConfigUpdate(BaseModel):
    """自动备份配置更新请求"""
    enabled: bool = Field(False, description="是否启用自动备份")
    schedule: str = Field("0 2 * * *", description="备份计划（cron 表达式，默认每天凌晨2点）")
    backup_type: str = Field("full", description="备份类型（full 或 incremental）")
    retention_days: int = Field(30, ge=1, le=365, description="保留天数（1-365）")
    
    @field_validator('backup_type')
    @classmethod
    def validate_backup_type(cls, v):
        if v not in ['full', 'incremental']:
            raise ValueError('备份类型必须是 full 或 incremental')
        return v
