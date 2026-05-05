import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const frontendRoot = path.resolve(scriptDir, '..')
const routerPath = path.join(frontendRoot, 'src/router/index.js')

const EXPECTED_ROUTE_WRAPPER_COUNT = 107
const EXPECTED_UNIQUE_WRAPPER_COUNT = 105
const EXPECTED_ROUTE_WRAPPER_ENTRIES = [
  {
    "routeIndex": 1,
    "specifier": "../views/Login.vue",
    "wrapper": "src/views/Login.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 2,
    "specifier": "../views/Register.vue",
    "wrapper": "src/views/Register.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 3,
    "specifier": "../views/admin/UserApproval.vue",
    "wrapper": "src/views/admin/UserApproval.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 4,
    "specifier": "../views/approval/TaskDetail.vue",
    "wrapper": "src/views/approval/TaskDetail.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 5,
    "specifier": "../views/UltraSimplePage.vue",
    "wrapper": "src/views/UltraSimplePage.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 6,
    "specifier": "../views/TestPage.vue",
    "wrapper": "src/views/TestPage.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 7,
    "specifier": "../views/BusinessOverview.vue",
    "wrapper": "src/views/BusinessOverview.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 8,
    "specifier": "../views/AnnualSummary.vue",
    "wrapper": "src/views/AnnualSummary.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 9,
    "specifier": "../views/SalesAnalysis.vue",
    "wrapper": "src/views/SalesAnalysis.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 10,
    "specifier": "../views/SalesDashboard.vue",
    "wrapper": "src/views/SalesDashboard.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 11,
    "specifier": "../views/sales/OrderManagement.vue",
    "wrapper": "src/views/sales/OrderManagement.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 12,
    "specifier": "../views/sales/SalesDetailByProduct.vue",
    "wrapper": "src/views/sales/SalesDetailByProduct.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 13,
    "specifier": "../views/inventory/InventoryBalances.vue",
    "wrapper": "src/views/inventory/InventoryBalances.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 14,
    "specifier": "../views/InventoryOverview.vue",
    "wrapper": "src/views/InventoryOverview.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 15,
    "specifier": "../views/inventory/InventoryLedger.vue",
    "wrapper": "src/views/inventory/InventoryLedger.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 16,
    "specifier": "../views/inventory/InventoryAdjustments.vue",
    "wrapper": "src/views/inventory/InventoryAdjustments.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 17,
    "specifier": "../views/inventory/InventoryGrns.vue",
    "wrapper": "src/views/inventory/InventoryGrns.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 18,
    "specifier": "../views/inventory/InventoryAlerts.vue",
    "wrapper": "src/views/inventory/InventoryAlerts.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 19,
    "specifier": "../views/inventory/InventoryReconciliation.vue",
    "wrapper": "src/views/inventory/InventoryReconciliation.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 20,
    "specifier": "../views/inventory/InventoryAging.vue",
    "wrapper": "src/views/inventory/InventoryAging.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 21,
    "specifier": "../views/inventory/InventoryOpeningBalances.vue",
    "wrapper": "src/views/inventory/InventoryOpeningBalances.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 22,
    "specifier": "../views/HumanResources.vue",
    "wrapper": "src/views/HumanResources.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 23,
    "specifier": "../views/FinancialManagement.vue",
    "wrapper": "src/views/FinancialManagement.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 24,
    "specifier": "../views/StoreManagement.vue",
    "wrapper": "src/views/StoreManagement.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 25,
    "specifier": "../views/system/SystemConfig.vue",
    "wrapper": "src/views/system/SystemConfig.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 26,
    "specifier": "../views/system/DatabaseConfig.vue",
    "wrapper": "src/views/system/DatabaseConfig.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 27,
    "specifier": "../views/system/SecuritySettings.vue",
    "wrapper": "src/views/system/SecuritySettings.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 28,
    "specifier": "../views/AccountManagement.vue",
    "wrapper": "src/views/AccountManagement.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 29,
    "specifier": "../views/PersonalSettings.vue",
    "wrapper": "src/views/PersonalSettings.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 30,
    "specifier": "../views/settings/NotificationPreferences.vue",
    "wrapper": "src/views/settings/NotificationPreferences.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 31,
    "specifier": "../views/settings/Sessions.vue",
    "wrapper": "src/views/settings/Sessions.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 32,
    "specifier": "../views/DataSyncFiles.vue",
    "wrapper": "src/views/DataSyncFiles.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 33,
    "specifier": "../views/DataSyncFileDetail.vue",
    "wrapper": "src/views/DataSyncFileDetail.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 34,
    "specifier": "../views/DataSyncTasks.vue",
    "wrapper": "src/views/DataSyncTasks.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 35,
    "specifier": "../views/DataSyncHistory.vue",
    "wrapper": "src/views/DataSyncHistory.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 36,
    "specifier": "../views/DataSyncTemplates.vue",
    "wrapper": "src/views/DataSyncTemplates.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 37,
    "specifier": "../views/DataSyncRefreshQueue.vue",
    "wrapper": "src/views/DataSyncRefreshQueue.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 38,
    "specifier": "../views/CloudSyncManagement.vue",
    "wrapper": "src/views/CloudSyncManagement.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 39,
    "specifier": "../views/DataConsistency.vue",
    "wrapper": "src/views/DataConsistency.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 40,
    "specifier": "../views/TopProducts.vue",
    "wrapper": "src/views/TopProducts.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 41,
    "specifier": "../views/InventoryHealthDashboard.vue",
    "wrapper": "src/views/InventoryHealthDashboard.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 42,
    "specifier": "../views/ProductQualityDashboard.vue",
    "wrapper": "src/views/ProductQualityDashboard.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 43,
    "specifier": "../views/SalesTrendChart.vue",
    "wrapper": "src/views/SalesTrendChart.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 44,
    "specifier": "../views/DataQuarantine.vue",
    "wrapper": "src/views/DataQuarantine.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 45,
    "specifier": "../views/AccountAlignment.vue",
    "wrapper": "src/views/AccountAlignment.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 46,
    "specifier": "../views/SalesDashboard.vue",
    "wrapper": "src/views/SalesDashboard.vue",
    "occurrence": 2
  },
  {
    "routeIndex": 47,
    "specifier": "../views/InventoryDashboardSimple.vue",
    "wrapper": "src/views/InventoryDashboardSimple.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 48,
    "specifier": "../views/UserManagement.vue",
    "wrapper": "src/views/UserManagement.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 49,
    "specifier": "../views/RoleManagement.vue",
    "wrapper": "src/views/RoleManagement.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 50,
    "specifier": "../views/PermissionManagement.vue",
    "wrapper": "src/views/PermissionManagement.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 51,
    "specifier": "../views/target/TargetManagement.vue",
    "wrapper": "src/views/target/TargetManagement.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 52,
    "specifier": "../views/config/SalesTargetManagement.vue",
    "wrapper": "src/views/config/SalesTargetManagement.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 53,
    "specifier": "../views/Debug.vue",
    "wrapper": "src/views/Debug.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 54,
    "specifier": "../views/Test.vue",
    "wrapper": "src/views/Test.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 55,
    "specifier": "../views/collection/CollectionConfig.vue",
    "wrapper": "src/views/collection/CollectionConfig.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 56,
    "specifier": "../views/collection/CollectionCoverageAudit.vue",
    "wrapper": "src/views/collection/CollectionCoverageAudit.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 57,
    "specifier": "../views/collection/CollectionTasks.vue",
    "wrapper": "src/views/collection/CollectionTasks.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 58,
    "specifier": "../views/collection/CollectionHistory.vue",
    "wrapper": "src/views/collection/CollectionHistory.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 59,
    "specifier": "../views/ComponentRecorder.vue",
    "wrapper": "src/views/ComponentRecorder.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 60,
    "specifier": "../views/ComponentVersions.vue",
    "wrapper": "src/views/ComponentVersions.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 61,
    "specifier": "../views/procurement/PurchaseOrders.vue",
    "wrapper": "src/views/procurement/PurchaseOrders.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 62,
    "specifier": "../views/procurement/GRNManagement.vue",
    "wrapper": "src/views/procurement/GRNManagement.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 63,
    "specifier": "../views/procurement/VendorManagement.vue",
    "wrapper": "src/views/procurement/VendorManagement.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 64,
    "specifier": "../views/procurement/InvoiceManagement.vue",
    "wrapper": "src/views/procurement/InvoiceManagement.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 65,
    "specifier": "../views/sales/CustomerManagement.vue",
    "wrapper": "src/views/sales/CustomerManagement.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 66,
    "specifier": "../views/sales/OrderManagement.vue",
    "wrapper": "src/views/sales/OrderManagement.vue",
    "occurrence": 2
  },
  {
    "routeIndex": 67,
    "specifier": "../views/sales/CampaignManagement.vue",
    "wrapper": "src/views/sales/CampaignManagement.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 68,
    "specifier": "../views/finance/ExpenseManagement.vue",
    "wrapper": "src/views/finance/ExpenseManagement.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 69,
    "specifier": "../views/finance/BCostAnalysis.vue",
    "wrapper": "src/views/finance/BCostAnalysis.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 70,
    "specifier": "../views/finance/FinanceReports.vue",
    "wrapper": "src/views/finance/FinanceReports.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 71,
    "specifier": "../views/finance/FXManagement.vue",
    "wrapper": "src/views/finance/FXManagement.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 72,
    "specifier": "../views/finance/FiscalPeriods.vue",
    "wrapper": "src/views/finance/FiscalPeriods.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 73,
    "specifier": "../views/store/StoreAnalytics.vue",
    "wrapper": "src/views/store/StoreAnalytics.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 74,
    "specifier": "../views/reports/SalesReports.vue",
    "wrapper": "src/views/reports/SalesReports.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 75,
    "specifier": "../views/reports/InventoryReports.vue",
    "wrapper": "src/views/reports/InventoryReports.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 76,
    "specifier": "../views/reports/FinanceReportsDetail.vue",
    "wrapper": "src/views/reports/FinanceReportsDetail.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 77,
    "specifier": "../views/reports/VendorReports.vue",
    "wrapper": "src/views/reports/VendorReports.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 78,
    "specifier": "../views/reports/CustomReports.vue",
    "wrapper": "src/views/reports/CustomReports.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 79,
    "specifier": "../views/hr/EmployeeManagement.vue",
    "wrapper": "src/views/hr/EmployeeManagement.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 80,
    "specifier": "../views/hr/MyIncome.vue",
    "wrapper": "src/views/hr/MyIncome.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 81,
    "specifier": "../views/hr/MyFollowInvestmentIncome.vue",
    "wrapper": "src/views/hr/MyFollowInvestmentIncome.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 82,
    "specifier": "../views/hr/EmployeeSalary.vue",
    "wrapper": "src/views/hr/EmployeeSalary.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 83,
    "specifier": "../views/hr/PerformanceManagement.vue",
    "wrapper": "src/views/hr/PerformanceManagement.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 84,
    "specifier": "../views/hr/PerformanceDisplay.vue",
    "wrapper": "src/views/hr/PerformanceDisplay.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 85,
    "specifier": "../views/hr/ShopAssignment.vue",
    "wrapper": "src/views/hr/ShopAssignment.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 86,
    "specifier": "../views/approval/MyTasks.vue",
    "wrapper": "src/views/approval/MyTasks.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 87,
    "specifier": "../views/training/TrainingOverview.vue",
    "wrapper": "src/views/training/TrainingOverview.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 88,
    "specifier": "../views/training/TrainingPrograms.vue",
    "wrapper": "src/views/training/TrainingPrograms.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 89,
    "specifier": "../views/training/TrainingAssignments.vue",
    "wrapper": "src/views/training/TrainingAssignments.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 90,
    "specifier": "../views/training/TrainingAssignmentDetail.vue",
    "wrapper": "src/views/training/TrainingAssignmentDetail.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 91,
    "specifier": "../views/training/TrainingResults.vue",
    "wrapper": "src/views/training/TrainingResults.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 92,
    "specifier": "../views/training/TrainingIntegration.vue",
    "wrapper": "src/views/training/TrainingIntegration.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 93,
    "specifier": "../views/training/MyTraining.vue",
    "wrapper": "src/views/training/MyTraining.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 94,
    "specifier": "../views/approval/MyRequests.vue",
    "wrapper": "src/views/approval/MyRequests.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 95,
    "specifier": "../views/approval/ApprovalHistory.vue",
    "wrapper": "src/views/approval/ApprovalHistory.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 96,
    "specifier": "../views/approval/WorkflowConfig.vue",
    "wrapper": "src/views/approval/WorkflowConfig.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 97,
    "specifier": "../views/messages/SystemNotifications.vue",
    "wrapper": "src/views/messages/SystemNotifications.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 98,
    "specifier": "../views/messages/Alerts.vue",
    "wrapper": "src/views/messages/Alerts.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 99,
    "specifier": "../views/messages/MessageSettings.vue",
    "wrapper": "src/views/messages/MessageSettings.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 100,
    "specifier": "../views/system/SystemLogs.vue",
    "wrapper": "src/views/system/SystemLogs.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 101,
    "specifier": "../views/system/DataBackup.vue",
    "wrapper": "src/views/system/DataBackup.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 102,
    "specifier": "../views/system/SystemMaintenance.vue",
    "wrapper": "src/views/system/SystemMaintenance.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 103,
    "specifier": "../views/system/NotificationConfig.vue",
    "wrapper": "src/views/system/NotificationConfig.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 104,
    "specifier": "../views/help/UserGuide.vue",
    "wrapper": "src/views/help/UserGuide.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 105,
    "specifier": "../views/help/VideoTutorials.vue",
    "wrapper": "src/views/help/VideoTutorials.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 106,
    "specifier": "../views/help/FAQ.vue",
    "wrapper": "src/views/help/FAQ.vue",
    "occurrence": 1
  },
  {
    "routeIndex": 107,
    "specifier": "../views/dev/APIDocs.vue",
    "wrapper": "src/views/dev/APIDocs.vue",
    "occurrence": 1
  }
]

function stripComments(source) {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1')
}

function normalizePath(filePath) {
  return filePath.replace(/\\/g, '/')
}

function extractBlock(source, tagName) {
  const blockPattern = new RegExp(`<${tagName}\\b[^>]*>([\\s\\S]*?)<\\/${tagName}>`, 'i')
  const match = source.match(blockPattern)
  return match ? match[1].trim() : null
}

function isSingleLineDomainImport(scriptBody) {
  const importPattern = /^import\s+([A-Z][A-Za-z0-9_]*)\s+from\s+['"](@\/domains\/[^'"]+)['"]\s*$/s
  return scriptBody.match(importPattern)
}

function isDomainWrapper(source) {
  const templateBody = extractBlock(source, 'template')
  const scriptBody = extractBlock(source, 'script')
  if (!templateBody || !scriptBody || !/<script\s+setup/i.test(source)) {
    return false
  }

  const templateMatch = templateBody.match(/^<([A-Z][A-Za-z0-9_]*)\s*\/?>\s*(?:<\/\1>)?$/s)
  const importMatch = isSingleLineDomainImport(scriptBody)

  return Boolean(templateMatch && importMatch && templateMatch[1] === importMatch[1])
}

function collectRouteWrapperInventory() {
  const routerSource = stripComments(fs.readFileSync(routerPath, 'utf8'))
  const routeImportPattern = /component:\s*\(\)\s*=>\s*import\((['"])([^'"]+)\1\)/g
  const occurrenceCounts = new Map()
  const routeWrapperEntries = []
  let routeIndex = 0

  for (const match of routerSource.matchAll(routeImportPattern)) {
    routeIndex += 1
    const specifier = match[2]
    if (!specifier.includes('../views/')) {
      continue
    }

    const wrapperPath = path.resolve(path.dirname(routerPath), specifier)
    if (!fs.existsSync(wrapperPath)) {
      continue
    }

    const wrapperSource = fs.readFileSync(wrapperPath, 'utf8')
    if (!isDomainWrapper(wrapperSource)) {
      continue
    }

    const occurrence = (occurrenceCounts.get(specifier) || 0) + 1
    occurrenceCounts.set(specifier, occurrence)
    routeWrapperEntries.push({
      routeIndex,
      specifier,
      wrapper: normalizePath(path.relative(frontendRoot, wrapperPath)),
      occurrence,
    })
  }

  return {
    routeWrapperCount: routeWrapperEntries.length,
    uniqueWrapperCount: new Set(routeWrapperEntries.map((entry) => entry.wrapper)).size,
    routeWrapperEntries,
  }
}

test('router wrapper inventory stays on the Phase 6 closure baseline', () => {
  const inventory = collectRouteWrapperInventory()

  assert.equal(inventory.routeWrapperCount, EXPECTED_ROUTE_WRAPPER_COUNT)
  assert.equal(inventory.uniqueWrapperCount, EXPECTED_UNIQUE_WRAPPER_COUNT)
  assert.deepEqual(inventory.routeWrapperEntries, EXPECTED_ROUTE_WRAPPER_ENTRIES)
})
