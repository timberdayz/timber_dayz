import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const repoRoot = resolve(import.meta.dirname, '..')
const source = readFileSync(resolve(repoRoot, 'src/views/finance/ExpenseManagement.vue'), 'utf8')

test('ExpenseManagement page replaces add-all-shops action with quick split flow', () => {
  assert.equal(source.includes('为所有店铺添加'), false)
  assert.equal(source.includes('快速拆分'), true)
  assert.equal(source.includes('平均分摊到当前全部店铺'), true)
  assert.equal(source.includes('handleApplyQuickSplit'), true)
})
