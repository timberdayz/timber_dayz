import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const source = fs.readFileSync(
  path.resolve(__dirname, '../src/views/hr/ShopAssignment.vue'),
  'utf8'
)

test('ShopAssignment page shows both analysis profit and settlement net profit', () => {
  assert.equal(source.includes('当月利润'), true)
  assert.equal(source.includes('当月净利润'), true)
  assert.equal(source.includes('profit_basis_amount'), true)
})

test('ShopAssignment page uses net-profit wording for allocation and payout labels', () => {
  assert.equal(source.includes('可分配净利润率'), true)
  assert.equal(source.includes('主管提成'), true)
  assert.equal(source.includes('操作员提成'), true)
})
