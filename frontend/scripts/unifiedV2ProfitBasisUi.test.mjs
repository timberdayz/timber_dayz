import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const apiSource = fs.readFileSync(path.resolve(__dirname, '../src/api/index.js'), 'utf8')
const salarySource = fs.readFileSync(
  path.resolve(__dirname, '../src/domains/business/views/hr/EmployeeSalary.vue'),
  'utf8'
)
const assignmentSource = fs.readFileSync(
  path.resolve(__dirname, '../src/domains/business/views/hr/ShopAssignment.vue'),
  'utf8'
)

test('frontend API exposes the fixed labor cost policy read helper', () => {
  assert.match(apiSource, /getHrLaborCostPolicy\s*\(\s*\)/)
  assert.match(apiSource, /['"]\/hr\/labor-cost-policy['"]/
  )
})

test('EmployeeSalary displays the system-wide fixed V2 labor cost policy', () => {
  assert.match(salarySource, /当前系统利润基数口径/)
  assert.match(salarySource, /A_PRE_COMMISSION_LABOR_V2/)
  assert.match(salarySource, /laborCostPolicy/)
})

test('ShopAssignment displays V2 cost breakdown and missing allocation warning', () => {
  for (const label of ['其他经营成本', '提成前人力成本', 'A类成本', 'V2']) {
    assert.match(assignmentSource, new RegExp(label))
  }
  assert.match(assignmentSource, /pre_commission_labor_cost_amount/)
  assert.match(assignmentSource, /cost_status/)
  assert.match(assignmentSource, /缺少.*人力成本分摊|人力成本分摊.*缺失/)
})
