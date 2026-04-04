import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const humanResourcesSource = fs.readFileSync(
  path.resolve(__dirname, '../src/views/HumanResources.vue'),
  'utf8'
)
const myIncomeSource = fs.readFileSync(
  path.resolve(__dirname, '../src/views/hr/MyIncome.vue'),
  'utf8'
)
const userGuideSource = fs.readFileSync(
  path.resolve(__dirname, '../src/views/help/UserGuide.vue'),
  'utf8'
)

test('HumanResources page exposes payroll runbook entry', () => {
  assert.equal(
    humanResourcesSource.includes('handleOpenPayrollRunbook') &&
      humanResourcesSource.includes('工资单运行手册') &&
      humanResourcesSource.includes("topic: 'hr-payroll'"),
    true,
    'HumanResources.vue should expose payroll runbook entry linked to hr-payroll guide topic'
  )
})

test('MyIncome page exposes payroll runbook entry', () => {
  assert.equal(
    myIncomeSource.includes('handleOpenPayrollRunbook') &&
      myIncomeSource.includes('工资单运行手册') &&
      myIncomeSource.includes("topic: 'hr-payroll'"),
    true,
    'MyIncome.vue should expose payroll runbook entry linked to hr-payroll guide topic'
  )
})

test('UserGuide page contains dedicated HR payroll guide section', () => {
  assert.equal(
    userGuideSource.includes('hr-payroll') &&
      userGuideSource.includes('HR工资单运行手册') &&
      userGuideSource.includes('HR_PAYROLL_OPERATIONS_RUNBOOK.md'),
    true,
    'UserGuide.vue should contain dedicated HR payroll guide section'
  )
})
