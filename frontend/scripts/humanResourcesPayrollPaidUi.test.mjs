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
const apiSource = fs.readFileSync(
  path.resolve(__dirname, '../src/api/index.js'),
  'utf8'
)

test('HumanResources payroll tab gates paid action behind admin visibility check', () => {
  assert.equal(
    viewSource.includes("scope.row.status === 'confirmed'") &&
      viewSource.includes('showPayrollPayAction') &&
      viewSource.includes('已发放'),
    true,
    'HumanResources.vue should guard 已发放 action with admin visibility check'
  )
})

test('HumanResources payroll tab calls dedicated paid payroll action', () => {
  assert.equal(
    viewSource.includes('markPayrollPaid') && viewSource.includes('api.markHrPayrollRecordPaid'),
    true,
    'HumanResources.vue should define markPayrollPaid and call payroll paid API'
  )
})

test('frontend API exposes payroll paid helper', () => {
  assert.equal(
    apiSource.includes('async markHrPayrollRecordPaid(recordId)'),
    true,
    'frontend API should expose markHrPayrollRecordPaid'
  )
})

test('HumanResources payroll tab derives pay action visibility from auth store roles', () => {
  assert.equal(
    viewSource.includes('useAuthStore') &&
      viewSource.includes('isPayrollAdmin') &&
      viewSource.includes('showPayrollPayAction'),
    true,
    'HumanResources.vue should compute payroll paid visibility from auth store roles'
  )
})
