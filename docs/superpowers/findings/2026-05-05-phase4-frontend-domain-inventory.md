# Phase 4 Frontend Domain Inventory (Draft)

Date: 2026-05-05

This inventory is generated from `frontend/src/router/index.js` and is intended to guide Phase 4 file moves without changing route contracts.

## Domain Counts (by route component)

| domain | routes |
|---|---:|
| business | 72 |
| platform | 20 |
| data_platform | 9 |
| collection | 6 |

## Route -> Domain -> Target View Path

| path | name | current view | proposed domain | proposed target |
|---|---|---|---|---|
| `/account-alignment` | `AccountAlignment` | `AccountAlignment.vue` | `business` | `frontend/src/domains/business/views/AccountAlignment.vue` |
| `/account-management` | `AccountManagement` | `AccountManagement.vue` | `platform` | `frontend/src/domains/platform/views/AccountManagement.vue` |
| `/admin/users/pending` | `UserApproval` | `admin/UserApproval.vue` | `platform` | `frontend/src/domains/platform/views/admin/UserApproval.vue` |
| `/alerts` | `Alerts` | `messages/Alerts.vue` | `platform` | `frontend/src/domains/platform/views/messages/Alerts.vue` |
| `/annual-summary` | `AnnualSummary` | `AnnualSummary.vue` | `business` | `frontend/src/domains/business/views/AnnualSummary.vue` |
| `/api-docs` | `APIDocs` | `dev/APIDocs.vue` | `platform` | `frontend/src/domains/platform/views/dev/APIDocs.vue` |
| `/approval-history` | `ApprovalHistory` | `approval/ApprovalHistory.vue` | `business` | `frontend/src/domains/business/views/approval/ApprovalHistory.vue` |
| `/b-cost-analysis` | `BCostAnalysis` | `finance/BCostAnalysis.vue` | `business` | `frontend/src/domains/business/views/finance/BCostAnalysis.vue` |
| `/business-overview` | `BusinessOverview` | `BusinessOverview.vue` | `business` | `frontend/src/domains/business/views/BusinessOverview.vue` |
| `/cloud-sync` | `CloudSyncManagement` | `CloudSyncManagement.vue` | `data_platform` | `frontend/src/domains/data_platform/views/CloudSyncManagement.vue` |
| `/collection-config` | `CollectionConfig` | `collection/CollectionConfig.vue` | `collection` | `frontend/src/domains/collection/views/collection/CollectionConfig.vue` |
| `/collection-coverage-audit` | `CollectionCoverageAudit` | `collection/CollectionCoverageAudit.vue` | `collection` | `frontend/src/domains/collection/views/collection/CollectionCoverageAudit.vue` |
| `/collection-history` | `CollectionHistory` | `collection/CollectionHistory.vue` | `collection` | `frontend/src/domains/collection/views/collection/CollectionHistory.vue` |
| `/collection-tasks` | `CollectionTasks` | `collection/CollectionTasks.vue` | `collection` | `frontend/src/domains/collection/views/collection/CollectionTasks.vue` |
| `/component-recorder` | `ComponentRecorder` | `ComponentRecorder.vue` | `collection` | `frontend/src/domains/collection/views/ComponentRecorder.vue` |
| `/component-versions` | `ComponentVersions` | `ComponentVersions.vue` | `collection` | `frontend/src/domains/collection/views/ComponentVersions.vue` |
| `/config/sales-targets` | `SalesTargetManagement` | `config/SalesTargetManagement.vue` | `business` | `frontend/src/domains/business/views/config/SalesTargetManagement.vue` |
| `/customer-management` | `CustomerManagement` | `sales/CustomerManagement.vue` | `business` | `frontend/src/domains/business/views/sales/CustomerManagement.vue` |
| `/custom-reports` | `CustomReports` | `reports/CustomReports.vue` | `business` | `frontend/src/domains/business/views/reports/CustomReports.vue` |
| `/data-backup` | `DataBackup` | `system/DataBackup.vue` | `platform` | `frontend/src/domains/platform/views/system/DataBackup.vue` |
| `/database-config` | `DatabaseConfig` | `system/DatabaseConfig.vue` | `platform` | `frontend/src/domains/platform/views/system/DatabaseConfig.vue` |
| `/data-consistency` | `DataConsistency` | `DataConsistency.vue` | `data_platform` | `frontend/src/domains/data_platform/views/DataConsistency.vue` |
| `/data-quarantine` | `DataQuarantine` | `DataQuarantine.vue` | `data_platform` | `frontend/src/domains/data_platform/views/DataQuarantine.vue` |
| `/data-sync/file-detail/:fileId` | `DataSyncFileDetail` | `DataSyncFileDetail.vue` | `data_platform` | `frontend/src/domains/data_platform/views/DataSyncFileDetail.vue` |
| `/data-sync/files` | `DataSyncFiles` | `DataSyncFiles.vue` | `data_platform` | `frontend/src/domains/data_platform/views/DataSyncFiles.vue` |
| `/data-sync/history` | `DataSyncHistory` | `DataSyncHistory.vue` | `data_platform` | `frontend/src/domains/data_platform/views/DataSyncHistory.vue` |
| `/data-sync/refresh-queue` | `DataSyncRefreshQueue` | `DataSyncRefreshQueue.vue` | `data_platform` | `frontend/src/domains/data_platform/views/DataSyncRefreshQueue.vue` |
| `/data-sync/tasks` | `DataSyncTasks` | `DataSyncTasks.vue` | `data_platform` | `frontend/src/domains/data_platform/views/DataSyncTasks.vue` |
| `/data-sync/templates` | `DataSyncTemplates` | `DataSyncTemplates.vue` | `data_platform` | `frontend/src/domains/data_platform/views/DataSyncTemplates.vue` |
| `/debug` | `Debug` | `Debug.vue` | `business` | `frontend/src/domains/business/views/Debug.vue` |
| `/employee-management` | `EmployeeManagement` | `hr/EmployeeManagement.vue` | `business` | `frontend/src/domains/business/views/hr/EmployeeManagement.vue` |
| `/employee-salary` | `EmployeeSalary` | `hr/EmployeeSalary.vue` | `business` | `frontend/src/domains/business/views/hr/EmployeeSalary.vue` |
| `/expense-management` | `ExpenseManagement` | `finance/ExpenseManagement.vue` | `business` | `frontend/src/domains/business/views/finance/ExpenseManagement.vue` |
| `/faq` | `FAQ` | `help/FAQ.vue` | `business` | `frontend/src/domains/business/views/help/FAQ.vue` |
| `/finance-reports` | `FinanceReports` | `finance/FinanceReports.vue` | `business` | `frontend/src/domains/business/views/finance/FinanceReports.vue` |
| `/finance-reports-detail` | `FinanceReportsDetail` | `reports/FinanceReportsDetail.vue` | `business` | `frontend/src/domains/business/views/reports/FinanceReportsDetail.vue` |
| `/financial-management` | `FinancialManagement` | `FinancialManagement.vue` | `business` | `frontend/src/domains/business/views/FinancialManagement.vue` |
| `/fiscal-periods` | `FiscalPeriods` | `finance/FiscalPeriods.vue` | `business` | `frontend/src/domains/business/views/finance/FiscalPeriods.vue` |
| `/fx-management` | `FXManagement` | `finance/FXManagement.vue` | `business` | `frontend/src/domains/business/views/finance/FXManagement.vue` |
| `/grn-management` | `GRNManagement` | `procurement/GRNManagement.vue` | `business` | `frontend/src/domains/business/views/procurement/GRNManagement.vue` |
| `/hr-performance-display` | `HRPerformanceDisplay` | `hr/PerformanceDisplay.vue` | `business` | `frontend/src/domains/business/views/hr/PerformanceDisplay.vue` |
| `/hr-performance-management` | `HRPerformanceManagement` | `hr/PerformanceManagement.vue` | `business` | `frontend/src/domains/business/views/hr/PerformanceManagement.vue` |
| `/hr-shop-assignment` | `ShopAssignment` | `hr/ShopAssignment.vue` | `business` | `frontend/src/domains/business/views/hr/ShopAssignment.vue` |
| `/human-resources` | `HumanResources` | `HumanResources.vue` | `business` | `frontend/src/domains/business/views/HumanResources.vue` |
| `/inventory/adjustments` | `InventoryAdjustments` | `inventory/InventoryAdjustments.vue` | `business` | `frontend/src/domains/business/views/inventory/InventoryAdjustments.vue` |
| `/inventory/aging` | `InventoryAging` | `inventory/InventoryAging.vue` | `business` | `frontend/src/domains/business/views/inventory/InventoryAging.vue` |
| `/inventory/alerts` | `InventoryAlerts` | `inventory/InventoryAlerts.vue` | `business` | `frontend/src/domains/business/views/inventory/InventoryAlerts.vue` |
| `/inventory/grns` | `InventoryGrns` | `inventory/InventoryGrns.vue` | `business` | `frontend/src/domains/business/views/inventory/InventoryGrns.vue` |
| `/inventory/ledger` | `InventoryLedger` | `inventory/InventoryLedger.vue` | `business` | `frontend/src/domains/business/views/inventory/InventoryLedger.vue` |
| `/inventory/opening-balances` | `InventoryOpeningBalances` | `inventory/InventoryOpeningBalances.vue` | `business` | `frontend/src/domains/business/views/inventory/InventoryOpeningBalances.vue` |
| `/inventory/reconciliation` | `InventoryReconciliation` | `inventory/InventoryReconciliation.vue` | `business` | `frontend/src/domains/business/views/inventory/InventoryReconciliation.vue` |
| `/inventory-dashboard-v3` | `InventoryDashboardV3` | `InventoryDashboardSimple.vue` | `business` | `frontend/src/domains/business/views/InventoryDashboardSimple.vue` |
| `/inventory-health` | `InventoryHealth` | `InventoryHealthDashboard.vue` | `business` | `frontend/src/domains/business/views/InventoryHealthDashboard.vue` |
| `/inventory-management` | `InventoryManagement` | `inventory/InventoryBalances.vue` | `business` | `frontend/src/domains/business/views/inventory/InventoryBalances.vue` |
| `/inventory-overview` | `InventoryOverview` | `InventoryOverview.vue` | `business` | `frontend/src/domains/business/views/InventoryOverview.vue` |
| `/inventory-reports` | `InventoryReports` | `reports/InventoryReports.vue` | `business` | `frontend/src/domains/business/views/reports/InventoryReports.vue` |
| `/invoice-management` | `InvoiceManagement` | `procurement/InvoiceManagement.vue` | `business` | `frontend/src/domains/business/views/procurement/InvoiceManagement.vue` |
| `/login` | `Login` | `Login.vue` | `platform` | `frontend/src/domains/platform/views/Login.vue` |
| `/message-settings` | `MessageSettings` | `messages/MessageSettings.vue` | `platform` | `frontend/src/domains/platform/views/messages/MessageSettings.vue` |
| `/my-follow-investment-income` | `MyFollowInvestmentIncome` | `hr/MyFollowInvestmentIncome.vue` | `business` | `frontend/src/domains/business/views/hr/MyFollowInvestmentIncome.vue` |
| `/my-income` | `MyIncome` | `hr/MyIncome.vue` | `business` | `frontend/src/domains/business/views/hr/MyIncome.vue` |
| `/my-requests` | `MyRequests` | `approval/MyRequests.vue` | `business` | `frontend/src/domains/business/views/approval/MyRequests.vue` |
| `/my-tasks` | `MyTasks` | `approval/MyTasks.vue` | `business` | `frontend/src/domains/business/views/approval/MyTasks.vue` |
| `/my-tasks/:taskId` | `TaskDetail` | `approval/TaskDetail.vue` | `business` | `frontend/src/domains/business/views/approval/TaskDetail.vue` |
| `/my-training` | `MyTraining` | `training/MyTraining.vue` | `business` | `frontend/src/domains/business/views/training/MyTraining.vue` |
| `/notification-config` | `NotificationConfig` | `system/NotificationConfig.vue` | `platform` | `frontend/src/domains/platform/views/system/NotificationConfig.vue` |
| `/order-management` | `OrderManagement` | `sales/OrderManagement.vue` | `business` | `frontend/src/domains/business/views/sales/OrderManagement.vue` |
| `/permission-management` | `PermissionManagement` | `PermissionManagement.vue` | `business` | `frontend/src/domains/business/views/PermissionManagement.vue` |
| `/personal-settings` | `PersonalSettings` | `PersonalSettings.vue` | `platform` | `frontend/src/domains/platform/views/PersonalSettings.vue` |
| `/product-quality` | `ProductQuality` | `ProductQualityDashboard.vue` | `business` | `frontend/src/domains/business/views/ProductQualityDashboard.vue` |
| `/purchase-orders` | `PurchaseOrders` | `procurement/PurchaseOrders.vue` | `business` | `frontend/src/domains/business/views/procurement/PurchaseOrders.vue` |
| `/register` | `Register` | `Register.vue` | `platform` | `frontend/src/domains/platform/views/Register.vue` |
| `/role-management` | `RoleManagement` | `RoleManagement.vue` | `business` | `frontend/src/domains/business/views/RoleManagement.vue` |
| `/sales/order-management` | `OrderManagement` | `sales/OrderManagement.vue` | `business` | `frontend/src/domains/business/views/sales/OrderManagement.vue` |
| `/sales/sales-detail-by-product` | `SalesDetailByProduct` | `sales/SalesDetailByProduct.vue` | `business` | `frontend/src/domains/business/views/sales/SalesDetailByProduct.vue` |
| `/sales-analysis` | `SalesAnalysis` | `SalesAnalysis.vue` | `business` | `frontend/src/domains/business/views/SalesAnalysis.vue` |
| `/sales-campaign-management` | `SalesCampaignManagement` | `sales/CampaignManagement.vue` | `business` | `frontend/src/domains/business/views/sales/CampaignManagement.vue` |
| `/sales-dashboard` | `SalesDashboard` | `SalesDashboard.vue` | `business` | `frontend/src/domains/business/views/SalesDashboard.vue` |
| `/sales-dashboard-v3` | `SalesDashboardV3` | `SalesDashboard.vue` | `business` | `frontend/src/domains/business/views/SalesDashboard.vue` |
| `/sales-reports` | `SalesReports` | `reports/SalesReports.vue` | `business` | `frontend/src/domains/business/views/reports/SalesReports.vue` |
| `/sales-trend` | `SalesTrend` | `SalesTrendChart.vue` | `business` | `frontend/src/domains/business/views/SalesTrendChart.vue` |
| `/security-settings` | `SecuritySettings` | `system/SecuritySettings.vue` | `platform` | `frontend/src/domains/platform/views/system/SecuritySettings.vue` |
| `/settings/notifications` | `NotificationPreferences` | `settings/NotificationPreferences.vue` | `platform` | `frontend/src/domains/platform/views/settings/NotificationPreferences.vue` |
| `/settings/sessions` | `Sessions` | `settings/Sessions.vue` | `platform` | `frontend/src/domains/platform/views/settings/Sessions.vue` |
| `/store-analytics` | `StoreAnalytics` | `store/StoreAnalytics.vue` | `business` | `frontend/src/domains/business/views/store/StoreAnalytics.vue` |
| `/store-management` | `StoreManagement` | `StoreManagement.vue` | `business` | `frontend/src/domains/business/views/StoreManagement.vue` |
| `/system-config` | `SystemConfig` | `system/SystemConfig.vue` | `platform` | `frontend/src/domains/platform/views/system/SystemConfig.vue` |
| `/system-logs` | `SystemLogs` | `system/SystemLogs.vue` | `platform` | `frontend/src/domains/platform/views/system/SystemLogs.vue` |
| `/system-maintenance` | `SystemMaintenance` | `system/SystemMaintenance.vue` | `platform` | `frontend/src/domains/platform/views/system/SystemMaintenance.vue` |
| `/system-notifications` | `SystemNotifications` | `messages/SystemNotifications.vue` | `platform` | `frontend/src/domains/platform/views/messages/SystemNotifications.vue` |
| `/target-management` | `TargetManagement` | `target/TargetManagement.vue` | `business` | `frontend/src/domains/business/views/target/TargetManagement.vue` |
| `/test` | `Test` | `Test.vue` | `business` | `frontend/src/domains/business/views/Test.vue` |
| `/test-legacy` | `TestLegacy` | `TestPage.vue` | `platform` | `frontend/src/domains/platform/views/TestPage.vue` |
| `/top-products` | `TopProducts` | `TopProducts.vue` | `business` | `frontend/src/domains/business/views/TopProducts.vue` |
| `/training/assignments` | `TrainingAssignments` | `training/TrainingAssignments.vue` | `business` | `frontend/src/domains/business/views/training/TrainingAssignments.vue` |
| `/training/assignments/:assignmentId` | `TrainingAssignmentDetail` | `training/TrainingAssignmentDetail.vue` | `business` | `frontend/src/domains/business/views/training/TrainingAssignmentDetail.vue` |
| `/training/integration` | `TrainingIntegration` | `training/TrainingIntegration.vue` | `business` | `frontend/src/domains/business/views/training/TrainingIntegration.vue` |
| `/training/overview` | `TrainingOverview` | `training/TrainingOverview.vue` | `business` | `frontend/src/domains/business/views/training/TrainingOverview.vue` |
| `/training/programs` | `TrainingPrograms` | `training/TrainingPrograms.vue` | `business` | `frontend/src/domains/business/views/training/TrainingPrograms.vue` |
| `/training/results` | `TrainingResults` | `training/TrainingResults.vue` | `business` | `frontend/src/domains/business/views/training/TrainingResults.vue` |
| `/ultra-simple` | `UltraSimple` | `UltraSimplePage.vue` | `platform` | `frontend/src/domains/platform/views/UltraSimplePage.vue` |
| `/user-guide` | `UserGuide` | `help/UserGuide.vue` | `business` | `frontend/src/domains/business/views/help/UserGuide.vue` |
| `/user-management` | `UserManagement` | `UserManagement.vue` | `business` | `frontend/src/domains/business/views/UserManagement.vue` |
| `/vendor-management` | `VendorManagement` | `procurement/VendorManagement.vue` | `business` | `frontend/src/domains/business/views/procurement/VendorManagement.vue` |
| `/vendor-reports` | `VendorReports` | `reports/VendorReports.vue` | `business` | `frontend/src/domains/business/views/reports/VendorReports.vue` |
| `/video-tutorials` | `VideoTutorials` | `help/VideoTutorials.vue` | `business` | `frontend/src/domains/business/views/help/VideoTutorials.vue` |
| `/workflow-config` | `WorkflowConfig` | `approval/WorkflowConfig.vue` | `business` | `frontend/src/domains/business/views/approval/WorkflowConfig.vue` |
