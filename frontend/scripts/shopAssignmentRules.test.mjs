import test from 'node:test'
import assert from 'node:assert/strict'

import {
  exceedsCommissionRatioLimit,
  sumCommissionRatio
} from '../src/domains/business/views/hr/shopAssignmentRules.js'

test('sumCommissionRatio sums valid commission ratios', () => {
  assert.equal(
    sumCommissionRatio([
      { commission_ratio: 0.2 },
      { commission_ratio: 0.35 },
      { commission_ratio: null }
    ]),
    0.55
  )
})

test('exceedsCommissionRatioLimit returns true when total would exceed 100%', () => {
  assert.equal(
    exceedsCommissionRatioLimit(
      [
        { employee_code: 'E001', commission_ratio: 0.6 }
      ],
      0.5
    ),
    true
  )
})

test('exceedsCommissionRatioLimit supports excluding the current assignment during edits', () => {
  assert.equal(
    exceedsCommissionRatioLimit(
      [
        { employee_code: 'E001', commission_ratio: 0.7 },
        { employee_code: 'E002', commission_ratio: 0.2 }
      ],
      0.3,
      (assignment) => assignment.employee_code === 'E002'
    ),
    false
  )
})
