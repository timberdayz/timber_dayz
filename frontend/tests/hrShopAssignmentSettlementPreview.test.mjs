import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import {
  calculateTrialCommission,
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

test('员工角色来自归属配置，预览接口不返回角色', () => {
  const summary = summarizeEmployeeCommissions([PREVIEW_EMPLOYEE], { EMP260001: 'supervisor' })
  assert.equal(summary[0].role, 'supervisor')

  const fallback = summarizeEmployeeCommissions([PREVIEW_EMPLOYEE])
  assert.equal(fallback[0].role, 'operator')
})

test('未保存编辑的试算 = 利润基数 × 可分配率 × 提成比 × 结算系数', () => {
  // 480 × 0.25 × 0.5 × 1.0 = 60
  assert.equal(
    calculateTrialCommission({
      profit_basis_amount: 480,
      allocatable_profit_rate: 0.25,
      commission_ratio: 0.5,
      settlement_coefficient: 1
    }),
    60
  )

  // 结算系数压档后金额同步下调：480 × 0.25 × 0.5 × 0.8 = 48
  assert.equal(
    calculateTrialCommission({
      profit_basis_amount: 480,
      allocatable_profit_rate: 0.25,
      commission_ratio: 0.5,
      settlement_coefficient: 0.8
    }),
    48
  )
})

test('试算不会把负的利润基数算成负提成', () => {
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

test('没改过就显示后端值，改了还没保存才走前端试算', () => {
  const trial = {
    profit_basis_amount: 480,
    allocatable_profit_rate: 0.25,
    commission_ratio: 0.5,
    settlement_coefficient: 1
  }

  assert.equal(
    resolveEstimatedCommission({ backendEstimatedCommission: 60, dirty: false, trial }),
    60
  )
  assert.equal(
    resolveEstimatedCommission({ backendEstimatedCommission: 60, dirty: true, trial }),
    60
  )

  // 改了提成比：0.5 -> 0.2，480 × 0.25 × 0.2 × 1 = 24
  assert.equal(
    resolveEstimatedCommission({
      backendEstimatedCommission: 60,
      dirty: true,
      trial: { ...trial, commission_ratio: 0.2 }
    }),
    24
  )

  // 后端没有这条（例如刚新增还没保存）时只能试算
  assert.equal(
    resolveEstimatedCommission({ backendEstimatedCommission: null, dirty: false, trial }),
    60
  )
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

test('前端不再自己实现后端的可分配利润 / 提成公式', () => {
  assert.equal(rulesSource.includes('export function calculateAllocatableProfit'), false)
  assert.equal(rulesSource.includes('export function calculateAssignmentCommission'), false)
  // 试算只允许这一条乘法链
  assert.match(rulesSource, /Math\.max\(profitBasisAmount, 0\) \* allocatableProfitRate \* commissionRatio \* coefficient/)
})

test('店铺归属页消费后端结算预览，不再前端拼历史口径默认值', () => {
  assert.match(shopAssignmentSource, /api\.getHrCommissionSettlementPreview\(\{\s*year_month:\s*configMonth\.value\s*\}\)/)
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
