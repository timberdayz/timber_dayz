import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const viewPath = path.resolve(__dirname, '../src/views/AccountManagement.vue')
const storePath = path.resolve(__dirname, '../src/stores/accounts.js')
const apiPath = path.resolve(__dirname, '../src/api/accounts.js')

const viewSource = fs.readFileSync(viewPath, 'utf8')
const storeSource = fs.readFileSync(storePath, 'utf8')
const apiSource = fs.readFileSync(apiPath, 'utf8')

test('account management exposes current shop discovery entry', () => {
  assert.equal(
    viewSource.includes('探测当前店铺'),
    true,
    'account management should render a current shop discovery action'
  )

  assert.equal(
    viewSource.includes('handleDiscoverCurrentShop'),
    true,
    'account management should wire a discovery handler'
  )
})

test('accounts api and store support current shop discovery workflow', () => {
  assert.equal(
    apiSource.includes('runCurrentShopDiscovery'),
    true,
    'accounts api should expose current shop discovery request'
  )
  assert.equal(
    apiSource.includes('createShopAccountFromDiscovery'),
    true,
    'accounts api should expose create-from-discovery request'
  )
  assert.equal(
    storeSource.includes('runCurrentShopDiscovery'),
    true,
    'accounts store should expose current shop discovery action'
  )
  assert.equal(
    storeSource.includes('createShopAccountFromDiscovery'),
    true,
    'accounts store should expose create-from-discovery action'
  )
})
