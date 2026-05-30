import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildMyIncomeExplanations,
  buildMyIncomeSummaryCards
} from '../src/domains/business/views/hr/myIncomeViewModel.js'

test('buildMyIncomeSummaryCards returns four summary cards including performance salary', () => {
  const cards = buildMyIncomeSummaryCards({
    total_income: 1888,
    base_salary: 1200,
    commission_amount: 300,
    breakdown: {
      payroll: {
        performance_salary: 200
      }
    }
  })

  assert.equal(cards.length, 4)
  assert.deepEqual(
    cards.map((card) => card.title),
    ['当月实发', '固定薪资', '绩效工资', '提成']
  )
  assert.equal(cards[2].value, 200)
})

test('buildMyIncomeExplanations describes the three income source narratives', () => {
  const explanations = buildMyIncomeExplanations()

  assert.equal(explanations.length, 3)
  assert.equal(explanations[0].title, '提成来源')
  assert.equal(explanations[1].title, '绩效工资来源')
  assert.equal(explanations[2].title, '个人绩效来源')
  assert.match(explanations[1].body, /独立绩效包/)
  assert.match(explanations[2].body, /个人绩效输入项/)
})
