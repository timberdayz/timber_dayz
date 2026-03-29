"""
数据采集相关的 Pydantic Schemas
用于采集配置、任务管理、账号管理等 API

v4.18.0: 从 backend/routers/collection.py 迁移到 schemas (Contract-First 架构)
"""

from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class CollectionConfigCreate(BaseModel):
    """创建采集配置请求(v4.7.0)"""

    name: Optional[str] = Field(None, min_length=1, max_length=100, description="配置名称(留空自动生成)")
    platform: str = Field(..., pattern="^(shopee|tiktok|miaoshou)$", description="平台")
    account_ids: List[str] = Field(..., description="账号ID列表(空数组表示所有活跃账号)")
    data_domains: List[str] = Field(..., min_length=1, description="数据域列表")
    sub_domains: Optional[Dict[str, List[str]] | List[str]] = Field(
        None,
        description="按数据域绑定的子类型映射,兼容旧 sub_domains 数组",
    )
    granularity: str = Field("daily", pattern="^(daily|weekly|monthly)$", description="粒度")
    date_range_type: str = Field("yesterday", description="日期范围类型")
    custom_date_start: Optional[date] = Field(None, description="自定义开始日期")
    custom_date_end: Optional[date] = Field(None, description="自定义结束日期")
    time_selection: Optional[TimeSelectionPayload] = Field(None, description="统一时间选择模型")
    schedule_enabled: bool = Field(False, description="是否启用定时")
    schedule_cron: Optional[str] = Field(None, description="Cron表达式")
    retry_count: int = Field(3, ge=0, le=10, description="重试次数")


class CollectionConfigUpdate(BaseModel):
    """更新采集配置请求(v4.7.0)"""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    account_ids: Optional[List[str]] = None
    data_domains: Optional[List[str]] = None
    sub_domains: Optional[Dict[str, List[str]] | List[str]] = Field(
        None,
        description="按数据域绑定的子类型映射,兼容旧 sub_domains 数组",
    )
    granularity: Optional[str] = None
    date_range_type: Optional[str] = None
    custom_date_start: Optional[date] = None
    custom_date_end: Optional[date] = None
    time_selection: Optional[TimeSelectionPayload] = Field(None, description="统一时间选择模型")
    schedule_enabled: Optional[bool] = None
    schedule_cron: Optional[str] = None
    retry_count: Optional[int] = None
    is_active: Optional[bool] = None


class CollectionConfigResponse(BaseModel):
    """采集配置响应(v4.7.0)"""

    id: int
    name: str
    platform: str
    account_ids: List[str]
    data_domains: List[str]
    sub_domains: Optional[Dict[str, List[str]] | List[str]] = Field(
        None,
        description="按数据域绑定的子类型映射,兼容旧 sub_domains 数组",
    )
    granularity: str
    date_range_type: str
    custom_date_start: Optional[date]
    custom_date_end: Optional[date]
    time_selection: Optional[TimeSelectionPayload] = None
    schedule_enabled: bool
    schedule_cron: Optional[str]
    retry_count: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class TaskCreateRequest(BaseModel):
    """创建采集任务请求(v4.7.0 + Phase 9.1)"""

    platform: str = Field(..., pattern="^(shopee|tiktok|miaoshou)$", description="平台")
    account_id: str = Field(..., description="账号ID")
    data_domains: List[str] = Field(..., min_length=1, description="数据域列表")
    sub_domains: Optional[Dict[str, List[str]] | List[str]] = Field(
        None,
        description="按数据域绑定的子类型映射,兼容旧 sub_domains 数组",
    )
    granularity: Optional[str] = Field("daily", pattern="^(daily|weekly|monthly)$", description="粒度")
    date_range: Optional[Dict[str, str]] = Field(
        None,
        description="日期范围 {'start': 'YYYY-MM-DD', 'end': 'YYYY-MM-DD'}",
    )
    time_selection: Optional[TimeSelectionPayload] = Field(None, description="统一时间选择模型")
    config_id: Optional[int] = Field(None, description="关联配置ID")
    debug_mode: bool = Field(False, description="调试模式(临时有头浏览器)")
    parallel_mode: bool = Field(False, description="并行执行模式(多域并行采集)")
    max_parallel: int = Field(3, ge=1, le=5, description="最大并发数(1-5)")


class ResumeTaskRequest(BaseModel):
    """继续任务请求(验证码恢复: 提交验证码、OTP、或手动完成信号)"""

    captcha_code: Optional[str] = Field(None, description="图形验证码(人工输入)")
    otp: Optional[str] = Field(None, description="短信/邮箱验证码(OTP)")
    manual_completed: Optional[bool] = Field(None, description="用户已手动完成滑块等验证, 请求继续")

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


class TaskResponse(BaseModel):
    """任务响应(v4.7.0)"""

    id: int
    task_id: str
    platform: str
    account: str
    status: str
    progress: int
    current_step: Optional[str]
    files_collected: int
    trigger_type: str
    data_domains: Optional[List[str]]
    sub_domains: Optional[Dict[str, List[str]] | List[str]] = Field(
        None,
        description="按数据域绑定的子类型映射,兼容旧 sub_domains 数组",
    )
    granularity: Optional[str]
    date_range: Optional[Dict[str, str]]
    time_selection: Optional[TimeSelectionPayload] = None
    total_domains: int = Field(0, description="总数据域数量")
    completed_domains: Optional[List[str]] = Field(None, description="已完成的数据域")
    failed_domains: Optional[List[Dict[str, str]]] = Field(None, description="失败的数据域")
    current_domain: Optional[str] = Field(None, description="当前数据域")
    debug_mode: bool = Field(False, description="调试模式")
    error_message: Optional[str]
    duration_seconds: Optional[int]
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = Field(None, description="任务实际开始执行时间")
    completed_at: Optional[datetime] = Field(None, description="任务结束时间")
    verification_type: Optional[str] = Field(None, description="验证码类型(如 graphical_captcha/otp/slide_captcha)")
    verification_screenshot: Optional[str] = Field(None, description="验证码截图路径或URL")
    verification_id: Optional[str] = Field(None, description="验证码实例ID")
    verification_message: Optional[str] = Field(None, description="验证码提示信息")
    verification_expires_at: Optional[str] = Field(None, description="验证码过期时间")
    verification_attempt_count: int = Field(0, description="验证码提交次数")
    verification_input_mode: Optional[str] = Field(None, description="验证码交互方式(code_entry/manual_continue)")


class CollectionVerificationItem(BaseModel):
    task_id: str
    account_id: str
    verification_id: str
    platform: str
    status: str
    verification_type: str
    verification_message: Optional[str] = None
    verification_screenshot: Optional[str] = None
    verification_expires_at: Optional[str] = None
    verification_attempt_count: int = 0
    verification_input_mode: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class TaskLogResponse(BaseModel):
    """任务日志响应"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    level: str
    message: str
    details: Optional[Dict[str, Any]]
    timestamp: datetime


class CollectionAccountResponse(BaseModel):
    """账号响应(脱敏,用于采集模块)"""

    id: str
    name: str
    platform: str
    shop_id: Optional[str] = None
    status: str = "active"
    shop_type: Optional[str] = None
    capabilities: Optional[Dict[str, bool]] = None


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
