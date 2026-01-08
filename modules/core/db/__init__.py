#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Database package (new unified ORM Base and schema)

Exports:
- Base: Declarative base for Alembic target metadata
- ORM models for dimensions and facts
"""

from .schema import (
    Base,
    # 维度表
    DimPlatform,
    DimShop,
    DimProduct,
    DimProductMaster,
    BridgeProductKeys,
    DimCurrencyRate,
    DimExchangeRate,  # v4.6.0: 汇率维度表
    # 事实表
    FactOrder,
    FactOrderItem,
    FactOrderAmount,  # v4.6.0: 订单金额维度表
    FactProductMetric,
    FactTraffic,  # v4.12.0: 运营数据 - 流量数据
    FactService,  # v4.12.0: 运营数据 - 服务数据
    FactAnalytics,  # v4.12.0: 运营数据 - 分析数据
    # 管理表
    CatalogFile,
    DataQuarantine,
    Account,
    AccountAlias,  # v4.3.6: 账号别名映射表
    CollectionConfig,  # v4.6.0: 采集配置表
    CollectionTask,
    CollectionTaskLog,  # v4.6.0: 采集任务日志表
    CollectionSyncPoint,  # Phase 9.2: 增量采集同步点表（已取消功能，保留表）
    ComponentVersion,  # Phase 9.4: 组件版本管理表
    ComponentTestHistory,  # Phase 8.2: 组件测试历史记录表（2025-12-17）
    PlatformAccount,  # v4.7.0: 平台账号管理表
    DataFile,
    DataRecord,
    FieldMapping,
    MappingSession,
    # 暂存表
    StagingOrders,
    StagingProductMetrics,
    StagingInventory,  # v4.11.4新增：库存数据暂存表
    # v3.0 产品图片表
    ProductImage,
    # 物化视图管理
    MaterializedViewRefreshLog,  # v4.11.4新增：物化视图刷新日志表
)

# v4.3.7: 字段映射辞典与模板
# v4.3.7: 字段映射系统（已并入schema，消除重复Base）
from .schema import (
    FieldMappingDictionary,
    FieldMappingTemplate,
    FieldMappingTemplateItem,
    FieldMappingAudit,
)

# v4.4.0: 财务域表（Modern ERP）
from .schema import (
    # 指标公式
    DimMetricFormula,
    # 财务维度
    DimCurrency,
    FxRate,
    DimFiscalCalendar,
    DimVendor,
    # 采购管理
    POHeader,
    POLine,
    GRNHeader,
    GRNLine,
    # 库存流水
    InventoryLedger,
    # 发票管理
    InvoiceHeader,
    InvoiceLine,
    InvoiceAttachment,
    ThreeWayMatchLog,
    # 费用管理
    FactExpensesMonth,
    AllocationRule,
    FactExpensesAllocated,
    # 物流成本
    LogisticsCost,
    LogisticsAllocationRule,
    # 税务管理
    TaxVoucher,
    TaxReport,
    # 总账
    GLAccount,
    JournalEntry,
    JournalEntryLine,
    # 期初余额
    OpeningBalance,
    # 审批与退货
    ApprovalLog,
    ReturnOrder,
    FieldUsageTracking,
    # v4.11.0: 销售战役与目标管理
    SalesCampaign,
    SalesCampaignShop,
    SalesTarget,
    TargetBreakdown,
    ShopHealthScore,
    ShopAlert,
    PerformanceScore,
    PerformanceConfig,
    ClearanceRanking,
    # v4.12.0: 用户权限和审计（SSOT迁移）
    DimUser,
    DimRole,
    UserApprovalLog,  # v4.19.0: 用户审批记录表
    UserSession,  # v4.19.0: 用户会话表
    Notification,  # v4.19.0: 系统通知表
    UserNotificationPreference,  # v4.19.0: 用户通知偏好表
    FactAuditLog,
    user_roles,
    # v4.19.4: 限流配置表（Phase 3）
    DimRateLimitConfig,  # v4.19.4: 限流配置维度表
    FactRateLimitConfigAudit,  # v4.19.4: 限流配置审计日志表
    # v4.20.0: 系统管理表
    SystemLog,  # v4.20.0: 系统日志表
    SecurityConfig,  # v4.20.0: 安全配置表
    BackupRecord,  # v4.20.0: 备份记录表
    SMTPConfig,  # v4.20.0: SMTP配置表
    NotificationTemplate,  # v4.20.0: 通知模板表
    AlertRule,  # v4.20.0: 告警规则表
    SystemConfig,  # v4.20.0: 系统配置表
    # v4.12.0: 数据同步进度跟踪
    SyncProgressTask,
    # v4.6.0+: DSS架构表
    # B类数据表（v4.17.0+：所有旧的固定表类已删除，通过PlatformTableManager动态创建）
    # 表名格式：fact_{platform}_{data_domain}_{sub_domain}_{granularity}
    # 所有表创建在b_class schema中
    # 统一对齐表
    EntityAlias,
    # Staging表
    StagingRawData,
    # A类数据表
    SalesTargetA,
    SalesCampaignA,
    OperatingCost,
    Employee,
    EmployeeTarget,
    AttendanceRecord,
    PerformanceConfigA,
    # C类数据表
    EmployeePerformance,
    EmployeeCommission,
    ShopCommission,
    PerformanceScoreC,
)

__all__ = [
    "Base",
    # 维度表
    "DimPlatform",
    "DimShop",
    "DimProduct",
    "DimProductMaster",
    "BridgeProductKeys",
    "DimCurrencyRate",
    "DimExchangeRate",  # v4.6.0
    # 事实表
    "FactOrder",
    "FactOrderItem",
    "FactOrderAmount",  # v4.6.0
    "FactProductMetric",
    "FactTraffic",  # v4.12.0: 运营数据 - 流量数据
    "FactService",  # v4.12.0: 运营数据 - 服务数据
    "FactAnalytics",  # v4.12.0: 运营数据 - 分析数据
    # 管理表
    "CatalogFile",
    "DataQuarantine",
    "Account",
    "AccountAlias",  # v4.3.6
    "CollectionConfig",  # v4.6.0: 采集配置表
    "CollectionTask",
    "CollectionTaskLog",  # v4.6.0: 采集任务日志表
    "CollectionSyncPoint",  # Phase 9.2: 增量采集同步点表（已取消功能，保留表）
    "ComponentVersion",  # Phase 9.4: 组件版本管理表
    "ComponentTestHistory",  # Phase 8.2: 组件测试历史记录表（2025-12-17）
    "PlatformAccount",  # v4.7.0: 平台账号管理表
    "DataFile",
    "DataRecord",
    "FieldMapping",
    "MappingSession",
    # 暂存表
    "StagingOrders",
    "StagingProductMetrics",
    # v3.0 产品图片表
    "ProductImage",
    # v4.3.7: 字段映射系统
    "FieldMappingDictionary",
    "FieldMappingTemplate",
    "FieldMappingTemplateItem",
    "FieldMappingAudit",
    # v4.4.0: 财务域
    "DimMetricFormula",
    "DimCurrency",
    "FxRate",
    "DimFiscalCalendar",
    "DimVendor",
    "POHeader",
    "POLine",
    "GRNHeader",
    "GRNLine",
    "InventoryLedger",
    "InvoiceHeader",
    "InvoiceLine",
    "InvoiceAttachment",
    "ThreeWayMatchLog",
    "FactExpensesMonth",
    "AllocationRule",
    "FactExpensesAllocated",
    "LogisticsCost",
    "LogisticsAllocationRule",
    "TaxVoucher",
    "TaxReport",
    "GLAccount",
    "JournalEntry",
    "JournalEntryLine",
    "OpeningBalance",
    "ApprovalLog",
    "ReturnOrder",
    # v4.7.0: 元数据与追踪
    "FieldUsageTracking",
    # v4.11.0: 销售战役与目标管理
    "SalesCampaign",
    "SalesCampaignShop",
    "SalesTarget",
    "TargetBreakdown",
    "ShopHealthScore",
    "ShopAlert",
    "PerformanceScore",
    "PerformanceConfig",
    "ClearanceRanking",
    # v4.12.0: 用户权限和审计（SSOT迁移）
    "DimUser",
    "DimRole",
    "UserApprovalLog",  # v4.19.0: 用户审批记录表
    "UserSession",  # v4.19.0: 用户会话表
    "Notification",  # v4.19.0: 系统通知表
    "UserNotificationPreference",  # v4.19.0: 用户通知偏好表
    "FactAuditLog",
    "user_roles",
    # v4.19.4: 限流配置表（Phase 3）
    "DimRateLimitConfig",  # v4.19.4: 限流配置维度表
    "FactRateLimitConfigAudit",  # v4.19.4: 限流配置审计日志表
    # v4.20.0: 系统管理表
    "SystemLog",  # v4.20.0: 系统日志表
    "SecurityConfig",  # v4.20.0: 安全配置表
    "BackupRecord",  # v4.20.0: 备份记录表
    "SMTPConfig",  # v4.20.0: SMTP配置表
    "NotificationTemplate",  # v4.20.0: 通知模板表
    "AlertRule",  # v4.20.0: 告警规则表
    "SystemConfig",  # v4.20.0: 系统配置表
    # v4.12.0: 数据同步进度跟踪
    "SyncProgressTask",
    # v4.6.0+: DSS架构表
    # B类数据表（v4.17.0+：所有旧的固定表类已删除，通过PlatformTableManager动态创建）
    # 统一对齐表
    "EntityAlias",
    # Staging表
    "StagingRawData",
    # A类数据表
    "SalesTargetA",
    "SalesCampaignA",
    "OperatingCost",
    "Employee",
    "EmployeeTarget",
    "AttendanceRecord",
    "PerformanceConfigA",
    # C类数据表
    "EmployeePerformance",
    "EmployeeCommission",
    "ShopCommission",
    "PerformanceScoreC",
]

