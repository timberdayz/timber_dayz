import test from 'node:test'
import assert from 'node:assert/strict'

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

test('shop ratio split uses entered percent values and exposes unresolved totals', () => {
  const shops = [
    { shop_id: 'A', ratio_percent: 30 },
    { shop_id: 'B', ratio_percent: 30 }
  ]

  const result = splitShopTargetsByPercent(shops, 1000, 100)
  const totals = calculateShopTargetTotals(result)

  assert.equal(totals.ratioPercent, 60)
  assert.equal(totals.amount, 600)
  assert.equal(totals.quantity, 60)
})

test('shop ratio split keeps exact monthly totals when ratio reaches 100 percent', () => {
  const shops = [
    { shop_id: 'A', ratio_percent: 33.33 },
    { shop_id: 'B', ratio_percent: 33.33 },
    { shop_id: 'C', ratio_percent: 33.34 }
  ]

  const result = splitShopTargetsByPercent(shops, 1000, 101)
  const totals = calculateShopTargetTotals(result)

  assert.equal(totals.ratioPercent, 100)
  assert.equal(totals.amount, 1000)
  assert.equal(totals.quantity, 101)
})

test('daily preview renders one calendar item per natural day and reconciles totals', () => {
  const rows = buildMonthDailyPreview({
    yearMonth: '2026-02',
    amountTotal: 2800,
    quantityTotal: 28,
    weekdayRatioPercents: { 1: 16, 2: 16, 3: 16, 4: 16, 5: 16, 6: 10, 7: 10 }
  })

  assert.equal(rows.length, 28)
  assert.equal(rows.reduce((sum, row) => sum + row.amount, 0), 2800)
  assert.equal(rows.reduce((sum, row) => sum + row.quantity, 0), 28)
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
