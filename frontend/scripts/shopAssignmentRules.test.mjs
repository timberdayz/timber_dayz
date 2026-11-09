import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

import {
  calculateTrialCommission,
  exceedsCommissionRatioLimit,
  inferAssignmentRole,
  isAssignmentDirty,
  readBackendAllocatableProfit,
  resolveEstimatedCommission,
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

test('calculateTrialCommission uses backend profit basis, rate, ratio and settlement coefficient', () => {
  assert.equal(
    calculateTrialCommission({
      profit_basis_amount: 480,
      allocatable_profit_rate: 0.25,
      commission_ratio: 0.5,
      settlement_coefficient: 1
    }),
    60
  )
})

test('calculateTrialCommission floors negative profit basis at zero', () => {
  assert.equal(
    calculateTrialCommission({
      profit_basis_amount: -480,
      allocatable_profit_rate: 0.25,
      commission_ratio: 0.5,
      settlement_coefficient: 1
    }),
    0
  )
})

test('summarizeEmployeeCommissions reads backend expected_commission instead of recomputing', () => {
  const previewEmployees = [
    {
      employee_code: 'E001',
      employee_name: 'Alice',
      calculation_status: 'complete',
      score_coefficient: 1,
      settlement_coefficient: 1,
      expected_commission: 279.15,
      shops: [
        { platform_code: 'shopee', shop_id: 'S1', estimated_commission: 60 },
        { platform_code: 'tiktok', shop_id: 'S2', estimated_commission: 219.15 }
      ]
    }
  ]

  assert.deepEqual(summarizeEmployeeCommissions(previewEmployees, { E001: 'supervisor' }), [
    {
      employee_code: 'E001',
      employee_name: 'Alice',
      role: 'supervisor',
      shop_count: 2,
      estimated_commission: 279.15,
      calculation_status: 'complete',
      performance_score: null,
      score_coefficient: 1,
      settlement_coefficient: 1
    }
  ])
})

test('summarizeEmployeeCommissions sorts employees by backend expected_commission', () => {
  const previewEmployees = [
    {
      employee_code: 'E001',
      employee_name: 'Alice',
      expected_commission: 250,
      shops: [{ platform_code: 'shopee', shop_id: 'S1' }, { platform_code: 'shopee', shop_id: 'S2' }]
    },
    {
      employee_code: 'E002',
      employee_name: 'Bob',
      expected_commission: 90,
      shops: [{ platform_code: 'shopee', shop_id: 'S1' }]
    },
    {
      employee_code: 'E003',
      employee_name: 'Carol',
      expected_commission: 0,
      shops: []
    }
  ]

  const summary = summarizeEmployeeCommissions(previewEmployees, { E001: 'supervisor', E002: 'operator' })
  assert.deepEqual(summary.map((item) => item.employee_code), ['E001', 'E002', 'E003'])
  assert.deepEqual(summary.map((item) => item.estimated_commission), [250, 90, 0])
  assert.deepEqual(summary.map((item) => item.shop_count), [2, 1, 0])
})

test('shop assignment page does not expose a fake add-all-shops action', () => {
  const source = readFileSync('src/domains/business/views/hr/ShopAssignment.vue', 'utf8')
  assert.equal(source.includes('为所有店铺添加'), false)
  assert.equal(source.includes('handleAddAllShops'), false)
})
