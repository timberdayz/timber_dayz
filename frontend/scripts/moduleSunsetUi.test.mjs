import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const menuGroupsPath = path.resolve(__dirname, '../src/config/menuGroups.js')
const routerPath = path.resolve(__dirname, '../src/router/index.js')
const businessOverviewPath = path.resolve(__dirname, '../src/domains/business/views/BusinessOverview.vue')
const dataSyncTemplatesPath = path.resolve(__dirname, '../src/domains/data_platform/views/DataSyncTemplates.vue')

const menuGroupsSource = fs.readFileSync(menuGroupsPath, 'utf8')
const routerSource = fs.readFileSync(routerPath, 'utf8')
const businessOverviewSource = fs.readFileSync(businessOverviewPath, 'utf8')
const dataSyncTemplatesSource = fs.readFileSync(dataSyncTemplatesPath, 'utf8')

test('sunset modules are removed from menu groups while inventory dependencies stay online', () => {
  for (const groupId of ['product-inventory', 'procurement', 'reports']) {
    assert.equal(
      menuGroupsSource.includes(`id: '${groupId}'`),
      false,
      `${groupId} should be removed from sidebar groups`
    )
  }

  for (const routePath of [
    '/inventory-management',
    '/inventory-overview',
    '/inventory/ledger',
    '/inventory/adjustments',
    '/inventory/grns',
    '/inventory/alerts',
    '/inventory/reconciliation',
    '/inventory/aging',
    '/inventory/opening-balances',
    '/inventory-health',
    '/product-quality',
    '/purchase-orders',
    '/grn-management',
    '/vendor-management',
    '/invoice-management',
    '/sales-reports',
    '/inventory-reports',
    '/finance-reports-detail',
    '/vendor-reports',
    '/custom-reports',
  ]) {
    assert.equal(
      routerSource.includes(`path: '${routePath}'`),
      false,
      `${routePath} should be removed from the router`
    )
  }

  assert.equal(
    businessOverviewSource.includes('getBusinessOverviewInventoryBacklog'),
    true,
    'business overview should keep inventory backlog dependency'
  )
  assert.equal(
    businessOverviewSource.includes('loadInventoryBacklog'),
    true,
    'business overview should still load inventory backlog'
  )

  assert.equal(
    dataSyncTemplatesSource.includes(`label="库存" value="inventory"`),
    true,
    'data sync templates should still expose inventory domain'
  )
  assert.equal(
    dataSyncTemplatesSource.includes(`if (domain === 'inventory')`),
    true,
    'data sync templates should keep inventory domain template branch'
  )
})
