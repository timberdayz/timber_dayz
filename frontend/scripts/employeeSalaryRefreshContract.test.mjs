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

test('EmployeeSalary refresh flow accepts interceptor-unwrapped payroll payloads', () => {
  assert.equal(source.includes('const record = response?.data || response || null'), true)
  assert.equal(source.includes('applyPayrollRecord(record)'), true)
})
