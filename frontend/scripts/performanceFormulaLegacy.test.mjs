import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const managementSource = readFileSync(
  new URL('../src/domains/business/views/hr/PerformanceManagement.vue', import.meta.url),
  'utf8'
)
const displaySource = readFileSync(
  new URL('../src/domains/business/views/hr/PerformanceDisplay.vue', import.meta.url),
  'utf8'
)
const salarySource = readFileSync(
  new URL('../src/domains/business/views/hr/EmployeeSalary.vue', import.meta.url),
  'utf8'
)
const overviewSource = readFileSync(
  new URL('../src/domains/business/views/BusinessOverview.vue', import.meta.url),
  'utf8'
)

test('shop performance pages do not expose key product as a current formula column', () => {
  for (const source of [managementSource, displaySource]) {
    assert.equal(source.includes('label="重点产品目标"'), false)
    assert.equal(source.includes('label="重点产品达成"'), false)
    assert.equal(source.includes('label="重点产品达成率"'), false)
    assert.equal(source.includes('label="重点产品得分"'), false)
  }
})

test('shop performance detail copy uses formal max score language instead of weight language', () => {
  for (const source of [managementSource, displaySource]) {
    assert.equal(source.includes('权重 {{ card.weight }}%'), false)
    assert.equal(source.includes('满分 {{ card.maxScore }}'), true)
  }
})

test('performance config submit path updates current config before creating', () => {
  assert.equal(managementSource.includes('currentConfigId'), true)
  assert.equal(managementSource.includes('savePerformanceConfig'), true)
  assert.equal(managementSource.includes('updatePerformanceConfig'), false)
  assert.equal(managementSource.includes('createPerformanceConfig({'), false)
})

test('salary performance ratio is marked as a legacy compatibility field', () => {
  assert.equal(salarySource.includes('绩效比例(兼容)'), true)
  assert.equal(salarySource.includes('performance_ratio_percent'), true)
})

test('performance pages use settlement profit terminology and expose calculation mode', () => {
  for (const source of [managementSource, displaySource]) {
    assert.equal(source.includes('结算利润目标'), true)
    assert.equal(source.includes('结算利润达成'), true)
    assert.equal(source.includes('calculationModeText'), true)
    assert.equal(source.includes('label="毛利目标"'), false)
  }
})

test('business overview presents operating result as forecast settlement profit basis', () => {
  assert.equal(overviewSource.includes('预估结算利润基数'), true)
  assert.equal(overviewSource.includes('formatNumber(operationalMetrics.operating_result)'), true)
})
