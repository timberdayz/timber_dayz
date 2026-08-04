import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const source = fs.readFileSync(
  path.resolve(__dirname, '../src/domains/business/views/finance/ExpenseManagement.vue'),
  'utf8'
)

test('Expense management excludes system-projected labor from save payloads', () => {
  assert.equal(source.includes('const laborCostForPayload'), true)
  assert.equal(source.includes("row.labor_cost_source === 'system' ? 0"), true)
  assert.equal(source.includes('labor_cost: laborCostForPayload(row)'), true)
})
