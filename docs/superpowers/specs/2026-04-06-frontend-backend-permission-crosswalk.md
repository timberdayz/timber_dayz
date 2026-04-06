# Frontend To Backend Permission Crosswalk

**Date:** 2026-04-06

This document summarizes the current permission alignment across:

- frontend page classification
- frontend API module entrypoints
- backend route groups
- backend auth mode

It is intended as the maintenance reference after the permission-unification work.

## Auth Modes

- **Public**: no login required
- **Authenticated**: requires `get_current_user`
- **Admin**: requires `require_admin`
- **Self-scoped**: authenticated endpoint restricted to the current user’s own records

## 1. Workspace

| Frontend Page | Route | Frontend API | Backend Route Group | Auth Mode | Notes |
|---|---|---|---|---|---|
| 业务概览 | `/business-overview` | `@/api` generic dashboard/business-overview calls | dashboard / business-overview APIs | Mixed business read access | Frontend page is broad view page |
| 年度数据总结 | `/annual-summary` | `@/api/dashboard` | dashboard summary APIs | Admin page at frontend | Confirm backend separately when this page becomes active |

## 2. Data Collection And Management

| Frontend Page | Route | Frontend API | Backend Route Group | Auth Mode | Notes |
|---|---|---|---|---|---|
| 采集配置 | `/collection-config` | [collection.js](F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/api/collection.js) | [collection_config.py](F:/Vscode/python_programme/AI_code/xihong_erp/backend/routers/collection_config.py) | Admin | Create/update/delete/coverage all aligned to admin |
| 采集覆盖率巡检 | `/collection-coverage-audit` | [collection.js](F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/api/collection.js) | [collection_config.py](F:/Vscode/python_programme/AI_code/xihong_erp/backend/routers/collection_config.py) | Admin | Batch remediation also admin |
| 采集任务 | `/collection-tasks` | [collection.js](F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/api/collection.js) | [collection_tasks.py](F:/Vscode/python_programme/AI_code/xihong_erp/backend/routers/collection_tasks.py) | Existing collection auth model | Not part of this round’s high-risk fix |
| 采集历史 | `/collection-history` | [collection.js](F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/api/collection.js) | collection history endpoints | Existing collection auth model | Not part of this round’s high-risk fix |
| 组件录制工具 | `/component-recorder` | `@/api` generic component-recorder calls | [component_recorder.py](F:/Vscode/python_programme/AI_code/xihong_erp/backend/routers/component_recorder.py) | Admin | Router-level admin added |
| 组件版本管理 | `/component-versions` | `@/api` generic component-version calls | [component_versions.py](F:/Vscode/python_programme/AI_code/xihong_erp/backend/routers/component_versions.py) | Admin | Router-level admin added |
| 数据同步相关页 | `/data-sync/*` | `@/api` generic sync calls | data-sync routers | Mixed | This session did not fully remap every data-sync read surface |

## 3. Product And Inventory

| Frontend Page | Route | Frontend API | Backend Route Group | Auth Mode | Notes |
|---|---|---|---|---|---|
| 库存管理 | `/inventory-management` | [inventoryDomain.js](F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/api/inventoryDomain.js) | [inventory_domain.py](F:/Vscode/python_programme/AI_code/xihong_erp/backend/routers/inventory_domain.py) | Authenticated | View endpoints require login |
| 库存总览 | `/inventory-overview` | [inventoryOverview.js](F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/api/inventoryOverview.js) | [inventory_overview.py](F:/Vscode/python_programme/AI_code/xihong_erp/backend/routers/inventory_overview.py) | Authenticated | View endpoints require login |
| 库存流水 | `/inventory/ledger` | [inventoryDomain.js](F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/api/inventoryDomain.js) | [inventory_domain.py](F:/Vscode/python_programme/AI_code/xihong_erp/backend/routers/inventory_domain.py) | Authenticated | View page |
| 库存预警 | `/inventory/alerts` | [inventoryDomain.js](F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/api/inventoryDomain.js) | [inventory_domain.py](F:/Vscode/python_programme/AI_code/xihong_erp/backend/routers/inventory_domain.py) | Authenticated | View page |
| 库存对账 | `/inventory/reconciliation` | [inventoryDomain.js](F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/api/inventoryDomain.js) | [inventory_domain.py](F:/Vscode/python_programme/AI_code/xihong_erp/backend/routers/inventory_domain.py) | Authenticated | View page |
| 库存库龄 | `/inventory/aging` | [inventoryDomain.js](F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/api/inventoryDomain.js) | [inventory_domain.py](F:/Vscode/python_programme/AI_code/xihong_erp/backend/routers/inventory_domain.py) | Authenticated | View page |
| 库存健康仪表盘 | `/inventory-health` | `@/api` generic inventory dashboard calls | inventory dashboard / overview routes | Authenticated | View page |
| 产品质量仪表盘 | `/product-quality` | `@/api` generic product-quality calls | product analytics routes | Authenticated | View page |
| 库存看板 v3 | `/inventory-dashboard-v3` | no dedicated module; dashboard-style page | inventory dashboard routes | Authenticated | View page |
| 库存调整 | `/inventory/adjustments` | [inventoryDomain.js](F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/api/inventoryDomain.js) | [inventory_domain.py](F:/Vscode/python_programme/AI_code/xihong_erp/backend/routers/inventory_domain.py) | Admin | Write endpoint locked to admin |
| 入库单管理 | `/inventory/grns` | [inventoryDomain.js](F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/api/inventoryDomain.js) | [inventory_domain.py](F:/Vscode/python_programme/AI_code/xihong_erp/backend/routers/inventory_domain.py) | Admin for write / Authenticated for read | Read list requires login, post requires admin |
| 期初余额 | `/inventory/opening-balances` | [inventoryDomain.js](F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/api/inventoryDomain.js) | [inventory_domain.py](F:/Vscode/python_programme/AI_code/xihong_erp/backend/routers/inventory_domain.py) | Admin for write / Authenticated for read | Read list requires login, create requires admin |

## 4. Account Management

| Frontend Page | Route | Frontend API | Backend Route Group | Auth Mode | Notes |
|---|---|---|---|---|---|
| 账号管理 | `/account-management` | [accounts.js](F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/api/accounts.js) | [main_accounts.py](F:/Vscode/python_programme/AI_code/xihong_erp/backend/routers/main_accounts.py), [shop_accounts.py](F:/Vscode/python_programme/AI_code/xihong_erp/backend/routers/shop_accounts.py), [shop_account_aliases.py](F:/Vscode/python_programme/AI_code/xihong_erp/backend/routers/shop_account_aliases.py), [platform_shop_discoveries.py](F:/Vscode/python_programme/AI_code/xihong_erp/backend/routers/platform_shop_discoveries.py) | Admin | High-risk account surfaces aligned |
| 账号对齐 | `/account-alignment` | no dedicated frontend module import shown in this round | [account_alignment.py](F:/Vscode/python_programme/AI_code/xihong_erp/backend/routers/account_alignment.py) | Admin | Import / batch / backfill / alias writes locked to admin |

## 5. Role And Permission Management

| Frontend Page | Route | Frontend API | Backend Route Group | Auth Mode | Notes |
|---|---|---|---|---|---|
| 角色管理 | `/role-management` | [roles.js](F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/api/roles.js) | [roles.py](F:/Vscode/python_programme/AI_code/xihong_erp/backend/routers/roles.py) | Admin | Read and write now aligned to admin |
| 权限管理 | `/permission-management` | [system.js](F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/api/system.js) and [roles.js](F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/api/roles.js) | [permission.py](F:/Vscode/python_programme/AI_code/xihong_erp/backend/routers/permission.py), [permissions.py](F:/Vscode/python_programme/AI_code/xihong_erp/backend/routers/permissions.py), [roles.py](F:/Vscode/python_programme/AI_code/xihong_erp/backend/routers/roles.py) | Admin | Low-risk admin-read alignment completed |

## 6. System Management

| Frontend Page | Route | Frontend API | Backend Route Group | Auth Mode | Notes |
|---|---|---|---|---|---|
| 系统配置 | `/system-config` | [system.js](F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/api/system.js) | [system.py](F:/Vscode/python_programme/AI_code/xihong_erp/backend/routers/system.py) | Admin | Write and read already aligned |
| 数据库配置 | `/database-config` | [system.js](F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/api/system.js) | [system.py](F:/Vscode/python_programme/AI_code/xihong_erp/backend/routers/system.py) | Admin | Includes test connection |
| 安全设置 | `/security-settings` | [system.js](F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/api/system.js) | security router | Admin | Already aligned before this session |
| 系统日志 | `/system-logs` | [system.js](F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/api/system.js) | [system_logs.py](F:/Vscode/python_programme/AI_code/xihong_erp/backend/routers/system_logs.py) | Admin | Read/export/delete all admin |
| 数据备份 | `/data-backup` | [system.js](F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/api/system.js) | backup router | Admin | Already aligned |
| 系统维护 | `/system-maintenance` | [system.js](F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/api/system.js) | maintenance router | Admin | Already aligned |
| 通知配置 | `/notification-config` | [system.js](F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/api/system.js) | [notification_config.py](F:/Vscode/python_programme/AI_code/xihong_erp/backend/routers/notification_config.py) | Admin | SMTP/template/alert-rule management |

## 7. Personal Pages

| Frontend Page | Route | Frontend API | Backend Route Group | Auth Mode | Notes |
|---|---|---|---|---|---|
| 我的档案 | `/employee-management` | `@/api` generic HR calls | HR self/profile endpoints | Self-scoped | Intended current-user data only |
| 我的收入 | `/my-income` | `@/api` generic HR calls | HR self-income endpoints | Self-scoped | Current-user only |
| 个人设置 | `/personal-settings` | page currently uses generic/global client pattern | auth / users-me / self-service endpoints | Self-scoped | Personal page |
| 通知偏好设置 | `/settings/notifications` | [users.js](F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/api/users.js) | [users_me.py](F:/Vscode/python_programme/AI_code/xihong_erp/backend/routers/users_me.py) | Self-scoped | Current user’s notification preferences |
| 会话管理 | `/settings/sessions` | [users.js](F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/api/users.js) | [users_me.py](F:/Vscode/python_programme/AI_code/xihong_erp/backend/routers/users_me.py) | Self-scoped | Current user’s sessions only |
| 系统通知 | `/system-notifications` | [notifications.js](F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/api/notifications.js) | [notifications.py](F:/Vscode/python_programme/AI_code/xihong_erp/backend/routers/notifications.py) | Self-scoped + admin-only action gating | Page is personal surface; some buttons admin-only |
| 预警提醒 | `/alerts` | currently under-development/no dedicated module import in this audit | alerts/notification surfaces | View/self-scoped mix | Frontend page is broad view page |
| 消息设置 | `/message-settings` | no dedicated API import in page yet | current-user settings semantics | Personal | Frontend page treated as personal page |

## 8. Under-Development Or Generic-Client Pages

Some pages still use `@/api` generic access rather than a dedicated domain module, or are currently placeholder/under-development pages. For these, the most reliable maintenance rule is to treat the backend route group as the source of truth rather than the page import line.

Examples:

- `BusinessOverview.vue`
- `FinancialOverview.vue`
- `SalesDashboard.vue`
- `StoreAnalytics.vue`
- HR detail/config pages using generic `@/api`

## 9. Current Alignment Status

- **Frontend page classification:** completed
- **High-risk backend admin route alignment:** completed
- **Low-risk admin-read backend alignment:** completed
- **Personal-page backend self-scope alignment:** largely aligned

## 10. Remaining Gaps

These are not blockers for the current permission model, but are follow-up quality items:

- Some pages still use the generic `@/api` aggregator rather than a clearly scoped domain API module.
- Some placeholder pages do not yet have a stable backend contract worth documenting per-endpoint.
- The crosswalk is maintained at route-group level for some domains instead of enumerating every individual endpoint, because the page implementation is still evolving.
