import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const viewSource = fs.readFileSync(
  path.resolve(__dirname, '../src/domains/platform/views/AccountManagement.vue'),
  'utf8'
)
const storeSource = fs.readFileSync(
  path.resolve(__dirname, '../src/stores/accounts.js'),
  'utf8'
)
const apiSource = fs.readFileSync(
  path.resolve(__dirname, '../src/api/accounts.js'),
  'utf8'
)

test('account management distinguishes operating stores from collection sources', () => {
  assert.equal(viewSource.includes('data-testid="business-role-operating-store"'), true)
  assert.equal(viewSource.includes('data-testid="business-role-collection-source"'), true)
  assert.equal(viewSource.includes('business_role'), true)
})

test('accounts store and API preserve business role through management flows and statistics', () => {
  assert.equal(storeSource.includes("business_role: shopAccount.business_role || 'operating_store'"), true)
  assert.equal(storeSource.includes('business_role: data.business_role'), true)
  assert.equal(apiSource.includes('operating_store'), true)
  assert.equal(apiSource.includes('collection_source'), true)
})
