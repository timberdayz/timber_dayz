import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const source = fs.readFileSync(
  path.resolve(__dirname, '../src/views/hr/MyIncome.vue'),
  'utf8'
)

test('MyIncome page renders grouped payroll detail sections', () => {
  for (const label of ['应发项', '扣除项', '公司成本']) {
    assert.equal(source.includes(label), true, `MyIncome.vue should contain section ${label}`)
  }
})

test('MyIncome page exposes key payroll detail fields', () => {
  for (const label of [
    '岗位工资',
    '绩效工资',
    '加班费',
    '奖金',
    '应发合计',
    '个人社保',
    '个人公积金',
    '个税',
    '其他扣款',
    '扣款合计',
    '公司社保',
    '公司公积金',
    '公司总成本'
  ]) {
    assert.equal(source.includes(label), true, `MyIncome.vue should contain payroll label ${label}`)
  }
})
