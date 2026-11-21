import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

import {
  collectEstimateOverrides,
  estimateKey,
  exceedsCommissionRatioLimit,
  indexEstimateRows,
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

test('前端不再自己算提成：试算只把输入交给后端', () => {
  const row = {
    _shop: {
      platform_code: 'shopee',
      shop_id: 'S1',
      allocatable_profit_rate: 0.3,
      _backend_allocatable_profit_rate: 0.25
    },
    _person: {
      employee_code: 'E001',
      commission_ratio: 0.2,
      _backend_commission_ratio: 0.5
    }
  }

  const overrides = collectEstimateOverrides([row])
  assert.equal(overrides.length, 1)
  assert.deepEqual(overrides[0], {
    employee_code: 'E001',
    platform_code: 'shopee',
    shop_id: 'S1',
    commission_ratio: 0.2,
    allocatable_profit_rate: 0.3
  })
  // 金额必须由后端算，前端不产金额
  assert.equal('estimated_commission' in overrides[0], false)
})

test('后端试算结果按「员工 × 店铺」对齐，平台大小写不敏感', () => {
  const rows = [
    { employee_code: 'E001', platform_code: 'shopee', shop_id: 'S1', estimated_commission: 28.8 }
  ]
  const index = indexEstimateRows(rows)
  assert.equal(index.get(estimateKey(rows[0])).estimated_commission, 28.8)
  assert.equal(estimateKey({ employee_code: 'E001', platform_code: 'ShopEE', shop_id: 'S1' }), 'E001|shopee|S1')
})

test('有试算金额用试算金额，否则用后端结算预览的金额', () => {
  assert.equal(resolveEstimatedCommission({ backendEstimatedCommission: 60, estimateAmount: 28.8 }), 28.8)
  assert.equal(resolveEstimatedCommission({ backendEstimatedCommission: 60, estimateAmount: null }), 60)
  assert.equal(resolveEstimatedCommission({ backendEstimatedCommission: null, estimateAmount: null }), null)
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
