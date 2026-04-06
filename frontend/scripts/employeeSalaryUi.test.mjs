import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const source = fs.readFileSync(
  path.resolve(__dirname, '../src/views/hr/EmployeeSalary.vue'),
  'utf8'
)

test('EmployeeSalary page contains primary sections', () => {
  for (const label of ['固定薪资', '月度录入', '工资单结果']) {
    assert.equal(source.includes(label), true, `EmployeeSalary.vue should contain section ${label}`)
  }
})

test('EmployeeSalary page contains key salary labels and actions', () => {
  for (const label of [
    '底薪',
    '岗位工资',
    '月度奖金',
    '实发工资',
    '确认工资单',
    '标记已发放'
  ]) {
    assert.equal(source.includes(label), true, `EmployeeSalary.vue should contain label ${label}`)
  }
})
