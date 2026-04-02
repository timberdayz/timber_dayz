"""
Backend Pydantic Schemas (Contract-First架构)
所有API请求/响应模型的集中定义

组织原则:
1. 按业务域拆分文件(account, collection, finance等)
2. 每个文件包含该域的所有Pydantic模型
3. 在__init__.py中统一导出
4. router文件只从schemas导入,不自定义模型

v4.18.0: 初始创建,Contract-First迁移计划
"""

# ==================== 账号管理 ====================
from backend.schemas.account import (
    CapabilitiesModel,
    AccountCreate,
    AccountUpdate,
    AccountResponse,
    AccountStats,
    BatchCreateRequest,
)
from backend.schemas.main_account import MainAccountCreate, MainAccountUpdate, MainAccountResponse
from backend.schemas.shop_account import ShopAccountCreate, ShopAccountUpdate, ShopAccountResponse
from backend.schemas.shop_account_alias import ShopAccountAliasCreate, ShopAccountAliasResponse
from backend.schemas.platform_shop_discovery import PlatformShopDiscoveryResponse

# ==================== 通用响应 ====================
from backend.schemas.common import (
    SuccessResponse,
    ErrorResponse,
    PaginationMeta,
    PaginatedResponse,
)

# ==================== 数据采集 ====================
from backend.schemas.collection import (
    CollectionConfigCreate,
    CollectionConfigUpdate,
    CollectionConfigResponse,
    TaskCreateRequest,
    TaskResponse,
    TaskLogResponse,
    CollectionAccountResponse,
    # 历史记录与统计
    TaskHistoryResponse,
    DailyStats,
    TaskStatsResponse,
    # 定时调度
    ScheduleUpdateRequest,
    CronValidateRequest,
    ScheduleResponse,
    ScheduleInfoResponse,
    CronValidationResponse,
    CronPresetItem,
    CronPresetsResponse,
    ScheduledJobInfo,
    ScheduledJobsResponse,
    # 健康检查
    BrowserPoolStatus,
    HealthCheckResponse,
)

# ==================== 字段映射 ====================
# 注意:field_mapping.py不使用Pydantic模型,使用通用响应函数

# ==================== 数据同步 ====================
from backend.schemas.data_sync import (
    SingleFileSyncRequest,
    BatchSyncRequest,
    BatchSyncByFileIdsRequest,
    DataSyncFilePreviewRequest,
    FileListRequest,
)

# ==================== 限流管理 ====================
from backend.schemas.rate_limit import (
    RateLimitEventResponse,
    RateLimitStatsResponse,
    RateLimitAnomalyResponse,
    RateLimitConfigResponse,
    RateLimitInfoResponse,
    RateLimitRuleResponse,
    RateLimitRuleCreate,
    RateLimitRuleUpdate,
    RateLimitRuleListResponse,
)

# ==================== HR 人力/我的收入 ====================
from backend.schemas.hr import (
    MyIncomeResponse,
    IncomeCalculationResponse,
    DepartmentCreate,
    DepartmentUpdate,
    DepartmentResponse,
    PositionCreate,
    PositionUpdate,
    PositionResponse,
    EmployeeCreate,
    EmployeeUpdate,
    EmployeeResponse,
    WorkShiftCreate,
    WorkShiftResponse,
    AttendanceRecordCreate,
    AttendanceRecordUpdate,
    AttendanceRecordResponse,
    LeaveTypeCreate,
    LeaveTypeResponse,
    LeaveRecordCreate,
    LeaveRecordUpdate,
    LeaveRecordResponse,
    OvertimeRecordCreate,
    OvertimeRecordUpdate,
    OvertimeRecordResponse,
    SalaryStructureCreate,
    SalaryStructureResponse,
    PayrollRecordResponse,
    EmployeeTargetCreate,
    EmployeeTargetUpdate,
    EmployeeTargetResponse,
    EmployeePerformanceResponse,
    EmployeeCommissionResponse,
    ShopCommissionResponse,
    EmployeeShopAssignmentCreate,
    EmployeeShopAssignmentUpdate,
    EmployeeShopAssignmentResponse,
    CopyFromPrevMonthBody,
    ShopCommissionConfigUpdate,
    MeProfileUpdate,
)

# ==================== 组件版本管理 ====================
from backend.schemas.component_version import (
    ComponentVersionResponse,
    VersionListResponse,
    VersionRegisterRequest,
    ABTestRequest,
    VersionUpdateRequest,
    BatchRegisterRequest,
    BatchRegisterResult,
    BatchRegisterResponse,
    ComponentTestRequest,
    TestHistoryResponse,
    TestHistoryListResponse,
    TestResumeRequest,
)

# ==================== 通知管理 (v4.19.0) ====================
from backend.schemas.notification import (
    NotificationType,
    NotificationBase,
    NotificationCreate,
    NotificationResponse,
    NotificationListResponse,
    UnreadCountResponse,
    MarkReadRequest,
    MarkReadResponse,
    NotificationDeleteResponse,
    NotificationBatchCreate,
)

# ==================== 配置管理 ====================
from backend.schemas.config import (
    SalesTargetCreate,
    SalesTargetUpdate,
    SalesTargetResponse,
    CampaignTargetCreate,
    CampaignTargetUpdate,
    CampaignTargetResponse,
)

# ==================== 目标管理 ====================
from backend.schemas.target import (
    TargetCreateRequest,
    TargetUpdateRequest,
    BreakdownCreateRequest,
    GenerateDailyBreakdownRequest,
    TargetResponse,
    BreakdownResponse,
)

# ==================== 销售战役 ====================
from backend.schemas.sales_campaign import (
    CampaignCreateRequest,
    CampaignUpdateRequest,
    CampaignShopRequest,
    CampaignResponse,
    CampaignShopResponse,
)

# ==================== 绩效管理 ====================
from backend.schemas.performance import (
    PerformanceConfigCreateRequest,
    PerformanceConfigUpdateRequest,
    PerformanceConfigResponse,
    PerformanceScoreResponse,
)

# ==================== 组件录制 ====================
from backend.schemas.component_recorder import (
    RecorderStartRequest,
    RecorderStepResponse,
    RecorderSaveRequest,
    GeneratePythonRequest,
)

# ==================== 费用管理 ====================
from backend.schemas.expense import (
    ExpenseCreateRequest,
    ExpenseUpdateRequest,
    ExpenseResponse,
    ExpenseSummaryResponse,
)

# ==================== 数据隔离 ====================
from backend.schemas.data_quarantine import (
    QuarantineListRequest,
    QuarantineDetailResponse,
    ReprocessRequest,
    ReprocessResponse,
)

# ==================== 自动入库 ====================
from backend.schemas.auto_ingest import (
    BatchAutoIngestRequest,
    SingleAutoIngestRequest,
    ClearDataRequest,
)

# ==================== WebSocket ====================
from backend.schemas.websocket import (
    CollectionWebSocketMessage,
    NotificationWebSocketMessage,
    NotificationMessage,
)

# ==================== 数据质量 ====================
from backend.schemas.data_quality import (
    CClassReadinessResponse,
    CoreFieldsStatusResponse,
)
