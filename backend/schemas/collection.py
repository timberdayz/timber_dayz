"""
??????? Pydantic Schemas?
????????????????? API?

v4.18.0: ? backend/routers/collection.py ??? schemas?Contract-First ????
"""

from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TimeSelectionPayload(BaseModel):
    """????????"""

    mode: Literal["preset", "custom", "dynamic"] = Field(..., description="????")
    preset: Optional[Literal["today", "yesterday", "last_7_days", "last_30_days"]] = Field(
        None,
        description="??????",
    )
    strategy: Optional[
        Literal[
            "previous_day",
            "current_week_to_available_day",
            "current_month_to_available_day",
        ]
    ] = Field(None, description="动态时间策略")
    available_after_time: Optional[str] = Field("06:00", description="平台数据可用时间 HH:MM")
    start_date: Optional[str] = Field(None, description="鑷畾涔夊紑濮嬫棩鏈?YYYY-MM-DD")
    end_date: Optional[str] = Field(None, description="鑷畾涔夌粨鏉熸棩鏈?YYYY-MM-DD")
    start_time: Optional[str] = Field("00:00:00", description="鑷畾涔夊紑濮嬫椂闂?HH:MM:SS")
    end_time: Optional[str] = Field("23:59:59", description="鑷畾涔夌粨鏉熸椂闂?HH:MM:SS")

    @model_validator(mode="after")
    def validate_payload_shape(self):
        mode = self.mode
        if mode == "preset":
            if not self.preset:
                raise ValueError("preset time selection requires preset")
            if self.start_date or self.end_date:
                raise ValueError("preset time selection cannot include custom range fields")
            self.start_time = "00:00:00"
            self.end_time = "23:59:59"
            return self

        if mode == "custom":
            if self.preset:
                raise ValueError("custom time selection cannot include preset fields")
            if self.strategy:
                raise ValueError("custom time selection cannot include dynamic strategy")
            if not self.start_date or not self.end_date:
                raise ValueError("custom time selection requires start_date and end_date")
            self.start_time = self.start_time or "00:00:00"
            self.end_time = self.end_time or "23:59:59"
            return self

        if mode == "dynamic":
            if self.preset:
                raise ValueError("dynamic time selection cannot include preset fields")
            if self.start_date or self.end_date:
                raise ValueError("dynamic time selection cannot include custom range fields")
            if not self.strategy:
                raise ValueError("dynamic time selection requires strategy")
            self.available_after_time = self.available_after_time or "06:00"
            self.start_time = "00:00:00"
            self.end_time = "23:59:59"
            return self

        return self


class CollectionConfigShopScopePayload(BaseModel):
    """店铺维度配置输入/输出载荷"""

    shop_account_id: str = Field(..., min_length=1, description="店铺账号ID")
    data_domains: List[str] = Field(default_factory=list, description="该店铺实际采集的数据域")
    sub_domains: Optional[Dict[str, List[str]] | List[str]] = Field(
        None,
        description="按数据域绑定的子类型映射,兼容旧 sub_domains 数组",
    )
    enabled: bool = Field(True, description="该店铺 scope 是否启用")


class CollectionConfigShopScopeResponse(CollectionConfigShopScopePayload):
    id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class CollectionConfigCreate(BaseModel):
    """创建采集配置请求"""

    name: Optional[str] = Field(None, min_length=1, max_length=100, description="配置名称(留空自动生成)")
    platform: str = Field(..., pattern="^(shopee|tiktok|miaoshou)$", description="平台")
    main_account_id: str = Field(..., min_length=1, description="归属主账号ID")
    shop_scopes: List[CollectionConfigShopScopePayload] = Field(
        ...,
        min_length=1,
        description="店铺维度采集配置明细",
    )
    granularity: str = Field("daily", pattern="^(daily|weekly|monthly)$", description="粒度")
    date_range_type: str = Field("yesterday", description="日期范围类型")
    custom_date_start: Optional[date] = Field(None, description="自定义开始日期")
    custom_date_end: Optional[date] = Field(None, description="自定义结束日期")
    time_selection: Optional[TimeSelectionPayload] = Field(None, description="统一时间选择模型")
    execution_mode: Literal["headless", "headed"] = Field("headless", description="默认执行模式")
    schedule_enabled: bool = Field(False, description="是否启用定时")
    schedule_cron: Optional[str] = Field(None, description="Cron表达式")
    retry_count: int = Field(3, ge=0, le=10, description="重试次数")


class CollectionConfigUpdate(BaseModel):
    """更新采集配置请求"""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    main_account_id: Optional[str] = Field(None, min_length=1)
    shop_scopes: Optional[List[CollectionConfigShopScopePayload]] = None
    granularity: Optional[str] = None
    date_range_type: Optional[str] = None
    custom_date_start: Optional[date] = None
    custom_date_end: Optional[date] = None
    time_selection: Optional[TimeSelectionPayload] = Field(None, description="统一时间选择模型")
    execution_mode: Optional[Literal["headless", "headed"]] = Field(None, description="默认执行模式")
    schedule_enabled: Optional[bool] = None
    schedule_cron: Optional[str] = None
    retry_count: Optional[int] = None
    is_active: Optional[bool] = None
    batch_key: Optional[str] = Field(None, min_length=1, max_length=32)
    batch_status: Optional[Literal["draft", "active", "completed", "disabled"]] = None
    batch_note: Optional[str] = Field(None, max_length=500)


class CollectionConfigResponse(BaseModel):
    """采集配置响应"""

    id: int
    name: str
    platform: str
    main_account_id: str
    main_account_name: Optional[str] = None
    account_ids: List[str] = Field(default_factory=list, description="兼容旧摘要字段")
    data_domains: List[str] = Field(default_factory=list, description="兼容旧摘要字段")
    sub_domains: Optional[Dict[str, List[str]] | List[str]] = Field(
        None,
        description="兼容旧摘要字段",
    )
    shop_scopes: List[CollectionConfigShopScopeResponse] = Field(default_factory=list)
    granularity: str
    date_range_type: str
    custom_date_start: Optional[date]
    custom_date_end: Optional[date]
    time_selection: Optional[TimeSelectionPayload] = None
    time_window_preview: Optional[Dict[str, Any]] = None
    execution_mode: Literal["headless", "headed"] = "headless"
    schedule_enabled: bool
    schedule_cron: Optional[str]
    retry_count: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str]

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def hydrate_time_selection(self):
        if self.time_selection is None:
            if str(self.date_range_type or "").startswith("dynamic:"):
                payload = {
                    "mode": "dynamic",
                    "strategy": str(self.date_range_type).split(":", 1)[1],
                }
                self.time_selection = TimeSelectionPayload.model_validate(payload)
                return self
            mode = "custom" if self.date_range_type == "custom" else "preset"
            payload = {"mode": mode}
            if mode == "preset" and self.date_range_type:
                payload["preset"] = self.date_range_type
            elif mode == "custom" and self.custom_date_start and self.custom_date_end:
                payload["start_date"] = self.custom_date_start.isoformat()
                payload["end_date"] = self.custom_date_end.isoformat()
            else:
                return self
            self.time_selection = TimeSelectionPayload.model_validate(payload)
        return self


class CollectionTemplateShopScopePayload(BaseModel):
    shop_account_id: str = Field(..., min_length=1)
    data_domains: List[str] = Field(default_factory=list)
    sub_domains: Optional[Dict[str, List[str]] | List[str]] = None
    enabled: bool = True


class CollectionTemplateShopScopeResponse(CollectionTemplateShopScopePayload):
    model_config = ConfigDict(from_attributes=True)


class CollectionConfigTemplateCreate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    platform: str = Field(..., pattern="^(shopee|tiktok|miaoshou)$")
    main_account_id: str = Field(..., min_length=1)
    granularity: Literal["daily", "weekly", "monthly"]
    default_date_range_type: str = Field(...)
    default_execution_mode: Literal["headless", "headed"] = "headless"
    default_schedule_enabled: bool = False
    default_schedule_cron: Optional[str] = None
    default_retry_count: int = Field(3, ge=0, le=10)
    default_shop_scopes: List[CollectionTemplateShopScopePayload] = Field(..., min_length=1)


class CollectionConfigTemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    default_date_range_type: Optional[str] = None
    default_execution_mode: Optional[Literal["headless", "headed"]] = None
    default_schedule_enabled: Optional[bool] = None
    default_schedule_cron: Optional[str] = None
    default_retry_count: Optional[int] = Field(None, ge=0, le=10)
    default_shop_scopes: Optional[List[CollectionTemplateShopScopePayload]] = None
    is_active: Optional[bool] = None


class CollectionConfigBatchCreate(BaseModel):
    batch_key: str = Field(..., min_length=1, max_length=32)
    time_selection: TimeSelectionPayload
    status: Literal["draft", "active", "completed", "disabled"] = "draft"
    note: Optional[str] = Field(None, max_length=500)
    shop_overrides: List[CollectionTemplateShopScopePayload] = Field(default_factory=list)


class CollectionConfigFutureBatchCreateRequest(BaseModel):
    periods: int = Field(..., ge=1, le=12)


class CollectionConfigFutureBatchCreateResponse(BaseModel):
    created_batches: List["CollectionConfigBatchResponse"]
    skipped_batch_keys: List[str] = Field(default_factory=list)


class CollectionConfigBulkAdvanceRequest(BaseModel):
    granularity: Literal["daily", "weekly", "monthly"]
    platform: Optional[str] = None
    main_account_ids: List[str] = Field(default_factory=list)


class CollectionConfigBulkAdvanceResponse(BaseModel):
    affected_config_ids: List[int] = Field(default_factory=list)
    skipped_config_ids: List[int] = Field(default_factory=list)


class CollectionConfigBulkRunRequest(BaseModel):
    granularity: Literal["daily", "weekly", "monthly"]
    platform: Optional[str] = None
    main_account_ids: List[str] = Field(default_factory=list)


class CollectionConfigBulkRunResponse(BaseModel):
    created_run_count: int = 0
    skipped_config_count: int = 0
    runs: List["CollectionConfigRunResponse"] = Field(default_factory=list)
    skipped_config_ids: List[int] = Field(default_factory=list)


class CollectionConfigTemplateBackfillResponse(BaseModel):
    created_template_count: int = 0
    attached_batch_count: int = 0
    skipped_config_ids: List[int] = Field(default_factory=list)


class CollectionConfigBatchResponse(CollectionConfigResponse):
    template_id: Optional[int] = None
    batch_key: Optional[str] = None
    status: Literal["draft", "active", "completed", "disabled"] = "draft"
    note: Optional[str] = None
    shop_overrides: List[CollectionTemplateShopScopeResponse] = Field(default_factory=list)
    missing_template_shop_scope_ids: List[str] = Field(default_factory=list)
    stale_template_shop_scope_ids: List[str] = Field(default_factory=list)


CollectionConfigFutureBatchCreateResponse.model_rebuild()


class CollectionConfigTemplateSummaryResponse(BaseModel):
    id: int
    name: Optional[str] = None
    platform: str
    main_account_id: str
    granularity: Literal["daily", "weekly", "monthly"]
    default_date_range_type: str
    default_execution_mode: Literal["headless", "headed"] = "headless"
    default_schedule_enabled: bool = False
    default_schedule_cron: Optional[str] = None
    default_retry_count: int = 3
    default_shop_scopes: List[CollectionTemplateShopScopeResponse] = Field(default_factory=list)
    active_shop_count: int = 0
    template_shop_count: int = 0
    missing_shop_scope_ids: List[str] = Field(default_factory=list)
    stale_shop_scope_ids: List[str] = Field(default_factory=list)
    batch_count: int = 0
    batches: List[CollectionConfigBatchResponse] = Field(default_factory=list)
    is_active: bool = True
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskCreateRequest(BaseModel):
    """创建采集任务请求"""

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
    """???????????????????OTP?????????"""

    captcha_code: Optional[str] = Field(None, description="???????????")
    otp: Optional[str] = Field(None, description="??/??????OTP?")
    manual_completed: Optional[bool] = Field(None, description="?????????????????")

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
    """????"""

class TaskResponse(BaseModel):
    """任务响应"""

    id: int
    task_id: str
    platform: str
    account: str
    status: str
    progress: int
    current_step: Optional[str]
    files_collected: int
    trigger_type: str
    config_id: Optional[int] = None
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
    execution_mode: Literal["headless", "headed"] = "headless"
    error_message: Optional[str]
    duration_seconds: Optional[int]
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = Field(None, description="任务实际开始执行时间")
    completed_at: Optional[datetime] = Field(None, description="任务结束时间")
    verification_type: Optional[str] = Field(None, description="验证码类型")
    verification_screenshot: Optional[str] = Field(None, description="验证码截图路径或URL")
    verification_id: Optional[str] = Field(None, description="验证码实例ID")
    verification_message: Optional[str] = Field(None, description="验证码提示信息")
    verification_expires_at: Optional[str] = Field(None, description="验证码过期时间")
    verification_attempt_count: int = Field(0, description="验证码提交次数")
    verification_input_mode: Optional[str] = Field(None, description="验证码交互方式")
    actual_execution_mode: Optional[Literal["headless", "headed"]] = None
    runtime_session_mode: Optional[str] = None
    login_gate_ready: Optional[bool] = None
    login_gate_reason: Optional[str] = None
    login_gate_url: Optional[str] = None
    runtime_strategy_reason: Optional[str] = None
    session_source: Optional[str] = None
    runtime_metadata: Optional[Dict[str, Any]] = None


class CollectionConfigRunResponse(BaseModel):
    id: int
    run_id: str
    config_id: int
    platform: str
    main_account_id: str
    trigger_type: str
    status: str
    priority: int
    scheduled_for: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    task_count: int = 0
    active_task_count: int = 0
    terminal_task_count: int = 0
    last_task_status: Optional[str] = None
    can_cancel: bool = False
    status_reason: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


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
    """??????"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    level: str
    message: str
    details: Optional[Dict[str, Any]]
    timestamp: datetime


class CollectionAccountResponse(BaseModel):
    """???????????????"""

    id: str
    name: str
    platform: str
    shop_id: Optional[str] = None
    shop_region: Optional[str] = None
    status: str = "active"
    shop_type: Optional[str] = None
    main_account_id: Optional[str] = None
    main_account_name: Optional[str] = None
    capabilities: Optional[Dict[str, bool]] = None


class CollectionAccountGroupRegionResponse(BaseModel):
    shop_region: Optional[str] = None
    shops: List[CollectionAccountResponse]


class CollectionAccountGroupResponse(BaseModel):
    platform: str
    main_account_id: str
    main_account_name: Optional[str] = None
    regions: List[CollectionAccountGroupRegionResponse]


class CollectionConfigCoverageItem(BaseModel):
    shop_account_id: str
    shop_account_name: str
    platform: str
    main_account_id: str
    main_account_name: Optional[str] = None
    shop_region: Optional[str] = None
    shop_type: Optional[str] = None
    daily_covered: bool
    weekly_covered: bool
    monthly_covered: bool
    missing_granularities: List[str]
    partial_covered: bool
    fully_covered: bool
    is_partially_covered: bool = False
    recommended_domains: List[str] = Field(default_factory=list)


class CollectionConfigCoverageSummary(BaseModel):
    total_shop_count: int
    fully_covered_count: int
    partial_covered_count: int
    daily_covered_count: int = 0
    weekly_covered_count: int = 0
    monthly_covered_count: int = 0
    daily_missing_count: int
    weekly_missing_count: int
    monthly_missing_count: int


class CollectionConfigCoverageResponse(BaseModel):
    summary: CollectionConfigCoverageSummary
    items: List[CollectionConfigCoverageItem]


class CollectionConfigBatchRemediationRequest(BaseModel):
    shop_account_ids: List[str] = Field(..., min_length=1)
    granularity: Literal["daily", "weekly", "monthly"]
    platform: Optional[str] = None


class CollectionConfigBatchRemediationCreatedItem(BaseModel):
    config_id: int
    config_name: str
    shop_account_id: str
    granularity: Literal["daily", "weekly", "monthly"]


class CollectionConfigBatchRemediationSkippedItem(BaseModel):
    shop_account_id: str
    reason: str


class CollectionConfigBatchRemediationResponse(BaseModel):
    granularity: Literal["daily", "weekly", "monthly"]
    created_configs: List[CollectionConfigBatchRemediationCreatedItem]
    skipped_shops: List[CollectionConfigBatchRemediationSkippedItem]


class TaskHistoryResponse(BaseModel):
    """????????"""

    data: List[TaskResponse]
    total: int
    page: int
    page_size: int
    pages: int


class DailyStats(BaseModel):
    """????"""

    date: date
    total: int
    completed: int
    failed: int
    success_rate: float


class TaskStatsResponse(BaseModel):
    """??????"""

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


class GranularityScheduleUpdateRequest(BaseModel):
    schedule_enabled: bool = Field(..., description="是否启用该粒度统一定时")


class GranularityScheduleResponse(BaseModel):
    granularity: Literal["daily", "weekly", "monthly"]
    enabled: bool
    cron: Optional[str] = None
    description: str
    affected_config_count: int = 0
    enabled_config_count: int = 0
    is_mixed: bool = False


class CronValidateRequest(BaseModel):
    """Cron 验证请求"""

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
    """Cron 表达式验证响应"""

    valid: bool
    error: Optional[str] = None
    next_run_times: Optional[List[datetime]] = None
    description: Optional[str] = None


class CronPresetItem(BaseModel):
    """Cron 预设项"""

    name: str
    cron: str
    description: str


class CronPresetsResponse(BaseModel):
    """Cron 预设列表响应"""

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


class ActiveConfigRunStatus(BaseModel):
    id: int
    run_id: str
    config_id: int
    main_account_id: str
    platform: str
    trigger_type: str
    status: str
    started_at: Optional[datetime] = None


class HealthCheckResponse(BaseModel):
    """健康检查响应"""

    status: str
    running_tasks: int
    queued_tasks: int
    running_config_runs: int = 0
    queued_config_runs: int = 0
    active_config_run: Optional[ActiveConfigRunStatus] = None
    browser_pool: BrowserPoolStatus
    database: str
    scheduler: str
    queue_runner: str = "unknown"
    leader_lock: str = "unknown"
    runtime_mode: str = "unknown"
    deployment_role: str = "unknown"
    can_consume_queue: bool = False
