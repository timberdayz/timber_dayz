import test from 'node:test'
import assert from 'node:assert/strict'

import { formatPayrollLockedConflictSummary } from '../src/utils/payrollConflict.js'

test('formatPayrollLockedConflictSummary maps changed field codes to readable Chinese labels', () => {
  const text = formatPayrollLockedConflictSummary([
    {
      employee_code: 'EMP001',
      payroll_status: 'confirmed',
      changed_fields: ['base_salary', 'net_salary', 'total_cost']
    }
  ])

  assert.equal(
    text,
    'EMP001（已确认）: 基本工资、实发工资、公司总成本'
  )
})

test('formatPayrollLockedConflictSummary falls back to count summary when details are absent', () => {
  assert.equal(
    formatPayrollLockedConflictSummary([], 3),
    '共有 3 份已锁定工资单未被覆盖'
  )
})
