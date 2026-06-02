import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const menuGroupsPath = path.resolve(__dirname, '../src/config/menuGroups.js')
const menuGroupsSource = fs.readFileSync(menuGroupsPath, 'utf8')

test('sales analytics menu uses shared order-management route instead of retired admin-only alias', () => {
  assert.equal(
    menuGroupsSource.includes("'/sales/order-management'"),
    true,
    'sales analytics group should point to shared order-management route',
  )
  assert.equal(
    menuGroupsSource.includes("'/order-management'"),
    false,
    'sales analytics group should not keep the admin-only order-management alias',
  )
})
