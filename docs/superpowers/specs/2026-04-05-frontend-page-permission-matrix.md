# Frontend Page Permission Matrix

**Date:** 2026-04-05

This document records the current intended frontend page permission matrix after the page-permission unification work.

## Classification Rules

- **View page**: read-only dashboards, analytics, query/list/detail pages
- **Operation page**: pages containing create/edit/delete/configure/post/sync/export-initiation or other state-changing workflow actions
- **Personal page**: pages that show or edit only the current user's own data or preferences
- **Help page**: documentation/tutorial/help content
- **Dev/System admin page**: development and system-management surfaces

## Role Keys

- `admin`
- `manager`
- `operator`
- `finance`
- `tourist`

## 1. Workspace

| Page | Route | Category | Roles |
|---|---|---|---|
| 业务概览 | `/business-overview` | View | `admin, manager, operator, finance, tourist` |
| 年度数据总结 | `/annual-summary` | Operation/Admin | `admin` |

## 2. Data Collection And Management

All collection-management pages are admin-only by product rule.

| Page | Route | Category | Roles |
|---|---|---|---|
| 云端同步管理 | `/cloud-sync` | Operation/Admin | `admin` |
| 采集配置 | `/collection-config` | Operation/Admin | `admin` |
| 采集覆盖率巡检 | `/collection-coverage-audit` | Operation/Admin | `admin` |
| 采集任务 | `/collection-tasks` | Operation/Admin | `admin` |
| 采集历史 | `/collection-history` | Operation/Admin | `admin` |
| 组件录制工具 | `/component-recorder` | Operation/Admin | `admin` |
| 组件版本管理 | `/component-versions` | Operation/Admin | `admin` |
| 文件列表 | `/data-sync/files` | Operation/Admin | `admin` |
| 文件详情 | `/data-sync/file-detail/:fileId` | Operation/Admin | `admin` |
| 同步任务 | `/data-sync/tasks` | Operation/Admin | `admin` |
| 同步历史 | `/data-sync/history` | Operation/Admin | `admin` |
| 模板管理 | `/data-sync/templates` | Operation/Admin | `admin` |
| 数据一致性验证 | `/data-consistency` | Operation/Admin | `admin` |
| 数据隔离区 | `/data-quarantine` | Operation/Admin | `admin` |

## 3. Product And Inventory

| Page | Route | Category | Roles |
|---|---|---|---|
| 库存管理 | `/inventory-management` | View | `admin, manager, operator` |
| 库存总览 | `/inventory-overview` | View | `admin, manager, operator` |
| 库存流水 | `/inventory/ledger` | View | `admin, manager, operator` |
| 库存预警 | `/inventory/alerts` | View | `admin, manager, operator` |
| 库存对账 | `/inventory/reconciliation` | View | `admin, manager, operator` |
| 库存库龄 | `/inventory/aging` | View | `admin, manager, operator` |
| 库存健康仪表盘 | `/inventory-health` | View | `admin, manager, operator` |
| 产品质量仪表盘 | `/product-quality` | View | `admin, manager, operator` |
| 库存看板 v3 | `/inventory-dashboard-v3` | View | `admin, manager, operator` |
| 库存调整 | `/inventory/adjustments` | Operation/Admin | `admin` |
| 入库单管理 | `/inventory/grns` | Operation/Admin | `admin` |
| 期初余额 | `/inventory/opening-balances` | Operation/Admin | `admin` |

## 4. Procurement

| Page | Route | Category | Roles |
|---|---|---|---|
| 采购订单 | `/purchase-orders` | View/Business | `admin, manager, finance` |
| 入库单 | `/grn-management` | View/Business | `admin, manager, finance` |
| 供应商管理 | `/vendor-management` | View/Business | `admin, manager, finance` |
| 发票管理 | `/invoice-management` | View/Business | `admin, manager, finance` |

## 5. Sales And Store

| Page | Route | Category | Roles |
|---|---|---|---|
| 销售分析 | `/sales-analysis` | View | `admin, manager, operator, finance` |
| 销售看板 | `/sales-dashboard` | View | `admin, manager, operator, finance` |
| 销售看板 v3 | `/sales-dashboard-v3` | View | `admin, manager, operator, finance` |
| 店铺分析 | `/store-analytics` | View | `admin, manager, operator` |
| 销售明细（产品ID级别） | `/sales/sales-detail-by-product` | Operation/Admin | `admin` |
| 客户管理 | `/customer-management` | Operation/Admin | `admin` |
| 订单管理 | `/order-management` | Operation/Admin | `admin` |
| 销售战役管理 | `/sales-campaign-management` | Operation/Admin | `admin` |
| 店铺管理 | `/store-management` | Operation/Admin | `admin` |

## 6. Finance

| Page | Route | Category | Roles |
|---|---|---|---|
| 财务总览 | `/financial-overview` | View | `admin, manager, finance` |
| 财务管理 | `/financial-management` | View/Business | `admin, manager, finance` |
| 费用管理 | `/expense-management` | View/Business | `admin, manager, finance` |
| B 类成本分析 | `/b-cost-analysis` | View | `admin, manager, finance` |
| 财务报表 | `/finance-reports` | View | `admin, manager, finance` |
| 财务报表详情 | `/finance-reports-detail` | View | `admin, finance` |
| 汇率管理 | `/fx-management` | View/Business | `admin, manager, finance` |
| 会计期间 | `/fiscal-periods` | View/Business | `admin, manager, finance` |

## 7. Reports

| Page | Route | Category | Roles |
|---|---|---|---|
| 销售报表 | `/sales-reports` | View | `admin, manager, operator` |
| 库存报表 | `/inventory-reports` | View | `admin, manager, operator` |
| 供应商报表 | `/vendor-reports` | View | `admin, manager, operator` |
| 自定义报表 | `/custom-reports` | Operation/Admin | `admin` |

## 8. HR

| Page | Route | Category | Roles |
|---|---|---|---|
| 人力管理 | `/human-resources` | Operation/Admin | `admin` |
| 我的档案 | `/employee-management` | Personal | `admin, manager, operator, finance` |
| 我的收入 | `/my-income` | Personal | `admin, manager, operator, finance` |
| 绩效公示 | `/hr-performance-display` | View | `admin, manager, operator, finance, tourist` |
| 绩效管理 | `/hr-performance-management` | Operation/Admin | `admin` |
| 人员店铺归属和提成比 | `/hr-shop-assignment` | Operation/Admin | `admin` |

## 9. Approval

| Page | Route | Category | Roles |
|---|---|---|---|
| 我的待办 | `/my-tasks` | Operation/Admin | `admin` |
| 我的申请 | `/my-requests` | Operation/Admin | `admin` |
| 审批历史 | `/approval-history` | Operation/Admin | `admin` |
| 流程配置 | `/workflow-config` | Operation/Admin | `admin` |

## 10. Messaging And Personal Notification Surfaces

| Page | Route | Category | Roles |
|---|---|---|---|
| 系统通知 | `/system-notifications` | Personal | `admin, manager, operator, finance` |
| 预警提醒 | `/alerts` | View | `admin, manager, operator, finance` |
| 消息设置 | `/message-settings` | Personal | `admin, manager, operator, finance` |
| 个人设置 | `/personal-settings` | Personal | `admin, manager, operator, finance` |
| 通知偏好设置 | `/settings/notifications` | Personal | `admin, manager, operator, finance` |
| 会话管理 | `/settings/sessions` | Personal | `admin, manager, operator, finance` |

### Personal-page note for system notifications

`/system-notifications` is intentionally treated as a personal page, but the page still contains some admin-only controls.

Those controls are gated inside the component and shown only to admins:

- 用户审批入口
- 用户管理入口
- 批量标记已读
- 批量删除已读
- 分组批量已读

## 11. System Management

| Page | Route | Category | Roles |
|---|---|---|---|
| 用户审批 | `/admin/users/pending` | Operation/Admin | `admin` |
| 用户管理 | `/user-management` | Operation/Admin | `admin` |
| 角色管理 | `/role-management` | Operation/Admin | `admin` |
| 权限管理 | `/permission-management` | Operation/Admin | `admin` |
| 系统配置 | `/system-config` | Operation/Admin | `admin` |
| 数据库配置 | `/database-config` | Operation/Admin | `admin` |
| 安全设置 | `/security-settings` | Operation/Admin | `admin` |
| 系统日志 | `/system-logs` | Operation/Admin | `admin` |
| 数据备份 | `/data-backup` | Operation/Admin | `admin` |
| 系统维护 | `/system-maintenance` | Operation/Admin | `admin` |
| 通知配置 | `/notification-config` | Operation/Admin | `admin` |
| 账号管理 | `/account-management` | Operation/Admin | `admin` |
| 账号对齐 | `/account-alignment` | Operation/Admin | `admin` |

## 12. Help Center

| Page | Route | Category | Roles |
|---|---|---|---|
| 操作指南 | `/user-guide` | Help | `admin, manager, operator, finance, tourist` |
| 视频教程 | `/video-tutorials` | Help | `admin, manager, operator, finance, tourist` |
| 常见问题 | `/faq` | Help | `admin, manager, operator, finance, tourist` |

## 13. Dev Tools

| Page | Route | Category | Roles |
|---|---|---|---|
| 超简化页面 | `/ultra-simple` | Dev/Admin | `admin` |
| 测试页面（legacy） | `/test-legacy` | Dev/Admin | `admin` |
| 测试页面 | `/test` | Dev/Admin | `admin` |
| 调试信息 | `/debug` | Dev/Admin | `admin` |
| API 文档 | `/api-docs` | Dev/Admin | `admin` |

## Notes

- Route access is still enforced by both `meta.permission` and `meta.roles`.
- Admin keeps universal access through the frontend permission helper.
- This matrix reflects the intended page classification, not backend API authorization guarantees.
