import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import {
  collectEstimateOverrides,
  estimateKey,
  indexEstimateRows,
  isAssignmentDirty,
  readBackendAllocatableProfit,
  resolveEstimatedCommission,
  summarizeEmployeeCommissions
} from '../src/domains/business/views/hr/shopAssignmentRules.js'

const repoRoot = resolve(import.meta.dirname, '..')
const rulesSource = readFileSync(
  resolve(repoRoot, 'src/domains/business/views/hr/shopAssignmentRules.js'),
  'utf8'
)
const shopAssignmentSource = readFileSync(
  resolve(repoRoot, 'src/domains/business/views/hr/ShopAssignment.vue'),
  'utf8'
)

const PREVIEW_EMPLOYEE = {
  employee_code: 'EMP260001',
  employee_name: '叶海川',
  performance_score: 85,
  score_coefficient: 1,
  settlement_coefficient: 1,
  calculation_status: 'complete',
  expected_commission: 279.15,
  shops: [
    {
      platform_code: 'shopee',
      shop_id: '1407964586',
      commission_ratio: 0.5,
      allocatable_profit_rate: 0.25,
      allocatable_profit_amount: 120,
      profit_basis_amount: 480,
      shop_coefficient: 1,
      settlement_coefficient: 1,
      estimated_commission: 60,
      commission_zero_reason: null
    },
    {
      platform_code: 'tiktok',
      shop_id: '998877',
      commission_ratio: 0.25,
      allocatable_profit_rate: 0.25,
      allocatable_profit_amount: 875.4,
      profit_basis_amount: 3501.6,
      shop_coefficient: 1,
      settlement_coefficient: 1,
      estimated_commission: 218.85,
      commission_zero_reason: null
    }
  ]
}

test('预计提成取后端 expected_commission，前端不再自己累加', () => {
  const summary = summarizeEmployeeCommissions([PREVIEW_EMPLOYEE])

  assert.equal(summary.length, 1)
  // 后端给 279.15，前端就必须显示 279.15，哪怕前端自己算会算出别的数
  assert.equal(summary[0].estimated_commission, 279.15)
  assert.equal(summary[0].shop_count, 2)
  assert.equal(summary[0].employee_name, '叶海川')
  assert.equal(summary[0].calculation_status, 'complete')
  assert.equal(summary[0].settlement_coefficient, 1)
})

test('层级只展示员工档案的职位名，不再有角色概念', () => {
  const summary = summarizeEmployeeCommissions([PREVIEW_EMPLOYEE], { EMP260001: '总经理' })
  assert.equal(summary[0].position_name, '总经理')
  assert.equal('role' in summary[0], false)

  const fallback = summarizeEmployeeCommissions([PREVIEW_EMPLOYEE])
  assert.equal(fallback[0].position_name, '（未设岗位）')
})

test('前端不再自己算提成：试算改为把输入交给后端', () => {
  const row = {
    _shop: {
      platform_code: 'shopee',
      shop_id: '1407964586',
      allocatable_profit_rate: 0.3,
      _backend_allocatable_profit_rate: 0.25
    },
    _person: {
      employee_code: 'EMP260001',
      commission_ratio: 0.2,
      _backend_commission_ratio: 0.5
    }
  }

  const overrides = collectEstimateOverrides([row])
  assert.equal(overrides.length, 1)
  // 只搬输入：提成比、可分配率。不含任何金额。
  assert.deepEqual(overrides[0], {
    employee_code: 'EMP260001',
    platform_code: 'shopee',
    shop_id: '1407964586',
    commission_ratio: 0.2,
    allocatable_profit_rate: 0.3
  })
  assert.equal('estimated_commission' in overrides[0], false)
  assert.equal('allocatable_profit_amount' in overrides[0], false)
})

test('试算只送「改了还没保存」的行', () => {
  const dirtyRow = {
    _shop: {
      platform_code: 'shopee',
      shop_id: '1407964586',
      allocatable_profit_rate: 0.3,
      _backend_allocatable_profit_rate: 0.25
    },
    _person: {
      employee_code: 'EMP260001',
      commission_ratio: 0.5,
      _backend_commission_ratio: 0.5
    }
  }
  const cleanRow = {
    _shop: {
      platform_code: 'shopee',
      shop_id: '1407964586',
      allocatable_profit_rate: 0.25,
      _backend_allocatable_profit_rate: 0.25
    },
    _person: {
      employee_code: 'EMP260002',
      commission_ratio: 0.5,
      _backend_commission_ratio: 0.5
    }
  }

  const overrides = collectEstimateOverrides([dirtyRow, cleanRow], (row) =>
    isAssignmentDirty(row._shop, row._person)
  )
  assert.equal(overrides.length, 1)
  assert.equal(overrides[0].employee_code, 'EMP260001')
})

test('后端返回的试算行按「员工 × 店铺」建索引', () => {
  const rows = [
    {
      employee_code: 'EMP260001',
      platform_code: 'shopee',
      shop_id: '1407964586',
      estimated_commission: 28.8
    }
  ]
  const index = indexEstimateRows(rows)
  assert.equal(index.get(estimateKey(rows[0])).estimated_commission, 28.8)
  // 平台大小写不同也要对上
  assert.equal(
    estimateKey({ employee_code: 'EMP260001', platform_code: 'ShopEE', shop_id: '1407964586' }),
    'EMP260001|shopee|1407964586'
  )
})

test('有试算结果用试算结果，否则用后端结算预览的金额', () => {
  assert.equal(
    resolveEstimatedCommission({ backendEstimatedCommission: 60, estimateAmount: 28.8 }),
    28.8
  )
  assert.equal(resolveEstimatedCommission({ backendEstimatedCommission: 60, estimateAmount: null }), 60)
  assert.equal(resolveEstimatedCommission({ backendEstimatedCommission: null, estimateAmount: null }), null)
})

test('能否识别「改了还没保存」', () => {
  const shop = { allocatable_profit_rate: 0.25, _backend_allocatable_profit_rate: 0.25 }
  const assignment = { commission_ratio: 0.5, _backend_commission_ratio: 0.5 }

  assert.equal(isAssignmentDirty(shop, assignment), false)

  assert.equal(
    isAssignmentDirty({ ...shop, allocatable_profit_rate: 0.3 }, assignment),
    true
  )
  assert.equal(
    isAssignmentDirty(shop, { ...assignment, commission_ratio: 0.2 }),
    true
  )
})

test('可分配利润直接读后端算好的值', () => {
  assert.equal(readBackendAllocatableProfit({ allocatable_profit_amount: 120 }), 120)
  assert.equal(readBackendAllocatableProfit({ allocatable_profit_amount: 0 }), 0)
  assert.equal(readBackendAllocatableProfit({}), null)
  assert.equal(readBackendAllocatableProfit(null), null)
})

test('前端源码里不得再出现提成/绩效金额公式', () => {
  // 提成公式的真源在 backend/services/commission_caliber.py，前端只能调后端。
  assert.equal(rulesSource.includes('export function calculateAllocatableProfit'), false)
  assert.equal(rulesSource.includes('export function calculateAssignmentCommission'), false)
  assert.equal(rulesSource.includes('export function calculateTrialCommission'), false)
  assert.doesNotMatch(
    rulesSource,
    /profitBasisAmount[\s\S]{0,80}\*\s*allocatableProfitRate[\s\S]{0,80}\*\s*commissionRatio/
  )
  assert.doesNotMatch(rulesSource, /settlement_coefficient\s*\*/)
  assert.doesNotMatch(rulesSource, /score_coefficient\s*\*/)
})

test('店铺归属页消费后端结算预览与后端试算，不再前端拼历史口径默认值', () => {
  assert.match(shopAssignmentSource, /api\.getHrCommissionSettlementPreview\(\{\s*year_month:\s*configMonth\.value\s*\}\)/)
  assert.match(shopAssignmentSource, /api\.postHrCommissionSettlementEstimate\(/)
  assert.equal(shopAssignmentSource.includes('A_PRE_COMMISSION_LABOR_V2'), false)
  assert.equal(shopAssignmentSource.includes("cost_status: 'missing_labor_allocation'"), false)
  assert.match(shopAssignmentSource, /formatBasisVersion\(row\.basis_version\)/)
  // 零提成原因要能显示出来
  assert.match(shopAssignmentSource, /commission_zero_reason/)
})

test('店铺归属页区分「没配可分配率」和「配成 0」', () => {
  assert.match(shopAssignmentSource, /is_allocatable_rate_configured/)
  assert.match(shopAssignmentSource, /allocatableRateTag/)
})

test('页面不再并列展示「未含结算系数」的两套口径', () => {
  assert.equal(shopAssignmentSource.includes('未含结算系数'), false)
  assert.equal(shopAssignmentSource.includes('预计提成（结算口径）'), false)
  assert.match(shopAssignmentSource, /预计提成（实发口径）/)
})
