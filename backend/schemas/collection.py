"""
数据采集相关的Pydantic Schemas
用于采集配置、任务管理、账号管理等API

v4.18.0: 从backend/routers/collection.py迁移到schemas（Contract-First架构）
"""

from datetime import datetime, date
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


# ==================== 采集配置 ====================

class CollectionConfigCreate(BaseModel):
    """创建采集配置请求（v4.7.0）"""
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="配置名称（留空自动生成）")
    platform: str = Field(..., pattern="^(shopee|tiktok|miaoshou)$", description="平台")
    account_ids: List[str] = Field(..., description="账号ID列表（空数组表示所有活跃账号）")
    data_domains: List[str] = Field(..., min_length=1, description="数据域列表")
    sub_domains: Optional[List[str]] = Field(None, description="子域数组（v4.7.0）")
    granularity: str = Field("daily", pattern="^(daily|weekly|monthly)$", description="粒度")
    date_range_type: str = Field("yesterday", description="日期范围类型")
    custom_date_start: Optional[date] = Field(None, description="自定义开始日期")
    custom_date_end: Optional[date] = Field(None, description="自定义结束日期")
    schedule_enabled: bool = Field(False, description="是否启用定时")
    schedule_cron: Optional[str] = Field(None, description="Cron表达式")
    retry_count: int = Field(3, ge=0, le=10, description="重试次数")


class CollectionConfigUpdate(BaseModel):
    """更新采集配置请求（v4.7.0）"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    account_ids: Optional[List[str]] = None
    data_domains: Optional[List[str]] = None
    sub_domains: Optional[List[str]] = Field(None, description="子域数组（v4.7.0）")
    granularity: Optional[str] = None
    date_range_type: Optional[str] = None
    custom_date_start: Optional[date] = None
    custom_date_end: Optional[date] = None
    schedule_enabled: Optional[bool] = None
    schedule_cron: Optional[str] = None
    retry_count: Optional[int] = None
    is_active: Optional[bool] = None


class CollectionConfigResponse(BaseModel):
    """采集配置响应（v4.7.0）"""
    id: int
    name: str
    platform: str
    account_ids: List[str]
    data_domains: List[str]
    sub_domains: Optional[List[str]] = Field(None, description="子域数组（v4.7.0）")
    granularity: str
    date_range_type: str
    custom_date_start: Optional[date]
    custom_date_end: Optional[date]
    schedule_enabled: bool
    schedule_cron: Optional[str]
    retry_count: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str]
    
    model_config = ConfigDict(from_attributes=True)


# ==================== 采集任务 ====================

class TaskCreateRequest(BaseModel):
    """创建采集任务请求（v4.7.0 + Phase 9.1）"""
    platform: str = Field(..., pattern="^(shopee|tiktok|miaoshou)$", description="平台")
    account_id: str = Field(..., description="账号ID")
    data_domains: List[str] = Field(..., min_length=1, description="数据域列表")
    sub_domains: Optional[List[str]] = Field(None, description="子域数组（v4.7.0）")
    granularity: str = Field("daily", pattern="^(daily|weekly|monthly)$", description="粒度")
    date_range: Dict[str, str] = Field(..., description="日期范围 {'start': 'YYYY-MM-DD', 'end': 'YYYY-MM-DD'}")
    config_id: Optional[int] = Field(None, description="关联配置ID")
    debug_mode: bool = Field(False, description="调试模式（临时有头浏览器）")
    parallel_mode: bool = Field(False, description="[*] Phase 9.1: 并行执行模式（多域并行采集）")
    max_parallel: int = Field(3, ge=1, le=5, description="[*] Phase 9.1: 最大并发数（1-5）")


class TaskResponse(BaseModel):
    """任务响应（v4.7.0）"""
    id: int
    task_id: str
    platform: str
    account: str
    status: str  # v4.7.0: 新增 partial_success 状态
    progress: int
    current_step: Optional[str]
    files_collected: int
    trigger_type: str
    data_domains: Optional[List[str]]
    sub_domains: Optional[List[str]] = Field(None, description="子域数组（v4.7.0）")
    granularity: Optional[str]
    date_range: Optional[Dict[str, str]]
    # v4.7.0 任务粒度优化字段
    total_domains: int = Field(0, description="总数据域数量")
    completed_domains: Optional[List[str]] = Field(None, description="已完成的数据域")
    failed_domains: Optional[List[Dict[str, str]]] = Field(None, description="失败的数据域")
    current_domain: Optional[str] = Field(None, description="当前数据域")
    debug_mode: bool = Field(False, description="调试模式")
    # 其他字段
    error_message: Optional[str]
    duration_seconds: Optional[int]
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class TaskLogResponse(BaseModel):
    """任务日志响应"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    level: str
    message: str
    details: Optional[Dict[str, Any]]
    timestamp: datetime


# ==================== 账号管理（采集模块专用）====================

class CollectionAccountResponse(BaseModel):
    """账号响应（脱敏，用于采集模块）"""
    id: str
    name: str
    platform: str
    shop_id: Optional[str] = None
    status: str = "active"


# ==================== 历史记录与统计 ====================

class TaskHistoryResponse(BaseModel):
    """任务历史分页响应"""
    data: List[TaskResponse]
    total: int
    page: int
    page_size: int
    pages: int


class DailyStats(BaseModel):
    """每日统计"""
    date: date
    total: int
    completed: int
    failed: int
    success_rate: float


class TaskStatsResponse(BaseModel):
    """任务统计响应"""
    total_tasks: int
    completed: int
    failed: int
    running: int
    queued: int
    success_rate: float
    daily_stats: List[DailyStats]


# ==================== 定时调度 ====================

class ScheduleUpdateRequest(BaseModel):
    """调度更新请求"""
    schedule_enabled: bool = Field(..., description="是否启用定时")
    schedule_cron: Optional[str] = Field(None, description="Cron表达式")


class CronValidateRequest(BaseModel):
    """Cron验证请求"""
    cron_expression: str = Field(..., description="Cron表达式")


class ScheduleResponse(BaseModel):
    """定时调度响应"""
    message: str
    config_id: int
    job_id: Optional[str] = None
    next_run_time: Optional[datetime] = None


class ScheduleInfoResponse(BaseModel):
    """定时调度信息响应"""
    enabled: bool
    cron: Optional[str]
    next_run_time: Optional[datetime]
    job_id: Optional[str]


class CronValidationResponse(BaseModel):
    """Cron表达式验证响应"""
    valid: bool
    error: Optional[str] = None
    next_run_times: Optional[List[datetime]] = None
    description: Optional[str] = None


class CronPresetItem(BaseModel):
    """Cron预设项"""
    name: str
    cron: str
    description: str


class CronPresetsResponse(BaseModel):
    """Cron预设列表响应"""
    presets: List[CronPresetItem]


class ScheduledJobInfo(BaseModel):
    """定时任务信息"""
    job_id: str
    name: str
    next_run_time: Optional[datetime]
    trigger: str


class ScheduledJobsResponse(BaseModel):
    """定时任务列表响应"""
    jobs: List[ScheduledJobInfo]
    total: int
    error: Optional[str] = None


# ==================== 健康检查 ====================

class BrowserPoolStatus(BaseModel):
    """浏览器池状态"""
    active: int
    max_allowed: int


class HealthCheckResponse(BaseModel):
    """健康检查响应"""
    status: str
    running_tasks: int
    queued_tasks: int
    browser_pool: BrowserPoolStatus
    database: str
    scheduler: str

