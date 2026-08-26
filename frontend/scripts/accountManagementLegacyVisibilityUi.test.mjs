import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const viewPath = path.resolve(__dirname, '../src/domains/platform/views/AccountManagement.vue')
const storePath = path.resolve(__dirname, '../src/stores/accounts.js')
const apiPath = path.resolve(__dirname, '../src/api/accounts.js')
const viewSource = fs.readFileSync(viewPath, 'utf8')
const storeSource = fs.readFileSync(storePath, 'utf8')
const apiSource = fs.readFileSync(apiPath, 'utf8')
const updateAccountSource = storeSource.slice(storeSource.indexOf('async updateAccount('))

test('account management exposes legacy visibility switch', () => {
  assert.equal(
    viewSource.includes('v-model="filters.include_disabled"'),
    true,
    'account management should expose a toggle for historical disabled records'
  )
})

test('accounts store does not hard-force enabled=true when historical records are visible', () => {
  assert.equal(
    storeSource.includes('const defaultEnabled = mergedParams.include_disabled ? mergedParams.enabled : true'),
    false,
    'accounts store should not force enabled=true when the UI can show historical disabled records'
  )
})

test('accounts api stats include disabled shop accounts in the total dataset', () => {
  assert.equal(
    apiSource.includes('await this.listShopAccounts({ include_disabled: true })'),
    true,
    'account statistics should request the full shop-account dataset, including disabled records'
  )
})

test('shop status updates do not clear platform shop id when shop id is omitted', () => {
  assert.equal(
    updateAccountSource.includes('platform_shop_id: data.shop_id || null'),
    false,
    'status-only updates must not turn an omitted shop id into null'
  )
  assert.equal(
    storeSource.includes("Object.prototype.hasOwnProperty.call(source, key)") &&
      storeSource.includes("hasOwn(data, 'shop_id')"),
    true,
    'platform shop id updates must distinguish omitted and explicitly cleared values'
  )
})

test('disabled quick filter is backed by a loaded disabled-record path', () => {
  assert.equal(
    storeSource.includes('const shouldIncludeDisabled = Boolean(mergedParams.include_disabled)'),
    true,
    'store should expose an explicit path for loading disabled records'
  )
  assert.equal(
    viewSource.includes("case 'disabled':\n      return shops.filter((shop) => !shop.enabled)"),
    true,
    'disabled quick filter should filter the loaded shop collection'
  )
  assert.equal(
    viewSource.includes('@change="handleShopQuickFilterChange"'),
    true,
    'disabled quick filter should load historical records when needed'
  )
  assert.equal(
    viewSource.includes('filters.enabled = null'),
    true,
    'quick filters should clear a conflicting top-level enabled filter'
  )
  assert.equal(
    viewSource.includes('显示历史记录'),
    true,
    'account management should keep a visible recovery path for disabled shops'
  )
  assert.equal(
    viewSource.includes('缺少平台店铺ID'),
    true,
    'disabled shop rows with no platform id should expose an explicit anomaly label'
  )
  assert.equal(
    viewSource.includes("String(row.shop_id || '').trim()"),
    true,
    'platform shop id display should treat whitespace-only values as missing'
  )
  assert.equal(
    viewSource.includes("shopQuickFilter.value = 'all'"),
    true,
    'turning off history should not leave a disabled quick filter selected'
  )
})
