import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const frontendRoot = path.resolve(scriptDir, '..')
const routerPath = path.join(frontendRoot, 'src/router/index.js')

const EXPECTED_ROUTE_WRAPPER_COUNT = 0
const EXPECTED_UNIQUE_WRAPPER_COUNT = 0
const EXPECTED_DIRECT_DOMAIN_ROUTE_COUNT = 106
const EXPECTED_DIRECT_DOMAIN_COUNTS = {
  business: 52,
  collection: 6,
  data_platform: 9,
  platform: 39,
}
const EXPECTED_WRAPPER_DOMAIN_COUNTS = {}
const EXPECTED_ROUTE_SPECIFIERS = [
  '@/domains/platform/views/Login.vue',
  '@/domains/platform/views/Register.vue',
  '@/domains/platform/views/admin/UserApproval.vue',
  '@/domains/platform/views/approval/TaskDetail.vue',
  '@/domains/platform/views/UltraSimplePage.vue',
  '@/domains/platform/views/TestPage.vue',
  '@/domains/business/views/BusinessOverview.vue',
  '@/domains/business/views/SalesAnalysis.vue',
  '@/domains/business/views/SalesDashboard.vue',
  '@/domains/business/views/sales/OrderManagement.vue',
  '@/domains/business/views/sales/SalesDetailByProduct.vue',
  '@/domains/business/views/inventory/InventoryBalances.vue',
  '@/domains/business/views/InventoryOverview.vue',
  '@/domains/business/views/inventory/InventoryLedger.vue',
  '@/domains/business/views/inventory/InventoryAdjustments.vue',
  '@/domains/business/views/inventory/InventoryGrns.vue',
  '@/domains/business/views/inventory/InventoryAlerts.vue',
  '@/domains/business/views/inventory/InventoryReconciliation.vue',
  '@/domains/business/views/inventory/InventoryAging.vue',
  '@/domains/business/views/inventory/InventoryOpeningBalances.vue',
  '@/domains/business/views/HumanResources.vue',
  '@/domains/business/views/FinancialManagement.vue',
  '@/domains/business/views/StoreManagement.vue',
  '@/domains/platform/views/system/SystemConfig.vue',
  '@/domains/platform/views/system/DatabaseConfig.vue',
  '@/domains/platform/views/system/SecuritySettings.vue',
  '@/domains/platform/views/AccountManagement.vue',
  '@/domains/platform/views/PersonalSettings.vue',
  '@/domains/platform/views/settings/NotificationPreferences.vue',
  '@/domains/platform/views/settings/Sessions.vue',
  '@/domains/data_platform/views/DataSyncFiles.vue',
  '@/domains/data_platform/views/DataSyncFileDetail.vue',
  '@/domains/data_platform/views/DataSyncTasks.vue',
  '@/domains/data_platform/views/DataSyncHistory.vue',
  '@/domains/data_platform/views/DataSyncTemplates.vue',
  '@/domains/data_platform/views/DataSyncRefreshQueue.vue',
  '@/domains/data_platform/views/CloudSyncManagement.vue',
  '@/domains/data_platform/views/DataConsistency.vue',
  '@/domains/business/views/TopProducts.vue',
  '@/domains/business/views/InventoryHealthDashboard.vue',
  '@/domains/business/views/ProductQualityDashboard.vue',
  '@/domains/business/views/SalesTrendChart.vue',
  '@/domains/data_platform/views/DataQuarantine.vue',
  '@/domains/business/views/AccountAlignment.vue',
  '@/domains/business/views/SalesDashboard.vue',
  '@/domains/business/views/InventoryDashboardSimple.vue',
  '@/domains/platform/views/UserManagement.vue',
  '@/domains/platform/views/RoleManagement.vue',
  '@/domains/platform/views/PermissionManagement.vue',
  '@/domains/business/views/target/TargetManagement.vue',
  '@/domains/business/views/config/SalesTargetManagement.vue',
  '@/domains/platform/views/Debug.vue',
  '@/domains/business/views/Test.vue',
  '@/domains/collection/views/collection/CollectionConfig.vue',
  '@/domains/collection/views/collection/CollectionCoverageAudit.vue',
  '@/domains/collection/views/collection/CollectionTasks.vue',
  '@/domains/collection/views/collection/CollectionHistory.vue',
  '@/domains/collection/views/ComponentRecorder.vue',
  '@/domains/collection/views/ComponentVersions.vue',
  '@/domains/business/views/procurement/PurchaseOrders.vue',
  '@/domains/business/views/procurement/GRNManagement.vue',
  '@/domains/business/views/procurement/VendorManagement.vue',
  '@/domains/business/views/procurement/InvoiceManagement.vue',
  '@/domains/business/views/sales/CustomerManagement.vue',
  '@/domains/business/views/sales/OrderManagement.vue',
  '@/domains/business/views/sales/CampaignManagement.vue',
  '@/domains/business/views/finance/ExpenseManagement.vue',
  '@/domains/business/views/finance/BCostAnalysis.vue',
  '@/domains/business/views/finance/FinanceReports.vue',
  '@/domains/business/views/finance/FXManagement.vue',
  '@/domains/business/views/finance/FiscalPeriods.vue',
  '@/domains/business/views/store/StoreAnalytics.vue',
  '@/domains/business/views/reports/SalesReports.vue',
  '@/domains/business/views/reports/InventoryReports.vue',
  '@/domains/business/views/reports/FinanceReportsDetail.vue',
  '@/domains/business/views/reports/VendorReports.vue',
  '@/domains/business/views/reports/CustomReports.vue',
  '@/domains/business/views/hr/EmployeeManagement.vue',
  '@/domains/business/views/hr/MyIncome.vue',
  '@/domains/business/views/hr/MyFollowInvestmentIncome.vue',
  '@/domains/business/views/hr/EmployeeSalary.vue',
  '@/domains/business/views/hr/PerformanceManagement.vue',
  '@/domains/business/views/hr/PerformanceDisplay.vue',
  '@/domains/business/views/hr/ShopAssignment.vue',
  '@/domains/platform/views/approval/MyTasks.vue',
  '@/domains/platform/views/training/TrainingOverview.vue',
  '@/domains/platform/views/training/TrainingPrograms.vue',
  '@/domains/platform/views/training/TrainingAssignments.vue',
  '@/domains/platform/views/training/TrainingAssignmentDetail.vue',
  '@/domains/platform/views/training/TrainingResults.vue',
  '@/domains/platform/views/training/TrainingIntegration.vue',
  '@/domains/platform/views/training/MyTraining.vue',
  '@/domains/platform/views/approval/MyRequests.vue',
  '@/domains/platform/views/approval/ApprovalHistory.vue',
  '@/domains/platform/views/approval/WorkflowConfig.vue',
  '@/domains/platform/views/messages/SystemNotifications.vue',
  '@/domains/platform/views/messages/Alerts.vue',
  '@/domains/platform/views/messages/MessageSettings.vue',
  '@/domains/platform/views/system/SystemLogs.vue',
  '@/domains/platform/views/system/DataBackup.vue',
  '@/domains/platform/views/system/SystemMaintenance.vue',
  '@/domains/platform/views/system/NotificationConfig.vue',
  '@/domains/platform/views/help/UserGuide.vue',
  '@/domains/platform/views/help/VideoTutorials.vue',
  '@/domains/platform/views/help/FAQ.vue',
  '@/domains/platform/views/dev/APIDocs.vue',
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

function collectRouteOwnershipInventory() {
  const routerSource = stripComments(fs.readFileSync(routerPath, 'utf8'))
  const routeImportPattern = /component:\s*\(\)\s*=>\s*import\((['"])([^'"]+)\1\)/g
  const occurrenceCounts = new Map()
  const directDomainCounts = new Map()
  const wrapperDomainCounts = new Map()
  const directRouteSpecifiers = []
  const routeWrapperEntries = []
  let directDomainRouteCount = 0
  let routeIndex = 0

  for (const match of routerSource.matchAll(routeImportPattern)) {
    routeIndex += 1
    const specifier = match[2]
    const directDomainMatch = specifier.match(/^@\/domains\/([^/]+)\/views\//)
    if (directDomainMatch) {
      const domainName = directDomainMatch[1]
      directDomainRouteCount += 1
      directDomainCounts.set(domainName, (directDomainCounts.get(domainName) || 0) + 1)
      directRouteSpecifiers.push(specifier)
      continue
    }

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
    const wrapperImportMatch = extractBlock(wrapperSource, 'script')?.match(/@\/domains\/([^/]+)\//)
    if (wrapperImportMatch) {
      const domainName = wrapperImportMatch[1]
      wrapperDomainCounts.set(domainName, (wrapperDomainCounts.get(domainName) || 0) + 1)
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
    directDomainRouteCount,
    directDomainCounts: Object.fromEntries(
      [...directDomainCounts.entries()].sort(([left], [right]) => left.localeCompare(right)),
    ),
    directRouteSpecifiers,
    wrapperDomainCounts: Object.fromEntries(
      [...wrapperDomainCounts.entries()].sort(([left], [right]) => left.localeCompare(right)),
    ),
    routeWrapperCount: routeWrapperEntries.length,
    uniqueWrapperCount: new Set(routeWrapperEntries.map((entry) => entry.wrapper)).size,
    routeWrapperEntries,
  }
}

test('router route ownership matches the post-migration domain baseline', () => {
  const inventory = collectRouteOwnershipInventory()

  assert.equal(inventory.directDomainRouteCount, EXPECTED_DIRECT_DOMAIN_ROUTE_COUNT)
  assert.deepEqual(inventory.directDomainCounts, EXPECTED_DIRECT_DOMAIN_COUNTS)
  assert.deepEqual(inventory.directRouteSpecifiers, EXPECTED_ROUTE_SPECIFIERS)
  assert.deepEqual(inventory.wrapperDomainCounts, EXPECTED_WRAPPER_DOMAIN_COUNTS)
  assert.equal(inventory.routeWrapperCount, EXPECTED_ROUTE_WRAPPER_COUNT)
  assert.equal(inventory.uniqueWrapperCount, EXPECTED_UNIQUE_WRAPPER_COUNT)
})
