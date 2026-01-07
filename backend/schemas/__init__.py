"""
Backend Pydantic Schemas (Contract-First架构)
所有API请求/响应模型的集中定义

组织原则：
1. 按业务域拆分文件（account, collection, finance等）
2. 每个文件包含该域的所有Pydantic模型
3. 在__init__.py中统一导出
4. router文件只从schemas导入，不自定义模型

v4.18.0: 初始创建，Contract-First迁移计划
"""

# ==================== 账号管理 ====================
from backend.schemas.account import (
    CapabilitiesModel,
    AccountCreate,
    AccountUpdate,
    AccountResponse,
    AccountStats,
)

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
# 注意：field_mapping.py不使用Pydantic模型，使用通用响应函数

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

__all__ = [
    # Account
    "CapabilitiesModel",
    "AccountCreate",
    "AccountUpdate",
    "AccountResponse",
    "AccountStats",
    # Common
    "SuccessResponse",
    "ErrorResponse",
    "PaginationMeta",
    "PaginatedResponse",
    # Collection
    "CollectionConfigCreate",
    "CollectionConfigUpdate",
    "CollectionConfigResponse",
    "TaskCreateRequest",
    "TaskResponse",
    "TaskLogResponse",
    "CollectionAccountResponse",
    "TaskHistoryResponse",
    "DailyStats",
    "TaskStatsResponse",
    "ScheduleUpdateRequest",
    "CronValidateRequest",
    "ScheduleResponse",
    "ScheduleInfoResponse",
    "CronValidationResponse",
    "CronPresetItem",
    "CronPresetsResponse",
    "ScheduledJobInfo",
    "ScheduledJobsResponse",
    "BrowserPoolStatus",
    "HealthCheckResponse",
    # Data Sync
    "SingleFileSyncRequest",
    "BatchSyncRequest",
    "BatchSyncByFileIdsRequest",
    "DataSyncFilePreviewRequest",
    "FileListRequest",
    # Rate Limit
    "RateLimitEventResponse",
    "RateLimitStatsResponse",
    "RateLimitAnomalyResponse",
    "RateLimitConfigResponse",
    "RateLimitInfoResponse",
    # Notification (v4.19.0)
    "NotificationType",
    "NotificationBase",
    "NotificationCreate",
    "NotificationResponse",
    "NotificationListResponse",
    "UnreadCountResponse",
    "MarkReadRequest",
    "MarkReadResponse",
    "NotificationDeleteResponse",
    "NotificationBatchCreate",
]

