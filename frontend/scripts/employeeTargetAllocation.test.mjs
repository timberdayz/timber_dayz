import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

import * as targetUtils from '../src/domains/business/views/target/personTargetUtils.js'
import * as assignmentRules from '../src/domains/business/views/hr/shopAssignmentRules.js'

test('personal target summary exposes allocated shop targets, actuals, and achievement rates', () => {
  assert.equal(typeof targetUtils.buildEmployeeTargetSummary, 'function')

  const summary = targetUtils.buildEmployeeTargetSummary({
    employee_code: 'E1',
    assignments: [
      {
        platform_code: 'shopee',
        shop_id: 'S1',
        shop_name: '店铺一',
        target_allocation_ratio: 0.5,
        sales_target: 1000,
        sales_actual: 400,
        gross_profit_target: 200,
        gross_profit_actual: 100
      }
    ]
  })

  assert.deepEqual(summary.shops[0], {
    shop_name: '店铺一',
    target_allocation_ratio: 0.5,
    sales_target: 500,
    sales_actual: 200,
    sales_achievement_rate: 0.4,
    gross_profit_target: 100,
    gross_profit_actual: 50,
    gross_profit_achievement_rate: 0.5
  })
  assert.equal(summary.sales_target, 500)
  assert.equal(summary.sales_actual, 200)
  assert.equal(summary.sales_achievement_rate, 0.4)
})

test('personal target summary keeps API values that are already allocated', () => {
  const summary = targetUtils.buildEmployeeTargetSummary({
    valuesAlreadyAllocated: true,
    assignments: [{
      shop_name: '店铺一',
      target_allocation_ratio: 0.5,
      sales_target: 500,
      sales_actual: 200,
      gross_profit_target: 100,
      gross_profit_actual: 50
    }]
  })

  assert.equal(summary.sales_target, 500)
  assert.equal(summary.sales_actual, 200)
  assert.equal(summary.gross_profit_target, 100)
  assert.equal(summary.gross_profit_actual, 50)
})

test('target allocation risk is visible without reusing commission ratio rules', () => {
  assert.equal(typeof assignmentRules.summarizeTargetAllocationRisk, 'function')
  assert.deepEqual(
    assignmentRules.summarizeTargetAllocationRisk([
      { target_allocation_ratio: 0.4 },
      { target_allocation_ratio: 0.5 }
    ]),
    { total: 0.9, hasRisk: true }
  )
})

test('personal target page requests allocated target summaries and renders source shops', () => {
  const source = readFileSync(
    new URL('../src/domains/business/views/target/TargetPersonManagement.vue', import.meta.url),
    'utf8'
  )

  assert.equal(source.includes('getHrEmployeeTargetSummary'), true)
  assert.equal(source.includes('shop_summaries'), true)
})

test('shop assignment preserves target allocation ratio source through load and mutations', () => {
  const source = readFileSync(
    new URL('../src/domains/business/views/hr/ShopAssignment.vue', import.meta.url),
    'utf8'
  )

  assert.equal(source.includes('target_allocation_ratio_source'), true)
  assert.equal(source.includes('target_allocation_ratio_source: p.target_allocation_ratio_source'), true)
  assert.equal(source.includes('target_allocation_ratio_source: form.value.target_allocation_ratio_source'), true)
})
