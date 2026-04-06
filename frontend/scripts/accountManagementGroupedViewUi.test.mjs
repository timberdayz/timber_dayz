import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const viewPath = path.resolve(__dirname, '../src/views/AccountManagement.vue')
const source = fs.readFileSync(viewPath, 'utf8')

test('account management exposes grouped navigator and detail workspace', () => {
  assert.equal(
    source.includes('account-management-workspace'),
    true,
    'account management should expose a grouped master-detail workspace'
  )

  assert.equal(
    source.includes('account-management-navigator'),
    true,
    'account management should render a left-side main-account navigator'
  )

  assert.equal(
    source.includes('current-main-account-summary'),
    true,
    'account management should render a current main-account summary panel'
  )

  assert.equal(
    source.includes('current-main-account-shops'),
    true,
    'account management should render a current main-account scoped shop table'
  )
})

test('account management exposes grouped empty state copy', () => {
  assert.equal(
    source.includes('暂时没有符合条件的主账号或店铺账号'),
    true,
    'account management should explain when grouped results are empty'
  )
})

test('account management no longer keeps the legacy hidden full-table block', () => {
  assert.equal(
    source.includes('v-if="false" class="table-card"'),
    false,
    'account management should remove the hidden legacy table block after the grouped layout ships'
  )
})

test('current main-account actions prefill dialogs from the selected context', () => {
  assert.equal(
    source.includes('openCreateDialogForSelectedMainAccount'),
    true,
    'account management should expose a selected-main-account create action'
  )

  assert.equal(
    source.includes('openBatchDialogForSelectedMainAccount'),
    true,
    'account management should expose a selected-main-account batch create action'
  )
})

test('account management highlights navigator anomalies and exposes quick shop filters', () => {
  assert.equal(
    source.includes("'has-warning': mainAccount.missingShopIdCount > 0"),
    true,
    'account management should visually highlight main accounts with missing shop ids'
  )

  assert.equal(
    source.includes('shopQuickFilter'),
    true,
    'account management should expose a quick filter state for the selected shop table'
  )

  assert.equal(
    source.includes('filteredSelectedMainAccountShops'),
    true,
    'account management should derive a filtered shop list for the selected main account'
  )
})
