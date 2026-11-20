import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const repoRoot = resolve(import.meta.dirname, '..')

const shopAssignmentSource = readFileSync(resolve(repoRoot, 'src/domains/business/views/hr/ShopAssignment.vue'), 'utf8')
const financialManagementSource = readFileSync(resolve(repoRoot, 'src/domains/business/views/FinancialManagement.vue'), 'utf8')
const financeDashboardSource = readFileSync(resolve(repoRoot, 'src/domains/business/views/finance-dashboard/FinanceDashboardView.vue'), 'utf8')
const shopAllocationTableSource = readFileSync(resolve(repoRoot, 'src/domains/business/views/finance-dashboard/ShopAllocationTable.vue'), 'utf8')
const performanceManagementSource = readFileSync(resolve(repoRoot, 'src/domains/business/views/hr/PerformanceManagement.vue'), 'utf8')
const performanceDisplaySource = readFileSync(resolve(repoRoot, 'src/domains/business/views/hr/PerformanceDisplay.vue'), 'utf8')

test('ShopAssignment uses shared shop display helpers and shop directory', () => {
  assert.equal(shopAssignmentSource.includes("from '@/utils/shopDisplay'"), true)
  assert.equal(shopAssignmentSource.includes('api.getShopDirectory('), true)
})

test('Financial dashboard pages use shared shop display helpers and shop directory', () => {
  assert.equal(financialManagementSource.includes('FinanceDashboardView'), true)
  assert.equal(financeDashboardSource.includes("from '@/utils/shopDisplay'"), true)
  assert.equal(financeDashboardSource.includes('api.getShopDirectory('), true)
  assert.equal(shopAllocationTableSource.includes("from '@/utils/shopDisplay'"), true)
  assert.equal(shopAllocationTableSource.includes('shop-display-cell'), true)
})

test('Performance management pages use shared shop display helpers and shop directory', () => {
  assert.equal(performanceManagementSource.includes("from '@/utils/shopDisplay'"), true)
  assert.equal(performanceManagementSource.includes('api.getShopDirectory('), true)
  assert.equal(performanceDisplaySource.includes("from '@/utils/shopDisplay'"), true)
  assert.equal(performanceDisplaySource.includes('api.getShopDirectory('), true)
})
