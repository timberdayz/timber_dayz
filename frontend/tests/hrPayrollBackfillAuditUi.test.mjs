import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const repoRoot = resolve(import.meta.dirname, '..')
const source = readFileSync(
  resolve(repoRoot, 'src/domains/business/views/hr/EmployeeSalary.vue'),
  'utf8',
)

test('payroll draft form records supplement source month and note', () => {
  assert.match(source, /v-model="payrollForm\.backfill_source_month"/)
  assert.match(source, /v-model="payrollForm\.backfill_note"/)
  assert.match(source, /backfill_source_month:\s*payrollForm\.backfill_source_month\s*\|\|\s*null/)
  assert.match(source, /backfill_note:\s*payrollForm\.backfill_note\s*\|\|\s*null/)
})
