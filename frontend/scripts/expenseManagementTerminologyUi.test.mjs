import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const repoRoot = resolve(import.meta.dirname, '..')
const source = readFileSync(resolve(repoRoot, 'src/views/finance/ExpenseManagement.vue'), 'utf8')

test('ExpenseManagement page shows marketing terminology instead of salary terminology', () => {
  assert.equal(source.includes('本月营销费用'), true)
  assert.equal(source.includes('年度营销费用'), true)
  assert.equal(source.includes('营销费用(¥)'), true)
  assert.equal(source.includes('本月工资'), false)
  assert.equal(source.includes('年度工资'), false)
  assert.equal(source.includes('工资(¥)'), false)
})
