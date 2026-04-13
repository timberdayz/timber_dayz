import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const repoRoot = resolve(import.meta.dirname, '..')
const source = readFileSync(resolve(repoRoot, 'src/views/finance/ExpenseManagement.vue'), 'utf8')

test('ExpenseManagement page uses only marketing fee fields in the expense management chain', () => {
  assert.equal(source.includes('marketing_fee'), true)
  assert.equal(source.includes('total_marketing_fee'), true)
  assert.equal(source.includes('total_salary'), false)
  assert.equal(source.includes('row.salary'), false)
})
