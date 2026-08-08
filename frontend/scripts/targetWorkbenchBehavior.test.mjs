import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

import {
  buildPersonTargetRows,
  filterTargetEmployees,
  normalizeApiList
} from '../src/domains/business/views/target/personTargetUtils.js'
import {
  buildMonthDailyPreview,
  calculateShopTargetTotals,
  splitShopTargetsByPercent
} from '../src/domains/business/views/target/shopTargetUtils.js'

test('shop ratio split only recalculates sales and settlement profit targets', () => {
  const shops = [
    { shop_id: 'A', ratio_percent: 30, target_quantity: 30 },
    { shop_id: 'B', ratio_percent: 30, target_quantity: 70 }
  ]

  const result = splitShopTargetsByPercent(shops, 1000, 180)
  const totals = calculateShopTargetTotals(result)

  assert.equal(totals.ratioPercent, 60)
  assert.equal(totals.amount, 600)
  assert.equal(totals.profitBasisAmount, 108)
  assert.equal('quantity' in totals, false)
  assert.deepEqual(result.map((shop) => shop.target_quantity), [30, 70])
})

test('shop ratio split keeps exact sales and settlement profit totals when ratio reaches 100 percent', () => {
  const shops = [
    { shop_id: 'A', ratio_percent: 33.33, target_quantity: 10 },
    { shop_id: 'B', ratio_percent: 33.33, target_quantity: 20 },
    { shop_id: 'C', ratio_percent: 33.34, target_quantity: 30 }
  ]

  const result = splitShopTargetsByPercent(shops, 1000, 101)
  const totals = calculateShopTargetTotals(result)

  assert.equal(totals.ratioPercent, 100)
  assert.equal(totals.amount, 1000)
  assert.equal(totals.profitBasisAmount, 101)
  assert.deepEqual(result.map((shop) => shop.target_quantity), [10, 20, 30])
})

test('shop ratio split keeps settlement profit targets aligned with the company target', () => {
  const result = splitShopTargetsByPercent(
    [
      { shop_id: 'A', ratio_percent: 33.33 },
      { shop_id: 'B', ratio_percent: 33.33 },
      { shop_id: 'C', ratio_percent: 33.34 }
    ],
    1000,
    180
  )
  const totals = calculateShopTargetTotals(result)

  assert.equal(totals.profitBasisAmount, 180)
  assert.equal(result[2].target_profit_basis_amount, 60.02)
})

test('shop target workbench exposes settlement profit target inputs and target margin', () => {
  const source = readFileSync(
    new URL('../src/domains/business/views/target/TargetShopWorkbench.vue', import.meta.url),
    'utf8'
  )

  assert.equal(source.includes('结算利润目标'), true)
  assert.equal(source.includes('目标结算利润率'), true)
  assert.equal(source.includes('company_target_profit_basis_amount'), true)
  assert.equal(source.includes('target_profit_basis_amount'), true)
})

test('shop target workbench presents order targets as a read-only reserved metric', () => {
  const source = readFileSync(
    new URL('../src/domains/business/views/target/TargetShopWorkbench.vue', import.meta.url),
    'utf8'
  )

  assert.equal(source.includes('data-testid="reserved-order-targets"'), true)
  assert.equal(source.includes('v-model="summary.company_target_quantity"'), false)
  assert.equal(source.includes('v-model="row.target_quantity"'), false)
  const saveFunction = source.slice(
    source.indexOf('async function saveWorkbench()'),
    source.indexOf('async function copyPrevMonth()')
  )
  assert.equal(saveFunction.includes('company_target_quantity'), false)
  assert.equal(saveFunction.includes('target_quantity'), false)
})

test('daily preview renders one calendar item per natural day without order targets', () => {
  const rows = buildMonthDailyPreview({
    yearMonth: '2026-02',
    amountTotal: 2800,
    weekdayRatioPercents: { 1: 16, 2: 16, 3: 16, 4: 16, 5: 16, 6: 10, 7: 10 }
  })

  assert.equal(rows.length, 28)
  assert.equal(rows.reduce((sum, row) => sum + row.amount, 0), 2800)
  assert.equal(rows.every((row) => !Object.hasOwn(row, 'quantity')), true)
  assert.equal(rows[0].date, '2026-02-01')
})

test('person target employee filtering keeps returned employees unless clearly inactive', () => {
  const employees = filterTargetEmployees([
    { employee_code: 'E1', name: 'A', status: 'active' },
    { employee_code: 'E2', name: 'B', status: '在岗' },
    { employee_code: 'E3', name: 'C', status: 'inactive' },
    { employee_code: 'E4', name: 'D', status: '离职' }
  ])

  assert.deepEqual(employees.map((item) => item.employee_code), ['E1', 'E2'])
})

test('person target rows merge existing target records by employee and type', () => {
  const employees = normalizeApiList({
    data: [
      { employee_code: 'E1', name: '张三', status: 'active' }
    ]
  })
  const targets = [
    { id: 10, employee_code: 'E1', target_type: 'sales', target_value: '1200.50' }
  ]

  const rows = buildPersonTargetRows(employees, targets)

  assert.equal(rows.length, 1)
  assert.equal(rows[0].sales.id, 10)
  assert.equal(rows[0].sales.target_value, 1200.5)
  assert.equal(rows[0].orders.target_value, 0)
  assert.equal(rows[0].hasExistingTarget, true)
})
