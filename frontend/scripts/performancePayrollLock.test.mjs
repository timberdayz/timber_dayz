import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const apiSource = readFileSync(new URL('../src/api/index.js', import.meta.url), 'utf8')
const managementSource = readFileSync(new URL('../src/domains/business/views/hr/PerformanceManagement.vue', import.meta.url), 'utf8')
const displaySource = readFileSync(new URL('../src/domains/business/views/hr/PerformanceDisplay.vue', import.meta.url), 'utf8')

test('performance API exposes the monthly payroll-lock status query', () => {
  assert.equal(apiSource.includes('getPerformancePeriodStatus(period)'), true)
  assert.equal(apiSource.includes("/performance/period-status"), true)
})

for (const [name, source] of [
  ['management', managementSource],
  ['display', displaySource],
]) {
  test(`${name} page disables recalculation for a locked payroll month`, () => {
    assert.equal(source.includes('periodLockStatus.can_recalculate'), true)
    assert.equal(source.includes(':disabled="!periodLockStatus.can_recalculate"'), true)
    assert.equal(source.includes('PAYROLL_PERIOD_LOCKED'), true)
  })
}
