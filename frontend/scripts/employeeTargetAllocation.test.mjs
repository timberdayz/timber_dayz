import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

import * as targetUtils from '../src/domains/business/views/target/personTargetUtils.js'
import * as assignmentRules from '../src/domains/business/views/hr/shopAssignmentRules.js'

test('personal target summary renders backend allocated shop targets, actuals, and achievement rates', () => {
  const source = readFileSync(
    new URL('../src/domains/business/views/target/TargetPersonManagement.vue', import.meta.url),
    'utf8'
  )

  // 目标分配口径由后端统一给出，前端不再自己算一遍（否则就是第二份真相）
  assert.equal(
    targetUtils.buildEmployeeTargetSummary,
    undefined,
    'frontend must not re-compute the target allocation summary: the backend summary is the single source of truth'
  )

  assert.equal(source.includes('shop_summaries: summary.shops || []'), true)

  for (const field of [
    'sales_target',
    'sales_actual',
    'sales_achievement_rate',
    'gross_profit_target',
    'gross_profit_actual',
    'gross_profit_achievement_rate'
  ]) {
    assert.equal(
      source.includes(`shop.${field}`),
      true,
      `page should render the backend provided shop.${field}`
    )
  }
})

test('personal target summary keeps API values that are already allocated', () => {
  const source = readFileSync(
    new URL('../src/domains/business/views/target/TargetPersonManagement.vue', import.meta.url),
    'utf8'
  )

  assert.equal(
    source.includes('target_allocation_ratio'),
    false,
    'allocated target values must be shown as delivered by the backend, without a frontend allocation ratio'
  )

  assert.equal(source.includes('formatNumber(row.sales_target)'), true)
  assert.equal(source.includes('formatNumber(row.sales_actual)'), true)
  assert.equal(source.includes('formatPercent(row.sales_achievement_rate)'), true)
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

test('shop assignment delegates target allocation to the backend', () => {
  const source = readFileSync(
    new URL('../src/domains/business/views/hr/ShopAssignment.vue', import.meta.url),
    'utf8'
  )

  assert.equal(
    source.includes('target_allocation_ratio'),
    false,
    'shop assignment must not own the target allocation ratio: shared shop responsibility is decided by the backend'
  )

  assert.equal(
    source.includes('共同承接店铺目标'),
    true,
    'shop assignment should tell the user that the shop target is shared'
  )

  assert.equal(
    source.includes('commission_ratio: p.commission_ratio'),
    true,
    'shop assignment should still own the commission ratio'
  )
})
