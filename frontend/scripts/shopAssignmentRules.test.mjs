import test from 'node:test'
import assert from 'node:assert/strict'

import {
  calculateAllocatableProfit,
  calculateAssignmentCommission,
  exceedsCommissionRatioLimit,
  inferAssignmentRole,
  setShopAllocatableProfitRate,
  summarizeEmployeeCommissions,
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

test('setShopAllocatableProfitRate syncs table row and source shop object', () => {
  const shop = { allocatable_profit_rate: 0 }
  const row = { _shop: shop, allocatable_profit_rate: 0 }

  setShopAllocatableProfitRate(row, 45)

  assert.equal(row.allocatable_profit_rate, 0.45)
  assert.equal(shop.allocatable_profit_rate, 0.45)
})

test('inferAssignmentRole maps supervisor-like positions and defaults to operator', () => {
  assert.equal(inferAssignmentRole({ position_name: '店铺主管' }), 'supervisor')
  assert.equal(inferAssignmentRole({ position_code: 'SUPV' }), 'supervisor')
  assert.equal(inferAssignmentRole({ position_name: 'Operations Manager' }), 'supervisor')
  assert.equal(inferAssignmentRole({ position_name: '' }), 'operator')
  assert.equal(inferAssignmentRole(null), 'operator')
})

test('calculateAllocatableProfit uses net profit times allocatable rate', () => {
  assert.equal(
    calculateAllocatableProfit({ profit_basis_amount: 10000, allocatable_profit_rate: 0.3 }),
    3000
  )
})

test('calculateAllocatableProfit floors negative net profit at zero', () => {
  assert.equal(
    calculateAllocatableProfit({ profit_basis_amount: -1000, allocatable_profit_rate: 0.25 }),
    0
  )
})

test('calculateAssignmentCommission uses net profit, allocatable rate, and person ratio', () => {
  assert.equal(
    calculateAssignmentCommission(
      { profit_basis_amount: 10000, allocatable_profit_rate: 0.3 },
      { commission_ratio: 0.05 }
    ),
    150
  )
})

test('summarizeEmployeeCommissions does not let negative net profit reduce employee total', () => {
  const rows = [
    {
      profit_basis_amount: 1000,
      allocatable_profit_rate: 0.25,
      assignments: [
        { employee_code: 'E001', employee_name: 'Alice', role: 'supervisor', commission_ratio: 0.25 }
      ]
    },
    {
      profit_basis_amount: -1000,
      allocatable_profit_rate: 0.25,
      assignments: [
        { employee_code: 'E001', employee_name: 'Alice', role: 'supervisor', commission_ratio: 0.25 }
      ]
    }
  ]

  assert.deepEqual(summarizeEmployeeCommissions(rows), [
    {
      employee_code: 'E001',
      employee_name: 'Alice',
      role: 'supervisor',
      shop_count: 2,
      estimated_commission: 62.5
    }
  ])
})

test('summarizeEmployeeCommissions totals estimated monthly commission by employee', () => {
  const rows = [
    {
      profit_basis_amount: 10000,
      allocatable_profit_rate: 0.3,
      assignments: [
        { employee_code: 'E001', employee_name: 'Alice', role: 'supervisor', commission_ratio: 0.05 },
        { employee_code: 'E002', employee_name: 'Bob', role: 'operator', commission_ratio: 0.03 }
      ]
    },
    {
      profit_basis_amount: 5000,
      allocatable_profit_rate: 0.4,
      assignments: [
        { employee_code: 'E001', employee_name: 'Alice', role: 'supervisor', commission_ratio: 0.05 }
      ]
    },
    {
      profit_basis_amount: 9000,
      allocatable_profit_rate: 0.2,
      assignments: []
    }
  ]

  assert.deepEqual(summarizeEmployeeCommissions(rows), [
    {
      employee_code: 'E001',
      employee_name: 'Alice',
      role: 'supervisor',
      shop_count: 2,
      estimated_commission: 250
    },
    {
      employee_code: 'E002',
      employee_name: 'Bob',
      role: 'operator',
      shop_count: 1,
      estimated_commission: 90
    }
  ])
})
