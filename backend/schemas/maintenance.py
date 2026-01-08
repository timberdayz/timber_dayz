"""
系统维护相关的Pydantic Schemas
用于缓存清理、数据清理、系统升级等API

v4.20.0: 系统管理模块API实现
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, field_validator


# ==================== 缓存清理 ====================

class CacheClearRequest(BaseModel):
    """缓存清理请求"""
    cache_type: str = Field("all", description="缓存类型（all/redis/app）")
    pattern: Optional[str] = Field(None, description="缓存键模式（仅用于redis类型，如 'prefix:*'）")
    
    @field_validator('cache_type')
    @classmethod
    def validate_cache_type(cls, v):
        if v not in ['all', 'redis', 'app']:
            raise ValueError('缓存类型必须是 all、redis 或 app')
        return v


class CacheClearResponse(BaseModel):
    """缓存清理响应模型"""
    cache_type: str
    cleared_keys: int = Field(description="清理的键数量")
    cleared_memory: Optional[int] = Field(None, description="释放的内存（字节）")
    message: str


class CacheStatusResponse(BaseModel):
    """缓存状态响应模型"""
    redis_connected: bool = Field(description="Redis连接状态")
    redis_memory_used: Optional[int] = Field(None, description="Redis内存使用（字节）")
    redis_keys_count: Optional[int] = Field(None, description="Redis键数量")
    app_cache_size: Optional[int] = Field(None, description="应用缓存大小（键数量）")


# ==================== 数据清理 ====================

class DataCleanRequest(BaseModel):
    """数据清理请求"""
    clean_type: str = Field(..., description="清理类型（system_logs/task_logs/temp_files/staging_data）")
    retention_days: int = Field(30, ge=1, le=365, description="保留天数（1-365）")
    confirmed: bool = Field(True, description="二次确认标志（必须为 True）")
    
    @field_validator('clean_type')
    @classmethod
    def validate_clean_type(cls, v):
        allowed_types = ['system_logs', 'task_logs', 'temp_files', 'staging_data']
        if v not in allowed_types:
            raise ValueError(f'清理类型必须是 {", ".join(allowed_types)} 之一')
        return v
    
    @field_validator('confirmed')
    @classmethod
    def validate_confirmed(cls, v):
        if not v:
            raise ValueError('数据清理操作必须明确确认（confirmed 必须为 True）')
        return v


class DataCleanResponse(BaseModel):
    """数据清理响应模型"""
    clean_type: str
    deleted_count: int = Field(description="删除的记录数/文件数")
    freed_space: Optional[int] = Field(None, description="释放的空间（字节）")
    retention_days: int
    message: str


class DataStatusResponse(BaseModel):
    """数据状态响应模型"""
    system_logs_count: int = Field(description="系统日志数量")
    system_logs_size: Optional[int] = Field(None, description="系统日志大小（字节）")
    task_logs_count: int = Field(description="任务日志数量")
    task_logs_size: Optional[int] = Field(None, description="任务日志大小（字节）")
    temp_files_count: int = Field(description="临时文件数量")
    temp_files_size: Optional[int] = Field(None, description="临时文件大小（字节）")
    staging_data_count: int = Field(description="临时表数据数量")
    staging_data_size: Optional[int] = Field(None, description="临时表数据大小（字节）")


# ==================== 系统升级（P3 - 可选） ====================

class UpgradeCheckResponse(BaseModel):
    """升级检查响应模型"""
    current_version: str = Field(description="当前版本")
    latest_version: Optional[str] = Field(None, description="最新版本")
    upgrade_available: bool = Field(description="是否有可用升级")
    release_notes: Optional[str] = Field(None, description="发布说明")
    check_time: datetime = Field(description="检查时间")


class UpgradeRequest(BaseModel):
    """升级请求"""
    target_version: str = Field(..., description="目标版本")
    confirmed: bool = Field(True, description="二次确认标志（必须为 True）")
    confirmed_by: List[int] = Field(..., min_length=2, description="确认的管理员 ID 列表（至少 2 个不同的管理员 ID）")
    skip_backup: bool = Field(False, description="是否跳过自动备份（默认 False，不推荐）")
    
    @field_validator('confirmed')
    @classmethod
    def validate_confirmed(cls, v):
        if not v:
            raise ValueError('升级操作必须明确确认（confirmed 必须为 True）')
        return v
    
    @field_validator('confirmed_by')
    @classmethod
    def validate_confirmed_by(cls, v):
        if len(v) < 2:
            raise ValueError('升级操作需要至少 2 名管理员确认')
        if len(set(v)) != len(v):
            raise ValueError('确认的管理员 ID 必须不同')
        return v


class UpgradeResponse(BaseModel):
    """升级响应模型"""
    target_version: str
    status: str  # pending/completed/failed/rolled_back
    backup_id: Optional[int] = Field(None, description="升级前创建的备份 ID")
    started_at: datetime
    completed_at: Optional[datetime] = None
    message: str
