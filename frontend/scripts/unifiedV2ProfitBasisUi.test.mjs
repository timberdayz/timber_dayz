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

test('EmployeeSalary displays the system-wide fixed profit basis policy as a business label', () => {
  assert.match(salarySource, /当前系统利润基数口径/)
  assert.match(salarySource, /formatBasisVersion\(laborCostPolicy\.basis_version\)/)
  assert.match(salarySource, /laborCostPolicy/)
  // 前端不再硬编码历史口径（历史口径只用于识别旧快照）
  assert.equal(salarySource.includes("basis_version: 'A_PRE_COMMISSION_LABOR_V2'"), false)
})

test('ShopAssignment displays the cost breakdown and missing allocation warning', () => {
  // 列标题不再叫「V2成本明细」：系统只有一套结算口径，
  // 页面上不该再出现 V1 / V2 这种过渡期命名。
  for (const label of ['其他经营成本', '提成前人力成本', 'A类成本', '成本明细']) {
    assert.match(assignmentSource, new RegExp(label))
  }
  assert.match(assignmentSource, /pre_commission_labor_cost_amount/)
  assert.match(assignmentSource, /cost_status/)
  assert.match(assignmentSource, /缺少.*人力成本分摊|人力成本分摊.*缺失/)
  assert.doesNotMatch(assignmentSource, /V2成本明细/)
})
