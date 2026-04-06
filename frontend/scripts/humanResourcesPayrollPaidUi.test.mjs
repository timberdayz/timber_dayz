import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const viewSource = fs.readFileSync(
  path.resolve(__dirname, '../src/views/HumanResources.vue'),
  'utf8'
)

test('HumanResources salary tab is a migration entry, not the primary salary editor', () => {
  assert.equal(
    viewSource.includes('员工薪资') &&
      viewSource.includes('handleOpenEmployeeSalary') &&
      viewSource.includes('薪资维护已迁移'),
    true,
    'HumanResources.vue salary tab should direct users to the dedicated employee salary page'
  )
})

test('HumanResources salary tab no longer renders payroll primary action buttons', () => {
  assert.equal(
    viewSource.includes('确认工资单') &&
      viewSource.includes('标记已发放') &&
      viewSource.includes('@click="markPayrollPaid(scope.row)"'),
    false,
    'HumanResources.vue salary tab should not expose payroll primary actions after migration'
  )
})
