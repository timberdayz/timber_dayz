import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const source = fs.readFileSync(
  path.resolve(__dirname, '../src/domains/business/views/hr/EmployeeSalary.vue'),
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

test('EmployeeSalary page filters salary chain to employee identity', () => {
  assert.equal(
    source.includes("employee.employee_identity_type === 'employee'"),
    true,
    'EmployeeSalary.vue should only expose employee identity rows in salary page'
  )
})

test('EmployeeSalary page exposes batch payroll refresh action', () => {
  assert.equal(
    source.includes('handleBatchRefreshPayroll') && source.includes('按月份批量刷新全部工资单'),
    true,
    'EmployeeSalary.vue should contain month-level batch payroll refresh action'
  )
})

test('EmployeeSalary page keeps manual input separate from payroll generation', () => {
  assert.equal(source.includes('保存月度人工录入'), true)
  assert.equal(source.includes('尚未生成工资单，请先完成月度计算'), true)
  assert.equal(source.includes('performance_package_amount'), true)
  assert.equal(
    source.includes('const loadPayrollDataForEmployee = async () => {\n  await loadPayrollRecord()\n  await loadPayrollManualInput()'),
    true
  )
})
