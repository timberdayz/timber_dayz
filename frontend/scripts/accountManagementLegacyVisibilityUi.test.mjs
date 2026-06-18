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
