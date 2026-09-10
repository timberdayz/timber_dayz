import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const repoRoot = resolve(import.meta.dirname, '..')
const viewSource = readFileSync(
  resolve(repoRoot, 'src/domains/business/views/BusinessOverview.vue'),
  'utf8'
)

test('BusinessOverview keeps clearance ranking monthly-only', () => {
  assert.equal(viewSource.includes('滞销清理排名（周度）'), false)
  assert.equal(viewSource.includes('weeklyClearanceRanking'), false)
  assert.equal(viewSource.includes('clearanceWeek'), false)
  assert.equal(viewSource.includes("loadClearanceRanking('weekly')"), false)
  assert.equal(viewSource.includes('loadMonthlyClearanceRanking'), true)
  assert.equal(viewSource.includes("params.granularity = 'monthly'"), true)
  assert.equal(viewSource.includes('v-model="clearanceMonth"'), true)
})
