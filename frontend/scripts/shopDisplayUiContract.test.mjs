import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const repoRoot = resolve(import.meta.dirname, '..')
const expenseSource = readFileSync(resolve(repoRoot, 'src/domains/business/views/finance/ExpenseManagement.vue'), 'utf8')
const overviewSource = readFileSync(resolve(repoRoot, 'src/domains/business/views/BusinessOverview.vue'), 'utf8')

test('ExpenseManagement uses shared shop display helpers', () => {
  assert.equal(expenseSource.includes("from '@/utils/shopDisplay'"), true)
  assert.equal(expenseSource.includes('resolveShopDisplay('), true)
})

test('BusinessOverview uses shared shop display helpers', () => {
  assert.equal(overviewSource.includes("from '@/utils/shopDisplay'"), true)
  assert.equal(overviewSource.includes('resolveShopDisplay('), true)
})
