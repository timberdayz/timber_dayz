# backend/main.py — Legacy route registration snippet (archived)

该片段是历史遗留的 `app.include_router(...)` 注册方式，当前运行态由 `backend.app.runtime.bootstrap_app` + 各 domain `routes.py` 统一完成路由挂载。

此文件仅用于保留历史上下文与迁移对照，不应作为新开发入口模式参考。

## Archived snippet

```py
logger.info("Dashboard router source: PostgreSQL")
app.include_router(dashboard_api_postgresql.router, tags=["Dashboard"])

app.include_router(collection.router, prefix="/api/collection", tags=["数据采集"])

# Phase 8.1: UI化组件录制工具API
app.include_router(
    component_recorder.router, prefix="/api/collection", tags=["组件录制"]
)

# v4.6.0 数据采集WebSocket
try:
    from backend.routers import collection_websocket

    app.include_router(
        collection_websocket.router, prefix="/api/collection", tags=["采集WebSocket"]
    )

    from backend.routers import (
        main_accounts,
        platform_shop_discoveries,
        shop_account_aliases,
        shop_accounts,
    )

    app.include_router(main_accounts.router, prefix="/api", tags=["主账号管理"])
    app.include_router(shop_accounts.router, prefix="/api", tags=["店铺账号管理"])
    app.include_router(
        shop_account_aliases.router, prefix="/api", tags=["店铺别名管理"]
    )
    app.include_router(
        platform_shop_discoveries.router, prefix="/api", tags=["平台店铺ID发现"]
    )

    # Phase 9.4: 组件版本管理API
    from backend.routers import component_versions

    app.include_router(component_versions.router, prefix="/api", tags=["组件版本管理"])
except ImportError as e:
    logger.warning(f"Collection WebSocket router not loaded: {e}")

app.include_router(management.router, prefix="/api/management", tags=["数据管理"])

# v4.18.0: accounts.router 已删除，账号管理已全面切换到 main_accounts / shop_accounts / shop_account_aliases

app.include_router(field_mapping.router, prefix="/api/field-mapping", tags=["字段映射"])

# v4.3.7 字段映射辞典API(中文友好)
app.include_router(
    field_mapping_dictionary.router, prefix="/api/field-mapping", tags=["字段映射辞典"]
)
app.include_router(
    field_mapping_templates.router, prefix="/api/field-mapping", tags=["字段映射模板"]
)

# [WARN] v4.6.0 DSS架构重构:已删除field_mapping_dictionary_mv_display(DSS架构不再需要物化视图显示标识)

# v4.12.0: 数据同步API(新统一入口)
app.include_router(data_sync.router, prefix="/api", tags=["数据同步"])

# v4.13.0: 字段映射质量评分API
app.include_router(data_sync_mapping_quality.router, prefix="/api", tags=["数据同步"])

app.include_router(data_pipeline.router, tags=["数据管道"])

# v4.19.0: 通知WebSocket路由
try:
    from backend.routers import notification_websocket

    app.include_router(
        notification_websocket.router, prefix="/api", tags=["通知WebSocket"]
    )
    # WebSocket 清理任务将在 lifespan startup 中启动
except ImportError as e:
    logger.warning(f"Notification WebSocket router not loaded: {e}")

# v4.19.0: 系统资源监控API
from backend.routers import system_monitoring

app.include_router(system_monitoring.router, prefix="/api", tags=["系统监控"])

# v4.5.0: 自动入库API(v4.12.0已废弃,统一使用data_sync)
# [WARN] 注意:只保留治理统计API,自动入库API已移除
# 治理统计API(governance/*)仍然需要,因为数据治理功能依赖这些API
from backend.routers import auto_ingest
from backend.routers import refresh_queue

app.include_router(
    auto_ingest.router,
    prefix="/api/field-mapping",
    tags=["数据治理统计"],  # [*] 只保留治理统计API,自动入库API已废弃
)
app.include_router(refresh_queue.router, prefix="/api")

# v4.6.0 数据隔离区API(查看和重新处理隔离数据)
app.include_router(data_quarantine.router, prefix="/api", tags=["数据隔离区"])

app.include_router(data_quality.router, prefix="/api", tags=["数据质量监控"])

# ============================================================================
# Phase 3: A类数据管理API(销售目标、战役目标、经营成本)
# ============================================================================
app.include_router(config_management.router, tags=["A类数据管理", "配置管理"])

# ============================================================================
# Phase 3: HR管理API(员工管理、员工目标、考勤记录、绩效查询)
# ============================================================================
app.include_router(hr_management.router, tags=["HR管理"])

app.include_router(inventory_domain.router, tags=["库存管理"])

app.include_router(inventory_overview.router, tags=["库存总览"])

# v4.17.0: 财务域API已删除(财务域表已删除,API路由已移除)

from backend.routers import follow_investment, monthly_profit_settlement, profit_basis

app.include_router(profit_basis.router, tags=["利润结算基准"])
app.include_router(follow_investment.router, tags=["跟投收益"])
app.include_router(monthly_profit_settlement.router, tags=["月度利润结算中心"])

# 系统管理路由
app.include_router(auth.router, prefix="/api", tags=["认证管理"])
app.include_router(users.router, prefix="/api", tags=["用户管理"])
app.include_router(roles.router, prefix="/api", tags=["角色管理"])
app.include_router(permissions.router, tags=["权限管理"])  # /api/permissions/tree
app.include_router(permission.router, tags=["权限管理"])  # /api/system/permissions

# v4.19.0: 通知管理路由
app.include_router(notifications.router, prefix="/api", tags=["通知管理"])
app.include_router(training.router, prefix="/api", tags=["培训管理"])

# 开发工具路由
app.include_router(test_api.router, prefix="/api/test", tags=["测试诊断"])

app.include_router(
    performance.router,
    prefix="/api",
    tags=["系统性能监控"],  # v4.18.0: 修改为/api/system/performance,避免与绩效管理冲突
)

app.include_router(system.router, tags=["系统配置"])  # v4.20.0: 前缀已更新为 /api/system
app.include_router(system_logs.router, tags=["系统日志"])  # 前缀: /api/system/logs

from backend.routers import security as security_router
app.include_router(security_router.router, tags=["安全设置"])  # 前缀: /api/system/security

app.include_router(backup.router, tags=["数据备份"])  # 前缀: /api/system/backup
app.include_router(maintenance.router, tags=["系统维护"])  # 前缀: /api/system/maintenance
app.include_router(notification_config.router, tags=["通知配置"])  # 前缀: /api/system/notification

app.include_router(account_alignment.router, prefix="/api", tags=["账号对齐"])

app.include_router(sales_campaign.router, prefix="/api", tags=["销售战役管理"])
app.include_router(target_management.router, prefix="/api", tags=["目标管理"])
app.include_router(expense_management.router, prefix="/api", tags=["费用管理"])
app.include_router(performance_management.router, prefix="/api", tags=["绩效管理"])

app.include_router(raw_layer.router, tags=["原始数据层"])
app.include_router(raw_layer_export.router, tags=["原始数据层"])
app.include_router(data_flow.router, tags=["数据流转追踪"])
app.include_router(data_consistency.router, tags=["数据一致性验证"])
app.include_router(database_design_validator.router, tags=["数据库设计规范验证"])

app.include_router(mv.router, prefix="/api", tags=["遗留物化视图管理"])
app.include_router(rate_limit.router, prefix="/api", tags=["限流管理"])
app.include_router(rate_limit_config.router, tags=["限流配置管理"])

app.include_router(data_migration.router, prefix="/api", tags=["数据迁移"])
app.include_router(cloud_sync_router.router, tags=["云端同步管理"])

app.include_router(task_center.router, prefix="/api", tags=["任务中心"])
app.include_router(employee_tasks.router, prefix="/api", tags=["员工任务中心"])
app.include_router(approval_center.router, prefix="/api", tags=["审批中心"])
```

