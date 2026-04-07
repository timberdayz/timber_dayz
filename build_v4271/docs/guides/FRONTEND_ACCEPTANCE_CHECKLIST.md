# 前端验收清单

适用范围：
- Vue 3 + Element Plus + Pinia + Vite 页面
- 当前前端统一工作流下的页面结构、视觉、交互和基本可用性验收

当前页面基线：
- 统一使用 `PageHeader`
- 页面家族固定为 `dashboard` 或 `admin`
- 管理页优先复用 `erp-layout.css` 中的共享布局工具类
- 页面内不应继续新增组件级 `axios` 调用

## 第一批核心页面

优先验收：
- `BusinessOverview`
- `SalesDashboardV3`
- `SystemConfig`
- `InventoryManagement`
- `TargetManagement`
- `UserManagement`
- `RoleManagement`
- `PermissionManagement`

检查项：
- 页面标题与路由 `meta.title` 一致
- 页面头部、副标题、主操作按钮层级清晰
- 筛选区、内容区、操作区分层明确
- 无全屏阻塞 loading
- 主要表格、卡片、空态、错误态可正常展示
- 不存在明显视觉割裂或旧 header 残留

## 第二批高频管理页面

优先验收：
- `DataSyncFiles`
- `CollectionTasks`
- `CollectionHistory`
- `SystemNotifications`
- `Sessions`
- `DatabaseConfig`
- `SecuritySettings`
- `SystemLogs`
- `DataBackup`
- `SystemMaintenance`
- `AccountManagement`
- `NotificationConfig`
- `ExpenseManagement`

检查项：
- 页面已接入统一 `PageHeader`
- 页面仍保留原业务逻辑，未出现按钮失效或筛选失效
- 表格宽度、分页、按钮间距、统计卡片布局正常
- 关键批量操作按钮可正常显示且 loading 仅作用于局部
- 行内样式已显著减少，新增样式应优先使用共享布局类

## Smoke 覆盖页面

当前应保持固定 smoke 覆盖：
- `BusinessOverview`
- `SalesDashboardV3`
- `SystemConfig`
- `InventoryManagement`
- `TargetManagement`
- `UserManagement`
- `RoleManagement`
- `PermissionManagement`
- `AccountManagement`
- `Sessions`
- `SystemNotifications`
- `DatabaseConfig`
- `SecuritySettings`
- `SystemLogs`
- `DataBackup`
- `NotificationConfig`
- `SystemMaintenance`
- `CollectionConfig`
- `DataSyncTasks`
- `DataSyncHistory`
- `ComponentVersions`
- `StoreAnalytics`
- `FinancialOverview`
- `ExpenseManagement`
- `InventoryDashboardV3`
- `InventoryHealth`
- `ProductQuality`
- `SalesAnalysis`

Smoke 通过标准：
- 能正常进入页面
- 浏览器标题匹配预期
- 不跳回登录页
- 页面主体内容存在
- 无 console error / page error / 5xx API 请求失败

## 验收记录建议

每个页面至少记录：
- 页面名
- 验收日期
- 验收人
- 自动化状态：通过 / 未覆盖 / 失败
- 人工状态：通过 / 有问题 / 待验收
- 问题摘要：视觉 / 布局 / 交互 / 数据 / 权限

推荐结论标签：
- `PASS`：可进入下一轮页面
- `PASS_WITH_FIXES`：存在低风险问题，可并行修复
- `BLOCKED`：存在影响使用的问题，必须先修
